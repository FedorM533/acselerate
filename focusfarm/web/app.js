// Фокус-пруд — интерфейс. Чистый JavaScript (ES-модуль), без сборки.
// Состояние приходит с сервера по WebSocket раз в секунду, а кнопки
// вызывают REST API (см. focusfarm/api/server.py).

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// Состояние показываем тремя способами: цвет (класс s-XXX) + иконка + текст.
const STATE_LABELS = {
  IDLE: "Сессия не идёт",
  FOCUS: "Работаешь 🐟",
  NOTEBOOK: "Пишешь в тетради ✏️",
  MAYBE_DISTRACTED: "Кажется, отвлёкся…",
  DISTRACTED: "Отвлёкся — вода мутнеет",
  PHONE_OUT: "Телефон отключён",
  PAUSED: "Пауза",
};
// Короткие названия — для легенд и таблиц.
const STATE_SHORT = {
  IDLE: "Нет сессии", FOCUS: "Работа", NOTEBOOK: "Тетрадь", MAYBE_DISTRACTED: "Кажется, отвлёкся",
  DISTRACTED: "Отвлёкся", PHONE_OUT: "Телефон отключён", PAUSED: "Пауза",
};
const CATEGORY_LABELS = { work: "работа", neutral: "нейтрально", distraction: "отвлечение" };
const SOUND_NAMES = { 1: "мягкий сигнал", 2: "сигнал «отвлёкся»", 3: "«рыбка выпущена»", 4: "«сессия началась»" };

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
    if (e.type === "weed") toast("В воде появился ил 🫧");
    if (e.type === "crop_ready") toast("Рыбка выросла! Нажми на неё, чтобы выпустить 🎉");
    if (e.type === "session_started") toast("Сессия началась. Удачи! 🐟");
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

// Как сейчас определяется телефон: кабель (usb), подставка ESP32 (serial) или вручную (mock).
const PHONE_SOURCE_TEXT = { usb: "по кабелю", serial: "на подставке", mock: "вручную" };

function dockStatus(s) {
  if (s.phone.docked) return { cls: "ok", text: "подключён · " + (PHONE_SOURCE_TEXT[s.phone.source] || "") };
  if (s.device.status && s.device.source === "serial" && !s.device.connected) return { cls: "bad", text: "не подключён" };
  return { cls: "virtual", text: "не подключён" };
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
  $("#dock-chip").title = s.device.status || `Телефон: ${dock.text}`;
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
  if (state && state.phone.usb && state.phone.usb.error) messages.push(state.phone.usb.error);
  if (state && state.device.error) messages.push("Подставка: " + state.device.error);
  const banner = $("#banner");
  banner.hidden = messages.length === 0;
  banner.textContent = messages.join(" • ");
}

// ================= пруд =================

// «Погода» в пруду — прозрачность воды: чистая → слегка мутная → мутная.
const WEATHER = {
  FOCUS: "sunny", NOTEBOOK: "sunny", IDLE: "sunny", PAUSED: "sunny",
  MAYBE_DISTRACTED: "cloudy", DISTRACTED: "gloomy", PHONE_OUT: "gloomy",
};
const WEATHER_TEXT = {
  sunny: "💧 Вода чистая — рыбки растут",
  cloudy: "🌫 Вода слегка мутнеет…",
  gloomy: "🌊 Вода мутная — рыбки ждут тебя",
};

function plotSprite(p) {
  return p.crop ? `sprites/${p.crop}_${p.stage}.svg` : null;
}

function plotHtml(p, s) {
  let html = `<img class="bed" src="sprites/spot.svg" alt="">`;
  if (p.crop) html += `<span class="plant${p.stage === "seed" ? " egg" : ""}"><img src="${plotSprite(p)}" alt=""></span>`;
  if (p.weeds) html += `<img class="weed" src="sprites/silt.svg" alt="ил">`;
  if (p.thirsty) html += `<img class="drop" src="sprites/bubble.svg" alt="ждёт тебя">`;
  if (p.crop && (p.active || p.ripe)) html += `<span class="stars">${"★".repeat(p.stars)}</span>`;
  if (p.ripe) {
    html += `<span class="sparkle k1">✦</span><span class="sparkle k2">✦</span><span class="sparkle k3">✦</span>`;
    html += `<span class="harvest">Выпустить +${p.value}</span>`;
  } else if (p.active) {
    html += `<span class="bar"><div style="width:${Math.round(p.progress * 100)}%"></div></span>`;
  }
  const tip = plotTip(p, s);
  if (tip) html += `<span class="hover-tip">${tip}</span>`;
  return html;
}

