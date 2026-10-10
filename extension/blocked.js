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
