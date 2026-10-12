package com.example.vizistock

import com.google.firebase.Timestamp

data class Data (
    var id: String = "",
    var timeStamp: Timestamp? = null,
    var totalObjectsFound: Int = 0,
    var originalImageURL: String = "",
    var annotatedImageURL: String = "",
    var objectCounts: Map<String, Int> = emptyMap(),
    var confidenceThreshold: Double = 0.0,
)