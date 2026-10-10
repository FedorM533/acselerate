package com.focusfarm.shield

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning

/** Главный экран: состояние, сопряжение с ПК, режим списков и учёба на самом телефоне. */
class MainActivity : Activity() {
    private lateinit var prefs: Prefs
    private val handler = Handler(Looper.getMainLooper())

    private lateinit var serviceView: TextView
    private lateinit var serviceButton: android.widget.Button
    private lateinit var linkView: TextView
    private lateinit var shieldView: TextView
    private lateinit var pairView: TextView
    private lateinit var scanButton: android.widget.Button
    private lateinit var pasteButton: android.widget.Button
    private lateinit var unpairButton: android.widget.Button
    private lateinit var countView: TextView
    private lateinit var minutes: EditText
    private lateinit var startButton: android.widget.Button
    private lateinit var stopButton: android.widget.Button
    private lateinit var hardSwitch: Switch

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        buildUi()
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        if (prefs.paired) LinkService.start(this)
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        handler.post(object : Runnable {
            override fun run() {
                refresh()
                handler.postDelayed(this, 1000)
            }
        })
    }

    override fun onPause() {
        handler.removeCallbacksAndMessages(null)
        super.onPause()
    }

    // ---------- интерфейс ----------

    private fun buildUi() {
        val column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(text("🐟 Фокус-пруд Щит", 24f, bold = true).apply { setPadding(dp(16), dp(20), dp(16), dp(4)) })

        serviceView = text("", 16f)
        serviceButton = button("Включить службу блокировки") { openAccessibility() }
        linkView = text("", 15f, color = MUTED)
        shieldView = text("", 17f, bold = true)
        column.addView(card(text("Состояние", 14f, color = MUTED), serviceView, serviceButton, linkView, shieldView))

        pairView = text("", 15f)
        scanButton = button("Сканировать QR с компьютера") { scanQr() }
        pasteButton = button("Вставить ссылку вручную") { askLink() }
        unpairButton = button("Отключить от компьютера") { unpair() }
        column.addView(card(text("Компьютер", 14f, color = MUTED), pairView, scanButton, pasteButton, unpairButton))

        val group = RadioGroup(this).apply { orientation = RadioGroup.VERTICAL }
        val black = RadioButton(this).apply { text = "Чёрный список: нельзя только выбранное"; id = 1 }
        val white = RadioButton(this).apply { text = "Белый список: можно только выбранное"; id = 2 }
        group.addView(black)
        group.addView(white)
        group.check(if (prefs.listMode == ShieldState.MODE_WHITELIST) 2 else 1)
        group.setOnCheckedChangeListener { g, id ->
            if (refuseWhileLocked()) {
                g.setOnCheckedChangeListener(null)
                g.check(if (prefs.listMode == ShieldState.MODE_WHITELIST) 2 else 1)
                return@setOnCheckedChangeListener
            }
            prefs.listMode = if (id == 2) ShieldState.MODE_WHITELIST else ShieldState.MODE_BLACKLIST
            refresh()
        }
        countView = text("", 14f, color = MUTED)
        hardSwitch = Switch(this).apply {
            text = "Жёсткий режим (без кнопки «всё равно открыть»)"
            isChecked = prefs.hard
            setOnCheckedChangeListener { button, checked ->
                if (!checked && refuseWhileLocked()) button.isChecked = true else prefs.hard = checked
            }
        }
        column.addView(card(
            text("Что блокировать", 14f, color = MUTED), group,
            button("Выбрать приложения…") {
                if (refuseWhileLocked()) return@button
                startActivity(Intent(this, AppPickerActivity::class.java).putExtra(AppPickerActivity.EXTRA_MODE, prefs.listMode))
            },
            countView, hardSwitch,
            text("Телефон, сообщения, клавиатура, настройки и главный экран разрешены всегда.", 13f, color = MUTED),
        ))

        minutes = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            setText("25")
            hint = "минут"
        }
        startButton = button("Начать учёбу на телефоне") { startLocal() }
        stopButton = button("Закончить учёбу") { stopLocal() }
        column.addView(card(
            text("Учёба без компьютера", 14f, color = MUTED), minutes, startButton, stopButton,
            text("Когда учёбу запускает компьютер, телефон защищается сам.", 13f, color = MUTED),
        ))

        setContentView(ScrollView(this).apply { addView(column); padForSystemBars() })
    }

    private fun refresh() {
        val now = System.currentTimeMillis()
        val enabled = isServiceEnabled()
        serviceView.text = if (enabled) "✅ Служба блокировки включена" else "⚠ Служба блокировки выключена: блокировка не работает"
        serviceButton.visibility = if (enabled) android.view.View.GONE else android.view.View.VISIBLE

        linkView.text = if (prefs.paired) "Связь с компьютером: ${LinkStatus.label()}" else "Компьютер не подключён (блокировка работает и без него)"
        val state = prefs.shieldState()
        shieldView.text = if (state.active(now)) {
            val who = if (state.remoteActive(now)) "по команде компьютера" else "на телефоне"
            "🔒 Идёт учёба $who, осталось ${formatTime(state.remainingMs(now))}"
        } else "Сейчас учёбы нет"

        pairView.text = if (prefs.paired) "Подключён: ${prefs.host}:${prefs.port}" else "Не подключён"
        val paired = prefs.paired
        scanButton.visibility = if (paired) android.view.View.GONE else android.view.View.VISIBLE
        pasteButton.visibility = scanButton.visibility
        unpairButton.visibility = if (paired) android.view.View.VISIBLE else android.view.View.GONE

        val white = prefs.listMode == ShieldState.MODE_WHITELIST
        val n = if (white) prefs.allowed.size else prefs.blocked.size
        countView.text = (if (white) "Разрешено приложений: $n" else "Запрещено приложений: $n") +
            if (white && n == 0) ". Пока список пуст, ничего не блокируется." else ""
        val localOn = state.localActive(now)
        startButton.visibility = if (localOn) android.view.View.GONE else android.view.View.VISIBLE
        stopButton.visibility = if (localOn) android.view.View.VISIBLE else android.view.View.GONE
    }

    // ---------- действия ----------

    private fun isServiceEnabled(): Boolean {
        val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()
        return enabled.split(':').any { it.startsWith("$packageName/") && it.endsWith("FocusAccessibilityService") }
    }

    private fun openAccessibility() {
        Toast.makeText(
            this,
            "Найдите «Фокус-пруд Щит» и включите. Если пункт серый: Настройки → Приложения → Фокус-пруд Щит → ⋮ → «Разрешить ограниченные настройки».",
            Toast.LENGTH_LONG,
        ).show()
        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }

    private fun scanQr() {
        val options = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
        GmsBarcodeScanning.getClient(this, options).startScan()
            .addOnSuccessListener { barcode -> handlePairingText(barcode.rawValue) }
            .addOnFailureListener {
                Toast.makeText(this, "Сканер недоступен. Вставьте ссылку вручную.", Toast.LENGTH_LONG).show()
            }
    }

    private fun askLink() {
        val input = EditText(this).apply { hint = "focusfarm://pair?h=…" }
        android.app.AlertDialog.Builder(this)
            .setTitle("Ссылка из окна «Настройки» на ПК")
            .setView(input)
            .setPositiveButton("Подключить") { _, _ -> handlePairingText(input.text.toString()) }
            .setNegativeButton("Отмена", null)
            .show()
    }

    /** Ссылку из браузера или чужого приложения принимаем только после подтверждения: иначе ПК можно подменить. */
    private fun handleIntent(intent: Intent?) {
        val data: Uri = intent?.data ?: return
        intent.data = null
        val link = PairingLink.parse(data.toString())
        if (link == null || refuseWhileLocked()) {
            Toast.makeText(this, "Ссылка сопряжения отклонена", Toast.LENGTH_LONG).show()
            return
        }
        android.app.AlertDialog.Builder(this)
            .setTitle("Подключить к компьютеру?")
            .setMessage("Адрес: ${link.host}:${link.port}\nПодключайтесь только к своему компьютеру.")
            .setPositiveButton("Подключить") { _, _ -> handlePairingText(data.toString()) }
            .setNegativeButton("Отмена", null)
            .show()
    }

    private fun handlePairingText(text: String?) {
        val link = PairingLink.parse(text)
        if (link == null) {
            Toast.makeText(this, "Это не код сопряжения Фокус-пруда или адрес не из домашней сети", Toast.LENGTH_LONG).show()
            return
        }
        if (link.host.startsWith("127.")) {      // «компьютер» на самом телефоне — это подмена, а не ПК
            Toast.makeText(this, "Адрес компьютера не может быть этим телефоном", Toast.LENGTH_LONG).show()
            return
        }
        Toast.makeText(this, "Подключаюсь к ${link.host}…", Toast.LENGTH_SHORT).show()
        Thread {
            val result = PairingClient.pair(link, Build.MODEL ?: "Телефон")
            runOnUiThread {
                result.onSuccess { token ->
                    prefs.pair(link.host, link.port, token)
                    LinkService.start(this)
                    Toast.makeText(this, "Телефон подключён ✔", Toast.LENGTH_LONG).show()
                }.onFailure { Toast.makeText(this, it.message, Toast.LENGTH_LONG).show() }
                refresh()
            }
        }.start()
    }

    /** Во время жёсткой учёбы защиту не снять: ни отключением от ПК, ни сменой списков, ни выключением режима. */
    private fun lockedNow(): Boolean {
        val now = System.currentTimeMillis()
        return prefs.shieldState().let { it.active(now) && it.hard(now) }
    }

    private fun refuseWhileLocked(): Boolean {
        if (!lockedNow()) return false
        Toast.makeText(this, "Идёт жёсткая учёба: это можно менять после её конца", Toast.LENGTH_LONG).show()
        return true
    }

    private fun unpair() {
        if (refuseWhileLocked()) return
        LinkService.stop(this)
        prefs.unpair()
        Toast.makeText(this, "Отключено. Удалите телефон и в списке на компьютере.", Toast.LENGTH_LONG).show()
        refresh()
    }

    private fun startLocal() {
        val m = minutes.text.toString().toLongOrNull()
        if (m == null || m !in 1..600) {
            Toast.makeText(this, "Введите минуты от 1 до 600", Toast.LENGTH_SHORT).show()
            return
        }
        if (!isServiceEnabled()) openAccessibility()
        prefs.localUntil = System.currentTimeMillis() + m * 60_000
        Snooze.clear()
        refresh()
    }

    private fun stopLocal() {
        if (prefs.hard) {
            Toast.makeText(this, "В жёстком режиме учёбу нельзя прервать: дождитесь конца", Toast.LENGTH_LONG).show()
            return
        }
        prefs.localUntil = 0
        refresh()
    }
}
