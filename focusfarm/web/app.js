// Фокус-пруд — интерфейс. Чистый JavaScript (ES-модуль), без сборки.
// Состояние приходит с сервера по WebSocket раз в секунду, а кнопки
// вызывают REST API (см. focusfarm/api/server.py).

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// Состояние показываем тремя способами: цвет (класс s-XXX) + иконка + текст.
const STATE_LABELS = {
  IDLE: "Сессия не идёт",
  FOCUS: "Работаешь",
  NOTEBOOK: "Пишешь в тетради",
  MAYBE_DISTRACTED: "Кажется, отвлёкся…",
  DISTRACTED: "Отвлёкся",
  PHONE_OUT: "Телефон отключён",
  PAUSED: "Пауза",
  BREAK: "Перерыв",
};
// Короткие названия — для легенд и таблиц.
const STATE_SHORT = {
  IDLE: "Нет сессии", FOCUS: "Работа", NOTEBOOK: "Тетрадь", MAYBE_DISTRACTED: "Кажется, отвлёкся",
  DISTRACTED: "Отвлёкся", PHONE_OUT: "Телефон отключён", PAUSED: "Пауза", BREAK: "Перерыв",
};
const CATEGORY_LABELS = { work: "работа", neutral: "нейтрально", distraction: "отвлечение" };
const SOUND_NAMES = { 1: "мягкий сигнал", 2: "сигнал «отвлёкся»", 4: "«сессия началась»" };

