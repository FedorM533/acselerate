package com.focusfarm.shield

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PolicyTest {
    private val always = setOf("com.android.launcher", "com.focusfarm.shield")
    private val black = ShieldState.MODE_BLACKLIST
    private val white = ShieldState.MODE_WHITELIST

    @Test fun blacklistBlocksOnlyListed() {
        assertTrue(Policy.isBlocked("com.game", black, setOf("com.game"), emptySet(), always))
        assertFalse(Policy.isBlocked("com.notes", black, setOf("com.game"), emptySet(), always))
    }

    @Test fun whitelistBlocksEverythingNotAllowed() {
        val allowed = setOf("com.notes")
        assertFalse(Policy.isBlocked("com.notes", white, emptySet(), allowed, always))
        assertTrue(Policy.isBlocked("com.game", white, emptySet(), allowed, always))
    }

    @Test fun emptyWhitelistBlocksNothing() {
        assertFalse(Policy.isBlocked("com.game", white, emptySet(), emptySet(), always))
    }

    @Test fun systemAppsAreNeverBlocked() {
        assertFalse(Policy.isBlocked("com.android.launcher", black, setOf("com.android.launcher"), emptySet(), always))
        assertFalse(Policy.isBlocked("com.focusfarm.shield", white, emptySet(), setOf("x"), always))
    }

    @Test fun snoozeLastsFiveMinutes() {
        Snooze.clear()
        Snooze.set("com.game", now = 1000)
        assertTrue(Snooze.active("com.game", now = 1000 + Snooze.DURATION_MS - 1))
        assertFalse(Snooze.active("com.game", now = 1000 + Snooze.DURATION_MS))
        assertFalse(Snooze.active("com.other", now = 1000))
    }
}
