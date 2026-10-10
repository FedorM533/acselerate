package com.focusfarm.shield

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Небольшие помощники, чтобы собирать экраны кодом без XML-разметки. */
const val INK = 0xFF1F2A44.toInt()
const val MUTED = 0xFF5A6B80.toInt()
const val ACCENT = 0xFF2A7F9E.toInt()

fun Context.dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

fun Context.text(text: String, size: Float = 16f, bold: Boolean = false, color: Int = INK): TextView =
    TextView(this).apply {
        this.text = text
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

fun Context.button(text: String, onClick: () -> Unit): Button = Button(this).apply {
    this.text = text
    isAllCaps = false
    setTextColor(Color.WHITE)
    background = GradientDrawable().apply {
        setColor(ACCENT)
        cornerRadius = dp(12).toFloat()
    }
    setPadding(dp(16), dp(10), dp(16), dp(10))
    setOnClickListener { onClick() }
}

fun Context.card(vararg children: View): LinearLayout = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    setPadding(dp(16), dp(14), dp(16), dp(14))
    background = GradientDrawable().apply {
        setColor(Color.WHITE)
        cornerRadius = dp(16).toFloat()
    }
    layoutParams = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
    ).apply { setMargins(dp(16), dp(8), dp(16), dp(4)) }
    children.forEach { addView(it, LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
    ).apply { topMargin = dp(6) }) }
}

fun formatTime(ms: Long): String {
    val s = ms / 1000
    return "%d:%02d".format(s / 60, s % 60)
}

/** На Android 15 экран рисуется под строкой состояния и жестовой панелью: отступаем от них. */
@Suppress("DEPRECATION")
fun View.padForSystemBars() {
    val (l, t, r, b) = listOf(paddingLeft, paddingTop, paddingRight, paddingBottom)
    setOnApplyWindowInsetsListener { v, insets ->
        v.setPadding(l, t + insets.systemWindowInsetTop, r, b + insets.systemWindowInsetBottom)
        insets
    }
}
