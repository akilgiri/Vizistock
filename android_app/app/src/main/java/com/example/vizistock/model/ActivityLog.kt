package com.example.vizistock.model

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class ActivityLog(
    val message: String = "",
    val timestamp: Long = System.currentTimeMillis()
) {
    fun getFormattedMessage(): String {
        val sdf = SimpleDateFormat("MMM dd, h:mm a", Locale.getDefault())
        return "${sdf.format(Date(timestamp))}: $message"
    }
}
