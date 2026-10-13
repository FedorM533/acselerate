package com.focusfarm.shield

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NudgeTest {
    private val sec = 1000L

    @Test fun firstAttemptIsSilentThenLevelsGrowToFour() {
        assertEquals(listOf(0, 1, 2, 3, 4, 4, 4), (1..7).map { Nudge.levelForAttempt(it) })
        assertEquals(0, Nudge.levelForAttempt(0))
    }

    @Test fun levelsGrowWithTimeInDistractingApp() {
        val t = NudgeTracker()
        val start = 1_000_000L
        assertEquals(0, t.tick(true, start))                 // зашёл: отсчёт пошёл
        assertEquals(0, t.tick(true, start + 59 * sec))
        assertEquals(1, t.tick(true, start + 60 * sec))
        assertEquals(0, t.tick(true, start + 65 * sec))      // тот же уровень дважды не играем
        assertEquals(2, t.tick(true, start + 180 * sec))
        assertEquals(3, t.tick(true, start + 360 * sec))
        assertEquals(4, t.tick(true, start + 600 * sec))
    }

    @Test fun topLevelRepeatsNotOftenerThanEveryTwoMinutes() {
        val t = NudgeTracker()
        val start = 1_000_000L
        t.tick(true, start)
        t.tick(true, start + 600 * sec)
        assertEquals(0, t.tick(true, start + 719 * sec))
        assertEquals(4, t.tick(true, start + 720 * sec))
        assertEquals(0, t.tick(true, start + 725 * sec))
    }

    @Test fun leavingTheAppResetsEverything() {
        val t = NudgeTracker()
        val start = 1_000_000L
        t.tick(true, start)
        assertEquals(1, t.tick(true, start + 60 * sec))
        assertEquals(0, t.tick(false, start + 70 * sec))      // вернулся к делу
        assertEquals(0, t.tick(true, start + 80 * sec))       // новый заход: отсчёт заново
        assertEquals(1, t.tick(true, start + 140 * sec))
    }

    @Test fun everyLevelIsValidAndLevelsDiffer() {
        val sizes = (1..Nudge.LEVELS).map { level ->
            val pcm = Nudge.render(level, 0.6f)
            val peak = pcm.maxOf { kotlin.math.abs(it.toInt()) }
            assertTrue("уровень $level тихий или переполнен", peak in 1..32766)
            pcm.size
        }
        assertEquals(sizes.size, sizes.toSet().size)
    }

    @Test fun badLevelAndVolumeDoNotCrash() {
        assertTrue(Nudge.render(99, 5f).isNotEmpty())
        assertTrue(Nudge.render(-3, -1f).isNotEmpty())
    }
}
