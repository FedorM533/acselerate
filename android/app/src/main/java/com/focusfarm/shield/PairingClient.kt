package com.focusfarm.shield

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Компьютер, откликнувшийся на поиск в сети. */
data class FoundPc(val name: String, val host: String, val port: Int)

/** Обмен секрета из QR-кода на токен: POST /pair (см. docs/PHONE_PROTOCOL.md). Вызывать не из главного потока. */
object PairingClient {
    private const val DISCOVERY_PORT = 48766
    private const val DISCOVERY_QUERY = "FOCUSFARM_DISCOVER"

    /**
     * Ищет ПК в домашней сети: широковещательный запрос по UDP, отвечает только компьютер с открытым сопряжением.
     * Берём лишь ответы с частным адресом. Вызывать не из главного потока.
     */
    fun discover(timeoutMs: Int = 3000): List<FoundPc> {
        val found = LinkedHashMap<String, FoundPc>()
        runCatching {
            java.net.DatagramSocket().use { socket ->
                socket.broadcast = true
                socket.soTimeout = 500
                val data = DISCOVERY_QUERY.toByteArray()
                val targets = HashSet<java.net.InetAddress>()
                targets += java.net.InetAddress.getByName("255.255.255.255")
                java.net.NetworkInterface.getNetworkInterfaces()?.toList().orEmpty()
                    .filter { it.isUp && !it.isLoopback }
                    .flatMap { it.interfaceAddresses }
                    .mapNotNullTo(targets) { it.broadcast }
                val end = System.currentTimeMillis() + timeoutMs
                var lastSend = 0L
                val buffer = ByteArray(512)
                while (System.currentTimeMillis() < end) {
                    if (System.currentTimeMillis() - lastSend > 1000) {      // UDP теряется: повторяем раз в секунду
                        targets.forEach { runCatching { socket.send(java.net.DatagramPacket(data, data.size, it, DISCOVERY_PORT)) } }
                        lastSend = System.currentTimeMillis()
                    }
                    val packet = java.net.DatagramPacket(buffer, buffer.size)
                    try { socket.receive(packet) } catch (_: java.net.SocketTimeoutException) { continue }
                    runCatching {
                        val json = JSONObject(String(packet.data, 0, packet.length))
                        val host = json.getString("host")
                        val port = json.getInt("port")
                        // Адрес в ответе должен совпадать с тем, откуда он пришёл: чужой ПК не подсунет другой адрес.
                        if (host == packet.address.hostAddress && PairingLink.isPrivateIpv4(host) && port in 1..65535) {
                            found[host] = FoundPc(json.optString("name", "Компьютер").take(40), host, port)
                        }
                    }
                }
            }
        }
        return found.values.toList()
    }

    fun pair(link: PairingLink, deviceName: String): Result<String> = runCatching {
        val conn = URL("http://${link.host}:${link.port}/pair").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 5000
            conn.readTimeout = 8000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            val body = JSONObject().put("secret", link.secret).put("name", deviceName).toString()
            conn.outputStream.use { it.write(body.toByteArray()) }
            val code = conn.responseCode
            val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val detail = runCatching { JSONObject(text).optString("detail") }.getOrDefault("")
                error(detail.ifEmpty { "ПК ответил кодом $code" })
            }
            JSONObject(text).getString("token")
        } finally {
            conn.disconnect()
        }
    }.recoverCatching { e ->
        throw Exception(e.message ?: "Не удалось связаться с ПК. Проверьте, что телефон и ПК в одной сети Wi-Fi.")
    }
}
