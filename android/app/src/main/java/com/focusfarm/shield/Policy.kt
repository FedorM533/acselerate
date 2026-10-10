package com.focusfarm.shield

/** Решение «закрыть ли это приложение». Без Android-классов, чтобы проверять обычными тестами. */
object Policy {
    /**
     * @param alwaysAllowed домашний экран, звонилка, клавиатура, настройки и само приложение
     * Белый список без единого приложения ничего не блокирует (иначе закрылось бы вообще всё),
     * так же работает и компьютер.
     */
    fun isBlocked(
        pkg: String,
        mode: String,
        blocked: Set<String>,
        allowed: Set<String>,
        alwaysAllowed: Set<String>,
    ): Boolean {
        if (pkg in alwaysAllowed) return false
        return if (mode == ShieldState.MODE_WHITELIST) {
            allowed.isNotEmpty() && pkg !in allowed
        } else {
            pkg in blocked
        }
    }
}

/** В мягком режиме можно открыть приложение «всё равно» на 5 минут. Хранится только в памяти. */
object Snooze {
    const val DURATION_MS = 5 * 60_000L
    private val until = HashMap<String, Long>()

    @Synchronized
    fun set(pkg: String, now: Long = System.currentTimeMillis()) {
        until[pkg] = now + DURATION_MS
    }

    @Synchronized
    fun active(pkg: String, now: Long = System.currentTimeMillis()): Boolean = (until[pkg] ?: 0L) > now

    @Synchronized
    fun clear() = until.clear()
}
