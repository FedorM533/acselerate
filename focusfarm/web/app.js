// Фокус-ферма — интерфейс. Чистый JavaScript (ES-модуль), без сборки.
// Состояние приходит с сервера по WebSocket раз в секунду, а кнопки
// вызывают REST API (см. focusfarm/api/server.py).

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// Состояние показываем тремя способами: цвет (класс s-XXX) + иконка + текст.
const STATE_LABELS = {
  IDLE: "Сессия не идёт",
  FOCUS: "Работаешь 🌱",
  NOTEBOOK: "Пишешь в тетради ✏️",
  MAYBE_DISTRACTED: "Кажется, отвлёкся…",
  DISTRACTED: "Отвлёкся — огород ждёт",
  PHONE_OUT: "Телефон вынут",
  PAUSED: "Пауза",
};
// Короткие названия — для легенд и таблиц.
const STATE_SHORT = {
  IDLE: "Нет сессии", FOCUS: "Работа", NOTEBOOK: "Тетрадь", MAYBE_DISTRACTED: "Кажется, отвлёкся",
  DISTRACTED: "Отвлёкся", PHONE_OUT: "Телефон вынут", PAUSED: "Пауза",
};
const CATEGORY_LABELS = { work: "работа", neutral: "нейтрально", distraction: "отвлечение" };
const SOUND_NAMES = { 1: "мягкий сигнал", 2: "сигнал «отвлёкся»", 3: "«урожай собран»", 4: "«сессия началась»" };

// Иконки состояний — простые SVG (свои).
const STROKE = 'stroke="#3B2A1E" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"';
const STATE_ICONS = {
  FOCUS: `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="7" fill="#F5C542" ${STROKE}/><path d="M16 2v4M16 26v4M2 16h4M26 16h4M6 6l3 3M23 23l3 3M6 26l3-3M23 9l3-3" ${STROKE} fill="none"/></svg>`,
  NOTEBOOK: `<svg viewBox="0 0 32 32"><path d="M7 25l2-7L22 5l5 5L14 23z" fill="#8FD3C8" ${STROKE}/><path d="M7 25l7-2" ${STROKE}/></svg>`,
  MAYBE_DISTRACTED: `<svg viewBox="0 0 32 32"><circle cx="20" cy="11" r="6" fill="#F5C542" ${STROKE}/><path d="M6 25a5 5 0 0 1 1-10 7 7 0 0 1 13 1 4.5 4.5 0 0 1 2 9z" fill="#fff" ${STROKE}/></svg>`,
  DISTRACTED: `<svg viewBox="0 0 32 32"><path d="M6 20a5 5 0 0 1 1-10 7 7 0 0 1 13 1 4.5 4.5 0 0 1 2 9z" fill="#D9DEE3" ${STROKE}/><path d="M10 24l-1 4M16 24l-1 4M22 24l-1 4" ${STROKE} stroke="#5B8DEF"/></svg>`,
  PHONE_OUT: `<svg viewBox="0 0 32 32"><rect x="10" y="4" width="12" height="22" rx="3" fill="#fff" ${STROKE}/><path d="M4 29h24" ${STROKE}/><path d="M24 8l5-4" ${STROKE}/></svg>`,
  PAUSED: `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="12" fill="#DCE7FD" ${STROKE}/><path d="M13 11v10M19 11v10" ${STROKE}/></svg>`,
  IDLE: `<svg viewBox="0 0 32 32"><path d="M22 5a11 11 0 1 0 5 16A9 9 0 0 1 22 5z" fill="#F6EAC2" ${STROKE}/></svg>`,
};

let state = null;          // последний снимок с сервера
let connected = false;
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ================= общие помощники =================

async function api(method, url, body) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) options.body = JSON.stringify(body);
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Что-то пошло не так";
    toast(detail, true);
    throw new Error(detail);
  }
  return data;
}

function toast(text, error = false) {
  const el = document.createElement("div");
  el.className = "toast" + (error ? " error" : "");
  el.textContent = text;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4500);
}

