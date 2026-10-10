package com.focusfarm.shield

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ShieldStateTest {
    @Test fun inactiveByDefault() {
        val s = ShieldState()
        assertFalse(s.active(1000))
        assertEquals(0L, s.remainingMs(1000))
    }

    @Test fun remoteSessionKeepsWorkingWithoutLinkUntilItsEnd() {
        val s = ShieldState(remoteUntil = 10_000)
        assertTrue(s.active(9_999))
        assertFalse(s.active(10_000))
    }

    @Test fun remoteModeWinsWhileRemoteIsActive() {
        val s = ShieldState(remoteUntil = 10_000, remoteMode = ShieldState.MODE_WHITELIST, localMode = ShieldState.MODE_BLACKLIST,
            localUntil = 20_000)
        assertEquals(ShieldState.MODE_WHITELIST, s.mode(5_000))
        assertEquals(ShieldState.MODE_BLACKLIST, s.mode(15_000))
    }

    @Test fun hardWhenAnyRunningSessionIsHard() {
        val s = ShieldState(remoteUntil = 10_000, remoteHard = false, localUntil = 10_000, localHard = true)
        assertTrue(s.hard(5_000))
        assertFalse(ShieldState(remoteUntil = 10_000, localHard = true).hard(5_000))   // локальная настройка без локальной учёбы не в счёт
    }

    @Test fun remainingIsTheLongerOfTheTwo() {
        val s = ShieldState(remoteUntil = 8_000, localUntil = 12_000)
        assertEquals(7_000L, s.remainingMs(5_000))
    }
}
