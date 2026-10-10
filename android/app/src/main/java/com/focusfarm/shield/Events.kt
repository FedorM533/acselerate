package com.focusfarm.shield

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Очередь событий для ПК. Хранится на телефоне, пока нет связи, и уходит отчётом при подключении.
 * Пишем только вид события и название пакета приложения (kind: blocked, opened, service_off, service_on).
 */
object Events {
    private const val KEY = "events"
    private const val LIMIT = 500

    @Synchronized
    fun add(context: Context, kind: String, app: String = "") {
        val sp = prefs(context)
        val list = load(sp.getString(KEY, null))
        list.put(JSONObject().put("kind", kind).put("app", app).put("ts", System.currentTimeMillis() / 1000))
        sp.edit().putString(KEY, trim(list).toString()).apply()
    }

    /** Первые n событий (сколько отправлять в одном отчёте). */
    @Synchronized
    fun peek(context: Context, n: Int): JSONArray {
        val list = load(prefs(context).getString(KEY, null))
        val out = JSONArray()
        for (i in 0 until minOf(n, list.length())) out.put(list.get(i))
        return out
    }

    @Synchronized
    fun drop(context: Context, n: Int) {
        val sp = prefs(context)
        val list = load(sp.getString(KEY, null))
        val rest = JSONArray()
        for (i in n until list.length()) rest.put(list.get(i))
        sp.edit().putString(KEY, rest.toString()).apply()
    }

    @Synchronized
    fun size(context: Context): Int = load(prefs(context).getString(KEY, null)).length()

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences("shield_events", Context.MODE_PRIVATE)

    private fun load(raw: String?): JSONArray = try {
        if (raw.isNullOrEmpty()) JSONArray() else JSONArray(raw)
    } catch (_: Exception) {
        JSONArray()
    }

    private fun trim(list: JSONArray): JSONArray {
        if (list.length() <= LIMIT) return list
        val out = JSONArray()
        for (i in list.length() - LIMIT until list.length()) out.put(list.get(i))
        return out
    }
}
