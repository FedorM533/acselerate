package com.focusfarm.shield

/** Что сейчас со связью с ПК; читает главный экран. */
object LinkStatus {
    const val OFF = 0
    const val CONNECTING = 1
    const val ONLINE = 2

    @Volatile var state = OFF
    @Volatile var detail = ""

    fun label(): String = when (state) {
        ONLINE -> "на связи"
        CONNECTING -> "подключаюсь…"
        else -> if (detail.isEmpty()) "нет связи" else "нет связи ($detail)"
    }
}
