// Фокус-пруд: блокировка сайтов.
// Раз в полминуты и при каждом переходе спрашиваем у программы (127.0.0.1),
// идёт ли сейчас сессия, и какие сайты закрыть. Программа не запущена — ничего не блокируем.
//
// Порт программы находится сам: пробуем запомненный, потом 8765 и ближайшие (флаг --port).
// 8766 занят связью с телефоном, его пропускаем.
const DEFAULT_PORTS = [8765, ...Array.from({ length: 19 }, (_, i) => 8767 + i)];
const POLL_MINUTES = 0.5;          // Chrome не даёт будильникам срабатывать чаще

const FETCH_TIMEOUT_MS = 2500;     // программа бывает занята опросом окон: ей нужно время на ответ
const STALE_OK_MS = 120000;        // «не успела ответить» — верим последнему ответу не дольше двух минут

// {data} — ответ получен; {data: null, slow: true} — программа есть, но не успела ответить;
// {data: null} — здесь программы нет (или это чужой сервис).
async function fetchFrom(port) {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/protection/sites`,
      { signal: abort.signal, cache: "no-store" });
    const data = response.ok ? await response.json() : null;
    return { data: data && typeof data.active === "boolean" ? data : null };
  } catch (e) {
    return { data: null, slow: Boolean(e && e.name === "AbortError") };
  } finally {
    clearTimeout(timer);
  }
}

async function fetchState() {
  let saved = null;
  try { saved = (await chrome.storage.local.get("port")).port; } catch (_) { /* без памяти тоже работаем */ }
  const ports = saved ? [saved, ...DEFAULT_PORTS.filter((p) => p !== saved)] : DEFAULT_PORTS;
  let slow = false;
  for (const port of ports) {
    const result = await fetchFrom(port);
    if (result.data) {
      if (port !== saved) chrome.storage.local.set({ port }).catch(() => {});
      chrome.storage.session.set({ lastState: { data: result.data, at: Date.now() } }).catch(() => {});
      return result.data;
    }
    slow = slow || result.slow;
  }
  if (slow) {   // программа жива, но занята: не пропускаем отвлечение из-за одного пропущенного ответа
    try {
      const { lastState } = await chrome.storage.session.get("lastState");
      if (lastState && Date.now() - lastState.at < STALE_OK_MS) return lastState.data;
    } catch (_) { /* без памяти — как раньше */ }
  }
  return null;   // программа не запущена — не мешаем
}

function hostOf(url) {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.hostname.toLowerCase() : null;
  } catch (_) {
    return null;
  }
}

function matches(host, domains) {
  return domains.some((d) => host === d || host.endsWith(`.${d}`));
}

// Свою программу (127.0.0.1, localhost) не блокируем никогда, иначе из режима не выйти.
const OWN_HOSTS = ["127.0.0.1", "localhost"];

function isBlocked(host, state) {
  if (!host || matches(host, OWN_HOSTS)) return false;
  // Белый список: можно только перечисленное. Чёрный: нельзя только перечисленное.
  return state.mode === "whitelist" ? !matches(host, state.allow || []) : matches(host, state.domains);
}


async function inGrace(host) {
  try {
    const key = `grace:${host}`;
    const saved = await chrome.storage.session.get(key);
    return Boolean(saved[key]) && Date.now() / 1000 < saved[key];
  } catch (_) {
    return false;
  }
}

async function handle(tabId, url, state) {
  const host = hostOf(url);
  if (!state || !state.active || !isBlocked(host, state)) return;
  if (!state.hard && await inGrace(host)) return;
  // И жёсткий, и мягкий режим закрывают вкладку целой страницей: всплывающее уведомление
  // система может заглушить (режим «Не беспокоить»), а такую страницу не пропустить.
  const page = chrome.runtime.getURL("blocked.html") +
    `?site=${encodeURIComponent(host)}&left=${Math.round(state.remaining_s)}` +
    (state.hard ? "" : `&soft=1&url=${encodeURIComponent(url)}`);
  chrome.tabs.update(tabId, { url: page }).catch((e) => console.warn("не удалось закрыть вкладку", tabId, String(e)));
}

// Страница уже загрузилась: проверяем ещё раз. Так ловим случаи, когда сайт успел перенаправить вкладку
// (http → https, www, страницы согласия) и обогнал замену на «сайт закрыт».
chrome.webNavigation.onCommitted.addListener(async (details) => {
  if (details.frameId !== 0) return;
  await handle(details.tabId, details.url, await fetchState());
});

// Переходы внутри страницы без перезагрузки (YouTube, ВК и другие одностраничные сайты):
// onBeforeNavigate их не видит, а адрес меняется.
chrome.webNavigation.onHistoryStateUpdated.addListener(async (details) => {
  if (details.frameId !== 0) return;
  await handle(details.tabId, details.url, await fetchState());
});

// Переход на новую страницу (только основное окно вкладки, не рамки внутри страницы).
chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
  if (details.frameId !== 0) return;
  await handle(details.tabId, details.url, await fetchState());
});

// Уже открытые вкладки: сессия могла начаться, пока сайт был открыт.
async function sweep() {
  const state = await fetchState();
  if (!state || !state.active) return;
  for (const tab of await chrome.tabs.query({})) {
    if (tab.url) await handle(tab.id, tab.url, state);
  }
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "poll") sweep();
});

function ensureAlarm() {
  chrome.alarms.get("poll", (alarm) => {
    if (!alarm) chrome.alarms.create("poll", { periodInMinutes: POLL_MINUTES });
  });
}

chrome.runtime.onInstalled.addListener(() => { ensureAlarm(); sweep(); });
chrome.runtime.onStartup.addListener(() => { ensureAlarm(); sweep(); });
ensureAlarm();
