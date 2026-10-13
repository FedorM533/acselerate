package com.focusfarm.shield

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator

/**
 * Проигрывает звуки-«возвращалки» (см. [Nudge]). Звук идёт как «уведомление»: если на телефоне
 * включён беззвучный режим, он молчит и остаётся только вибрация. Начиная со 2-го уровня телефон ещё и вибрирует.
 */
object NudgePlayer {
    private val main = Handler(Looper.getMainLooper())

    fun play(context: Context, level: Int, volume: Float) {
        runCatching {
            val pcm = Nudge.render(level, volume)
            val track = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_NOTIFICATION_EVENT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(Nudge.RATE)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build()
                )
                .setBufferSizeInBytes(pcm.size * 2)
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build()
            track.write(pcm, 0, pcm.size)
            track.play()
            // Освобождаем плеер, когда звук доиграл.
            main.postDelayed({ runCatching { track.release() } }, pcm.size * 1000L / Nudge.RATE + 300)
        }
        if (level >= 2) vibrate(context, level)
    }

    @Suppress("DEPRECATION")
    private fun vibrate(context: Context, level: Int) {
        val vibrator = context.getSystemService(Vibrator::class.java) ?: return
        if (!vibrator.hasVibrator()) return
        val pattern = if (level >= 4) longArrayOf(0, 300, 120, 300, 120, 300) else longArrayOf(0, 200, 120, 200)
        runCatching { vibrator.vibrate(VibrationEffect.createWaveform(pattern, -1)) }
    }
}
