package com.focusfarm.shield

/**
 * Мягкий режим: прежде чем разрешить «всё равно открыть», человек несколько секунд читает сообщение.
 * Первый заход подряд: 5 секунд, каждый следующий добавляет ещё 5. Если 15 минут не было ни одного захода
 * в запрещённое, счёт начинается заново.
 */
object Escalation {
    const val STEP_S = 5
    const val RESET_MS = 15 * 60_000L

    /** Номер захода подряд: 1 для первого или после 15 минут спокойной работы. */
    fun nextCount(count: Int, lastMs: Long, now: Long): Int =
        if (lastMs <= 0L || now - lastMs >= RESET_MS || count < 1) 1 else count + 1

    /** Сколько секунд нельзя нажимать «всё равно открыть». */
    fun delaySeconds(count: Int): Int = STEP_S * maxOf(1, count)
}