function formatTime(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function minutes(seconds) {
  return Math.round(seconds / 60);
}

function setStateClass(el, stateName) {
  // classList работает и для HTML, и для SVG-элементов.
  [...el.classList].filter((c) => c.startsWith("s-")).forEach((c) => el.classList.remove(c));
  el.classList.add("s-" + stateName);
}

// Обновляет innerHTML, только если он изменился (чтобы не сбивать клики и выбор).
function setHtml(el, html) {
  if (el._html !== html) {
    el.innerHTML = html;
    el._html = html;
  }
}

// ================= вкладки =================

const tabLoaders = {};   // вкладка → функция, которая вызывается при открытии

function showTab(name) {
  $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (tabLoaders[name]) tabLoaders[name]();
}
$$(".tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

// ================= звуки интерфейса (Web Audio, без аудиофайлов) =================

let soundOn = localStorage.getItem("uiSound") === "on";
let audioCtx = null;

function updateSoundButton() {
  $("#sound-toggle").textContent = soundOn ? "🔊" : "🔈";
  $("#sound-toggle").title = soundOn ? "Звук включён — нажми, чтобы выключить" : "Звук выключен — нажми, чтобы включить";
}
$("#sound-toggle").onclick = () => {
  soundOn = !soundOn;
  localStorage.setItem("uiSound", soundOn ? "on" : "off");
  updateSoundButton();
  playTone("plant");
};
updateSoundButton();

// Каждая мелодия — список нот [частота Гц, начало с, длительность с].
const TONES = {
  plant: [[523, 0, 0.12], [784, 0.1, 0.18]],                 // посадка / старт
  harvest: [[523, 0, 0.12], [659, 0.1, 0.12], [784, 0.2, 0.12], [1047, 0.3, 0.3]],
  soft: [[440, 0, 0.25], [392, 0.2, 0.3]],                   // мягкий сигнал
  distracted: [[392, 0, 0.25], [330, 0.22, 0.35]],
  click: [[880, 0, 0.05]],
};
// Номер звука подставки → мелодия интерфейса.
const SOUND_TONES = { 1: "soft", 2: "distracted", 3: "harvest", 4: "plant" };

function playTone(name) {
  if (!soundOn) return;
  audioCtx = audioCtx || new AudioContext();
  for (const [freq, start, dur] of TONES[name] || []) {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    const t0 = audioCtx.currentTime + start;
    osc.type = "triangle";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.18, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.05);
  }
}

// ================= связь с сервером =================

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { connected = true; renderBanner(); };
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    render(data);
    handleEvents(data.events || []);
  };
  ws.onclose = () => {
    connected = false;
    renderBanner();
    setTimeout(connect, 2000);   // переподключение
  };
}

async function refresh() {
  render(await api("GET", "/api/state"));
}

const eventHooks = [];   // вкладки могут реагировать на события (урожай, сорняк…)

function handleEvents(events) {
  for (const e of events) {
    if (e.type === "notice") toast(e.text);
    if (e.type === "weed") toast("На грядке вырос сорняк 🌿");
    if (e.type === "crop_ready") toast("Урожай созрел! Нажми на грядку, чтобы собрать 🎉");
    if (e.type === "session_started") toast("Сессия началась. Удачи! 🌱");
    if (e.type === "session_ended") toast(e.message);
    if (e.type === "sound") {
      playTone(SOUND_TONES[e.n]);
      showStandNote(e.n);
    }
    for (const hook of eventHooks) hook(e);
  }
}

function render(s) {
  state = s;
  renderHeader(s);
  renderBanner();
  renderFarm(s);
  renderSession(s);
  renderDevPanel(s);
  for (const hook of renderHooks) hook(s);
}
const renderHooks = [];   // сюда вкладки добавляют свои обновления

// ================= шапка =================

function setStateView(pill, iconEl, textEl, stateName) {
  setStateClass(pill, stateName);
  setHtml(iconEl, STATE_ICONS[stateName]);
  textEl.textContent = STATE_LABELS[stateName];
}

let lastCoins = null;

function dockStatus(s) {
  const d = s.device;
  if (d.source === "serial" && d.connected) return { cls: "ok", text: "подставка подключена" };
  if (d.status) return { cls: "bad", text: "подставка не подключена" };
  return { cls: "virtual", text: "виртуальная подставка" };
}

