package com.example.vizistock

class Product (
    val id: String,
    val name: String,
    val category: String,
    val currentWeight: Int,
    val price: Double,
    val sku: String,
    val isLowStock: Boolean,
    val description: String? = null
)