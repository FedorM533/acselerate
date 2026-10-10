package com.focusfarm.shield

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PairingLinkTest {
    @Test fun parsesLinkFromPc() {
        val link = PairingLink.parse("focusfarm://pair?h=192.168.33.227&p=8766&s=abc_DEF-123")
        assertNotNull(link)
        assertEquals("192.168.33.227", link!!.host)
        assertEquals(8766, link.port)
        assertEquals("abc_DEF-123", link.secret)
    }

    @Test fun trimsSpaces() {
        assertNotNull(PairingLink.parse("  focusfarm://pair?h=10.0.0.5&p=9000&s=x \n"))
    }

    @Test fun rejectsBrokenLinks() {
        for (bad in listOf(
            null, "", "https://pair?h=10.0.0.5&p=1&s=x", "focusfarm://pair?h=10.0.0.5&p=abc&s=x",
            "focusfarm://pair?h=10.0.0.5&p=0&s=x", "focusfarm://pair?h=10.0.0.5&p=70000&s=x",
            "focusfarm://pair?h=10.0.0.5&p=8766", "focusfarm://pair?h=10.0.0.5&p=8766&s=",
        )) assertNull("должно быть отвергнуто: $bad", PairingLink.parse(bad))
    }

    @Test fun rejectsAddressesOutsideHomeNetwork() {
        assertNull(PairingLink.parse("focusfarm://pair?h=8.8.8.8&p=8766&s=x"))
        assertNull(PairingLink.parse("focusfarm://pair?h=evil.example.com&p=8766&s=x"))
        assertNull(PairingLink.parse("focusfarm://pair?h=172.32.0.1&p=8766&s=x"))
    }

    @Test fun privateRanges() {
        for (ok in listOf("10.1.2.3", "192.168.0.1", "172.16.0.1", "172.31.255.255", "127.0.0.1")) assertTrue(ok, PairingLink.isPrivateIpv4(ok))
        for (bad in listOf("172.15.0.1", "11.0.0.1", "192.169.0.1", "1.2.3", "300.1.1.1", "a.b.c.d")) assertFalse(bad, PairingLink.isPrivateIpv4(bad))
    }
}