function renderHeader(s) {
  setStateView($("#state-pill"), $("#state-icon"), $("#state-label"), s.state);
  const coins = s.farm.coins;
  if (lastCoins !== null && coins !== lastCoins) bumpCoins();
  lastCoins = coins;
  $("#coins").textContent = coins;
  $("#streak").textContent = s.farm.streak;
  const dock = dockStatus(s);
  $("#dock-chip").className = "chip dock-chip " + dock.cls;
  $("#dock-chip-text").textContent = dock.text;
  $("#dock-chip").title = s.device.status || dock.text;
  const badge = $("#demo-badge");
  badge.hidden = s.mode !== "demo";
  badge.textContent = `ДЕМО ×${s.speed}`;
}

function bumpCoins() {
  const chip = $("#coins-chip");
  chip.classList.remove("bump");
  void chip.offsetWidth;   // перезапуск CSS-анимации
  chip.classList.add("bump");
}

function renderBanner() {
  const messages = [];
  if (!connected) messages.push("Нет связи с программой — переподключаюсь…");
  if (state && !state.activity.available) {
    messages.push("Монитор активности недоступен, работает только датчик телефона.");
  }
  if (state && state.device.error) messages.push("Подставка: " + state.device.error);
  const banner = $("#banner");
  banner.hidden = messages.length === 0;
  banner.textContent = messages.join(" • ");
}

// ================= ферма =================

function plotSprite(p) {
  if (!p.crop) return null;
  if (p.stage === "adult" || p.stage === "ready") return `sprites/${p.crop}_${p.stage}.svg`;
  return `sprites/${p.stage}.svg`;
}

function plotHtml(p) {
  let html = "";
  const sprite = plotSprite(p);
  if (sprite) html += `<img class="plant" src="${sprite}" alt="">`;
  if (p.weeds) html += `<img class="weed" src="sprites/weed.svg" alt="сорняк">`;
  if (p.thirsty) html += `<img class="drop" src="sprites/drop.svg" alt="хочет пить">`;
  if (p.crop) {
    html += `<span class="stars">${"★".repeat(p.stars)}</span>`;
    html += `<span class="label">${p.crop_name}</span>`;
    if (p.ripe) html += `<span class="harvest">Собрать +${p.value}</span>`;
    else html += `<span class="bar"><div style="width:${Math.round(p.progress * 100)}%"></div></span>`;
  }
  return html;
}

function plotTitle(p) {
  if (!p.crop) return p.weeds ? "Пустая грядка с сорняком" : "Пустая грядка";
  const parts = [p.crop_name];
  if (p.ripe) parts.push(`готово! +${p.value} монет`);
  else parts.push(`${Math.round(p.progress * 100)}%, ещё ${minutes(p.left_s)} мин фокуса`);
  if (p.weeds) parts.push("сорняк: −20% урожая соседям");
  if (p.thirsty) parts.push("хочет пить — вернись к работе");
  return parts.join(" • ");
}

function renderFarm(s) {
  const grid = $("#farm-grid");
  const size = s.farm.size;
  if (grid.childElementCount !== size * size) {
    grid.style.gridTemplateColumns = `repeat(${size}, auto)`;
    grid.innerHTML = "";
    for (const p of s.farm.plots) {
      const btn = document.createElement("button");
      btn.className = "plot";
      btn.dataset.x = p.x;
      btn.dataset.y = p.y;
      grid.append(btn);
    }
  }
  for (const p of s.farm.plots) {
    const btn = grid.querySelector(`[data-x="${p.x}"][data-y="${p.y}"]`);
    setHtml(btn, plotHtml(p));
    btn.title = plotTitle(p);
    btn.classList.toggle("active", p.active);
    btn.classList.toggle("ripe", !!p.ripe);
    btn.classList.toggle("thirsty", !!p.thirsty);
  }

  // Декор по краям огорода.
  const decor = s.farm.decor;
  setHtml($("#decor-left"), decor.filter((d) => d !== "bench").map((d) => `<img src="sprites/${d}.svg" alt="">`).join(""));
  setHtml($("#decor-right"), decor.includes("bench") ? `<img src="sprites/bench.svg" alt="">` : "");
  $("#rain").hidden = !s.farm.raining;

  // Боковая панель.
  $("#farm-status").textContent = STATE_LABELS[s.state];
  $("#farm-start").hidden = !!s.session;
  const active = s.farm.plots.find((p) => p.active);
  let hint = s.message || "";
  if (s.session && active && !active.ripe) hint = `${active.crop_name}: ещё ${minutes(active.left_s)} мин фокуса`;
  $("#farm-hint").textContent = hint;
  $("#weed-status").textContent = s.farm.can_weed
    ? "Можно полоть: нажми на сорняк."
    : `Прополка откроется через ${minutes(s.farm.weed_unlock_left_s)} мин фокуса в сессии.`;
  $("#today-focus").textContent = minutes(s.farm.today_focus_s);
}

