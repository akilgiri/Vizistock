package com.example.vizistock.ui

import com.example.vizistock.ShelfViewModel
import com.example.vizistock.model.*

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import coil.compose.AsyncImage
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShelfOverviewScreen(viewModel: ShelfViewModel, navController: NavController, cameraId: String) {
    LaunchedEffect(cameraId) {
        viewModel.startSyncing(cameraId)
    }

    val shelfConfig = viewModel.shelfConfig
    val slotCounts = viewModel.slotCounts
    val alerts = viewModel.alerts
    val detections = viewModel.currentDetections
    val lastSync = getCurrentTime()
    val misplacedCountNum = viewModel.misplacedCount

    // State to track which slot is being edited (holds the Firebase Key and the Slot Data)
    var selectedSlotForEdit by remember { mutableStateOf<Pair<String, SlotData>?>(null) }

    Scaffold(
        containerColor = Color(0xFF0D1B2A),
        topBar = {
            TopAppBar(
                title = {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                        Text("SHELF OVERVIEW", fontSize = 18.sp, fontWeight = FontWeight.Black, color = Color.White)
                        Text("Last Sync: $lastSync", fontSize = 12.sp, color = Color.Gray)
                    }
                },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = Color.White)
                    }
                },
                actions = {
                    Spacer(modifier = Modifier.width(48.dp)) // Standard width of an IconButton
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent)
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.padding(padding).fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // 1. LIVE IMAGE HEADER
            item {
                ShelfImageHeader(viewModel.latestImageUrl)
            }

            // 2. FILTER CHIPS
            item {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatusChip("All (${detections.size})", Color(0xFF4CAF50))
                    StatusChip("Low Stock (${alerts.size})", Color(0xFFFB8500))
                    StatusChip("Misplaced (${misplacedCountNum})", Color(0xFF778DA9))
                }
            }

            // 3. RESTOCK ALERT
            if (alerts.isNotEmpty()) {
                item {
                    RestockPriorityCard(alerts)
                }
            }

            // 4. SLOT CARDS (Updated to use entries to get the Map Key for Firebase)
            val sortedEntries = shelfConfig?.planogram?.entries?.sortedBy { it.value.xStart } ?: emptyList()

            items(sortedEntries) { entry ->
                val slotKey = entry.key
                val slot = entry.value
                val currentCount = slotCounts[slot.name] ?: 0
                val isLow = currentCount < slot.threshold

                SlotStatusCard(
                    slotName = slot.name,
                    currentCount = currentCount,
                    threshold = slot.threshold,
                    validClasses = slot.validClasses,
                    isLow = isLow,
                    onEditThresholdClick = {
                        selectedSlotForEdit = slotKey to slot
                    }
                )
            }
        }
    }

    // 5. THRESHOLD EDIT DIALOG
    selectedSlotForEdit?.let { (key, slot) ->
        ThresholdEditDialog(
            slotName = slot.name,
            currentThreshold = slot.threshold,
            onDismiss = { selectedSlotForEdit = null },
            onSave = { newValue ->
                viewModel.updateThreshold(cameraId, key, newValue)
                selectedSlotForEdit = null
            }
        )
    }
}

@Composable
fun ShelfImageHeader(url: String?) {
    Card(
        modifier = Modifier.fillMaxWidth().height(200.dp).border(2.dp, Color.White.copy(alpha = 0.1f), RoundedCornerShape(16.dp)),
        shape = RoundedCornerShape(16.dp)
    ) {
        Box {
            AsyncImage(
                model = url ?: "https://your-placeholder-url.com/shelf.jpg",
                contentDescription = "Shelf Live View",
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop
            )
            Surface(
                color = Color.Black.copy(alpha = 0.6f),
                modifier = Modifier.padding(12.dp).align(Alignment.TopStart),
                shape = RoundedCornerShape(4.dp)
            ) {
                Text("LIVE AI FEED", color = Color.Green, fontSize = 10.sp, modifier = Modifier.padding(4.dp))
            }
        }
    }
}

