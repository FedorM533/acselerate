// Фокус-ферма — интерфейс. Чистый JavaScript (ES-модуль), без сборки.
// Состояние приходит с сервера по WebSocket раз в секунду, а кнопки
// вызывают REST API (см. focusfarm/api/server.py).

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const STATE_LABELS = {
  IDLE: "Сессия не идёт",
  FOCUS: "Работаешь",
  NOTEBOOK: "Пишешь в тетради",
  MAYBE_DISTRACTED: "Кажется, отвлёкся",
  DISTRACTED: "Отвлёкся",
  PHONE_OUT: "Телефон вынут",
  PAUSED: "Пауза",
};
const CATEGORY_LABELS = { work: "работа", neutral: "нейтрально", distraction: "отвлечение" };
const SOUND_NAMES = { 1: "мягкий сигнал", 2: "сигнал «отвлёкся»", 3: "«урожай собран»", 4: "«сессия началась»" };

let state = null;          // последний снимок с сервера
let connected = false;

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
  el.className = el.className.replace(/\bs-\w+/g, "").trim() + " s-" + stateName;
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

// ================= звук в браузере (необязательно) =================

let browserSound = localStorage.getItem("browserSound") === "on";
let audioCtx = null;

function updateSoundButton() {
  $("#browser-sound").textContent = browserSound ? "🔊" : "🔈";
  $("#browser-sound").title = browserSound ? "Звук в браузере включён" : "Звук в браузере выключен";
}
$("#browser-sound").onclick = () => {
  browserSound = !browserSound;
  localStorage.setItem("browserSound", browserSound ? "on" : "off");
  updateSoundButton();
  if (browserSound) beep(4);
};
updateSoundButton();

// Простые мелодии из пары нот вместо mp3 — у каждого сигнала своя.
const MELODIES = { 1: [440, 392], 2: [330, 262], 3: [523, 659, 784], 4: [392, 523] };

function beep(n) {
  if (!browserSound) return;
  audioCtx = audioCtx || new AudioContext();
  (MELODIES[n] || [440]).forEach((freq, i) => {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    const start = audioCtx.currentTime + i * 0.18;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.15, start);
    gain.gain.exponentialRampToValueAtTime(0.001, start + 0.3);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start(start);
    osc.stop(start + 0.32);
  });
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

function handleEvents(events) {
  for (const e of events) {
    if (e.type === "notice") toast(e.text);
    if (e.type === "weed") toast("На грядке вырос сорняк 🌿");
    if (e.type === "crop_ready") toast("Урожай созрел! Нажми на грядку, чтобы собрать 🎉");
    if (e.type === "session_started") toast("Сессия началась. Удачи! 🌱");
    if (e.type === "session_ended") toast(e.message);
    if (e.type === "sound") beep(e.n);
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

function renderHeader(s) {
  $("#coins").textContent = s.farm.coins;
  $("#streak").textContent = s.farm.streak;
  $("#weather").textContent = s.farm.raining ? "🌧 Дождь: рост +10%" : "☀️ Ясно";
  const pill = $("#state-pill");
  pill.textContent = STATE_LABELS[s.state];
  setStateClass(pill, s.state);
  const badge = $("#demo-badge");
  badge.hidden = s.mode !== "demo";
  badge.textContent = `ДЕМО ×${s.speed}`;
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
    beep(3);
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

function renderSession(s) {
  const session = s.session;
  setStateClass($("#state-indicator"), s.state);
  setStateClass($(".state-dot"), s.state);
  setStateClass($(".progress"), s.state);
  $("#state-text").textContent = STATE_LABELS[s.state];

  $("#start-form").hidden = !!session;
  $("#session-controls").hidden = !session;
  $("#presence").hidden = !(session && session.ask_presence);

  if (session) {
    $("#timer").textContent = formatTime(session.remaining_s);
    $("#timer-sub").textContent = `осталось из ${minutes(session.planned_s)} мин`;
    $("#session-progress").style.width = `${Math.min(100, (session.elapsed_s / session.planned_s) * 100)}%`;
    $("#pause-btn").textContent = session.paused ? "▶ Продолжить" : "⏸ Пауза";
    $("#notebook-btn").classList.toggle("active", session.notebook);
    const totals = Object.entries(session.totals).filter(([, sec]) => sec >= 1);
    setHtml($("#session-totals"), totals.length
      ? totals.map(([st, sec]) => `<div><span class="cat s-${st}" style="background:var(--c)">${STATE_LABELS[st]}</span><b>${formatTime(sec)}</b></div>`).join("")
      : `<p class="muted">Пока пусто</p>`);
  } else {
    renderStartForm(s);
    $("#timer").textContent = formatTime(Number($("#start-length").value || 25) * 60);
    $("#timer-sub").textContent = s.message || "положи телефон в подставку или нажми «Начать»";
    $("#session-progress").style.width = "0";
    setHtml($("#session-totals"), `<p class="muted">Сессия не идёт</p>`);
  }

  // Подставка (настоящая или виртуальная).
  const d = s.device;
  $("#dock-led").className = "dock-led " + (d.led || "OFF");
  let status = d.status;
  if (!status) status = d.source === "mock" ? "Виртуальная подставка" : (d.connected ? "Подставка подключена" : "Подставка не подключена");
  $("#dock-status").textContent = status;
  $("#dock-phone").textContent = s.phone.docked ? "📱 Телефон в подставке" : "📵 Телефона нет в подставке";
  $("#dock-sound").textContent = d.last_sound ? `последний звук: ${SOUND_NAMES[d.last_sound]}` : "";

  // Активное окно.
  const a = s.activity;
  $("#act-category").textContent = CATEGORY_LABELS[a.category] || a.category;
  $("#act-category").className = "cat " + a.category;
  $("#act-process").textContent = a.process;
  $("#act-idle").textContent = Math.round(a.idle_s);
}

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
      const title = `${STATE_LABELS[seg.state]}: ${formatTime(seg.to_s - seg.from_s)}`;
      return `<div class="s-${seg.state}" style="width:${width}%" title="${title}"></div>`;
    }).join("");
  } else {
    $("#timeline").innerHTML = "";
  }
  $("#legend").innerHTML = STATE_ORDER.map((s) => `<span class="s-${s}">${STATE_LABELS[s]}</span>`).join("");

  // Время по состояниям.
  const total = Object.values(st.by_state_s).reduce((a, b) => a + b, 0) || 1;
  $("#st-states").innerHTML = STATE_ORDER.map((s) => {
    const sec = st.by_state_s[s] || 0;
    return `<div class="row s-${s}"><span>${STATE_LABELS[s]}</span>` +
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
    `<span class="chip">${w}<button data-del="${i},${key},${j}" title="Удалить">×</button></span>`).join("");
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

export { api, toast, formatTime, minutes, showTab, tabLoaders, renderHooks, setHtml, STATE_LABELS, CATEGORY_LABELS };
