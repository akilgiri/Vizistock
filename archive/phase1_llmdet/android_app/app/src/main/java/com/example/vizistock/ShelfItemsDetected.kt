package com.example.vizistock

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import androidx.compose.foundation.lazy.items
import coil.compose.AsyncImage
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.draw.blur
import androidx.compose.ui.platform.LocalContext
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShelfItemsDetected(navController: NavController, shelfSnapshot: List<Data>) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Shelf Items") },
                navigationIcon = {
                    IconButton(onClick = { navController.navigate("homePage") }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
//                colors = TopAppBarDefaults.smallTopAppBarColors(containerColor = Color(0xFF0D1B2A))
            )
        },
        containerColor = Color(0xFF0D1B2A)
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(12.dp)
        ) {
            items(shelfSnapshot) { snapshot ->
                ShelfItemsList(snapshot = snapshot)
                {
                    // Navigate to Product Detail screen with product ID or name
                    navController.navigate("productDetail/${snapshot.timeStamp}")
                }
                Spacer(modifier = Modifier.height(10.dp))
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ShelfItemsList(snapshot: Data, onClick: () -> Unit) {
    var showImageDialog by remember { mutableStateOf<String?>(null) }

    if (showImageDialog != null) {
        ZoomableImageDialog(
            imageUrl = showImageDialog!!,
            onDismiss = { showImageDialog = null }
        )
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF1B263B)),
        elevation = CardDefaults.cardElevation(6.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            val formatter = DateTimeFormatter.ofPattern("MMM dd, yyyy h:mm a")
                .withZone(ZoneId.systemDefault())

            val formattedTime = snapshot.timeStamp?.toDate()?.toInstant()?.let {
                formatter.format(it)
            } ?: "N/A"

            Text("Timestamp: $formattedTime",
                color = Color.White,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium
            )

            Spacer(modifier = Modifier.height(4.dp))

            Row(
                horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Confidence: ${snapshot.confidenceThreshold}%",
                    color = Color(0xFFB0BEC5),
                    fontSize = 13.sp,
                )
                Text("Total Objects Found: ${snapshot.totalObjectsFound}",
                    color = Color.LightGray,
                    fontSize = 13.sp)
            }

            Spacer(modifier = Modifier.height(12.dp))


            Text("Detected Objects:", fontWeight = FontWeight.Bold, color = Color.White)
            Spacer(modifier = Modifier.height(4.dp))

            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                snapshot.objectCounts.forEach { (label, count) ->
//                    Text("$label: $count", color = Color.LightGray)
                    AssistChip(
                        onClick = {},
                        label = {
                            Text("$label: $count", color = Color.White, fontSize = 13.sp)
                        },
                        shape = RoundedCornerShape(50),
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = Color(0xFF344966)
                        )
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {

                Text("Original Image:", color = Color.LightGray, fontSize = 12.sp)
                AsyncImage(
                    model = snapshot.originalImageURL,
                    contentDescription = "Original Shelf Image",
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(200.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .clickable { showImageDialog = snapshot.originalImageURL },
                    contentScale = ContentScale.Crop
                )

                Spacer(modifier = Modifier.height(8.dp))

                Text("Annotated Image:", color = Color.LightGray, fontSize = 12.sp)
                AsyncImage(
                    model = snapshot.annotatedImageURL,
                    contentDescription = "Annotated Shelf Image",
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(200.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .clickable { showImageDialog= snapshot.annotatedImageURL },
                    contentScale = ContentScale.Crop
                )

            }


            Spacer(modifier = Modifier.height(8.dp))


//            Row(
//                modifier = Modifier.fillMaxWidth(),
//                horizontalArrangement = Arrangement.SpaceBetween
//            ) {
//                Text(
//                    text = product.name,
//                    fontSize = 18.sp,
//                    fontWeight = FontWeight.Bold,
//                    color = Color.White
//                )
//                Text(
//                    text = "$${product.price}",
//                    fontSize = 16.sp,
//                    color = Color.White
//                )
//            }
//
//            Spacer(modifier = Modifier.height(8.dp))
//
//            Text("SKU: ${product.sku}", color = Color.LightGray, fontSize = 14.sp)
//            Text("Stock: ${product.currentWeight} units", color = Color.LightGray, fontSize = 14.sp)
//
//            Text(
//                text = when {
//                    product.currentWeight == 0 -> "Out of Stock"
//                    product.isLowStock -> "Low Stock"
//                    else -> "In Stock"
//                },
//                color = when {
//                    product.currentWeight == 0 -> Color.Red
//                    product.isLowStock -> Color.Yellow
//                    else -> Color.Green
//                },
//                fontWeight = FontWeight.SemiBold
//            )
        }
    }
}


@Composable
fun ZoomableImageDialog(
    imageUrl: String,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        // Layer 1: dimmed + blurred backdrop
        Box(
            modifier = Modifier
                .fillMaxSize()
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.3f))
                    .blur(16.dp)
            )

            // Layer 2: image with back button overlay
            Box(
                modifier = Modifier
                    .fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                // Zoomable image with dynamic size
                ZoomableImage(imageUrl = imageUrl)

                // Floating back arrow in top-left corner of image
                IconButton(
                    onClick = onDismiss,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(24.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.ArrowBack,
                        contentDescription = "Close",
                        tint = Color.White
                    )
                }
            }
        }
    }
}



@Composable
fun ZoomableImage(imageUrl: String) {
    var scale by remember { mutableStateOf(1f) }

    val transformModifier = Modifier
        .pointerInput(Unit) {
            detectTransformGestures { _, _, zoom, _ ->
                scale *= zoom
            }
        }
        .graphicsLayer(
            scaleX = scale.coerceIn(1f, 5f),
            scaleY = scale.coerceIn(1f, 5f)
        )

    Box(
        modifier = Modifier
            .wrapContentSize()
            .then(transformModifier),
        contentAlignment = Alignment.Center
    ) {
        AsyncImage(
            model = imageUrl,
            contentDescription = "Zoomable Image",
            contentScale = ContentScale.Fit,
            modifier = Modifier
                .clip(RoundedCornerShape(12.dp))
        )
    }
}



