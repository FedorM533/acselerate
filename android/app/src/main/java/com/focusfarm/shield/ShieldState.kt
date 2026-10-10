package com.focusfarm.shield

/**
 * Идёт ли сейчас учёба и по каким правилам. Учёба может прийти с ПК (remote) или быть запущена
 * на самом телефоне (local). Если связь с ПК пропала, учёба с ПК доходит до своего конца
 * (remoteUntil), поэтому телефон защищается и без связи.
 */
data class ShieldState(
    val remoteUntil: Long = 0,
    val remoteMode: String = MODE_BLACKLIST,
    val remoteHard: Boolean = false,
    val localUntil: Long = 0,
    val localMode: String = MODE_BLACKLIST,
    val localHard: Boolean = false,
) {
    fun remoteActive(now: Long) = now < remoteUntil
    fun localActive(now: Long) = now < localUntil
    fun active(now: Long) = remoteActive(now) || localActive(now)

    /** Режим списков: пока идёт учёба с ПК, главный ПК; иначе выбор на телефоне. */
    fun mode(now: Long) = if (remoteActive(now)) remoteMode else localMode

    /** Жёсткий режим, если его требует любая из идущих учёб. */
    fun hard(now: Long) = (remoteActive(now) && remoteHard) || (localActive(now) && localHard)

    fun remainingMs(now: Long) = maxOf(0L, maxOf(remoteUntil, localUntil) - now)

    companion object {
        const val MODE_BLACKLIST = "blacklist"
        const val MODE_WHITELIST = "whitelist"
    }
}