$("#farm-grid").onclick = async (e) => {
  const btn = e.target.closest(".plot");
  if (!btn || !state) return;
  const x = Number(btn.dataset.x);
  const y = Number(btn.dataset.y);
  const p = state.farm.plots.find((q) => q.x === x && q.y === y);
  if (p.ripe) {
    const r = await api("POST", "/api/farm/harvest", { x, y });
    toast(`+${r.coins} монет ${"★".repeat(r.stars)}${r.weed_penalty ? " (сорняк рядом: −20%)" : ""}`);
    playTone("harvest");
  } else if (p.weeds) {
    await api("POST", "/api/farm/weed", { x, y });
    toast("Сорняк убран 👍");
  } else if (!state.session) {
    selectedPlot = `${x},${y}`;
    showTab("session");
  }
  refresh();
};
$("#farm-start").onclick = () => showTab("session");

// ================= сессия =================

let selectedPlot = "";   // выбранная для старта грядка ("x,y" или "" — авто)
const RING_LENGTH = 2 * Math.PI * 112;

function renderStartForm(s) {
  // Грядки, на которых можно начать: пустые или с недоросшим растением.
  const plots = s.farm.plots.filter((p) => !p.crop || !p.ripe);
  const plotOptions = [`<option value="">авто</option>`].concat(plots.map((p) => {
    const text = p.crop ? `${p.crop_name} ${Math.round(p.progress * 100)}%` : "пустая";
    return `<option value="${p.x},${p.y}">${p.y + 1} ряд, ${p.x + 1} место — ${text}</option>`;
  }));
  const prevPlot = $("#start-plot").value;
  setHtml($("#start-plot"), plotOptions.join(""));
  $("#start-plot").value = selectedPlot !== null ? selectedPlot : prevPlot;
  if ($("#start-plot").selectedIndex < 0) $("#start-plot").value = "";
  selectedPlot = null;

  const crops = s.farm.crops.filter((c) => c.unlocked);
  const prevCrop = $("#start-crop").value;
  setHtml($("#start-crop"), [`<option value="">авто (по длине сессии)</option>`]
    .concat(crops.map((c) => `<option value="${c.id}">${c.name} — ${c.focus_min} мин</option>`)).join(""));
  $("#start-crop").value = prevCrop;
  if ($("#start-crop").selectedIndex < 0) $("#start-crop").value = "";
  // Для недоросшего растения выбирать растение не нужно.
  const chosen = s.farm.plots.find((p) => `${p.x},${p.y}` === $("#start-plot").value);
  $("#start-crop").disabled = !!(chosen && chosen.crop);
}

function renderRing(fraction, stateName) {
  const ring = $("#ring-fg");
  setStateClass(ring, stateName);
  ring.style.strokeDasharray = RING_LENGTH;
  ring.style.strokeDashoffset = RING_LENGTH * (1 - Math.max(0, Math.min(1, fraction)));
}

function renderCropLine(s) {
  const p = s.farm.plots.find((q) => q.active);
  let html = "";
  if (p && p.crop) {
    const img = `<img src="${plotSprite(p)}" alt="">`;
    html = p.ripe
      ? `${img}<span><b>${p.crop_name}</b> созрела — собери урожай на «Ферме»!</span>`
      : `${img}<span>Растёт <b>${p.crop_name}</b>: ещё ${minutes(p.left_s)} мин фокуса до урожая</span>`;
  } else if (!s.session) {
    html = `<span class="muted">Положи телефон в подставку или нажми «Начать»</span>`;
  }
  setHtml($("#crop-line"), html);
}

