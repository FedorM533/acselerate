/**
 * Carpo Pond — эталонная реализация движка прогресса (чистые функции, без зависимостей).
 *
 * Это СПРАВКА для переноса в язык проекта (Kotlin / Java / Swift / Dart / TS ...).
 * Поведение зафиксировано тест-векторами в config/progress_test_vectors.json —
 * порт считается правильным, когда проходит их все.
 *
 * Работает и в браузере, и в Node:  node reference/checkVectors.mjs
 */

/** @typedef {{
 *   id: string,
 *   endedAt: number,              // epoch ms — только для сортировки
 *   localDate: string,            // "YYYY-MM-DD" в часовом поясе пользователя (считает вызывающий код)
 *   plannedMinutes: number,
 *   focusedSeconds: number,       // фактически отработанное время по таймеру (монотонные часы)
 *   endReason: "completed" | "interrupted",
 *   reasonCode: string | null     // код причины прерывания или null, если пропустил вопрос
 * }} FocusSession */

/** ceil(base * percent / 100) только в целых числах — без ошибок плавающей точки */
function percentCeil(base, percent) {
  return Math.floor((base * percent + 99) / 100);
}

/**
 * Начисление капель по всем сессиям. Порядок важен (дневные лимиты), поэтому
 * сессии сортируются по endedAt, при равенстве — по id.
 * @param {FocusSession[]} sessions
 * @param {object} scoring  progression.json → scoring
 */
export function scoreSessions(sessions, scoring) {
  const sorted = [...sessions].sort((a, b) => (a.endedAt - b.endedAt) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const baseByDay = new Map();
  const reasonBonusesByDay = new Map();
  const results = [];
  let drops = 0;

  for (const s of sorted) {
    const day = s.localDate;
    if (s.focusedSeconds < scoring.minCountedSeconds) {
      results.push({ id: s.id, status: "too_short", base: 0, bonus: 0 });
      continue;
    }
    const cappedSeconds = Math.min(s.focusedSeconds, s.plannedMinutes * 60, scoring.maxSessionMinutes * 60);
    const minutes = Math.floor(cappedSeconds / scoring.secondsPerDrop);
    const usedToday = baseByDay.get(day) || 0;
    const base = Math.max(0, Math.min(minutes, scoring.dailyBaseCapDrops - usedToday));
    baseByDay.set(day, usedToday + base);

    let bonus = 0;
    let status;
    if (s.endReason === "completed") {
      status = "completed";
      bonus = Math.min(scoring.completionBonus.max, percentCeil(base, scoring.completionBonus.percent));
    } else if (s.reasonCode) {
      status = "interrupted_with_reason";
      const rb = scoring.reasonBonus;
      const used = reasonBonusesByDay.get(day) || 0;
      if (base >= rb.minBaseDrops && used < rb.maxPerDay) {
        bonus = Math.min(rb.max, percentCeil(base, rb.percent));
        reasonBonusesByDay.set(day, used + 1);
      }
    } else {
      status = "interrupted_no_reason";
    }
    drops += base + bonus;
    results.push({ id: s.id, status, base, bonus });
  }

  let focusDays = 0;
  for (const v of baseByDay.values()) if (v >= scoring.focusDayMinBaseDrops) focusDays++;
  return { drops, focusDays, sessions: results };
}

/** Какие открытия доступны при данных каплях/днях. Открытое однажды НЕ отбирается (см. mergeUnlocked). */
export function computeUnlocks(drops, focusDays, unlocks) {
  return unlocks
    .filter(u => drops >= u.requires.drops && focusDays >= u.requires.focusDays)
    .sort((a, b) => a.order - b.order)
    .map(u => u.id);
}

/** Объединить сохранённые открытия с вычисленными — пруд никогда не «откатывается» */
export function mergeUnlocked(stored, computed) {
  return Array.from(new Set([...stored, ...computed]));
}

export function currentStage(drops, stages) {
  let st = stages[0];
  for (const s of stages) if (drops >= s.fromDrops) st = s;
  return st.id;
}

/** Полный пересчёт состояния пруда из журнала сессий (идемпотентно, можно вызывать сколько угодно раз) */
export function computePond(sessions, config, storedUnlocked = []) {
  const scored = scoreSessions(sessions, config.scoring);
  const computed = computeUnlocks(scored.drops, scored.focusDays, config.unlocks);
  const unlocked = mergeUnlocked(storedUnlocked, computed);
  const newlyUnlocked = unlocked.filter(id => !storedUnlocked.includes(id));
  return {
    drops: scored.drops,
    focusDays: scored.focusDays,
    stage: currentStage(scored.drops, config.stages),
    unlocked,
    newlyUnlocked,          // показать анимацией появления после сессии
    sessions: scored.sessions,
  };
}
