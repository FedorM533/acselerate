package com.focusfarm.shield

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Обмен секрета из QR-кода на токен: POST /pair (см. docs/PHONE_PROTOCOL.md). Вызывать не из главного потока. */
object PairingClient {
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
