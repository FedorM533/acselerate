// Мягкий режим: перед кнопкой «Всё равно открыть» человек несколько секунд читает сообщение.
// Первый заход подряд: 5 секунд, каждый следующий добавляет ещё 5. Если 15 минут не было ни одного
// захода на запрещённый сайт, счёт начинается заново. То же правило, что в приложении для телефона.
const ESCALATION_STEP_S = 5;
const ESCALATION_RESET_MS = 15 * 60 * 1000;

// Номер захода подряд: 1 для первого или после 15 минут спокойной работы.
function nextAttempt(count, lastMs, now) {
  return !lastMs || now - lastMs >= ESCALATION_RESET_MS || !(count >= 1) ? 1 : count + 1;
}

// Сколько секунд нельзя нажимать «Всё равно открыть».
function delaySeconds(count) {
  return ESCALATION_STEP_S * Math.max(1, count);
}

if (typeof module !== "undefined") module.exports = { nextAttempt, delaySeconds, ESCALATION_RESET_MS };
