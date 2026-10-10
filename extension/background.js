// Фокус-пруд: блокировка сайтов.
// Раз в полминуты и при каждом переходе спрашиваем у программы (127.0.0.1),
// идёт ли сейчас сессия, и какие сайты закрыть. Программа не запущена — ничего не блокируем.
//
// Если у «Фокус-пруда» другой порт (флаг --port), поменяйте SERVER и
// host_permissions в manifest.json.
const SERVER = "http://127.0.0.1:8765";
const API = `${SERVER}/api/protection/sites`;
const POLL_MINUTES = 0.5;          // Chrome не даёт будильникам срабатывать чаще
const SOFT_REMIND_S = 300;         // в мягком режиме напоминаем об одном сайте не чаще раза в 5 минут

async function fetchState() {
  try {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 1500);
    const response = await fetch(API, { signal: abort.signal, cache: "no-store" });
    clearTimeout(timer);
    return response.ok ? await response.json() : null;
  } catch (_) {
    return null;   // программа не запущена — не мешаем
  }
}

function hostOf(url) {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.hostname.toLowerCase() : null;
  } catch (_) {
    return null;
  }
}

function isBlocked(host, domains) {
  return !!host && domains.some((d) => host === d || host.endsWith(`.${d}`));
}

async function remindOnce(host) {
  const key = `reminded:${host}`;
  const saved = await chrome.storage.session.get(key);
  const now = Date.now() / 1000;
  if (saved[key] && now - saved[key] < SOFT_REMIND_S) return;
  await chrome.storage.session.set({ [key]: now });
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: "Идёт учёба 🐟",
    message: `${host} отвлекает. Вернись к делу, рыбка ждёт.`,
  });
}

async function handle(tabId, url, state) {
  const host = hostOf(url);
  if (!state || !state.active || !isBlocked(host, state.domains)) return;
  if (state.hard) {
    const page = chrome.runtime.getURL("blocked.html") +
      `?site=${encodeURIComponent(host)}&left=${Math.round(state.remaining_s)}`;
    chrome.tabs.update(tabId, { url: page }).catch(() => {});
  } else {
    await remindOnce(host);
  }
}

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
