package com.example.vizistock.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName

@Serializable
data class Detection(
    val label: String,
    val confidence: Double,
    @SerialName("center_x") val centerX: Double,
    val bbox: BBox,
    var isMisplaced: Boolean = false,
    var expectedSlotProduct: String = "",
    val slotKey: String = "",
    val itemKey: String = ""
)

@Serializable
data class BBox(
    val x1: Float = 0f,
    val y1: Float = 0f,
    val x2: Float = 0f,
    val y2: Float = 0f
)