// Иконки состояний — простые SVG (свои).
const STROKE = 'stroke="currentColor" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"';
const STATE_ICONS = {
  FOCUS: `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="7" fill="#F5C542" ${STROKE}/><path d="M16 2v4M16 26v4M2 16h4M26 16h4M6 6l3 3M23 23l3 3M6 26l3-3M23 9l3-3" ${STROKE} fill="none"/></svg>`,
  NOTEBOOK: `<svg viewBox="0 0 32 32"><path d="M7 25l2-7L22 5l5 5L14 23z" fill="#8FD3C8" ${STROKE}/><path d="M7 25l7-2" ${STROKE}/></svg>`,
  MAYBE_DISTRACTED: `<svg viewBox="0 0 32 32"><circle cx="20" cy="11" r="6" fill="#F5C542" ${STROKE}/><path d="M6 25a5 5 0 0 1 1-10 7 7 0 0 1 13 1 4.5 4.5 0 0 1 2 9z" fill="#fff" ${STROKE}/></svg>`,
  DISTRACTED: `<svg viewBox="0 0 32 32"><path d="M6 20a5 5 0 0 1 1-10 7 7 0 0 1 13 1 4.5 4.5 0 0 1 2 9z" fill="#D9DEE3" ${STROKE}/><path d="M10 24l-1 4M16 24l-1 4M22 24l-1 4" ${STROKE} stroke="#5B8DEF"/></svg>`,
  PHONE_OUT: `<svg viewBox="0 0 32 32"><rect x="10" y="4" width="12" height="22" rx="3" fill="#fff" ${STROKE}/><path d="M4 29h24" ${STROKE}/><path d="M24 8l5-4" ${STROKE}/></svg>`,
  PAUSED: `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="12" fill="#DCE7FD" ${STROKE}/><path d="M13 11v10M19 11v10" ${STROKE}/></svg>`,
  BREAK: `<svg viewBox="0 0 32 32"><path d="M6 12h17v7a6 6 0 0 1-6 6h-5a6 6 0 0 1-6-6z" fill="#F6D9E4" ${STROKE}/><path d="M23 14h2a3 3 0 0 1 0 6h-2" fill="none" ${STROKE}/><path d="M11 4c-1 2 1 3 0 5M16 4c-1 2 1 3 0 5" fill="none" ${STROKE}/></svg>`,
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
// Тема: light / dark / system. Выбор дублируется в localStorage, чтобы страница не мигала при загрузке.
const darkQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
let themeChoice = "system";
function applyTheme(choice) {
  themeChoice = ["light", "dark"].includes(choice) ? choice : "system";
  const dark = themeChoice === "dark" || (themeChoice === "system" && darkQuery && darkQuery.matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  try { localStorage.setItem("carpoTheme", themeChoice); } catch (e) { /* без localStorage тоже работает */ }
}
if (darkQuery) darkQuery.addEventListener("change", () => { if (themeChoice === "system") applyTheme("system"); });

$$(".tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

// ================= звуки интерфейса (Web Audio, без аудиофайлов) =================

let soundOn = localStorage.getItem("uiSound") === "on";
let audioCtx = null;

function updateSoundButton() {
  $("#sound-toggle").textContent = soundOn ? "Звук включён" : "Звук выключен";
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
  soft: [[440, 0, 0.25], [392, 0.2, 0.3]],                   // мягкий сигнал
  distracted: [[392, 0, 0.25], [330, 0.22, 0.35]],
  click: [[880, 0, 0.05]],
  // Запасные тоны «возвращалок» (если системный звук не сработал): от мягкого к настойчивому.
  nudge1: [[523, 0, 0.3], [659, 0.25, 0.5]],
  nudge2: [[523, 0, 0.14], [659, 0.12, 0.14], [784, 0.24, 0.14], [1047, 0.36, 0.4]],
  nudge3: [[880, 0, 0.12], [880, 0.18, 0.12], [880, 0.36, 0.12], [698, 0.56, 0.12], [698, 0.74, 0.12], [698, 0.92, 0.25]],
  nudge4: [[1000, 0, 0.18], [700, 0.2, 0.18], [1000, 0.4, 0.18], [700, 0.6, 0.18], [1000, 0.8, 0.18], [700, 1.0, 0.18]],
};
const NUDGE_TEXTS = {
  1: "Ты давно отвлёкся. Самое время вернуться к учёбе",
  2: "Пора вернуться к работе",
  3: "Отвлечение затянулось. Вернись к учёбе",
  4: "Хватит отвлекаться! Возвращайся к учёбе",
};
// Номер звука подставки → мелодия интерфейса.
const SOUND_TONES = { 1: "soft", 2: "distracted", 4: "plant" };

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

const eventHooks = [];   // вкладки могут реагировать на события

function handleEvents(events) {
  for (const e of events) {
    if (e.type === "notice") toast(e.text);
    if (e.type === "session_started") toast("Сессия началась. Удачи!");
    if (e.type === "session_ended") toast(e.message);
    if (e.type === "break_started" || e.type === "break_ended") toast(e.message);
    // Защита от отвлечений — часть самой учёбы, поэтому показываем сразу.
    if (e.type === "block_warning") {
      toast(e.hard ? `«${e.process}» отвлекает и закроется через ${e.seconds} с. Сохрани работу`
                   : `«${e.process}» отвлекает от учёбы`, true);
    }
    if (e.type === "phone_report" && e.kind === "service_off" && state && state.session) {
      toast("На телефоне выключили службу блокировки", true);
    }
    if (e.type === "extension_lost") toast(e.message, true);
    if (e.type === "app_closed") toast(`«${e.process}» закрыта — возвращаемся к учёбе`);
    if (e.type === "block_failed") toast(`Не получилось закрыть «${e.process}». Закрой её сам`, true);
    // Звук-«возвращалка» играет сам компьютер; браузер подхватывает, только если системный не сработал.
    if (e.type === "nudge") {
      if (!e.system) playTone("nudge" + e.level);
      toast(NUDGE_TEXTS[e.level] || NUDGE_TEXTS[4], true);
    }
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

// Как сейчас определяется телефон: кабель (usb), подставка ESP32 (serial) или вручную (mock).
const PHONE_SOURCE_TEXT = { usb: "по кабелю", serial: "на подставке", mock: "вручную" };

function dockStatus(s) {
  if (s.phone.docked) return { cls: "ok", text: "подключён · " + (PHONE_SOURCE_TEXT[s.phone.source] || "") };
  if (s.device.status && s.device.source === "serial" && !s.device.connected) return { cls: "bad", text: "не подключён" };
  return { cls: "virtual", text: "не подключён" };
}

function renderHeader(s) {
  setStateView($("#state-pill"), $("#state-icon"), $("#state-label"), s.state);
  const dock = dockStatus(s);
  $("#dock-chip").className = "chip dock-chip " + dock.cls;
  $("#dock-chip-text").textContent = dock.text;
  $("#dock-chip").title = s.device.status || `Телефон: ${dock.text}`;
  const badge = $("#demo-badge");
  badge.hidden = s.mode !== "demo";
  badge.textContent = `ДЕМО ×${s.speed}`;
}

function renderBanner() {
  const messages = [];
  if (!connected) messages.push("Нет связи с программой — переподключаюсь…");
  if (state && !state.activity.available) {
    messages.push(state.activity.hint || "Монитор активности недоступен, работает только датчик телефона.");
  }
  if (state && state.phone.usb && state.phone.usb.error) messages.push(state.phone.usb.error);
  if (state && state.device.error) messages.push("Подставка: " + state.device.error);
  const banner = $("#banner");
  banner.hidden = messages.length === 0;
  banner.textContent = messages.join(" • ");
}

// ================= сессия =================

const RING_LENGTH = 2 * Math.PI * 112;

function renderRing(fraction, stateName) {
  const ring = $("#ring-fg");
  setStateClass(ring, stateName);
  ring.style.strokeDasharray = RING_LENGTH;
  ring.style.strokeDashoffset = RING_LENGTH * (1 - Math.max(0, Math.min(1, fraction)));
}

function renderSession(s) {
  const session = s.session;
  setStateView($("#state-banner"), $("#state-banner-icon"), $("#state-banner-text"), s.state);

  $("#start-form").hidden = !!session;
  $("#session-controls").hidden = !session;
  $("#presence").hidden = !(session && session.ask_presence);

  if (session) {
    const pomo = session.pomodoro;
    const onBreak = !!pomo && pomo.phase === "break";
    if (onBreak) {
      $("#timer").textContent = formatTime(pomo.phase_left_s);
      $("#timer").classList.remove("long");
      $("#timer-sub").textContent = (pomo.break_long ? "длинный перерыв" : "перерыв") + " · блокировка выключена";
      renderRing(pomo.phase_left_s / pomo.phase_total_s, s.state);
    } else {
      $("#timer").textContent = formatTime(session.remaining_s);
      $("#timer").classList.toggle("long", session.remaining_s >= 3600);
      $("#timer-sub").textContent = `осталось из ${minutes(session.planned_s)} мин` +
        (pomo ? ` · перерыв через ${minutes(Math.min(pomo.phase_left_s, session.remaining_s))} мин` : "");
      renderRing(1 - session.elapsed_s / session.planned_s, s.state);
    }
    $("#skip-break-btn").hidden = !onBreak;
    $("#pause-btn").hidden = $("#notebook-btn").hidden = onBreak;
    $("#pause-btn .ico").textContent = "";
    $("#pause-btn .lbl").textContent = session.paused ? "Продолжить" : "Пауза";
    $("#notebook-btn").classList.toggle("active", session.notebook);
    const totals = Object.entries(session.totals).filter(([, sec]) => sec >= 1);
    setHtml($("#session-totals"), totals.length
      ? totals.map(([st, sec]) => `<div><span class="cat s-${st}">${STATE_SHORT[st]}</span><b>${formatTime(sec)}</b></div>`).join("")
      : `<p class="muted">Пока пусто</p>`);
  } else {
    const pc = s.pomodoro || {};
    $("#pomo-hint").textContent = pc.enabled === false ? "" :
      `Сессии от ${pc.min_session_min} мин идут по Pomodoro: ${pc.work_min} мин работы, ${pc.short_break_min} мин отдыха, ` +
      `после ${pc.cycles} кругов перерыв ${pc.long_break_min} мин. Во время отдыха блокировка выключена.`;
    // Без телефона таймер не запускается (кроме тренировки без телефона).
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
  $("#stand-status").textContent = s.phone.docked ? "Телефон подключён" : "Телефон не подключён";
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

$("#start-length").oninput = () => { if (state && !state.session) renderSession(state); };

function startBody(withoutPhone) {
  return {
    length_min: Number($("#start-length").value) || null,
    without_phone: withoutPhone,
  };
}
$("#start-btn").onclick = async () => render(await api("POST", "/api/session/start", startBody(false)));
$("#start-nophone-btn").onclick = async () => render(await api("POST", "/api/session/start", startBody(true)));
// Строгий режим: пока идёт жёсткая сессия, пауза, досрочный конец и ослабление защиты — только с паролем.
function strictLocked() {
  return !!(state && state.protection && state.protection.strict && state.protection.strict.locked);
}
function askStrictPassword(what) {
  if (!strictLocked()) return undefined;
  if (!state.protection.strict.password_set) {
    toast("Строгий режим: до конца таймера выйти нельзя. Пароль задаётся в настройках.", true);
    return null;
  }
  return prompt(`Строгий режим. Введите пароль, чтобы ${what}:`);
}

$("#pause-btn").onclick = async () => {
  if (state.session.paused) return render(await api("POST", "/api/session/resume"));
  const password = askStrictPassword("поставить паузу");
  if (password === null) return;
  render(await api("POST", "/api/session/pause", password === undefined ? undefined : { password }));
};
$("#skip-break-btn").onclick = async () => render(await api("POST", "/api/session/break/skip"));
$("#notebook-btn").onclick = async () => {
  render(await api("POST", "/api/session/notebook", { on: !state.session.notebook }));
};
$("#end-btn").onclick = async () => {
  const password = askStrictPassword("завершить сессию досрочно");
  if (password === null) return;
  if (password === undefined && !confirm("Завершить сессию?")) return;
  render(await api("POST", "/api/session/end", password === undefined ? undefined : { password }));
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
const TIMELINE_ORDER = [...STATE_ORDER, "BREAK"];     // отдых: на хронологии виден, в «времени по состояниям» нет

async function loadStats() {
  const st = await api("GET", `/api/stats?range=${statsRange}`);
  $("#st-focus").textContent = minutes(st.focus_s);
  $("#st-focus-label").textContent = statsRange === "week" ? "минут фокуса за неделю" : "минут фокуса сегодня";
  $("#st-sessions").textContent = st.sessions;
  $("#st-distr").textContent = st.distractions;
  $("#st-reasons").textContent = `окно: ${st.distraction_reasons.window} · телефон: ${st.distraction_reasons.phone}`;
  $("#st-rest").textContent = minutes(st.rest.seconds);
  $("#st-rest-sub").textContent = st.rest.count ? `перерывов: ${st.rest.count}` : "перерывов не было";
  renderTimeline(st.timeline);
  renderStateBars(st.by_state_s);
  renderTop(st.top_processes);
  renderDays(st.days);
}

// ---------- хронология: полоса из цветных отрезков ----------

function renderTimeline(tl) {
  timelineData = tl;
  const svg = $("#timeline");
  $("#legend").innerHTML = TIMELINE_ORDER.map((s) => `<span class="s-${s}">${STATE_SHORT[s]}</span>`).join("");
  if (!tl || tl.duration_s <= 0 || !tl.segments.length) {
    svg.innerHTML = "";
    $("#tl-start").textContent = "Сессий ещё не было — подключи телефон";
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
    : `<p class="empty-note">Отвлечений не было</p>`;
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

// ================= настройки =================

// Группы настроек: [раздел, ключ, подпись, единица].
const SETTINGS_GROUPS = [
  ["Телефон", [
    ["thresholds", "phone_grace_s", "Сколько секунд можно смотреть в телефон без последствий", "с"],
    ["session", "auto_start_on_dock", "Начинать сессию, когда подключаю телефон"],
    ["session", "auto_end_after_phone_out_min", "Через сколько минут без телефона завершать сессию", "мин"],
  ]],
  ["Отвлечения", [
    ["thresholds", "distraction_confirm_s", "Сколько секунд на YouTube и т. п. до «Отвлёкся»", "с"],
    ["thresholds", "neutral_limit_s", "Сколько секунд в «нейтральной» программе до «Кажется, отвлёкся»", "с"],
    ["thresholds", "idle_limit_s", "Сколько секунд без клавиатуры и мыши до «Кажется, отвлёкся»", "с"],
    ["thresholds", "maybe_to_distracted_s", "Через сколько секунд «Кажется» становится «Отвлёкся»", "с"],
    ["thresholds", "recover_s", "Сколько секунд работы нужно, чтобы вернуться в фокус", "с"],
  ]],
  ["Режим тетради", [
    ["thresholds", "notebook_max_min", "Сколько минут подряд можно писать до вопроса «Ты ещё здесь?»", "мин"],
    ["thresholds", "notebook_answer_s", "Сколько секунд ждать ответа", "с"],
  ]],
  ["Сессия", [
    ["session", "default_length_min", "Длина сессии", "мин"],
    ["session", "break_min", "Перерыв после сессии", "мин"],
    ["session", "demo_length_min", "Длина сессии в демо-режиме", "мин"],
  ]],
  ["Pomodoro (длинные сессии)", [
    ["pomodoro", "enabled", "Перерывы в длинных сессиях"],
    ["pomodoro", "min_session_min", "С какой длины сессии включать перерывы", "мин"],
    ["pomodoro", "work_min", "Работа между перерывами", "мин"],
    ["pomodoro", "short_break_min", "Короткий перерыв", "мин"],
    ["pomodoro", "cycles", "После скольких рабочих отрезков перерыв длинный", "шт"],
    ["pomodoro", "long_break_min", "Длинный перерыв (20–30)", "мин"],
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

const lines = (text) => text.split("\n").map((w) => w.trim().toLowerCase()).filter(Boolean);

function showAllowBox() {
  const white = $("#set-listmode").value === "whitelist";
  $("#allow-box").hidden = !white;
  $("#allow-warn").textContent = white && !lines($("#allow-apps").value).length && !lines($("#allow-sites").value).length
    ? "Белый список пуст — пока ничего не блокируется. Добавьте программы и сайты, которые нужны для учёбы."
    : white ? "Всё, чего нет в списках, будет блокироваться во время учёбы. Программа и браузер тоже должны быть в списке."
      : "";
}

async function loadWifi() {
  const w = await api("GET", "/api/wifi/status");
  $("#wifi-status").textContent = w.error ? `${w.error}`
    : w.running ? `Готово к подключению телефонов: ${w.address}`
      : w.enabled ? "Запускаю…" : "Выключено";
  $("#wifi-pair").disabled = !w.running;
  $("#wifi-devices").innerHTML = w.devices.map((d) => `<div class="field">
    <span><i class="dot ${d.online ? "on" : "off"}"></i>${d.name}</span>
    <button class="btn small danger" data-wifi-del="${d.id}">Удалить</button></div>`).join("")
    || '<p class="muted small">Телефонов пока нет.</p>';
  $$("[data-wifi-del]").forEach((b) => (b.onclick = async (e) => {
    e.preventDefault();
    await api("DELETE", `/api/wifi/devices/${b.dataset.wifiDel}`);
    loadWifi();
  }));
}

async function loadRunning() {
  try {
    const { apps } = await api("GET", "/api/protection/running");
    $("#allow-running").innerHTML = apps.map((a) => `<option>${a}</option>`).join("")
      || "<option value=''>нет запущенных программ с окнами</option>";
  } catch (_) {
    $("#allow-running").innerHTML = "<option value=''>список недоступен</option>";
  }
}

async function loadSettings() {
  const s = await api("GET", "/api/settings");
  let html = SETTINGS_GROUPS.map(([title, fields]) => `<div class="settings-group"><h3>${title}</h3>` +
    fields.filter(([group, key]) => key in s[group])
      .map(([group, key, label, unit]) => fieldHtml(group, key, label, unit, s[group][key])).join("") +
    `</div>`).join("");
  html = `<div class="settings-group"><h3>Защита от отвлечений</h3>
    <label class="field"><span>Насколько строго</span>
      <select id="set-strictness">
        <option value="soft">мягко — предупреждение, ничего не закрываем</option>
        <option value="hard">жёстко — блокируем сайты и приложения</option>
      </select></label>
    <label class="field"><span>Секунд на сохранение до закрытия программы (жёстко)</span>
      <input type="number" id="set-warns" min="3" max="120" step="1"></label>
    <label class="field"><span>Где защищать</span>
      <select id="set-targets">
        <option value="pc">только компьютер</option>
        <option value="phone">только телефон</option>
        <option value="both">компьютер и телефон</option>
      </select></label>
    <label class="field"><span>Какие списки</span>
      <select id="set-listmode">
        <option value="blacklist">чёрный список — нельзя только отвлекающее</option>
        <option value="whitelist">белый список — можно только то, что разрешено ниже</option>
      </select></label>
    <div id="allow-box" hidden>
      <div class="muted small">Разрешённые программы (по одной в строке, например code.exe)</div>
      <textarea id="allow-apps" rows="4" spellcheck="false"></textarea>
      <div class="form-row"><select id="allow-running"></select>
        <button class="btn small" id="allow-add-running">+ Добавить запущенную</button></div>
      <div class="muted small">Разрешённые сайты (по одному в строке, например wikipedia.org)</div>
      <textarea id="allow-sites" rows="4" spellcheck="false"></textarea>
      <p class="muted small" id="allow-warn"></p>
    </div>
    <p class="muted small" id="ext-status"></p>
    <p class="muted small">Программы закрывает сама «Фокус-пруд», сайты блокирует расширение для браузера
      (папка <code>extension/</code>). На телефоне то же делает приложение «Фокус-пруд Щит» (папка <code>android/</code>).</p>
  </div>
  <div class="settings-group"><h3>Строгий режим</h3>
    <p class="muted small">Если защита «жёсткая», то во время сессии нельзя поставить паузу, завершить её досрочно
      или ослабить защиту. Выйти можно только по таймеру или с паролем. Если программу закроют, сторож запустит её снова,
      а расширение браузера и телефон сообщат, если их отключат. Это защита от случайного «ну я на минутку»;
      человека с правами администратора она не остановит.</p>
    <p class="muted small" id="strict-status"></p>
    <label class="field"><span>Старый пароль</span><input type="password" id="strict-old" autocomplete="off"></label>
    <label class="field"><span>Новый пароль (от 4 символов)</span><input type="password" id="strict-new" autocomplete="off"></label>
    <div class="form-row"><button class="btn small" id="strict-set">Сохранить пароль</button>
      <button class="btn small" id="strict-clear">Убрать пароль</button></div>
  </div>
  <div class="settings-group"><h3>Телефон по Wi-Fi</h3>
    <label class="field"><span>Связь с телефоном</span>
      <span class="toggle"><input type="checkbox" id="set-lan"><span></span></span></label>
    <p class="muted small">Без интернета и чужих серверов: ПК и телефон должны быть в одной сети Wi-Fi.
      Пока выключено, программа слушает только этот компьютер. После включения нажмите «Сохранить».</p>
    <p class="muted small" id="wifi-status"></p>
    <div class="form-row"><button class="btn small" id="wifi-pair">Подключить телефон</button></div>
    <div id="wifi-qr"></div>
    <div id="wifi-devices"></div>
  </div>` + html;
  html += `<div class="settings-group"><h3>Оформление</h3>
    <label class="field"><span>Тема интерфейса</span>
      <select id="set-theme">
        <option value="light">Светлая</option>
        <option value="dark">Тёмная</option>
        <option value="system">Как в системе</option>
      </select></label>
  </div>`;
  html += `<div class="settings-group"><h3>Звук и режим</h3>
    <label class="field"><span>Звуки подставки</span>
      <span class="toggle"><input type="checkbox" id="set-sound" ${s.sound.enabled ? "checked" : ""}><span></span></span></label>
    <label class="field"><span>Звуки-напоминания, если долго отвлекаешься</span>
      <span class="toggle"><input type="checkbox" id="set-nudge" ${(s.sound.nudge || {}).enabled !== false ? "checked" : ""}><span></span></span></label>
    <label class="field"><span>Громкость напоминаний</span>
      <input type="range" id="set-nudge-volume" min="0.1" max="1" step="0.05" value="${(s.sound.nudge || {}).volume ?? 0.6}"></label>
    <div class="form-row">
      <span class="muted small">Прослушать:</span>
      ${[1, 2, 3, 4].map((n) => `<button class="btn small nudge-preview" data-level="${n}">${n}</button>`).join(" ")}
    </div>
    <p class="muted small">Чем дольше отвлечение, тем настойчивее звук: от мягкого «дзынь» до тревожной сирены.
      Играет сам компьютер, даже если эта вкладка закрыта.</p>
    <label class="field"><span>Режим работы</span>
      <select id="set-mode">
        <option value="normal">обычный</option>
        <option value="dev">разработчик</option>
        <option value="demo">демо (ускорение)</option>
      </select></label>
    <label class="field"><span>Во сколько раз ускорять время в демо</span>
      <span class="input-unit">×<input type="number" id="set-speed" min="1" max="1000" value="${s.demo_speed}"></span></label>
  </div>
  <div class="settings-group"><h3>Отзыв и поддержка</h3>
    <p id="about-version" class="muted small"></p>
    <div class="form-row">
      <button class="btn small" id="feedback-open">Написать отзыв</button>
      <a class="btn small" id="report-download" href="/api/diagnostics" download="carpo-report.zip">Скачать отчёт для разработчика</a>
    </div>
    <p class="muted small">Отчёт — это версия, система и журнал программы. Заголовков окон, паролей и личных
      данных в нём нет. Приложи его к отзыву, если что-то сломалось.</p>
  </div>
  <div class="settings-group"><h3>Телефон по кабелю</h3>
    <p id="usb-status" class="muted"></p>
    <div id="pair-box" class="pair-box"></div>
    <label class="field"><span>Чем определять «телефон подключён»</span>
      <select id="set-source">
        <option value="auto">любой способ (кабель или подставка)</option>
        <option value="usb">только USB-кабель</option>
        <option value="serial">только подставка ESP32</option>
        <option value="mock">только вручную (разработчик)</option>
      </select></label>
    <p class="muted small">Чтобы телефоном нельзя было пользоваться, включи на нём режим «Фокусирование»
      (iPhone) или «Цифровое благополучие → Режим фокусировки» (Android) и оставь только нужные приложения.</p>
  </div>
  <div class="settings-group"><h3>Подставка</h3>
    <label class="field"><span>COM-порт</span>
      <span class="input-unit"><select id="set-port"></select><button class="btn small" id="ports-refresh" title="Обновить список">↻</button></span></label>
    <p class="muted small">«Нет подставки» — телефон определяется только по кабелю.</p>
  </div>`;
  $("#settings-groups").innerHTML = html;
  $("#set-mode").value = s.mode;
  $("#set-theme").value = (s.ui || {}).theme || "system";
  $("#set-strictness").value = (s.protection || {}).strictness || "soft";
  $("#set-warns").value = (s.protection || {}).warn_s || 10;
  $("#set-targets").value = (s.protection || {}).targets || "pc";
  $("#set-listmode").value = (s.protection || {}).list_mode || "blacklist";
  $("#allow-apps").value = ((s.protection || {}).allow_apps || []).join("\n");
  $("#allow-sites").value = ((s.protection || {}).allow_sites || []).join("\n");
  $("#set-listmode").onchange = showAllowBox;
  $("#allow-apps").oninput = $("#allow-sites").oninput = showAllowBox;
  $("#allow-add-running").onclick = (e) => {
    e.preventDefault();
    const name = $("#allow-running").value;
    const have = lines($("#allow-apps").value);
    if (name && !have.includes(name)) $("#allow-apps").value = [...have, name].join("\n");
    showAllowBox();
  };
  showAllowBox();
  loadRunning();
  $("#set-lan").checked = !!(s.network || {}).lan_enabled;
  $("#wifi-pair").onclick = async (e) => {
    e.preventDefault();
    try {
      const r = await api("POST", "/api/wifi/pair");
      $("#wifi-qr").innerHTML = `<div class="qr">${r.qr_svg}</div>
        <p class="muted small">Откройте приложение на телефоне и отсканируйте код. Он действует ${r.expires_in} секунд.</p>`;
    } catch (err) {
      $("#wifi-qr").innerHTML = `<p class="muted small">${err.message || err}</p>`;
    }
  };
  await loadWifi();
  await loadStrict();
  const live = (await api("GET", "/api/state")).protection || {};
  $("#ext-status").textContent = live.extension_connected
    ? "Расширение браузера подключено"
    : "Расширение браузера не видно: сайты не блокируются (установка — extension/README.md)";
  $("#set-source").value = s.device.phone_source || "auto";
  const about = await api("GET", "/api/about");
  $("#about-version").textContent = `Carpo ${about.version}`;
  $("#feedback-open").onclick = (e) => {
    e.preventDefault();
    if (about.feedback_url) window.open(about.feedback_url, "_blank");
    else toast("Пока некуда отправлять отзыв: скачай отчёт и пришли его автору приложения");
  };
  await loadUsb();
  $("#ports-refresh").onclick = (e) => { e.preventDefault(); loadPorts($("#set-port").value); };
  await loadPorts(s.device.serial_port);
  await loadRules();
}

async function loadStrict() {
  const st = await api("GET", "/api/strict");
  $("#strict-status").textContent = (st.password_set ? "Пароль задан." : "Пароль не задан: в жёсткой сессии выйти нельзя вообще.")
    + (st.locked ? " Сейчас идёт строгая сессия: пароль менять нельзя." : "");
  $("#strict-old").parentElement.hidden = !st.password_set;
  $("#strict-clear").hidden = !st.password_set;
}

$("#settings-groups").addEventListener("click", async (e) => {
  if (e.target.classList.contains("nudge-preview")) {
    e.preventDefault();
    await api("POST", "/api/sound/preview", { level: Number(e.target.dataset.level), volume: Number($("#set-nudge-volume").value) });
  } else if (e.target.id === "strict-set") {
    await api("PUT", "/api/strict/password", { new: $("#strict-new").value, old: $("#strict-old").value || null });
    $("#strict-new").value = $("#strict-old").value = "";
    toast("Пароль сохранён");
    await loadStrict();
  } else if (e.target.id === "strict-clear") {
    await api("DELETE", "/api/strict/password", { password: $("#strict-old").value || null });
    $("#strict-old").value = "";
    toast("Пароль убран");
    await loadStrict();
  }
});

$("#settings-save").onclick = async () => {
  const body = { thresholds: {}, session: {}, ui: {} };
  $$("#settings-groups [data-group]").forEach((input) => {
    body[input.dataset.group][input.dataset.key] = input.type === "checkbox" ? input.checked : Number(input.value);
  });
  body.ui.theme = $("#set-theme").value;
  body.sound = { enabled: $("#set-sound").checked,
                 nudge: { enabled: $("#set-nudge").checked, volume: Number($("#set-nudge-volume").value) } };
  body.mode = $("#set-mode").value;
  body.network = { lan_enabled: $("#set-lan").checked };
  body.protection = {
    strictness: $("#set-strictness").value, warn_s: Number($("#set-warns").value) || 10, targets: $("#set-targets").value,
    list_mode: $("#set-listmode").value,
    allow_apps: lines($("#allow-apps").value), allow_sites: lines($("#allow-sites").value),
  };
  body.demo_speed = Number($("#set-speed").value);
  body.device = { serial_port: $("#set-port").value, phone_source: $("#set-source").value };
  const password = askStrictPassword("изменить защиту");
  if (password === null) return;
  if (password) body.password = password;
  await api("PUT", "/api/settings", body);
  applyTheme(body.ui.theme);
  toast("Настройки сохранены");
  refresh();
};
tabLoaders.settings = loadSettings;

// ---------- привязка телефона по USB ----------

let pairStep = "idle";   // idle → unplug → plug → manual

function renderPairBox(extra = "") {
  const box = $("#pair-box");
  if (!box) return;
  const steps = {
    idle: `<button class="btn" id="pair-start">Привязать телефон</button>`,
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
    ? `Привязан: ${usb.name || "телефон"} — сейчас ${usb.docked ? "подключён" : "не подключён"}.`
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
    if (r.paired) { toast("Телефон привязан"); await loadUsb(); }
    else if (r.candidates.length > 1) await manualPairList("Найдено несколько новых устройств — выбери телефон:");
    else await manualPairList("Новое устройство не появилось. Возможно, кабель только для зарядки. Выбери телефон из списка или смени кабель:");
  } else if (e.target.dataset && e.target.dataset.pair) {
    await api("POST", "/api/phone/pair", { id: e.target.dataset.pair, name: e.target.dataset.name });
    toast("Телефон привязан");
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
      ${chipList(i, "domains", "Сайты (для расширения браузера)", "например, youtube.com")}
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
  const clean = rules.rules.filter((r) => (r.process || []).length || (r.title_contains || []).length
    || (r.domains || []).length);
  rules = await api("PUT", "/api/rules", { default: rules.default, rules: clean });
  renderRules();
  toast("Правила сохранены");
};


// ================= запуск =================

refresh().catch(() => {});
api("GET", "/api/settings").then((cfg) => applyTheme(cfg.ui && cfg.ui.theme)).catch(() => {});
connect();
// Ссылка вида http://127.0.0.1:8765/#session сразу открывает нужную вкладку.
if (location.hash) showTab(location.hash.slice(1));

export { api, toast, formatTime, minutes, showTab, tabLoaders, renderHooks, eventHooks, setHtml, STATE_LABELS, STATE_SHORT, CATEGORY_LABELS };

// ================= карточка «Защита от отвлечений»: подключение без настроек =================

let codeTimer = null;

async function refreshSetup() {
  try {
    const wifi = await api("GET", "/api/wifi/status");
    const online = wifi.devices.filter((d) => d.online).length;
    $("#setup-phone").textContent = online ? `Подключён: ${wifi.devices.filter((d) => d.online).map((d) => d.name).join(", ")}`
      : wifi.devices.length ? "Телефон сопряжён, но сейчас не на связи" : "Не подключён";
    $("#setup-phone-btn").textContent = wifi.devices.length ? "Подключить ещё" : "Подключить телефон";
    if (online && !$("#setup-phone-box").hidden) $("#setup-phone-box").hidden = true;   // подключились: код больше не нужен
    const ext = await api("GET", "/api/extension/browsers");
    $("#setup-ext").textContent = ext.connected ? "Расширение работает" : "Расширение не установлено: сайты не блокируются";
    $("#setup-ext-btn").hidden = ext.connected;
  } catch (_) { /* карточка не должна мешать остальному интерфейсу */ }
}

$("#setup-phone-btn").onclick = async () => {
  try {
    const r = await api("POST", "/api/wifi/pair");
    $("#setup-code").textContent = r.code;
    $("#setup-qr").innerHTML = `<div class="qr">${r.qr_svg}</div>`;
    $("#setup-phone-box").hidden = false;
    clearTimeout(codeTimer);
    codeTimer = setTimeout(() => { $("#setup-phone-box").hidden = true; }, r.expires_in * 1000);
    refreshSetup();
  } catch (_) { /* текст ошибки уже показан */ }
};

$("#setup-ext-btn").onclick = async () => {
  const box = $("#setup-ext-box");
  box.hidden = !box.hidden;
  const { browsers } = await api("GET", "/api/extension/browsers");
  $("#setup-browser").innerHTML = browsers.map((b) => `<option value="${b.key}">${b.name}</option>`).join("")
    || "<option value=''>браузер не найден</option>";
};

$("#setup-ext-go").onclick = async () => {
  const browser = $("#setup-browser").value;
  if (!browser) return toast("Не нашёл Chrome, Edge, Firefox или Яндекс Браузер", true);
  const r = await api("POST", "/api/extension/install", { browser });
  const steps = $("#setup-ext-steps");
  steps.replaceChildren(...r.steps.map((text) => Object.assign(document.createElement("li"), { textContent: text })));
  steps.hidden = false;
  $("#setup-ext-path").textContent = (r.copied ? "Путь уже в буфере обмена (Ctrl+V): " : "Путь: ") + r.folder
    + (r.opened ? "" : ` (откройте страницу расширений в ${r.browser} сами)`);
};

refreshSetup();
setInterval(refreshSetup, 4000);
