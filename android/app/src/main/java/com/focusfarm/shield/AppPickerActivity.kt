package com.focusfarm.shield

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.widget.EditText
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.TextView

/** Выбор приложений для чёрного или белого списка (extra "mode"). Сохраняется сразу при нажатии. */
class AppPickerActivity : Activity() {
    private data class App(val pkg: String, val label: String)

    private lateinit var prefs: Prefs
    private lateinit var mode: String
    private var allApps: List<App> = emptyList()
    private var apps: List<App> = emptyList()
    private val chosen = HashSet<String>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        mode = intent.getStringExtra(EXTRA_MODE) ?: ShieldState.MODE_BLACKLIST
        val white = mode == ShieldState.MODE_WHITELIST
        chosen += if (white) prefs.allowed else prefs.blocked

        allApps = installedApps()
        apps = allApps
        val list = ListView(this).apply { divider = null }
        val header = text(
            if (white) "Белый список: отметьте то, что можно во время учёбы. Остальное будет закрываться."
            else "Чёрный список: отметьте то, что закрывать во время учёбы.",
            15f, color = MUTED,
        ).apply { setPadding(dp(16), dp(16), dp(16), dp(8)) }
        list.addHeaderView(header, null, false)
        val adapter = Adapter()
        list.adapter = adapter
        val search = EditText(this).apply {
            hint = "Поиск приложения"
            setSingleLine()
            setPadding(dp(16), dp(12), dp(16), dp(12))
            addTextChangedListener(object : TextWatcher {
                override fun afterTextChanged(s: Editable?) {
                    val q = s?.toString().orEmpty().trim().lowercase()
                    apps = if (q.isEmpty()) allApps
                    else allApps.filter { it.label.lowercase().contains(q) || it.pkg.lowercase().contains(q) }
                    adapter.notifyDataSetChanged()
                }
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            })
        }
        setContentView(LinearLayout(this).apply {
            padForSystemBars()
            orientation = LinearLayout.VERTICAL
            addView(search, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { setMargins(dp(8), dp(4), dp(8), 0) })
            addView(list, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        })
        title = if (white) "Разрешённые приложения" else "Запрещённые приложения"
    }

    private fun installedApps(): List<App> {
        val pm = packageManager
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return pm.queryIntentActivities(intent, PackageManager.MATCH_ALL)
            .map { App(it.activityInfo.packageName, it.loadLabel(pm).toString()) }
            .filter { it.pkg != packageName }
            .distinctBy { it.pkg }
            .sortedBy { it.label.lowercase() }
    }

    private fun save() {
        if (mode == ShieldState.MODE_WHITELIST) prefs.allowed = chosen else prefs.blocked = chosen
    }

    private inner class Adapter : BaseAdapter() {
        override fun getCount() = apps.size
        override fun getItem(position: Int) = apps[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: android.view.View?, parent: ViewGroup?): android.view.View {
            val app = apps[position]
            val row = LinearLayout(this@AppPickerActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(dp(16), dp(10), dp(16), dp(10))
            }
            val box = CheckBox(this@AppPickerActivity).apply {
                isChecked = app.pkg in chosen
                isClickable = false
                isFocusable = false
            }
            val label = TextView(this@AppPickerActivity).apply {
                text = app.label
                textSize = 16f
                setTextColor(INK)
            }
            row.addView(box)
            row.addView(label, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginStart = dp(8) })
            row.setOnClickListener {
                if (app.pkg in chosen) chosen.remove(app.pkg) else chosen.add(app.pkg)
                box.isChecked = app.pkg in chosen
                save()
            }
            return row
        }
    }

    companion object {
        const val EXTRA_MODE = "mode"
    }
}