// Короткая подсказка при наведении.
function plotTip(p, s) {
  if (p.ripe) return "";
  if (p.weeds) return s.farm.can_weed ? "Очистить воду" : "Очистить можно после 5 минут фокуса";
  if (!p.crop) return s.session ? "" : "Поселить рыбку";
  if (!s.session) return "Продолжить растить";
  return "";
}

function plotTitle(p) {
  if (!p.crop) return p.weeds ? "Свободное место, вода мутная" : "Свободное место";
  const parts = [p.crop_name];
  if (p.ripe) parts.push(`готово! +${p.value} монет`);
  else parts.push(`${Math.round(p.progress * 100)}%, ещё ${minutes(p.left_s)} мин фокуса`);
  if (p.weeds) parts.push("ил: −20% монет рядом");
  if (p.thirsty) parts.push("ждёт тебя — вернись к работе");
  return parts.join(" • ");
}

// Размер клетки подбираем под сцену, чтобы 3×3 и 5×5 помещались без прокрутки.
function layoutFarm(size) {
  const scene = $("#farm-scene");
  const cell = Math.floor(Math.min(210, (scene.clientHeight * 0.66) / (size * 0.74 + 0.4), (scene.clientWidth - 320) / (size * 1.08)));
  const grid = $("#farm-grid");
  grid.style.setProperty("--cell", `${Math.max(60, cell)}px`);
  grid.style.setProperty("--n", size);
}

function renderFarm(s) {
  const grid = $("#farm-grid");
  const size = s.farm.size;
  if (grid.childElementCount !== size * size) {
    grid.innerHTML = "";
    for (const p of s.farm.plots) {
      const btn = document.createElement("button");
      btn.className = "plot";
      btn.dataset.x = p.x;
      btn.dataset.y = p.y;
      btn.style.zIndex = p.y + 1;                                 // передние ряды поверх задних
      btn.style.setProperty("--d", `${-((p.x * 7 + p.y * 3) % 9) / 2}s`);  // растения качаются вразнобой
      grid.append(btn);
    }
    // Сетка идёт по строкам: y — ряд, x — место в ряду.
    grid.replaceChildren(...[...grid.children].sort((a, b) => (a.dataset.y - b.dataset.y) || (a.dataset.x - b.dataset.x)));
  }
  layoutFarm(size);
  for (const p of s.farm.plots) {
    const btn = grid.querySelector(`[data-x="${p.x}"][data-y="${p.y}"]`);
    setHtml(btn, plotHtml(p, s));
    btn.title = plotTitle(p);
    btn.setAttribute("aria-label", plotTitle(p));
    btn.classList.toggle("active", p.active);
    btn.classList.toggle("ripe", !!p.ripe);
    // Созревшая грядка поднимается над соседями, чтобы кнопку «Собрать» ничто не закрывало.
    btn.style.zIndex = p.ripe ? 50 + p.y : p.y + 1;
    btn.classList.toggle("thirsty", !!p.thirsty);
  }

  // Погода и дождик-бонус.
  const weather = WEATHER[s.state] || "sunny";
  const scene = $("#farm-scene");
  scene.classList.remove("weather-sunny", "weather-cloudy", "weather-gloomy");
  scene.classList.add("weather-" + weather);
  scene.classList.toggle("raining", s.farm.raining);

  // Декор.
  const decor = s.farm.decor;
  $("#fence-row").hidden = !decor.includes("rocks");
  setHtml($("#decor-left"), decor.includes("plants") ? `<img src="sprites/plants.svg" alt="водоросли">` : "");
  setHtml($("#decor-right"), decor.includes("castle") ? `<img src="sprites/castle.svg" alt="замок">` : "");

  // Боковая панель.
  setStateView($("#farm-state"), $("#farm-state-icon"), $("#farm-state-text"), s.state);
  $("#farm-weather").textContent = s.farm.raining ? "⛲ Родник: рост +10%" : WEATHER_TEXT[weather];
  $("#farm-start").hidden = !!s.session;
  const active = s.farm.plots.find((p) => p.active);
  let hint = s.message || "Нажми на свободное место, чтобы поселить рыбку.";
  if (s.session && active && !active.ripe) hint = `${active.crop_name}: ещё ${minutes(active.left_s)} мин фокуса`;
  if (s.session && active && active.ripe) hint = `${active.crop_name} выросла — нажми на неё, чтобы выпустить!`;
  $("#farm-hint").textContent = hint;
  $("#weed-status").textContent = s.farm.can_weed
    ? "Можно чистить: нажми на ил."
    : `Очистить воду можно после 5 минут фокуса в сессии (ещё ${minutes(s.farm.weed_unlock_left_s)} мин).`;
  const todayMin = minutes(s.farm.today_focus_s);
  $("#today-focus").textContent = todayMin;
  $("#today-goal").style.width = `${Math.min(100, (todayMin / 25) * 100)}%`;
  $("#today-goal-text").textContent = todayMin >= 25 ? "День засчитан в серию 🔥" : `До зачёта дня: ${25 - todayMin} мин`;
}

