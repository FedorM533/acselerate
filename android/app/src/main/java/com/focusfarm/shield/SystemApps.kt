package com.focusfarm.shield

import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.view.inputmethod.InputMethodManager

/**
 * Что нельзя блокировать никогда: без этого телефон станет непригодным.
 * Главный экран, звонилка, СМС по умолчанию, клавиатуры, системный интерфейс, настройки.
 */
object SystemApps {
    private val FIXED = setOf(
        "android", "com.android.systemui", "com.android.settings",
        "com.google.android.permissioncontroller", "com.android.permissioncontroller",
        "com.google.android.packageinstaller", "com.android.packageinstaller",
        "com.android.emergency", "com.google.android.gms",
    )

    @Volatile private var cache: Set<String> = emptySet()
    @Volatile private var cachedAt = 0L

    fun get(context: Context): Set<String> {
        val now = System.currentTimeMillis()
        if (cache.isEmpty() || now - cachedAt > 60_000) {
            cache = compute(context)
            cachedAt = now
        }
        return cache
    }

    private fun compute(context: Context): Set<String> {
        val pm = context.packageManager
        val result = HashSet(FIXED)
        result += context.packageName
        runCatching {
            pm.queryIntentActivities(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME), 0)
                .forEach { result += it.activityInfo.packageName }
        }
        runCatching {
            pm.queryIntentActivities(Intent(Intent.ACTION_DIAL), 0)
                .forEach { result += it.activityInfo.packageName }
        }
        runCatching { Telephony.Sms.getDefaultSmsPackage(context)?.let { result += it } }
        runCatching {
            (context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
                .enabledInputMethodList.forEach { result += it.packageName }
        }
        return result
    }
}
