package com.example.vizistock.ui

import com.example.vizistock.ShelfViewModel
import com.example.vizistock.model.*

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
// Explicit Material 2 Imports to fix "Unresolved reference"
import androidx.compose.material.Button
import androidx.compose.material.ButtonDefaults
import androidx.compose.material.Card
import androidx.compose.material.Icon
import androidx.compose.material.IconButton
import androidx.compose.material.MaterialTheme
import androidx.compose.material.Text
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Warning
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import coil.compose.AsyncImage
import androidx.compose.material.Surface
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.material.TextButton
import androidx.compose.material.AlertDialog
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.animateOffsetAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.TextField
import androidx.compose.material.TextFieldDefaults
import androidx.compose.material.icons.filled.Search

@Composable
fun MisplacedProductsScreen(viewModel: ShelfViewModel, navController: NavController) {
    // Track which detection is currently focused for zoom
    var selectedDetection by remember { mutableStateOf<Detection?>(null) }
    var searchQuery by remember { mutableStateOf("") }

    // Animate the zoom level (1f is normal, 2.5f is zoomed)
    val zoomScale by animateFloatAsState(
        targetValue = if (selectedDetection != null) 2.5f else 1f,
        animationSpec = tween(durationMillis = 500)
    )

    // Animate the focal point (where the camera is looking)
    val zoomOffset by animateOffsetAsState(
        targetValue = if (selectedDetection != null) {
            // Force the result to be a Float to satisfy the Offset constructor
            val centerX = ((selectedDetection!!.bbox.x1 + selectedDetection!!.bbox.x2) / 2.0).toFloat()
            val centerY = ((selectedDetection!!.bbox.y1 + selectedDetection!!.bbox.y2) / 2.0).toFloat()
            Offset(centerX, centerY)
        } else Offset.Zero,
        animationSpec = tween(durationMillis = 500)
    )

    var showDialog by remember { mutableStateOf(false) }
    var selectedItem by remember { mutableStateOf<Detection?>(null) }

    // THE DIALOG
    if (showDialog && selectedItem != null) {
        AlertDialog(
            onDismissRequest = { showDialog = false },
            title = { Text("Confirm Resolution") },
            text = { Text("Are you sure you have moved '${selectedItem?.label}' to the correct spot?") },
            confirmButton = {
                Button(
                    onClick = {
                        selectedItem?.let { viewModel.resolveDetection(viewModel.currentCameraId, it) } // Known issue: see README
                        showDialog = false
                    },
                    colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFFE63946))
                ) {
                    Text("YES, RESOLVE", color = Color.White)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDialog = false }) {
                    Text("CANCEL", color = Color.White)
                }
            },
            backgroundColor = Color(0xFF1B263B),
            contentColor = Color.White
        )
    }

    // These are already 'mutableStateOf' in your ViewModel, so we don't need .collectAsState()
    val detections = viewModel.currentDetections
    val latestImage = viewModel.latestImageUrl

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0D1B2A))
            .statusBarsPadding()
    ) {
        // --- TOP BAR ---
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = { navController.popBackStack() }) {
                Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Color.White)
            }
            // Using Material 2 Typography (h6) to match your import
            Text("Misplaced Products", color = Color.White, style = MaterialTheme.typography.h6)
            Spacer(modifier = Modifier.weight(1f))
            Box(modifier = Modifier.background(Color.Green, RoundedCornerShape(12.dp)).padding(horizontal = 8.dp, vertical = 4.dp)) {
                Text("SYSTEM LIVE", color = Color.Black, fontSize = 10.sp)
            }
        }

        // --- HERO IMAGE WITH ZOOM & BOUNDING BOXES ---
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(350.dp) // Slightly taller to account for zoom room
                .padding(horizontal = 16.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(Color.Black)
        ) {
            // This inner Box is the "Camera Lens"
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        scaleX = zoomScale
                        scaleY = zoomScale
                        transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, 0f)

                        if (selectedDetection != null) {
                            translationX = (size.width / 2f) - (zoomOffset.x * size.width * zoomScale)
                            translationY = (size.height / 2f) - (zoomOffset.y * size.height * zoomScale)
                        }
                    }
            ) {
                AsyncImage(
                    model = latestImage,
                    contentDescription = "Shelf View",
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.FillBounds
                )

                Canvas(modifier = Modifier.fillMaxSize()) {
                    // 1. Scale factors are now just the literal width/height of the Canvas
                    val scaleX = size.width
                    val scaleY = size.height

                    val misplacedItems = detections.filter { it.isMisplaced }

                    // PASS 1: Red Bounding Boxes
                    misplacedItems.forEach { detection ->
                        // 2. Multiply normalized values (e.g., 0.5) by screen pixels (e.g., 1080)
                        val left = detection.bbox.x1.toFloat() * scaleX
                        val top = detection.bbox.y1.toFloat() * scaleY
                        val rectWidth = (detection.bbox.x2 - detection.bbox.x1).toFloat() * scaleX
                        val rectHeight = (detection.bbox.y2 - detection.bbox.y1).toFloat() * scaleY

                        drawRect(
                            color = Color.Red,
                            topLeft = Offset(left, top),
                            size = Size(rectWidth, rectHeight),
                            style = Stroke(width = 8f) // Thick enough to see
                        )
                    }

                    // PASS 2: Callout Pins (Indices)
                    misplacedItems.withIndex().forEach { (index, detection) ->
                        val radius = 30f
                        val centerX = detection.bbox.x1.toFloat() * scaleX
                        val centerY = detection.bbox.y1.toFloat() * scaleY

                        // Ensure pins don't go off-screen
                        val safeLeft = centerX.coerceIn(radius, size.width - radius)
                        val safeTop = centerY.coerceIn(radius, size.height - radius)

                        drawCircle(color = Color.White, radius = radius, center = Offset(safeLeft, safeTop))
                        drawCircle(color = Color.Red, radius = radius, center = Offset(safeLeft, safeTop), style = Stroke(width = 4f))

                        drawContext.canvas.nativeCanvas.apply {
                            val paint = android.graphics.Paint().apply {
                                color = android.graphics.Color.RED
                                textSize = 36f
                                typeface = android.graphics.Typeface.create(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
                                textAlign = android.graphics.Paint.Align.CENTER
                            }
                            drawText("${index + 1}", safeLeft, safeTop + 13f, paint)
                        }
                    }
                }
            }

            // --- RESET ZOOM BUTTON ---
            if (selectedDetection != null) {
                IconButton(
                    onClick = { selectedDetection = null },
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(8.dp)
                        .background(Color.Black.copy(0.6f), RoundedCornerShape(50))
                ) {
                    Icon(Icons.Default.Close, contentDescription = "Close Zoom", tint = Color.White)
                }
            }
        }

        // --- SEARCH BAR ---
        TextField(
            value = searchQuery,
            onValueChange = { searchQuery = it },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp)
                .clip(RoundedCornerShape(12.dp)),
            placeholder = { Text("Search by product or slot name...", color = Color.Gray) },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Color.Gray) },
            trailingIcon = {
                if (searchQuery.isNotEmpty()) {
                    IconButton(onClick = { searchQuery = "" }) {
                        Icon(Icons.Default.Close, contentDescription = "Clear", tint = Color.Gray)
                    }
                }
            },
            colors = TextFieldDefaults.textFieldColors(
                backgroundColor = Color(0xFF1B263B),
                focusedIndicatorColor = Color.Transparent,
                unfocusedIndicatorColor = Color.Transparent,
                textColor = Color.White
            ),
            singleLine = true
        )

        Text(
            "Detected Conflicts",
            color = Color.White,
            modifier = Modifier.padding(16.dp),
            style = MaterialTheme.typography.subtitle1
        )

        LazyColumn(
            modifier = Modifier.weight(1f).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // STEP 3: Apply the search filter here
            val filteredItems = detections.filter { item ->
                item.isMisplaced && (
                        item.label.contains(searchQuery, ignoreCase = true) ||
                                item.expectedSlotProduct.contains(searchQuery, ignoreCase = true)
                        )
            }

            if (filteredItems.isEmpty()) {
                item {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(top = 40.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(
                                // Show a warning if searching, CheckCircle if just empty
                                imageVector = if (searchQuery.isEmpty()) Icons.Default.CheckCircle else Icons.Default.Warning,
                                contentDescription = null,
                                tint = if (searchQuery.isEmpty()) Color.Green else Color.Gray,
                                modifier = Modifier.size(48.dp)
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = if (searchQuery.isEmpty()) "No conflicts found!" else "No matches for '$searchQuery'",
                                color = Color.LightGray
                            )
                        }
                    }
                }
            } else {
                itemsIndexed(filteredItems) { index, item ->
                    ConflictCard(
                        detection = item,
                        index = index,
                        isSelected = (selectedDetection == item),
                        modifier = Modifier.clickable {
                            selectedDetection = if (selectedDetection == item) null else item
                        },
                        onResolveClick = {
                            selectedItem = item
                            showDialog = true
                        }
                    )
                }
            }
        }
    }
}

