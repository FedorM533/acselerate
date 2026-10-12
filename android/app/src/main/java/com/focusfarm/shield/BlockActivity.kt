package com.focusfarm.shield

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView

/** Экран «Идёт учёба» поверх запрещённого приложения. */
class BlockActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var prefs: Prefs
    private lateinit var timeView: TextView
    private var pkg = ""
    private var hard = false
    private var count = 1
    private var openAfterMs = 0L           // до этого момента «всё равно открыть» нажать нельзя
    private lateinit var openButton: android.widget.Button
    private lateinit var attemptView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        readIntent(intent)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(0xFF2A7F9E.toInt())
            setPadding(dp(24), dp(24), dp(24), dp(24))
        }
        root.addView(text("🐟", 64f))
        root.addView(text("Идёт учёба", 28f, bold = true, color = Color.WHITE))
        root.addView(text("${appLabel()} сейчас отвлекает.\nВернись к делу: рыбка ждёт.", 17f, color = Color.WHITE).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(12), 0, dp(12))
        })
        timeView = text("", 22f, bold = true, color = Color.WHITE)
        root.addView(timeView)
        root.addView(button("Вернуться к учёбе") { goHome() }.apply { setPadding(dp(24), dp(12), dp(24), dp(12)) },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
                .apply { topMargin = dp(24) })
        attemptView = text("", 15f, color = Color.WHITE).apply { gravity = Gravity.CENTER; setPadding(0, dp(16), 0, 0) }
        openButton = button("") {
            Snooze.set(pkg)
            packageManager.getLaunchIntentForPackage(pkg)?.let { startActivity(it) }
            finish()
        }.apply { alpha = 0.8f }
        if (!hard) {         // мягкий режим: можно открыть «всё равно», но не сразу и не навсегда
            root.addView(attemptView)
            root.addView(openButton,
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
                    .apply { topMargin = dp(12) })
        }
        updateOpenButton()
        root.padForSystemBars()
        setContentView(root)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        readIntent(intent)
    }

    private fun readIntent(intent: Intent) {
        pkg = intent.getStringExtra(EXTRA_PKG).orEmpty()
        hard = intent.getBooleanExtra(EXTRA_HARD, false)
        count = intent.getIntExtra(EXTRA_COUNT, 1)
        openAfterMs = android.os.SystemClock.elapsedRealtime() + Escalation.delaySeconds(count) * 1000L
        updateOpenButton()
    }

    /** Кнопка «всё равно открыть» оживает, когда прошла пауза на чтение сообщения. */
    private fun updateOpenButton() {
        if (hard || !::openButton.isInitialized) return
        val leftS = ((openAfterMs - android.os.SystemClock.elapsedRealtime() + 999) / 1000).toInt()
        attemptView.text = if (count > 1) "Это уже заход №$count подряд. Каждый следующий ждать дольше."
            else "Подумай: оно того стоит?"
        openButton.isEnabled = leftS <= 0
        openButton.text = if (leftS > 0) "Подожди ещё $leftS с…" else "Всё равно открыть на 5 минут"
    }

    private fun appLabel(): String = runCatching {
        packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, 0)).toString()
    }.getOrDefault("Это приложение")

    override fun onStart() {
        super.onStart()
        visible = true
        handler.post(object : Runnable {
            override fun run() {
                val state = prefs.shieldState()
                val now = System.currentTimeMillis()
                if (!state.active(now)) {      // учёба закончилась: экран больше не нужен
                    finish()
                    return
                }
                timeView.text = "Осталось ${formatTime(state.remainingMs(now))}"
                updateOpenButton()
                handler.postDelayed(this, 1000)
            }
        })
    }

    override fun onStop() {
        visible = false
        handler.removeCallbacksAndMessages(null)
        super.onStop()
    }

    @Deprecated("Назад ведёт на главный экран, а не обратно в запрещённое приложение")
    override fun onBackPressed() = goHome()

    private fun goHome() {
        startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        finish()
    }

    companion object {
        const val EXTRA_PKG = "pkg"
        const val EXTRA_HARD = "hard"
        const val EXTRA_COUNT = "count"

        @Volatile var visible = false
    }
}