function renderSession(s) {
  const session = s.session;
  setStateView($("#state-banner"), $("#state-banner-icon"), $("#state-banner-text"), s.state);
  renderCropLine(s);

  $("#start-form").hidden = !!session;
  $("#session-controls").hidden = !session;
  $("#presence").hidden = !(session && session.ask_presence);

  if (session) {
    $("#timer").textContent = formatTime(session.remaining_s);
    $("#timer").classList.toggle("long", session.remaining_s >= 3600);
    $("#timer-sub").textContent = `осталось из ${minutes(session.planned_s)} мин`;
    renderRing(1 - session.elapsed_s / session.planned_s, s.state);
    $("#pause-btn .ico").textContent = session.paused ? "▶" : "⏸";
    $("#pause-btn .lbl").textContent = session.paused ? "Продолжить" : "Пауза";
    $("#notebook-btn").classList.toggle("active", session.notebook);
    const totals = Object.entries(session.totals).filter(([, sec]) => sec >= 1);
    setHtml($("#session-totals"), totals.length
      ? totals.map(([st, sec]) => `<div><span class="cat s-${st}">${STATE_SHORT[st]}</span><b>${formatTime(sec)}</b></div>`).join("")
      : `<p class="muted">Пока пусто</p>`);
  } else {
    renderStartForm(s);
    $("#timer").textContent = formatTime(Number($("#start-length").value || 25) * 60);
    $("#timer").classList.toggle("long", Number($("#start-length").value) >= 60);
    $("#timer-sub").textContent = s.message || "запланировано";
    renderRing(1, "IDLE");
    setHtml($("#session-totals"), `<p class="muted">Сессия не идёт</p>`);
  }
  renderStand(s);

  // Активное окно.
  const a = s.activity;
  $("#act-category").textContent = CATEGORY_LABELS[a.category] || a.category;
  $("#act-category").className = "cat " + a.category;
  $("#act-process").textContent = a.process;
  $("#act-idle").textContent = Math.round(a.idle_s);
}

// ---------- нарисованная подставка ----------

const LED_COLORS = { GREEN: "#5BB85C", YELLOW: "#F2B33D", RED: "#E86A5B", BLINK_RED: "#E86A5B", BLUE: "#5B8DEF", OFF: "#9A8B7C" };

function renderStand(s) {
  const led = s.device.led || "OFF";
  const color = LED_COLORS[led] || LED_COLORS.OFF;
  for (const el of [$("#stand-led"), $("#stand-led-glow")]) {
    el.setAttribute("fill", color);
    el.classList.toggle("blink", led === "BLINK_RED");
  }
  $("#stand-led-glow").setAttribute("opacity", led === "OFF" ? "0" : ".9");
  $("#stand").classList.toggle("undocked", !s.phone.docked);
  $("#stand").classList.toggle("clickable", s.dev_tools);
  $("#stand").title = s.dev_tools ? "Нажми, чтобы положить или взять телефон" : "Подставка";
  $("#stand-status").textContent = s.phone.docked ? "📱 Телефон в подставке" : "Телефона нет в подставке";
  const dock = dockStatus(s);
  let hint = s.device.status || (dock.cls === "virtual" ? "Виртуальная подставка — настоящая не подключена" : "");
  if (s.dev_tools) hint += (hint ? ". " : "") + "Клик по подставке — взять/положить телефон";
  $("#stand-hint").textContent = hint;
}

function showStandNote(n) {
  const note = $("#stand-note");
  note.textContent = `♪ ${SOUND_NAMES[n] || "звук"}`;
  note.classList.remove("show");
  void note.offsetWidth;
  note.classList.add("show");
}

$("#stand").onclick = async () => {
  if (!state || !state.dev_tools) return;
  render(await api("POST", "/api/dev/phone", { docked: !state.phone.docked }));
};

$("#start-plot").onchange = () => renderStartForm(state);
$("#start-length").oninput = () => { if (state && !state.session) renderSession(state); };

$("#start-btn").onclick = async () => {
  const plot = $("#start-plot").value;
  const body = {
    plot: plot ? plot.split(",").map(Number) : null,
    crop: $("#start-crop").disabled ? null : ($("#start-crop").value || null),
    length_min: Number($("#start-length").value) || null,
  };
  render(await api("POST", "/api/session/start", body));
};
$("#pause-btn").onclick = async () => {
  render(await api("POST", state.session.paused ? "/api/session/resume" : "/api/session/pause"));
};
$("#notebook-btn").onclick = async () => {
  render(await api("POST", "/api/session/notebook", { on: !state.session.notebook }));
};
$("#end-btn").onclick = async () => {
  if (confirm("Завершить сессию?")) render(await api("POST", "/api/session/end"));
};
$("#presence-btn").onclick = async () => render(await api("POST", "/api/session/presence"));

