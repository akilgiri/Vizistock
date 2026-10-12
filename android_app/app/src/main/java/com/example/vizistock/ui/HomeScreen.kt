package com.example.vizistock.ui

import com.example.vizistock.ShelfViewModel
import com.example.vizistock.model.*

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import androidx.compose.foundation.lazy.itemsIndexed

@Composable
fun HomeScreen(navController: NavController, viewModel: ShelfViewModel) {
    // START SYNCING DEFAULT CAMERA ON LOAD
    LaunchedEffect(Unit) {
        viewModel.startSyncing(viewModel.currentCameraId)
    }

    val totalItems = viewModel.totalItemsRaw
    val lowStockCount = viewModel.alerts.size
    val misplacedCount = viewModel.misplacedCount
    val totalSlots = viewModel.shelfConfig?.planogram?.size ?: 0
    val isLive = viewModel.isLive
    val recentActivities = viewModel.recentActivities // Get the logs

    // Updates the timestamp
    val lastUpdated = remember(totalItems, misplacedCount) {
        val sdf = java.text.SimpleDateFormat("MMM dd, yyyy hh:mm a", java.util.Locale.getDefault())
        sdf.format(java.util.Date())
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0B131F))
            .padding(horizontal = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        SystemStatusHeader(isLive)

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = "ViziStock",
            fontSize = 36.sp,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF3B82F6)
        )

        Text(
            text = "Smart Shelf Monitoring App",
            fontSize = 16.sp,
            color = Color.LightGray,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        CameraSelector(
            currentCameraId = viewModel.currentCameraId,
            onCameraSelected = { newId -> viewModel.switchCamera(newId) }
        )

        GridSection(
            navController = navController,
            totalItems = totalItems,
            lowStockCount = lowStockCount,
            misplacedCount = misplacedCount,
            totalSlots = totalSlots
        )

        Spacer(modifier = Modifier.height(24.dp))

        RecentActivitySection(activities = recentActivities, onClear = { viewModel.clearActivities()})

        Spacer(modifier = Modifier.weight(1f))

        Text(
            text = "Last Sync: $lastUpdated",
            fontSize = 12.sp,
            color = Color.Gray,
            modifier = Modifier.padding(bottom = 16.dp)
        )
    }
}

