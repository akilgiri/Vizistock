package com.example.vizistock.ui

import com.example.vizistock.ShelfViewModel
import com.example.vizistock.model.*

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue

@Composable
fun ShelfInventoryScreen(viewModel: ShelfViewModel, navController: NavController) {
    var expanded by remember { mutableStateOf(false) }
    var currentCamera = viewModel.currentCameraId

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0D1B2A))
            .statusBarsPadding()
    ) {
        // --- TOP BAR ---
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = { navController.popBackStack() }) {
                Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Color.White)
            }

            // Header Text
            Column(modifier = Modifier.weight(1f)) {
                Text("SHELF INVENTORY", color = Color.White, style = MaterialTheme.typography.h6, fontWeight = FontWeight.Black)
                Text("Active Planogram: ${currentCamera}_Master", color = Color.Gray, fontSize = 12.sp)
            }

            // --- CAMERA DROPDOWN ---
            Box {
                Row(
                    modifier = Modifier
                        .clickable { expanded = true }
                        .padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(Icons.Default.PhotoCamera, contentDescription = null, tint = Color.White, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(currentCamera.uppercase(), color = Color.White, fontWeight = FontWeight.Bold)
                    Icon(Icons.Default.ArrowDropDown, contentDescription = null, tint = Color.White)
                }

                Box {
                    Row(
                        modifier = Modifier
                            .clip(RoundedCornerShape(8.dp))
                            .clickable { expanded = true }
                            .padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.PhotoCamera,
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        // Display currentCamera from ViewModel
                        Text(
                            currentCamera.uppercase(),
                            color = Color.White,
                            fontWeight = FontWeight.Bold
                        )
                        Icon(
                            Icons.Default.ArrowDropDown,
                            contentDescription = null,
                            tint = Color.White
                        )
                    }

                    DropdownMenu(
                        expanded = expanded,
                        onDismissRequest = { expanded = false },
                        modifier = Modifier.background(Color(0xFF1B263B))
                    ) {
                        DropdownMenuItem(onClick = {
                            // Use the switchCamera logic to cleanup listeners and restart
                            viewModel.switchCamera("cam_0")
                            expanded = false
                        }) {
                            Text("Camera 0 (Shelf 1)", color = Color.White)
                        }
                        DropdownMenuItem(onClick = {
                            viewModel.switchCamera("cam_1")
                            expanded = false
                        }) {
                            Text("Camera 1 (Shelf 2)", color = Color.White)
                        }
                    }
                }

                }
        }

        // --- SEARCH BAR ---
        TextField(
            value = viewModel.inventorySearchQuery,
            onValueChange = { viewModel.inventorySearchQuery = it },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .clip(RoundedCornerShape(12.dp)),
            placeholder = { Text("Search products...", color = Color.Gray) },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Color.Gray) },
            colors = TextFieldDefaults.textFieldColors(
                backgroundColor = Color(0xFF1B263B),
                textColor = Color.White,
                focusedIndicatorColor = Color.Transparent,
                unfocusedIndicatorColor = Color.Transparent
            )
        )

        // --- PRODUCT LIST ---
        LazyColumn(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            items(viewModel.filteredInventory) { slot ->
                val currentStock = viewModel.slotCounts[slot.name] ?: 0
                val isLow = currentStock < slot.threshold

                InventoryCard(
                    slot = slot,
                    currentStock = currentStock,
                    isLow = isLow
                )
            }
        }
    }
}

@Composable
fun InventoryCard(slot: SlotData, currentStock: Int, isLow: Boolean) {
    Card(
        backgroundColor = Color(0xFF1B263B),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier.padding(16.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(slot.name, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text("Slot ID: ${slot.name}", color = Color.Gray, fontSize = 12.sp)
                Text("Expected: ${slot.validClasses.joinToString()}", color = Color.LightGray, fontSize = 12.sp)
            }

            // Stock Indicator
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = "$currentStock / ${slot.threshold}+",
                    color = if (isLow) Color(0xFFE63946) else Color(0xFF52B788),
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp
                )
                Text(
                    text = if (isLow) "LOW STOCK" else "HEALTHY",
                    color = if (isLow) Color(0xFFE63946) else Color(0xFF52B788),
                    fontSize = 10.sp
                )
            }
        }
    }
}