package com.focusfarm.shield

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/**
 * Звуки-«возвращалки»: чем дольше отвлекаешься, тем настойчивее сигнал (как и на компьютере).
 * Четыре уровня: 1 — мягкий «дзынь», 2 — бодрое арпеджио, 3 — настойчивый двойной сигнал,
 * 4 — тревожная «сирена». Растёт резкость, а не громкость.
 */
object Nudge {
    const val LEVELS = 4
    const val RATE = 22050

    /** Через сколько секунд отвлечения звучит уровень 1, 2, 3, 4. */
    val AFTER_S = intArrayOf(60, 180, 360, 600)

    /** После последнего уровня повторяем его так часто. */
    const val REPEAT_S = 120

    /**
     * Заходы в запрещённое подряд (см. Escalation): первый заход молчит (экран «Идёт учёба» и так
     * всё сказал), со второго звучит уровень 1, дальше растёт до 4. 0 — без звука.
     */
    fun levelForAttempt(count: Int): Int = if (count < 2) 0 else min(count - 1, LEVELS)

    private enum class Shape { SINE, TRI, SQUARE }

    /** Нота: частота Гц, начало с, длительность с. */
    private class Note(val freq: Int, val start: Double, val dur: Double)

    private class Pattern(val shape: Shape, val notes: List<Note>)

    private val patterns = mapOf(
        1 to Pattern(Shape.SINE, listOf(Note(523, 0.00, 0.35), Note(659, 0.28, 0.55))),
        2 to Pattern(Shape.TRI, listOf(Note(523, 0.00, 0.16), Note(659, 0.14, 0.16), Note(784, 0.28, 0.16), Note(1047, 0.42, 0.45))),
        3 to Pattern(Shape.TRI, listOf(
            Note(880, 0.00, 0.14), Note(880, 0.20, 0.14), Note(880, 0.40, 0.14),
            Note(698, 0.62, 0.14), Note(698, 0.82, 0.14), Note(698, 1.02, 0.30),
        )),
        4 to Pattern(Shape.SQUARE, List(8) { i -> Note(if (i % 2 == 0) 1000 else 700, i * 0.22, 0.2) }),
    )

    private fun wave(shape: Shape, phase: Double): Double = when (shape) {
        Shape.SINE -> sin(2 * PI * phase)
        Shape.TRI -> 4 * abs(phase - 0.5) - 1
        Shape.SQUARE -> if (phase < 0.5) 1.0 else -1.0
    }

    /** Звук уровня level (1..4) как PCM 16 бит, моно, [RATE] Гц. Громкость volume 0.05..1. */
    fun render(level: Int, volume: Float = 0.6f): ShortArray {
        val pattern = patterns.getValue(level.coerceIn(1, LEVELS))
        val vol = volume.coerceIn(0.05f, 1f).toDouble()
        val total = pattern.notes.maxOf { it.start + it.dur } + 0.05
        val samples = DoubleArray((total * RATE).toInt())
        // Прямоугольная волна субъективно громче: гасим амплитуду, чтобы уровни были сравнимы по громкости.
        val amp = vol * (if (pattern.shape == Shape.SQUARE) 0.35 else 0.8)
        val attack = maxOf(1, (0.015 * RATE).toInt())
        for (note in pattern.notes) {
            val first = (note.start * RATE).toInt()
            val count = (note.dur * RATE).toInt()
            for (i in 0 until count) {
                if (first + i >= samples.size) break
                val env = min(1.0, i.toDouble() / attack) * (1.0 - i.toDouble() / count).pow(1.5)
                samples[first + i] += amp * env * wave(pattern.shape, (note.freq.toDouble() * i / RATE) % 1.0)
            }
        }
        return ShortArray(samples.size) { (samples[it].coerceIn(-1.0, 1.0) * 32767).toInt().toShort() }
    }
}

/**
 * Следит, как долго человек сидит в запрещённом приложении, которое открыл «всё равно» (мягкий режим),
 * и говорит, пора ли играть следующий уровень. Время приходит снаружи, поэтому проверяется обычными тестами.
 */
class NudgeTracker(
    private val afterS: IntArray = Nudge.AFTER_S,
    private val repeatS: Int = Nudge.REPEAT_S,
) {
    private var since = 0L
    private var done = 0
    private var lastAt = 0L

    fun reset() {
        since = 0L
        done = 0
        lastAt = 0L
    }

    /**
     * Вызывается каждые несколько секунд. distracted — сейчас на экране запрещённое приложение.
     * Возвращает уровень звука (1..4) или 0, если играть не надо.
     */
    fun tick(distracted: Boolean, nowMs: Long): Int {
        if (!distracted) {
            reset()
            return 0
        }
        if (since == 0L) {
            since = nowMs
            return 0
        }
        val elapsedS = (nowMs - since) / 1000
        val due = afterS.count { elapsedS >= it }
        if (due > done) {
            done = due
            lastAt = nowMs
            return due
        }
        if (due > 0 && due == afterS.size && nowMs - lastAt >= repeatS * 1000L) {
            lastAt = nowMs
            return due
        }
        return 0
    }
}
