package com.focusfarm.shield

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** После перезагрузки телефона или обновления приложения восстанавливаем связь с ПК. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (Prefs(context).paired) {
            runCatching { LinkService.start(context) }
        }
    }
}