// ================= панель разработчика =================

function renderDevPanel(s) {
  $("#dev-panel").hidden = !s.dev_tools;
  if (!s.dev_tools) return;
  $("#dev-phone").checked = s.phone.docked;
  $("#dev-category").value = s.activity.forced_category || "";
}
$("#dev-phone").onchange = async (e) => render(await api("POST", "/api/dev/phone", { docked: e.target.checked }));
$("#dev-category").onchange = async (e) => {
  render(await api("POST", "/api/dev/category", { category: e.target.value || null }));
};

// ================= статистика =================

// «1 раз», «2 раза», «5 раз»
function timesWord(n) {
  const last = n % 10;
  const lastTwo = n % 100;
  if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return "раза";
  return "раз";
}

let statsRange = "day";
const STATE_ORDER = ["FOCUS", "NOTEBOOK", "MAYBE_DISTRACTED", "DISTRACTED", "PHONE_OUT", "PAUSED"];

async function loadStats() {
  const st = await api("GET", `/api/stats?range=${statsRange}`);
  $("#st-focus").textContent = minutes(st.focus_s);
  $("#st-sessions").textContent = st.sessions;
  $("#st-distr").textContent = st.distractions;
  $("#st-reasons").textContent = `${st.distraction_reasons.window} / ${st.distraction_reasons.phone}`;

  // Хронология последней сессии: полоса из цветных отрезков.
  const tl = st.timeline;
  if (tl && tl.duration_s > 0) {
    $("#timeline").innerHTML = tl.segments.map((seg) => {
      const width = ((seg.to_s - seg.from_s) / tl.duration_s) * 100;
      const title = `${STATE_SHORT[seg.state]}: ${formatTime(seg.to_s - seg.from_s)}`;
      return `<div class="s-${seg.state}" style="width:${width}%" title="${title}"></div>`;
    }).join("");
  } else {
    $("#timeline").innerHTML = "";
  }
  $("#legend").innerHTML = STATE_ORDER.map((s) => `<span class="s-${s}">${STATE_SHORT[s]}</span>`).join("");

  // Время по состояниям.
  const total = Object.values(st.by_state_s).reduce((a, b) => a + b, 0) || 1;
  $("#st-states").innerHTML = STATE_ORDER.map((s) => {
    const sec = st.by_state_s[s] || 0;
    return `<div class="row s-${s}"><span>${STATE_SHORT[s]}</span>` +
      `<div><div class="fill" style="width:${(sec / total) * 100}%"></div></div><b>${minutes(sec)} мин</b></div>`;
  }).join("");

  // Куда отвлекались.
  const top = st.top_processes.map((p) => `<li><b>${p.name}</b> — ${p.count} ${timesWord(p.count)}</li>`);
  $("#st-top").innerHTML = top.length ? top.join("") : `<p class="muted">Отвлечений не было 🎉</p>`;

  // Минуты фокуса по дням (только для недели). Тёмный столбик — норма 25 мин выполнена.
  $("#week-card").hidden = statsRange !== "week";
  const max = Math.max(25, ...st.days.map((d) => d.focus_min));
  $("#st-days").innerHTML = st.days.map((d) => {
    const label = new Date(d.day).toLocaleDateString("ru-RU", { weekday: "short" });
    const goal = d.focus_min >= 25 ? " goal" : "";
    return `<div class="day"><b>${Math.round(d.focus_min)}</b>` +
      `<div class="col${goal}" style="height:${(d.focus_min / max) * 80}%"></div>${label}</div>`;
  }).join("");
}

$$("#stats-range button").forEach((b) => (b.onclick = () => {
  statsRange = b.dataset.range;
  $$("#stats-range button").forEach((x) => x.classList.toggle("active", x === b));
  loadStats();
}));
tabLoaders.stats = loadStats;

// ================= магазин =================