@Composable
fun SlotStatusCard(
    slotName: String,
    currentCount: Int,
    threshold: Int,
    validClasses: List<String>,
    isLow: Boolean,
    onEditThresholdClick: () -> Unit
) {
    val accentColor = if (isLow) Color(0xFFE63946) else Color(0xFF52B788)

    Surface(
        color = Color(0xFF1B263B),
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, accentColor.copy(alpha = 0.5f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier.size(50.dp).background(accentColor.copy(alpha = 0.1f), CircleShape).border(1.dp, accentColor, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(if (isLow) Icons.Default.Warning else Icons.Default.Inventory, contentDescription = null, tint = accentColor)
            }

            Spacer(modifier = Modifier.width(16.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(slotName.uppercase(), fontWeight = FontWeight.Black, color = Color.White, fontSize = 18.sp)
                Text("Products: ${validClasses.joinToString(", ")}", color = Color.Gray, fontSize = 12.sp)
                Text("Width: 12.0 in", color = Color(0xFF778DA9), fontSize = 10.sp)
            }

            Column(horizontalAlignment = Alignment.End) {
                Surface(
                    color = if (isLow) Color(0xFFE63946).copy(alpha = 0.2f) else Color.White.copy(alpha = 0.05f),
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, if (isLow) Color(0xFFE63946) else Color.White.copy(alpha = 0.2f)),
                    modifier = Modifier.clickable { onEditThresholdClick() }
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "Stock: $currentCount/$threshold",
                            color = if (isLow) Color(0xFFE63946) else Color.White,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.width(4.dp))
                        Icon(
                            Icons.Default.Edit,
                            contentDescription = null,
                            tint = if (isLow) Color(0xFFE63946) else Color.White.copy(alpha = 0.6f),
                            modifier = Modifier.size(12.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun ThresholdEditDialog(
    slotName: String,
    currentThreshold: Int,
    onDismiss: () -> Unit,
    onSave: (Int) -> Unit
) {
    var bufferThreshold by remember { mutableStateOf(currentThreshold) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Color(0xFF1B263B),
        title = { Text("Edit Threshold: $slotName", color = Color.White, fontWeight = FontWeight.Bold) },
        text = {
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(
                    onClick = { if (bufferThreshold > 0) bufferThreshold-- },
                    modifier = Modifier.background(Color.White.copy(alpha = 0.1f), CircleShape)
                ) {
                    Icon(Icons.Default.Remove, "Decrease", tint = Color.White)
                }
                Text(
                    text = bufferThreshold.toString(),
                    fontSize = 36.sp,
                    color = Color.White,
                    fontWeight = FontWeight.Black
                )
                IconButton(
                    onClick = { bufferThreshold++ },
                    modifier = Modifier.background(Color.White.copy(alpha = 0.1f), CircleShape)
                ) {
                    Icon(Icons.Default.Add, "Increase", tint = Color.White)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { onSave(bufferThreshold) },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFB8500))
            ) {
                Text("SAVE CHANGES", fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("CANCEL", color = Color.Gray)
            }
        }
    )
}

@Composable
fun StatusChip(text: String, color: Color) {
    Surface(
        color = color.copy(alpha = 0.2f),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, color)
    ) {
        Text(text, color = color, fontSize = 12.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
    }
}

@Composable
fun RestockPriorityCard(alerts: List<String>) {
    Surface(
        color = Color(0xFFE63946).copy(alpha = 0.1f),
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(2.dp, Color(0xFFE63946))
    ) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.NotificationsActive, contentDescription = null, tint = Color(0xFFE63946), modifier = Modifier.size(32.dp))
            Spacer(modifier = Modifier.width(12.dp))
            Column {
                Text("RESTOCK PRIORITY", fontWeight = FontWeight.Black, color = Color.White)
                Text("${alerts.size} slots require immediate attention", color = Color(0xFFE63946), fontSize = 12.sp)
            }
        }
    }
}

fun getCurrentTime(): String {
    val sdf = SimpleDateFormat("MMM dd, yyyy hh:mm a", Locale.getDefault())
    return sdf.format(Date())
}