@Composable
fun CameraSelector(currentCameraId: String, onCameraSelected: (String) -> Unit) {
    Text(
        text = "Select Camera View",
        fontSize = 12.sp,
        color = Color.Gray,
        modifier = Modifier.padding(bottom = 3.dp)
    )

    Row(
        modifier = Modifier.padding(vertical = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        listOf("cam_0", "cam_1").forEach { id ->
            val isSelected = currentCameraId == id
            Surface(
                modifier = Modifier.clickable { onCameraSelected(id) },
                shape = RoundedCornerShape(20.dp),
                color = if (isSelected) Color(0xFF3B82F6) else Color(0xFF1B263B),
                border = BorderStroke(1.dp, if (isSelected) Color.White else Color.Transparent)
            ) {
                Text(
                    text = id.uppercase(),
                    color = Color.White,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}

@Composable
fun SystemStatusHeader(isLive: Boolean) {
    val statusColor = if (isLive) Color(0xFF52B788) else Color(0xFFFFC107)
    val statusText = if (isLive) "SYSTEM LIVE" else "CONNECTING..."

    Surface(
        color = Color.White.copy(alpha = 0.05f),
        shape = RoundedCornerShape(50),
        modifier = Modifier.padding(top = 40.dp)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 15.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(modifier = Modifier.size(8.dp).background(statusColor, CircleShape))
            Spacer(modifier = Modifier.width(20.dp))
            Text(statusText, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun GridSection(
    navController: NavController,
    totalItems: Int,
    lowStockCount: Int,
    misplacedCount: Int,
    totalSlots: Int
) {
    Column(modifier = Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val cardModifier = Modifier.weight(1f).aspectRatio(1f)

        // Top Row
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // 1. Live Inventory - Increased Number and Icon size
            DashboardCard(modifier = cardModifier, onClick = { navController.navigate("itemInventory") }) {
                Text("LIVE INVENTORY", color = Color(0xFFE0E0E0), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.height(2.dp)) // Tightened spacer
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("$totalItems", color = Color(0xFF3B82F6), fontSize = 44.sp, fontWeight = FontWeight.Bold)
                    Spacer(modifier = Modifier.width(4.dp))
                    Icon(Icons.Default.ArrowUpward, contentDescription = null, tint = Color(0xFF52B788), modifier = Modifier.size(22.dp))
                }
                Text("Items Detected", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                Text("Real-time AI audit", color = Color.Gray, fontSize = 10.sp)
            }

            // 2. Planogram Coverage - Increased Progress Circle size
            DashboardCard(modifier = cardModifier, onClick = { navController.navigate("shelfInventory") }) {
                Text("PLANOGRAM COVERAGE", color = Color(0xFFE0E0E0), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.height(6.dp))
                Box(contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(
                        progress = { 1f },
                        modifier = Modifier.size(76.dp), // Increased from 64dp
                        color = Color(0xFF3B82F6),
                        trackColor = Color(0xFF52B788),
                        strokeWidth = 6.dp
                    )
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("$totalSlots/$totalSlots", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                        Text("Slots", color = Color.LightGray, fontSize = 10.sp)
                    }
                }
            }
        }

        // Bottom Row
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // 3. Stock Health - Increased Icon and Text size
            val healthColor = if (lowStockCount > 0) Color(0xFFE63946) else Color(0xFF52B788)
            DashboardCard(modifier = cardModifier, onClick = { navController.navigate("shelfOverview") }) {
                Text("STOCK HEALTH", color = Color(0xFFE0E0E0), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.height(6.dp))
                Icon(Icons.Default.CheckCircle, contentDescription = null, tint = healthColor, modifier = Modifier.size(40.dp)) // Increased from 32dp
                Spacer(modifier = Modifier.height(2.dp))
                Text(if (lowStockCount > 0) "Restock" else "Healthy", color = healthColor, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Text(if (lowStockCount > 0) "$lowStockCount alerts" else "All compliant", color = Color.Gray, fontSize = 10.sp)
            }

            // 4. Zoning Alerts - Increased Alert Number size
            val isAlertActive = misplacedCount > 0
            DashboardCard(
                modifier = cardModifier,
                backgroundColor = if (isAlertActive) Color(0xFFF48C06) else Color(0xFF1B263B),
                onClick = { navController.navigate("misplacedProducts") }
            ) {
                Text("ZONING ALERTS", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                // Removed spacer to allow the massive number to fit
                Text(if (isAlertActive) "$misplacedCount" else "0", color = Color.White, fontSize = 44.sp, fontWeight = FontWeight.Bold)
                Text(if (isAlertActive) "Zoning Alert" else "Perfect Alignment", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)

                if (isAlertActive) {
                    Spacer(modifier = Modifier.height(4.dp))
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = Color.White
                    ) {
                        Text(
                            "VIEW MAP",
                            color = Color(0xFFF48C06),
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 3.dp)
                        )
                    }
                } else {
                    Text("Compliant", color = Color.Gray, fontSize = 10.sp)
                }
            }
        }
    }
}

@Composable
fun DashboardCard(
    modifier: Modifier = Modifier,
    backgroundColor: Color = Color(0xFF1B263B),
    onClick: () -> Unit,
    content: @Composable ColumnScope.() -> Unit
) {
    Surface(
        color = backgroundColor,
        shape = RoundedCornerShape(16.dp),
        modifier = modifier.clickable { onClick() }
    ) {
        Column(
            modifier = Modifier.padding(12.dp).fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
            content = content
        )
    }
}

@Composable
fun RecentActivitySection(activities: List<ActivityLog>, onClear: () -> Unit) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "RECENT ACTIVITY",
                color = Color.White,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = 8.dp, start = 4.dp)
            )

            if (activities.isNotEmpty()) {
                Text(
                    text = "Clear",
                    color = Color(0xFF3B82F6),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier
                        .clickable { onClear() }
                        .padding(bottom = 8.dp, end = 4.dp)
                )
            }
        }

        Surface(
            color = Color(0xFF1B263B),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier
                .fillMaxWidth()
                // LIMIT HEIGHT: This makes the section scrollable instead of growing forever
                .heightIn(max = 240.dp)
        ) {
            if (activities.isEmpty()) {
                Box(modifier = Modifier.padding(12.dp)) {
                    Text("No recent activity.", color = Color.Gray, fontSize = 12.sp)
                }
            } else {
                // Use LazyColumn for efficient scrolling
                androidx.compose.foundation.lazy.LazyColumn(
                    modifier = Modifier.padding(horizontal = 12.dp),
                    contentPadding = PaddingValues(vertical = 12.dp)
                ) {
                    itemsIndexed(activities) { index, log ->
                        ActivityRow(log.getFormattedMessage())

                        if (index < activities.size - 1) {
                            HorizontalDivider(
                                color = Color.White.copy(alpha = 0.05f),
                                thickness = 1.dp,
                                modifier = Modifier.padding(vertical = 8.dp)
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun ActivityRow(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            imageVector = Icons.Default.Info,
            contentDescription = "Info",
            tint = Color(0xFF3B82F6),
            modifier = Modifier.size(16.dp)
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(text = text, color = Color.White.copy(alpha = 0.9f), fontSize = 12.sp)
    }
}