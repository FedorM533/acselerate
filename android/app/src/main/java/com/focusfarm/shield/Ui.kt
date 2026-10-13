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
// Цвета Carpo (те же значения, что в res/values/carpo_colors.xml и tokens.css).
const val INK = 0xFF1F2A25.toInt()
const val MUTED = 0xFF5B6F66.toInt()
const val ACCENT = 0xFF2E4A3F.toInt()
const val CREAM = 0xFFF6F2EB.toInt()
const val PAPER = 0xFFFBF9F5.toInt()
const val CLAY = 0xFFD97A5A.toInt()
const val LINE = 0xFFD8D0C2.toInt()

/** Вид кнопки: основная (зелёная), контурная и кнопка для тёмно-зелёного фона (терракотовая). */
enum class Look { PRIMARY, GHOST, ON_GREEN, GHOST_ON_GREEN }

fun Context.dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

fun Context.text(text: String, size: Float = 16f, bold: Boolean = false, color: Int = INK): TextView =
    TextView(this).apply {
        this.text = text
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

fun Context.button(text: String, look: Look = Look.PRIMARY, onClick: () -> Unit): Button = Button(this).apply {
    this.text = text
    isAllCaps = false
    stateListAnimator = null
    setTypeface(typeface, Typeface.BOLD)
    minHeight = dp(48)
    minimumHeight = dp(48)
    val (fill, stroke, textColor) = when (look) {
        Look.PRIMARY -> Triple(ACCENT, ACCENT, CREAM)
        Look.GHOST -> Triple(Color.TRANSPARENT, ACCENT, ACCENT)
        Look.ON_GREEN -> Triple(CLAY, CLAY, INK)
        Look.GHOST_ON_GREEN -> Triple(Color.TRANSPARENT, 0xFF5E7A6D.toInt(), CREAM)
    }
    setTextColor(textColor)
    background = GradientDrawable().apply {
        setColor(fill)
        setStroke(dp(1), stroke)
        cornerRadius = dp(999).toFloat()          // «таблетка»
    }
    setPadding(dp(22), dp(10), dp(22), dp(10))
    setOnClickListener { onClick() }
}

fun Context.card(vararg children: View): LinearLayout = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    setPadding(dp(20), dp(18), dp(20), dp(18))
    background = GradientDrawable().apply {
        setColor(PAPER)
        setStroke(dp(1), LINE)
        cornerRadius = dp(24).toFloat()
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
