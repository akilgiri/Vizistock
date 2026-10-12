package com.example.vizistock.model

import com.google.firebase.firestore.PropertyName

// 1. The Master Document
data class MasterConfig(
    @get:PropertyName("cam_0") @set:PropertyName("cam_0") var cam0: CameraConfig? = null,
    @get:PropertyName("cam_1") @set:PropertyName("cam_1") var cam1: CameraConfig? = null
)

// 2. The Individual Camera/Shelf Data
data class CameraConfig(
    val meta: MetaData? = null,
    val calibration: CalibrationData? = null,
    val planogram: Map<String, SlotData> = emptyMap()
)

data class MetaData(
    @get:PropertyName("shelf_id") val shelfId: String = "",
    @get:PropertyName("real_dimensions") val realDimensions: Map<String, Any>? = null
)

data class CalibrationData(
    @get:PropertyName("source_points") var sourcePoints: List<Double> = emptyList(),
    @get:PropertyName("homography_matrix") var homographyMatrix: List<Double> = emptyList(),
    @get:PropertyName("virtual_dim") var virtualDim: List<Int> = listOf(1000, 400)
)

data class SlotData(
    var name: String = "",

    @get:PropertyName("x_start")
    @set:PropertyName("x_start")
    var xStart: Double = 0.0,

    @get:PropertyName("x_end")
    @set:PropertyName("x_end")
    var xEnd: Double = 0.0,

    var threshold: Int = 0,

    @get:PropertyName("valid_classes")
    @set:PropertyName("valid_classes")
    var validClasses: List<String> = emptyList(),

    val aisle: String? = "1",
    val shelfNumber: String? = "A",

    var currentCount: Int = 0,
)