function shopImage(item) {
  if (item.kind === "crop") return `sprites/${item.item.split(":")[1]}_ready.svg`;
  if (item.kind === "decor") return `sprites/${item.item.split(":")[1]}.svg`;
  return "sprites/plot.svg";
}

function renderShop(s) {
  const coins = s.farm.coins;
  setHtml($("#shop"), s.farm.shop.map((item) => {
    let button;
    if (item.owned) button = `<button class="btn" disabled>✓ Есть</button>`;
    else if (item.available === false) button = `<button class="btn" disabled>Сначала предыдущее</button>`;
    else if (coins < item.price) button = `<button class="btn" disabled>Не хватает ${item.price - coins}</button>`;
    else button = `<button class="btn primary" data-buy="${item.item}">Купить</button>`;
    const kind = { crop: "Растение", expand: "Расширение", decor: "Декор" }[item.kind];
    return `<div class="card shop-item${item.owned ? " owned" : ""}">
      <div class="muted small">${kind}</div>
      <img src="${shopImage(item)}" alt="">
      <h3>${item.name}</h3>
      <div class="price"><img src="sprites/coin.svg" alt="">${item.price}</div>
      ${button}
    </div>`;
  }).join(""));
}

$("#shop").onclick = async (e) => {
  const item = e.target.dataset.buy;
  if (!item) return;
  render(await api("POST", "/api/shop/buy", { item }));
  toast("Покупка удалась! 🎉");
};
tabLoaders.shop = () => state && renderShop(state);
renderHooks.push((s) => { if ($("#tab-shop").classList.contains("active")) renderShop(s); });

// ================= настройки =================

const THRESHOLD_LABELS = {
  phone_grace_s: "Телефон можно достать без последствий, с",
  distraction_confirm_s: "Развлекательное окно до «отвлёкся», с",
  neutral_limit_s: "Нейтральное окно до «кажется, отвлёкся», с",
  idle_limit_s: "Без клавиатуры и мыши до «кажется», с",
  maybe_to_distracted_s: "«Кажется» переходит в «отвлёкся» через, с",
  recover_s: "Секунд работы для возврата в фокус",
  notebook_max_min: "Режим тетради подряд максимум, мин",
  notebook_answer_s: "Ждать ответа «Ты ещё здесь?», с",
};
const SESSION_LABELS = {
  auto_start_on_dock: "Начинать, когда кладу телефон",
  default_length_min: "Длина сессии, мин",
  auto_end_after_phone_out_min: "Завершать, если телефона нет, мин",
  break_min: "Перерыв после сессии, мин",
  demo_length_min: "Длина сессии в демо, мин",
};

function field(group, key, label, value) {
  if (typeof value === "boolean") {
    return `<label>${label}<input type="checkbox" data-group="${group}" data-key="${key}" ${value ? "checked" : ""}></label>`;
  }
  return `<label>${label}<input type="number" min="0" data-group="${group}" data-key="${key}" value="${value}"></label>`;
}

async function loadPorts(selected) {
  const ports = await api("GET", "/api/ports");
  $("#set-port").innerHTML = `<option value="">Нет подставки (виртуальная)</option>` +
    ports.map((p) => `<option value="${p.device}">${p.device} — ${p.description}</option>`).join("");
  if (selected && !ports.some((p) => p.device === selected)) {
    $("#set-port").innerHTML += `<option value="${selected}">${selected} (не найден)</option>`;
  }
  $("#set-port").value = selected || "";
}

async function loadSettings() {
  const s = await api("GET", "/api/settings");
  $("#thresholds").innerHTML = Object.entries(THRESHOLD_LABELS)
    .map(([key, label]) => field("thresholds", key, label, s.thresholds[key])).join("");
  $("#session-settings").innerHTML = Object.entries(SESSION_LABELS)
    .filter(([key]) => key in s.session)
    .map(([key, label]) => field("session", key, label, s.session[key])).join("");
  $("#set-sound").checked = s.sound.enabled;
  $("#set-mode").value = s.mode;
  $("#set-speed").value = s.demo_speed;
  await loadPorts(s.device.serial_port);
  await loadRules();
}

$("#ports-refresh").onclick = () => loadPorts($("#set-port").value);

