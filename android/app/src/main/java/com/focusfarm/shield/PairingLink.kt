package com.focusfarm.shield

import java.net.URLDecoder

/**
 * Ссылка из QR-кода на ПК: focusfarm://pair?h=192.168.1.5&p=8766&s=секрет
 * Принимаем только адреса домашней сети: чужой QR не должен отправить секрет в интернет.
 */
data class PairingLink(val host: String, val port: Int, val secret: String) {
    companion object {
        private const val PREFIX = "focusfarm://pair?"

        fun parse(text: String?): PairingLink? {
            val t = text?.trim() ?: return null
            if (!t.startsWith(PREFIX)) return null
            val params = t.removePrefix(PREFIX).split("&").mapNotNull { part ->
                val i = part.indexOf('=')
                if (i <= 0) null else part.substring(0, i) to URLDecoder.decode(part.substring(i + 1), "UTF-8")
            }.toMap()
            val host = params["h"] ?: return null
            val port = params["p"]?.toIntOrNull() ?: return null
            val secret = params["s"]?.takeIf { it.isNotBlank() && it.length <= 100 } ?: return null
            if (port !in 1..65535 || !isPrivateIpv4(host)) return null
            return PairingLink(host, port, secret)
        }

        /** 10.x.x.x, 172.16–31.x.x, 192.168.x.x и 127.x.x.x. */
        fun isPrivateIpv4(host: String): Boolean {
            val parts = host.split(".")
            if (parts.size != 4) return false
            val n = parts.map { it.toIntOrNull() ?: return false }
            if (n.any { it !in 0..255 }) return false
            return n[0] == 10 || n[0] == 127 || (n[0] == 172 && n[1] in 16..31) || (n[0] == 192 && n[1] == 168)
        }
    }
}