// ---------- анимация урожая: монеты летят к счётчику ----------

function celebrateHarvest(btn, result) {
  const from = btn.getBoundingClientRect();
  const to = $("#coins-chip").getBoundingClientRect();
  const text = document.createElement("div");
  text.className = "float-text";
  text.textContent = `+${result.coins} ${"★".repeat(result.stars)}`;
  text.style.left = `${from.left + from.width / 2}px`;
  text.style.top = `${from.top + from.height * 0.2}px`;
  document.body.append(text);
  setTimeout(() => text.remove(), 1900);
  if (reduceMotion) return;
  const count = Math.min(8, Math.max(3, result.coins));
  for (let i = 0; i < count; i++) {
    const coin = document.createElement("img");
    coin.src = "sprites/coin.svg";
    coin.className = "fly-coin";
    document.body.append(coin);
    const x0 = from.left + from.width / 2 - 17 + (Math.random() - 0.5) * 40;
    const y0 = from.top + from.height / 2 - 17;
    const x1 = to.left + 8;
    const y1 = to.top + 4;
    coin.animate([
      { transform: `translate(${x0}px, ${y0}px) scale(.6)`, opacity: 0 },
      { transform: `translate(${x0}px, ${y0 - 60}px) scale(1.1)`, opacity: 1, offset: 0.3 },
      { transform: `translate(${x1}px, ${y1}px) scale(.8)`, opacity: 1 },
    ], { duration: 900 + i * 90, easing: "cubic-bezier(.5,0,.4,1)" }).onfinish = () => {
      coin.remove();
      bumpCoins();
    };
  }
}

$("#farm-grid").onclick = async (e) => {
  const btn = e.target.closest(".plot");
  if (!btn || !state) return;
  const x = Number(btn.dataset.x);
  const y = Number(btn.dataset.y);
  const p = state.farm.plots.find((q) => q.x === x && q.y === y);
  if (p.ripe) {
    const r = await api("POST", "/api/farm/harvest", { x, y });
    celebrateHarvest(btn, r);
    if (r.weed_penalty) toast("Ил рядом забрал 20% монет — в следующий раз очисти воду 🫧");
    else toast("Рыбка выпущена в пруд 🐟");
    playTone("harvest");
  } else if (p.weeds) {
    if (!state.farm.can_weed) {
      toast(`Очистить воду можно после 5 минут фокуса — осталось ${minutes(state.farm.weed_unlock_left_s)} мин 🐟`);
      return;
    }
    await api("POST", "/api/farm/weed", { x, y });
    playTone("click");
    toast("Вода стала чище 👍");
  } else if (!state.session) {
    selectedPlot = `${x},${y}`;
    playTone("click");
    showTab("session");
  }
  refresh();
};
$("#farm-start").onclick = () => showTab("session");
window.addEventListener("resize", () => state && layoutFarm(state.farm.size));