$("#settings-save").onclick = async () => {
  const body = { thresholds: {}, session: {} };
  $$("#tab-settings [data-group]").forEach((input) => {
    body[input.dataset.group][input.dataset.key] = input.type === "checkbox" ? input.checked : Number(input.value);
  });
  body.sound = { enabled: $("#set-sound").checked };
  body.mode = $("#set-mode").value;
  body.demo_speed = Number($("#set-speed").value);
  body.device = { serial_port: $("#set-port").value };
  await api("PUT", "/api/settings", body);
  toast("Настройки сохранены ✔");
  refresh();
};
tabLoaders.settings = loadSettings;

// ---------- редактор правил ----------

let rules = { default: "neutral", rules: [] };

async function loadRules() {
  rules = await api("GET", "/api/rules");
  renderRules();
}

function chipList(i, key, title, placeholder) {
  const words = rules.rules[i][key] || [];
  const chips = words.map((w, j) =>
    `<span class="chip-word">${w}<button data-del="${i},${key},${j}" title="Удалить">×</button></span>`).join("");
  return `<div class="muted small">${title}</div><div class="chips">${chips}</div>
    <div class="form-row"><input type="text" placeholder="${placeholder}" data-input="${i},${key}">
    <button class="btn small" data-add="${i},${key}">Добавить</button></div>`;
}

function renderRules() {
  $("#rules-default").value = rules.default;
  $("#rules").innerHTML = rules.rules.map((rule, i) => `
    <div class="rule">
      <div class="rule-head">
        <b>${i + 1}.</b>
        <select data-cat="${i}">
          ${Object.entries(CATEGORY_LABELS).map(([v, t]) =>
            `<option value="${v}" ${rule.category === v ? "selected" : ""}>${t}</option>`).join("")}
        </select>
        <button class="btn small" data-move="${i},-1" title="Выше">↑</button>
        <button class="btn small" data-move="${i},1" title="Ниже">↓</button>
        <button class="btn small danger" data-remove="${i}">Удалить правило</button>
      </div>
      ${chipList(i, "process", "Программы", "например, code.exe")}
      ${chipList(i, "title_contains", "Слова в заголовке окна", "например, stepik")}
    </div>`).join("");
}

$("#rules").onclick = (e) => {
  const d = e.target.dataset;
  if (d.del) {
    const [i, key, j] = d.del.split(",");
    rules.rules[i][key].splice(Number(j), 1);
  } else if (d.add) {
    const [i, key] = d.add.split(",");
    const input = $(`[data-input="${i},${key}"]`);
    const word = input.value.trim().toLowerCase();
    if (!word) return;
    rules.rules[i][key] = [...(rules.rules[i][key] || []), word];
  } else if (d.move) {
    const [i, step] = d.move.split(",").map(Number);
    const j = i + step;
    if (j < 0 || j >= rules.rules.length) return;
    [rules.rules[i], rules.rules[j]] = [rules.rules[j], rules.rules[i]];
  } else if (d.remove) {
    rules.rules.splice(Number(d.remove), 1);
  } else {
    return;
  }
  renderRules();
};
$("#rules").onchange = (e) => {
  if (e.target.dataset.cat !== undefined) rules.rules[e.target.dataset.cat].category = e.target.value;
};
$("#rules").onkeydown = (e) => {
  if (e.key === "Enter" && e.target.dataset.input) $(`[data-add="${e.target.dataset.input}"]`).click();
};
$("#rules-default").onchange = (e) => (rules.default = e.target.value);
$("#rule-add").onclick = () => {
  rules.rules.push({ category: "distraction", process: [], title_contains: [] });
  renderRules();
};
$("#rules-save").onclick = async () => {
  // Пустые правила сервер не примет — убираем их перед сохранением.
  const clean = rules.rules.filter((r) => (r.process || []).length || (r.title_contains || []).length);
  rules = await api("PUT", "/api/rules", { default: rules.default, rules: clean });
  renderRules();
  toast("Правила сохранены ✔");
};

// ================= запуск =================

refresh().catch(() => {});
connect();
// Ссылка вида http://127.0.0.1:8765/#session сразу открывает нужную вкладку.
if (location.hash) showTab(location.hash.slice(1));

export { api, toast, formatTime, minutes, showTab, tabLoaders, renderHooks, eventHooks, setHtml, STATE_LABELS, STATE_SHORT, CATEGORY_LABELS };
