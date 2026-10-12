package com.focusfarm.shield

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Постоянная связь с ПК (docs/PHONE_PROTOCOL.md): получаем состояние учёбы, шлём heartbeat и отчёты.
 * Блокировка работает и без связи (FocusAccessibilityService), служба нужна только для синхронизации.
 */
class LinkService : Service() {
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS)
        .build()
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var prefs: Prefs
    private var ws: WebSocket? = null
    private var running = false
    private var backoffS = 2
    private var sentEvents = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, notification())
        if (!prefs.paired) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (!running) {
            running = true
            connect()
            handler.postDelayed(tick, HEARTBEAT_MS)
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        handler.removeCallbacksAndMessages(null)
        ws?.cancel()
        ws = null
        LinkStatus.state = LinkStatus.OFF
        LinkStatus.detail = ""
        super.onDestroy()
    }

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            if (LinkStatus.state == LinkStatus.ONLINE) {
                ws?.send("""{"type":"heartbeat"}""")
                flushEvents()
            }
            handler.postDelayed(this, HEARTBEAT_MS)
        }
    }

    private fun connect() {
        if (!running) return
        val host = prefs.host
        if (host == null || prefs.token == null) {
            stopSelf()
            return
        }
        LinkStatus.state = LinkStatus.CONNECTING
        val request = Request.Builder().url("ws://$host:${prefs.port}/phone").build()
        ws = client.newWebSocket(request, Listener())
    }

    private fun reconnectLater(reason: String) {
        LinkStatus.state = LinkStatus.OFF
        LinkStatus.detail = reason
        if (!running) return
        handler.postDelayed({ connect() }, backoffS * 1000L)
        backoffS = minOf(backoffS * 2, 60)
    }

    private fun flushEvents() {
        if (sentEvents > 0) return                       // ждём подтверждения прошлого отчёта
        val events = Events.peek(this, 100)
        if (events.length() == 0) return
        sentEvents = events.length()
        ws?.send(JSONObject().put("type", "report").put("events", events).toString())
    }

    private inner class Listener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            sentEvents = 0                                   // прошлый отчёт мог не дойти: отправим заново
            webSocket.send(JSONObject().put("type", "hello").put("token", prefs.token).toString())
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            handler.post { if (webSocket === ws) handle(JSONObject(text)) }
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            handler.post { if (webSocket === ws) reconnectLater("") }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            handler.post { if (webSocket === ws) reconnectLater(t.message?.take(60) ?: "ошибка сети") }
        }
    }

    private fun handle(msg: JSONObject) {
        when (msg.optString("type")) {
            "hello_ok" -> {
                LinkStatus.state = LinkStatus.ONLINE
                LinkStatus.detail = ""
                backoffS = 2
                flushEvents()
            }
            "state" -> {
                val now = System.currentTimeMillis()
                prefs.applyRemote(
                    active = msg.optBoolean("active"),
                    hard = msg.optBoolean("hard"),
                    mode = msg.optString("list_mode", ShieldState.MODE_BLACKLIST),
                    remainingS = msg.optLong("remaining_s"),
                    now = now,
                )
                val breakLeft = msg.optLong("break_left_s")      // перерыв Pomodoro: блокировки нет, показываем отдых
                prefs.breakUntil = if (breakLeft > 0) now + breakLeft * 1000 else 0
            }
            "report_ok" -> {
                Events.drop(this, sentEvents)
                sentEvents = 0
                flushEvents()
            }
            "revoked" -> {                               // телефон удалили на ПК
                prefs.unpair()
                prefs.remoteUntil = 0
                stopSelf()
            }
            "error" -> {
                if (msg.optString("reason") == "bad_token") {
                    prefs.unpair()
                    stopSelf()
                }
            }
        }
    }

    private fun notification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Связь с компьютером", NotificationManager.IMPORTANCE_LOW)
        )
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL) else Notification.Builder(this)
        return builder
            .setSmallIcon(R.drawable.ic_fish)
            .setContentTitle("Carpo")
            .setContentText("Связь с компьютером")
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CHANNEL = "link"
        private const val NOTIFICATION_ID = 1
        private const val HEARTBEAT_MS = 15_000L

        fun start(context: Context) {
            val intent = Intent(context, LinkService::class.java)
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent) else context.startService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, LinkService::class.java))
        }
    }
}