// ================= сессия =================

let selectedPlot = "";   // выбранная для старта грядка ("x,y" или "" — авто)
const RING_LENGTH = 2 * Math.PI * 112;

function renderStartForm(s) {
  // Грядки, на которых можно начать: пустые или с недоросшим растением.
  const plots = s.farm.plots.filter((p) => !p.crop || !p.ripe);
  const plotOptions = [`<option value="">авто</option>`].concat(plots.map((p) => {
    const text = p.crop ? `${p.crop_name} ${Math.round(p.progress * 100)}%` : "свободно";
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
      ? `${img}<span><b>${p.crop_name}</b> выросла — выпусти её на вкладке «Пруд»!</span>`
      : `${img}<span>Растёт <b>${p.crop_name}</b>: ещё ${minutes(p.left_s)} мин фокуса</span>`;
  } else if (!s.session) {
    html = `<span class="muted">Подключи телефон кабелем или поставь на подставку — таймер запустится сам</span>`;
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
    // Без телефона таймер не запускается (кроме тренировки без награды).
    $("#start-btn").disabled = !s.phone.docked;
    $("#phone-need").hidden = s.phone.docked;
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
  $("#stand").title = s.dev_tools ? "Нажми, чтобы положить или взять телефон" : "Телефон";
  $("#stand-status").textContent = s.phone.docked ? "📱 Телефон подключён" : "Телефон не подключён";
  const dock = dockStatus(s);
  const usb = s.phone.usb;
  let hint = s.device.status ? s.device.status + ". " : "";
  if (usb && usb.paired) hint = `Кабель: ${usb.name || "телефон привязан"}. ` + hint;
  else hint = "Телефон по кабелю не привязан — Настройки → «Телефон по кабелю». " + hint;
  if (s.dev_tools) hint += "Клик по рисунку — взять/положить телефон вручную.";
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

function startBody(withoutPhone) {
  const plot = $("#start-plot").value;
  return {
    plot: plot ? plot.split(",").map(Number) : null,
    crop: $("#start-crop").disabled ? null : ($("#start-crop").value || null),
    length_min: Number($("#start-length").value) || null,
    without_phone: withoutPhone,
  };
}
$("#start-btn").onclick = async () => render(await api("POST", "/api/session/start", startBody(false)));
$("#start-nophone-btn").onclick = async () => render(await api("POST", "/api/session/start", startBody(true)));
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

function clock(ts) {
  return new Date(ts * 1000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

let statsRange = "day";
let timelineData = null;
const STATE_ORDER = ["FOCUS", "NOTEBOOK", "MAYBE_DISTRACTED", "DISTRACTED", "PHONE_OUT", "PAUSED"];

async function loadStats() {
  const st = await api("GET", `/api/stats?range=${statsRange}`);
  $("#st-focus").textContent = minutes(st.focus_s);
  $("#st-focus-label").textContent = statsRange === "week" ? "минут фокуса за неделю" : "минут фокуса сегодня";
  $("#st-sessions").textContent = st.sessions;
  $("#st-distr").textContent = st.distractions;
  $("#st-reasons").textContent = `окно: ${st.distraction_reasons.window} · телефон: ${st.distraction_reasons.phone}`;
  $("#st-streak").textContent = state ? state.farm.streak : 0;
  renderTimeline(st.timeline);
  renderStateBars(st.by_state_s);
  renderTop(st.top_processes);
  renderDays(st.days);
}

// ---------- хронология: полоса из цветных отрезков ----------

function renderTimeline(tl) {
  timelineData = tl;
  const svg = $("#timeline");
  $("#legend").innerHTML = STATE_ORDER.map((s) => `<span class="s-${s}">${STATE_SHORT[s]}</span>`).join("");
  if (!tl || tl.duration_s <= 0 || !tl.segments.length) {
    svg.innerHTML = "";
    $("#tl-start").textContent = "Сессий ещё не было — подключи телефон 🐟";
    $("#tl-end").textContent = "";
    return;
  }
  svg.innerHTML = tl.segments.map((seg, i) => {
    const x = (seg.from_s / tl.duration_s) * 1000;
    const w = Math.max(2, ((seg.to_s - seg.from_s) / tl.duration_s) * 1000);
    return `<rect class="s-${seg.state}" data-i="${i}" x="${x}" y="0" width="${w}" height="56"></rect>`;
  }).join("");
  $("#tl-start").textContent = `начало ${clock(tl.start)}`;
  $("#tl-end").textContent = tl.end ? `конец ${clock(tl.end)}` : "идёт сейчас";
}

$("#timeline").addEventListener("mousemove", (e) => {
  const rect = e.target.closest("rect");
  const tip = $("#tl-tip");
  if (!rect || !timelineData) { tip.hidden = true; return; }
  const seg = timelineData.segments[Number(rect.dataset.i)];
  const start = timelineData.start;
  tip.textContent = `${STATE_SHORT[seg.state]}: ${formatTime(seg.to_s - seg.from_s)} (${clock(start + seg.from_s)}–${clock(start + seg.to_s)})`;
  const box = $("#timeline-wrap").getBoundingClientRect();
  tip.style.left = `${Math.min(Math.max(e.clientX - box.left, 120), box.width - 120)}px`;
  tip.hidden = false;
});
$("#timeline").addEventListener("mouseleave", () => { $("#tl-tip").hidden = true; });

function renderStateBars(byState) {
  const total = Object.values(byState).reduce((a, b) => a + b, 0) || 1;
  $("#st-states").innerHTML = STATE_ORDER.map((s) => {
    const sec = byState[s] || 0;
    return `<div class="row s-${s}"><span>${STATE_SHORT[s]}</span>` +
      `<div class="track"><div class="fill" style="width:${(sec / total) * 100}%"></div></div><b>${minutes(sec)} мин</b></div>`;
  }).join("");
}

function renderTop(top) {
  $("#st-top").innerHTML = top.length
    ? top.map((p) => `<li>${p.name} <span class="cnt">— ${p.count} ${timesWord(p.count)}</span></li>`).join("")
    : `<p class="empty-note">Отвлечений не было 🎉</p>`;
}

// ---------- неделя: столбцы по дням (SVG, без библиотек) ----------

function renderDays(days) {
  $("#week-card").hidden = statsRange !== "week";
  $("#stats-row").classList.toggle("two", statsRange !== "week");
  const W = 560, H = 230, top = 24, bottom = 36, left = 10;
  const max = Math.max(30, ...days.map((d) => d.focus_min));
  const step = (W - left * 2) / days.length;
  const barW = step * 0.6;
  const y = (v) => top + (H - top - bottom) * (1 - v / max);
  let html = `<line class="goal-line" x1="0" x2="${W}" y1="${y(25)}" y2="${y(25)}"/>`;
  html += `<text x="${W - 4}" y="${y(25) - 6}" text-anchor="end">цель 25 мин</text>`;
  days.forEach((d, i) => {
    const x = left + i * step + (step - barW) / 2;
    const h = Math.max(3, H - bottom - y(d.focus_min));
    const label = new Date(d.day).toLocaleDateString("ru-RU", { weekday: "short" });
    html += `<rect class="bar${d.focus_min >= 25 ? " goal" : ""}" x="${x}" y="${H - bottom - h}" width="${barW}" height="${h}" rx="8"><title>${d.day}: ${Math.round(d.focus_min)} мин</title></rect>`;
    html += `<text class="val" x="${x + barW / 2}" y="${H - bottom - h - 6}" text-anchor="middle">${Math.round(d.focus_min)}</text>`;
    html += `<text x="${x + barW / 2}" y="${H - 10}" text-anchor="middle">${label}</text>`;
  });
  $("#st-days").innerHTML = html;
}

$$("#stats-range button").forEach((b) => (b.onclick = () => {
  statsRange = b.dataset.range;
  $$("#stats-range button").forEach((x) => x.classList.toggle("active", x === b));
  loadStats();
}));
tabLoaders.stats = loadStats;

// ================= магазин =================

const SHOP_DESC = {
  crop: (item, s) => {
    const c = s.farm.crops.find((q) => `crop:${q.id}` === item.item);
    return c ? `${c.focus_min} мин фокуса → ${c.coins} монет` : "";
  },
  expand: (item) => `Больше мест — больше рыбок`,
  decor: () => "Для красоты, на игру не влияет",
};

function shopImage(item) {
  if (item.kind === "crop") return `sprites/${item.item.split(":")[1]}_ready.svg`;
  if (item.kind === "decor") return `sprites/${item.item.split(":")[1]}.svg`;
  return item.item === "expand_5" ? "sprites/grid5.svg" : "sprites/grid4.svg";
}

function renderShop(s) {
  const coins = s.farm.coins;
  $("#shop-coins").textContent = coins;
  const price = (n) => `<span class="price-tag"><img src="sprites/coin.svg" alt="">${n}</span>`;
  setHtml($("#shop-grid"), s.farm.shop.map((item) => {
    let button;
    if (item.owned) button = `<span class="owned-tag">✓ ${item.kind === "crop" ? "Открыто" : "Куплено"}</span>`;
    else if (item.available === false) button = `<button class="btn" disabled>Сначала пруд поменьше</button>`;
    else if (coins < item.price) button = `<button class="btn" disabled>ещё ${price(item.price - coins)}</button>`;
    else button = `<button class="btn primary" data-buy="${item.item}">Купить за ${price(item.price)}</button>`;
    const kind = { crop: "Рыбка", expand: "Пруд", decor: "Декор" }[item.kind];
    const locked = item.kind === "crop" && !item.owned;
    return `<div class="card shop-item${locked ? " locked" : ""}">
      <span class="shop-kind">${kind}</span>
      <div class="shop-pic"><img class="main" src="${shopImage(item)}" alt="">${locked ? `<img class="lock" src="sprites/lock.svg" alt="закрыто">` : ""}</div>
      <h3>${item.name}</h3>
      <p class="desc">${SHOP_DESC[item.kind](item, s)}</p>
      ${button}
    </div>`;
  }).join(""));
}

$("#shop-grid").onclick = async (e) => {
  const btn = e.target.closest("[data-buy]");
  if (!btn) return;
  render(await api("POST", "/api/shop/buy", { item: btn.dataset.buy }));
  playTone("harvest");
  toast("Покупка удалась! 🎉");
};
tabLoaders.shop = () => state && renderShop(state);
renderHooks.push((s) => { if ($("#tab-shop").classList.contains("active")) renderShop(s); });

// ================= настройки =================

// Группы настроек: [раздел, ключ, подпись, единица].
const SETTINGS_GROUPS = [
  ["📱 Телефон", [
    ["thresholds", "phone_grace_s", "Сколько секунд можно смотреть в телефон без последствий", "с"],
    ["session", "auto_start_on_dock", "Начинать сессию, когда подключаю телефон"],
    ["session", "auto_end_after_phone_out_min", "Через сколько минут без телефона завершать сессию", "мин"],
  ]],
  ["🎮 Отвлечения", [
    ["thresholds", "distraction_confirm_s", "Сколько секунд на YouTube и т. п. до «Отвлёкся»", "с"],
    ["thresholds", "neutral_limit_s", "Сколько секунд в «нейтральной» программе до «Кажется, отвлёкся»", "с"],
    ["thresholds", "idle_limit_s", "Сколько секунд без клавиатуры и мыши до «Кажется, отвлёкся»", "с"],
    ["thresholds", "maybe_to_distracted_s", "Через сколько секунд «Кажется» становится «Отвлёкся»", "с"],
    ["thresholds", "recover_s", "Сколько секунд работы нужно, чтобы вернуться в фокус", "с"],
  ]],
  ["✏️ Режим тетради", [
    ["thresholds", "notebook_max_min", "Сколько минут подряд можно писать до вопроса «Ты ещё здесь?»", "мин"],
    ["thresholds", "notebook_answer_s", "Сколько секунд ждать ответа", "с"],
  ]],
  ["⏱ Сессия", [
    ["session", "default_length_min", "Длина сессии", "мин"],
    ["session", "break_min", "Перерыв после сессии", "мин"],
    ["session", "demo_length_min", "Длина сессии в демо-режиме", "мин"],
  ]],
];

function fieldHtml(group, key, label, unit, value) {
  if (typeof value === "boolean") {
    return `<label class="field"><span>${label}</span>
      <span class="toggle"><input type="checkbox" data-group="${group}" data-key="${key}" ${value ? "checked" : ""}><span></span></span></label>`;
  }
  return `<label class="field"><span>${label}</span>
    <span class="input-unit"><input type="number" min="0" data-group="${group}" data-key="${key}" value="${value}">${unit || ""}</span></label>`;
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
  let html = SETTINGS_GROUPS.map(([title, fields]) => `<div class="settings-group"><h3>${title}</h3>` +
    fields.filter(([group, key]) => key in s[group])
      .map(([group, key, label, unit]) => fieldHtml(group, key, label, unit, s[group][key])).join("") +
    `</div>`).join("");
  html += `<div class="settings-group"><h3>🔊 Звук и режим</h3>
    <label class="field"><span>Звуки подставки</span>
      <span class="toggle"><input type="checkbox" id="set-sound" ${s.sound.enabled ? "checked" : ""}><span></span></span></label>
    <label class="field"><span>Режим работы</span>
      <select id="set-mode">
        <option value="normal">обычный</option>
        <option value="dev">разработчик</option>
        <option value="demo">демо (ускорение)</option>
      </select></label>
    <label class="field"><span>Во сколько раз ускорять время в демо</span>
      <span class="input-unit">×<input type="number" id="set-speed" min="1" max="1000" value="${s.demo_speed}"></span></label>
  </div>
  <div class="settings-group"><h3>📱 Телефон по кабелю</h3>
    <p id="usb-status" class="muted"></p>
    <div id="pair-box" class="pair-box"></div>
    <label class="field"><span>Чем определять «телефон подключён»</span>
      <select id="set-source">
        <option value="auto">любой способ (кабель или подставка)</option>
        <option value="usb">только USB-кабель</option>
        <option value="serial">только подставка ESP32</option>
        <option value="mock">только вручную (разработчик)</option>
      </select></label>
    <p class="muted small">💡 Чтобы телефоном нельзя было пользоваться, включи на нём режим «Фокусирование»
      (iPhone) или «Цифровое благополучие → Режим фокусировки» (Android) и оставь только нужные приложения.</p>
  </div>
  <div class="settings-group"><h3>🔌 Подставка</h3>
    <label class="field"><span>COM-порт</span>
      <span class="input-unit"><select id="set-port"></select><button class="btn small" id="ports-refresh" title="Обновить список">↻</button></span></label>
    <p class="muted small">«Нет подставки» — телефон определяется только по кабелю.</p>
  </div>`;
  $("#settings-groups").innerHTML = html;
  $("#set-mode").value = s.mode;
  $("#set-source").value = s.device.phone_source || "auto";
  await loadUsb();
  $("#ports-refresh").onclick = (e) => { e.preventDefault(); loadPorts($("#set-port").value); };
  await loadPorts(s.device.serial_port);
  await loadRules();
}

$("#settings-save").onclick = async () => {
  const body = { thresholds: {}, session: {} };
  $$("#settings-groups [data-group]").forEach((input) => {
    body[input.dataset.group][input.dataset.key] = input.type === "checkbox" ? input.checked : Number(input.value);
  });
  body.sound = { enabled: $("#set-sound").checked };
  body.mode = $("#set-mode").value;
  body.demo_speed = Number($("#set-speed").value);
  body.device = { serial_port: $("#set-port").value, phone_source: $("#set-source").value };
  await api("PUT", "/api/settings", body);
  toast("Настройки сохранены ✔");
  refresh();
};
tabLoaders.settings = loadSettings;

// ---------- привязка телефона по USB ----------

let pairStep = "idle";   // idle → unplug → plug → manual

function renderPairBox(extra = "") {
  const box = $("#pair-box");
  if (!box) return;
  const steps = {
    idle: `<button class="btn" id="pair-start">🔗 Привязать телефон</button>`,
    unplug: `<p><b>Шаг 1.</b> Отключи телефон от компьютера, потом нажми «Дальше».</p>
      <button class="btn primary" id="pair-next">Дальше</button> <button class="btn" id="pair-cancel">Отмена</button>`,
    plug: `<p><b>Шаг 2.</b> Подключи телефон кабелем (на телефоне выбери «Передача файлов», если спросит) и нажми «Найти».</p>
      <button class="btn primary" id="pair-find">Найти телефон</button> <button class="btn" id="pair-cancel">Отмена</button>`,
    manual: extra,
  };
  box.innerHTML = steps[pairStep];
}

async function loadUsb() {
  const info = await api("GET", "/api/phone");
  const usb = info.usb;
  $("#usb-status").textContent = usb && usb.paired
    ? `Привязан: ${usb.name || "телефон"} — сейчас ${usb.docked ? "подключён ✅" : "не подключён"}.`
    : "Телефон не привязан. Привяжи его один раз — дальше таймер будет стартовать при подключении кабеля.";
  pairStep = "idle";
  renderPairBox();
  if (usb && usb.paired) {
    $("#pair-box").innerHTML += ` <button class="btn danger small" id="pair-remove">Отвязать</button>`;
  }
}

async function manualPairList(message) {
  const { devices } = await api("GET", "/api/phone/devices");
  pairStep = "manual";
  const rows = devices.map((d) => `<li><button class="btn small" data-pair="${d.id}" data-name="${d.name}">Это он</button> ${d.name} <span class="muted small">(${d.id})</span></li>`).join("");
  renderPairBox(`<p>${message}</p><ul class="pair-list">${rows || "<li class='muted'>USB-устройств не найдено</li>"}</ul>
    <button class="btn" id="pair-cancel">Отмена</button>`);
}

document.addEventListener("click", async (e) => {
  const id = e.target.id;
  if (id === "pair-start") { pairStep = "unplug"; renderPairBox(); }
  else if (id === "pair-next") { await api("POST", "/api/phone/pair/begin"); pairStep = "plug"; renderPairBox(); }
  else if (id === "pair-cancel") { pairStep = "idle"; renderPairBox(); }
  else if (id === "pair-find") {
    const r = await api("POST", "/api/phone/pair/finish");
    if (r.paired) { toast("Телефон привязан ✔"); await loadUsb(); }
    else if (r.candidates.length > 1) await manualPairList("Найдено несколько новых устройств — выбери телефон:");
    else await manualPairList("Новое устройство не появилось. Возможно, кабель только для зарядки. Выбери телефон из списка или смени кабель:");
  } else if (e.target.dataset && e.target.dataset.pair) {
    await api("POST", "/api/phone/pair", { id: e.target.dataset.pair, name: e.target.dataset.name });
    toast("Телефон привязан ✔");
    await loadUsb();
  } else if (id === "pair-remove") {
    await api("DELETE", "/api/phone/pair");
    toast("Телефон отвязан");
    await loadUsb();
  }
});

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
  return `<div class="muted small">${title}</div><div class="chips">${chips || '<span class="muted small">пока пусто</span>'}</div>
    <div class="form-row"><input type="text" placeholder="${placeholder}" data-input="${i},${key}">
    <button class="btn small" data-add="${i},${key}">+ Добавить</button></div>`;
}

function renderRules() {
  $("#rules-default").value = rules.default;
  $("#rules").innerHTML = rules.rules.map((rule, i) => `
    <div class="rule cat-${rule.category}">
      <div class="rule-head">
        <span class="num">${i + 1}</span>
        <select data-cat="${i}">
          ${Object.entries(CATEGORY_LABELS).map(([v, t]) =>
            `<option value="${v}" ${rule.category === v ? "selected" : ""}>${t}</option>`).join("")}
        </select>
        <span class="spacer"></span>
        <button class="btn small" data-move="${i},-1" title="Выше">↑</button>
        <button class="btn small" data-move="${i},1" title="Ниже">↓</button>
        <button class="btn small danger" data-remove="${i}" title="Удалить правило">✕</button>
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
  if (e.target.dataset.cat !== undefined) {
    rules.rules[e.target.dataset.cat].category = e.target.value;
    renderRules();
  }
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