@Composable
fun ConflictCard(detection: Detection, index: Int, isSelected: Boolean, modifier: Modifier = Modifier, onResolveClick: () -> Unit) {
    Card(
        backgroundColor = Color(0xFF1B263B),
        shape = RoundedCornerShape(12.dp),
        elevation = 4.dp,
        modifier = modifier.fillMaxWidth(),
        border = if (isSelected) BorderStroke(2.dp, Color.White) else null

    ) {
        Row(
            modifier = Modifier
                .padding(12.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 1. FIXED NUMBER CIRCLE
            Surface(
                shape = RoundedCornerShape(50),
                color = Color.Red,
                modifier = Modifier.size(36.dp)
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        text = "${index + 1}",
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
                }
            }

            Spacer(modifier = Modifier.width(12.dp))

            // 2. TEXT COLUMN WITH WEIGHT
            // The .weight(1f) is the magic fix for overlapping buttons!
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Detected: ${detection.label}",
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    maxLines = 1 // Prevents pushing the button down
                )
                Text(
                    text = "Expected: ${detection.expectedSlotProduct}",
                    color = Color.LightGray,
                    fontSize = 12.sp,
                    maxLines = 1
                )
            }

            Spacer(modifier = Modifier.width(8.dp))

            // 3. PROPERLY SPACED BUTTON
            Button(
                onClick = onResolveClick,
                colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFFE63946)),
                shape = RoundedCornerShape(8.dp),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                modifier = Modifier.height(36.dp)
            ) {
                Text(
                    "RESOLVE",
                    color = Color.White,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}
