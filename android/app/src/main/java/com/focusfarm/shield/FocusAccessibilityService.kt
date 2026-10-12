package com.focusfarm.shield

import android.accessibilityservice.AccessibilityService
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent

/**
 * Замечает, какое приложение вышло на экран, и во время учёбы закрывает запрещённое экраном
 * «Идёт учёба». Содержимое экрана не читается: только название пакета.
 */
class FocusAccessibilityService : AccessibilityService() {
    private lateinit var prefs: Prefs
    private var lastPkg = ""
    private var lastAt = 0L

    override fun onServiceConnected() {
        super.onServiceConnected()
        prefs = Prefs(this)
        Events.add(this, "service_on")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null || event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return
        val pkg = event.packageName?.toString() ?: return
        val now = System.currentTimeMillis()
        val state = prefs.shieldState()
        if (!state.active(now)) return
        val blocked = Policy.isBlocked(
            pkg, state.mode(now), prefs.blocked, prefs.allowed, SystemApps.get(this),
        )
        if (!blocked || Snooze.active(pkg, now)) return
        // Одно и то же окно сообщает о себе несколько раз подряд: не мигаем экраном.
        if (BlockActivity.visible || (pkg == lastPkg && now - lastAt < 1500)) return
        lastPkg = pkg
        lastAt = now
        Events.add(this, "blocked", pkg)
        val count = Escalation.nextCount(prefs.escCount, prefs.escLast, now)
        prefs.escCount = count
        prefs.escLast = now
        startActivity(
            Intent(this, BlockActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .putExtra(BlockActivity.EXTRA_PKG, pkg)
                .putExtra(BlockActivity.EXTRA_HARD, state.hard(now))
                .putExtra(BlockActivity.EXTRA_COUNT, count)
        )
    }

    override fun onInterrupt() {}

    override fun onUnbind(intent: Intent?): Boolean {
        Events.add(this, "service_off")      // службу выключили: расскажем ПК при следующей связи
        // Если учёба идёт, не даём выключить блокировку молча: громкое уведомление с переходом в настройки.
        if (Prefs(this).shieldState().active(System.currentTimeMillis())) warnServiceOff()
        return super.onUnbind(intent)
    }

    private fun warnServiceOff() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(ALERT_CHANNEL, "Блокировка выключена", NotificationManager.IMPORTANCE_HIGH)
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        manager.notify(
            ALERT_ID,
            Notification.Builder(this, ALERT_CHANNEL)
                .setSmallIcon(R.drawable.ic_fish)
                .setContentTitle("Блокировка выключена во время учёбы")
                .setContentText("Нажмите, чтобы снова включить службу «Carpo».")
                .setContentIntent(open)
                .setAutoCancel(true)
                .build()
        )
    }

    private companion object {
        const val ALERT_CHANNEL = "alert"
        const val ALERT_ID = 2
    }
}
