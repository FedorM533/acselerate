// Фокус-пруд: блокировка сайтов.
// Раз в полминуты и при каждом переходе спрашиваем у программы (127.0.0.1),
// идёт ли сейчас сессия, и какие сайты закрыть. Программа не запущена — ничего не блокируем.
//
// Порт программы находится сам: пробуем запомненный, потом 8765 и ближайшие (флаг --port).
// 8766 занят связью с телефоном, его пропускаем.
const DEFAULT_PORTS = [8765, ...Array.from({ length: 19 }, (_, i) => 8767 + i)];
const POLL_MINUTES = 0.5;          // Chrome не даёт будильникам срабатывать чаще
const SOFT_REMIND_S = 30;          // в мягком режиме напоминаем снова при каждом заходе, но не чаще раза в 30 секунд

async function fetchFrom(port) {
  try {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 1000);
    const response = await fetch(`http://127.0.0.1:${port}/api/protection/sites`,
      { signal: abort.signal, cache: "no-store" });
    clearTimeout(timer);
    const data = response.ok ? await response.json() : null;
    return data && typeof data.active === "boolean" ? data : null;   // чужой сервис нам не нужен
  } catch (_) {
    return null;   // здесь программы нет
  }
}

async function fetchState() {
  let saved = null;
  try { saved = (await chrome.storage.local.get("port")).port; } catch (_) { /* без памяти тоже работаем */ }
  const ports = saved ? [saved, ...DEFAULT_PORTS.filter((p) => p !== saved)] : DEFAULT_PORTS;
  for (const port of ports) {
    const data = await fetchFrom(port);
    if (data) {
      if (port !== saved) chrome.storage.local.set({ port }).catch(() => {});
      return data;
    }
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
  if (!state || !state.active || !isBlocked(host, state)) return;
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
