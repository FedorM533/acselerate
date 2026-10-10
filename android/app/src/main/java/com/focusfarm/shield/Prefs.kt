package com.focusfarm.shield

import android.content.Context

/** Все настройки приложения. Живут только на телефоне. */
class Prefs(context: Context) {
    private val sp = context.applicationContext.getSharedPreferences("shield", Context.MODE_PRIVATE)

    // ---- связь с ПК ----
    var host: String?
        get() = sp.getString("host", null)
        set(v) = sp.edit().putString("host", v).apply()
    var port: Int
        get() = sp.getInt("port", 8766)
        set(v) = sp.edit().putInt("port", v).apply()
    var token: String?
        get() = sp.getString("token", null)
        set(v) = sp.edit().putString("token", v).apply()
    val paired: Boolean get() = !host.isNullOrEmpty() && !token.isNullOrEmpty()

    fun pair(host: String, port: Int, token: String) {
        sp.edit().putString("host", host).putInt("port", port).putString("token", token).apply()
    }

    fun unpair() {
        sp.edit().remove("host").remove("token").putLong("remoteUntil", 0).apply()
    }

    // ---- свои списки и режим ----
    var listMode: String
        get() = sp.getString("listMode", ShieldState.MODE_BLACKLIST) ?: ShieldState.MODE_BLACKLIST
        set(v) = sp.edit().putString("listMode", v).apply()
    var hard: Boolean
        get() = sp.getBoolean("hard", false)
        set(v) = sp.edit().putBoolean("hard", v).apply()
    var blocked: Set<String>
        get() = sp.getStringSet("blocked", emptySet())?.toSet() ?: emptySet()
        set(v) = sp.edit().putStringSet("blocked", HashSet(v)).apply()
    var allowed: Set<String>
        get() = sp.getStringSet("allowed", emptySet())?.toSet() ?: emptySet()
        set(v) = sp.edit().putStringSet("allowed", HashSet(v)).apply()

    // ---- учёба ----
    var remoteUntil: Long
        get() = sp.getLong("remoteUntil", 0)
        set(v) = sp.edit().putLong("remoteUntil", v).apply()
    var remoteMode: String
        get() = sp.getString("remoteMode", ShieldState.MODE_BLACKLIST) ?: ShieldState.MODE_BLACKLIST
        set(v) = sp.edit().putString("remoteMode", v).apply()
    var remoteHard: Boolean
        get() = sp.getBoolean("remoteHard", false)
        set(v) = sp.edit().putBoolean("remoteHard", v).apply()
    var localUntil: Long
        get() = sp.getLong("localUntil", 0)
        set(v) = sp.edit().putLong("localUntil", v).apply()

    fun applyRemote(active: Boolean, hard: Boolean, mode: String, remainingS: Long, now: Long) {
        sp.edit()
            .putLong("remoteUntil", if (active) now + remainingS * 1000 + 1500 else 0)
            .putBoolean("remoteHard", hard)
            .putString("remoteMode", if (mode == ShieldState.MODE_WHITELIST) mode else ShieldState.MODE_BLACKLIST)
            .apply()
    }

    fun shieldState() = ShieldState(
        remoteUntil = remoteUntil, remoteMode = remoteMode, remoteHard = remoteHard,
        localUntil = localUntil, localMode = listMode, localHard = hard,
    )
}
