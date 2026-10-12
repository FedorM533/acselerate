package com.focusfarm.shield

import org.junit.Assert.assertEquals
import org.junit.Test

class EscalationTest {
    private val minute = 60_000L

    @Test fun firstAttemptWaitsFiveSeconds() {
        val n = Escalation.nextCount(0, 0, 1_000_000)
        assertEquals(1, n)
        assertEquals(5, Escalation.delaySeconds(n))
    }

    @Test fun everyExtraAttemptAddsFiveSeconds() {
        var count = 0
        var last = 0L
        var now = 1_000_000L
        val delays = (1..4).map {
            count = Escalation.nextCount(count, last, now)
            last = now
            now += 2 * minute
            Escalation.delaySeconds(count)
        }
        assertEquals(listOf(5, 10, 15, 20), delays)
    }

    @Test fun fifteenMinutesWithoutDistractionResetsToFiveSeconds() {
        val last = 1_000_000L
        assertEquals(4, Escalation.nextCount(3, last, last + 14 * minute))        // ещё не прошло 15 минут
        val after = Escalation.nextCount(3, last, last + 15 * minute)
        assertEquals(1, after)
        assertEquals(5, Escalation.delaySeconds(after))
    }

    @Test fun brokenCounterIsTreatedAsFirstAttempt() {
        assertEquals(1, Escalation.nextCount(-3, 1_000_000, 1_000_500))
        assertEquals(5, Escalation.delaySeconds(0))
    }
}
