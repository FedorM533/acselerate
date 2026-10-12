// Страница «сайт закрыт»: название сайта и сколько осталось учиться — из адреса.
const params = new URLSearchParams(location.search);
const site = params.get("site");
const left = Number(params.get("left"));

if (site) document.getElementById("site").textContent = site;
if (left > 0) {
  const minutes = Math.max(1, Math.round(left / 60));
  document.getElementById("left").textContent = `До конца сессии примерно ${minutes} мин. Рыбка растёт 🌱`;
}

document.getElementById("close").onclick = async () => {
  const tab = await chrome.tabs.getCurrent();
  if (tab) chrome.tabs.remove(tab.id);
  else window.close();
};

// Мягкий режим: можно открыть сайт на 5 минут, но напоминание вернётся.
const target = params.get("url");
if (params.get("soft") && target && /^https?:\/\//i.test(target)) {
  document.getElementById("verdict").textContent = "отвлекает от учёбы. Вернись к делу, рыбка ждёт.";
  const openButton = document.getElementById("open");
  const attempt = document.getElementById("attempt");
  openButton.hidden = false;
  openButton.disabled = true;
  // Чем чаще заходишь на запрещённое, тем дольше ждать (см. escalation.js); 15 минут спокойной работы сбрасывают счёт.
  (async () => {
    let count = 1;
    try {
      const saved = await chrome.storage.local.get(["escCount", "escLast"]);
      count = nextAttempt(saved.escCount, saved.escLast, Date.now());
      await chrome.storage.local.set({ escCount: count, escLast: Date.now() });
    } catch (_) { /* без памяти считаем заход первым */ }
    attempt.hidden = false;
    attempt.textContent = count > 1 ? `Это уже заход №${count} подряд. Каждый следующий ждать дольше.` : "Подумай: оно того стоит?";
    const readyAt = Date.now() + delaySeconds(count) * 1000;
    const timer = setInterval(() => {
      const left = Math.ceil((readyAt - Date.now()) / 1000);
      openButton.disabled = left > 0;
      openButton.textContent = left > 0 ? `Подожди ещё ${left} с…` : "Всё равно открыть на 5 минут";
      if (left <= 0) clearInterval(timer);
    }, 250);
  })();
  openButton.onclick = async () => {
    if (openButton.disabled) return;
    try { await chrome.storage.session.set({ [`grace:${site}`]: Date.now() / 1000 + 300 }); } catch (_) { /* всё равно откроем */ }
    location.replace(target);
  };
}
