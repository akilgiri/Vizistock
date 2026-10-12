package com.example.vizistock.ui

import com.example.vizistock.ShelfViewModel
import com.example.vizistock.model.*

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController

@Composable
fun ItemInventoryScreen(viewModel: ShelfViewModel, navController: NavController) {
    var isAdvancedFilterOpen by remember { mutableStateOf(false) }

    // Draft states for the Advanced Panel
    var draftAisle by remember { mutableStateOf(viewModel.appliedAisleFilter) }
    var draftShelf by remember { mutableStateOf(viewModel.appliedShelfFilter) }

    // Quick Menu States
    var showQuickMenu by remember { mutableStateOf(false) }
    var quickMenuLevel by remember { mutableStateOf("MAIN") } // "MAIN", "AISLE", or "SHELF"

    // Dynamically extract unique Aisles and Shelves directly from the planogram data
    val availableAisles = viewModel.shelfConfig?.planogram?.values?.mapNotNull { it.aisle }?.distinct()?.filter { it != "N/A" } ?: emptyList()
    val availableShelves = viewModel.shelfConfig?.planogram?.values?.mapNotNull { it.shelfNumber }?.distinct()?.filter { it != "N/A" } ?: emptyList()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0D1B2A))
            .statusBarsPadding()
    ) {
        // --- HEADER ---
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = { navController.popBackStack() }) {
                Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Color.White)
            }
            Text(
                text = "INVENTORY",
                color = Color.White,
                style = MaterialTheme.typography.h4,
                fontWeight = FontWeight.Black
            )
        }

        // --- SEARCH & FILTER BUTTONS ---
        Column(modifier = Modifier.padding(horizontal = 16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {

                // Search Bar
                TextField(
                    value = viewModel.inventorySearchQuery,
                    onValueChange = { viewModel.inventorySearchQuery = it },
                    modifier = Modifier
                        .weight(1f)
                        .height(56.dp),
                    placeholder = { Text("Quick search...", color = Color.Gray) },
                    leadingIcon = { Icon(Icons.Default.Search, null, tint = Color.Gray) },
                    colors = TextFieldDefaults.textFieldColors(
                        backgroundColor = Color(0xFF1B263B),
                        textColor = Color.White,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = Color(0xFF3B82F6)
                    ),
                    shape = RoundedCornerShape(12.dp),
                    singleLine = true
                )

                Spacer(modifier = Modifier.width(8.dp))

                // --- NEW: QUICK FILTER DROPDOWN BUTTON ---
                Box {
                    IconButton(
                        onClick = {
                            showQuickMenu = true
                            quickMenuLevel = "MAIN"
                        },
                        modifier = Modifier
                            .height(56.dp)
                            .width(56.dp)
                            .background(Color(0xFF1B263B), RoundedCornerShape(12.dp))
                    ) {
                        Icon(Icons.Default.FilterList, contentDescription = "Quick Filters", tint = Color.White)
                    }

                    // Dropdown Content
                    DropdownMenu(
                        expanded = showQuickMenu,
                        onDismissRequest = { showQuickMenu = false },
                        modifier = Modifier.background(Color(0xFF1B263B))
                    ) {
                        if (quickMenuLevel == "MAIN") {
                            DropdownMenuItem(onClick = { quickMenuLevel = "AISLE" }) {
                                Text("Filter by Aisle...", color = Color.White)
                            }
                            DropdownMenuItem(onClick = { quickMenuLevel = "SHELF" }) {
                                Text("Filter by Shelf...", color = Color.White)
                            }

                            // Show clear option if a filter is active
                            if (viewModel.appliedAisleFilter.isNotEmpty() || viewModel.appliedShelfFilter.isNotEmpty()) {
                                Divider(color = Color.Gray.copy(alpha = 0.3f))
                                DropdownMenuItem(onClick = {
                                    viewModel.appliedAisleFilter = ""
                                    viewModel.appliedShelfFilter = ""
                                    draftAisle = ""
                                    draftShelf = ""
                                    showQuickMenu = false
                                }) {
                                    Text("Clear All Filters", color = Color(0xFFE63946), fontWeight = FontWeight.Bold)
                                }
                            }
                        } else if (quickMenuLevel == "AISLE") {
                            // Back Button
                            DropdownMenuItem(onClick = { quickMenuLevel = "MAIN" }) {
                                Text("← Back", color = Color.Gray)
                            }
                            Divider(color = Color.Gray.copy(alpha = 0.3f))

                            if (availableAisles.isEmpty()) {
                                DropdownMenuItem(onClick = { }) { Text("No Aisles found", color = Color.Gray) }
                            } else {
                                availableAisles.forEach { aisle ->
                                    DropdownMenuItem(onClick = {
                                        viewModel.appliedAisleFilter = aisle
                                        showQuickMenu = false
                                    }) {
                                        Text("Aisle $aisle", color = Color.White)
                                    }
                                }
                            }
                        } else if (quickMenuLevel == "SHELF") {
                            // Back Button
                            DropdownMenuItem(onClick = { quickMenuLevel = "MAIN" }) {
                                Text("← Back", color = Color.Gray)
                            }
                            Divider(color = Color.Gray.copy(alpha = 0.3f))

                            if (availableShelves.isEmpty()) {
                                DropdownMenuItem(onClick = { }) { Text("No Shelves found", color = Color.Gray) }
                            } else {
                                availableShelves.forEach { shelf ->
                                    DropdownMenuItem(onClick = {
                                        viewModel.appliedShelfFilter = shelf
                                        showQuickMenu = false
                                    }) {
                                        Text("Shelf $shelf", color = Color.White)
                                    }
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.width(8.dp))

                // --- ADVANCED FILTER TOGGLE ---
                IconButton(
                    onClick = {
                        isAdvancedFilterOpen = !isAdvancedFilterOpen
                        if (isAdvancedFilterOpen) {
                            draftAisle = viewModel.appliedAisleFilter
                            draftShelf = viewModel.appliedShelfFilter
                        }
                    },
                    modifier = Modifier
                        .height(56.dp)
                        .width(56.dp)
                        .background(Color(0xFF1B263B), RoundedCornerShape(12.dp))
                ) {
                    Icon(
                        imageVector = if (isAdvancedFilterOpen) Icons.Default.KeyboardArrowUp else Icons.Default.Tune,
                        contentDescription = "Advanced Filter",
                        tint = if (isAdvancedFilterOpen) Color(0xFF3B82F6) else Color.White
                    )
                }
            }

            // --- ADVANCED FILTER PANEL ---
            AnimatedVisibility(
                visible = isAdvancedFilterOpen,
                enter = expandVertically() + fadeIn(),
                exit = shrinkVertically() + fadeOut()
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp)
                        .background(Color(0xFF1B263B), RoundedCornerShape(12.dp))
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("Advanced Search", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        if (viewModel.appliedAisleFilter.isNotEmpty() || viewModel.appliedShelfFilter.isNotEmpty()) {
                            Text(
                                text = "Clear",
                                color = Color(0xFFE63946),
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.clickable {
                                    draftAisle = ""
                                    draftShelf = ""
                                    viewModel.appliedAisleFilter = ""
                                    viewModel.appliedShelfFilter = ""
                                }
                            )
                        }
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        AdvancedInputField(
                            label = "Aisle",
                            value = draftAisle,
                            onValueChange = { draftAisle = it },
                            modifier = Modifier.weight(1f)
                        )
                        AdvancedInputField(
                            label = "Shelf",
                            value = draftShelf,
                            onValueChange = { draftShelf = it },
                            modifier = Modifier.weight(1f)
                        )
                    }

                    Button(
                        onClick = {
                            viewModel.appliedAisleFilter = draftAisle
                            viewModel.appliedShelfFilter = draftShelf
                            isAdvancedFilterOpen = false
                        },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF3B82F6)),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text("Apply Filters", color = Color.White, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))
        Divider(color = Color(0xFF1B263B), thickness = 1.dp)

        // --- FILTERED LIST & EMPTY STATE ---
        if (viewModel.filteredInventory.isEmpty()) {
            Column(
                modifier = Modifier.fillMaxSize().padding(32.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("No items found", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.height(8.dp))
                Text("Try adjusting your search or clearing active filters.", color = Color.Gray, textAlign = TextAlign.Center, fontSize = 14.sp)
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(viewModel.filteredInventory) { slot ->
                    val currentCount = viewModel.slotCounts[slot.name] ?: 0
                    DetailedItemCard(slot = slot, count = currentCount)
                }
            }
        }
    }
}

@Composable
fun AdvancedInputField(label: String, value: String, onValueChange: (String) -> Unit, modifier: Modifier = Modifier) {
    TextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier,
        label = { Text(label, color = Color.Gray, fontSize = 12.sp) },
        colors = TextFieldDefaults.textFieldColors(
            backgroundColor = Color(0xFF0D1B2A),
            textColor = Color.White,
            unfocusedIndicatorColor = Color.Gray.copy(alpha = 0.5f),
            focusedIndicatorColor = Color(0xFF3B82F6),
            cursorColor = Color(0xFF3B82F6)
        ),
        shape = RoundedCornerShape(8.dp),
        singleLine = true
    )
}

@Composable
fun DetailedItemCard(slot: SlotData, count: Int) {
    val isLow = count < slot.threshold

    Card(
        backgroundColor = Color(0xFF1B263B),
        shape = RoundedCornerShape(16.dp),
        elevation = 0.dp
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Top Row: Name and Count
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = slot.name,
                    color = Color.White,
                    fontWeight = FontWeight.ExtraBold,
                    fontSize = 18.sp,
                    modifier = Modifier.weight(1f)
                )

                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "$count",
                        color = if (isLow) Color(0xFFE63946) else Color(0xFF52B788),
                        fontWeight = FontWeight.Black,
                        fontSize = 28.sp
                    )
                    Text(
                        text = if (isLow) "LOW STOCK" else "IN STOCK",
                        color = if (isLow) Color(0xFFE63946) else Color(0xFF52B788),
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))
            Divider(color = Color.White.copy(alpha = 0.1f))
            Spacer(modifier = Modifier.height(12.dp))

            // Information Grid
            Row(modifier = Modifier.fillMaxWidth()) {
                InfoBlock(label = "AISLE", value = slot.aisle ?: "N/A", modifier = Modifier.weight(1f))
                InfoBlock(label = "SHELF", value = slot.shelfNumber ?: "N/A", modifier = Modifier.weight(1f))
                InfoBlock(label = "MIN REQ", value = "${slot.threshold}", modifier = Modifier.weight(1f))
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Products Allowed (Valid Classes)
            Text("PRODUCTS ALLOWED", color = Color.Gray, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.height(4.dp))
            Row(modifier = Modifier.horizontalScroll(rememberScrollState())) {
                if (slot.validClasses.isEmpty()) {
                    Badge(text = "None specified", color = Color.Gray)
                } else {
                    slot.validClasses.forEach { className ->
                        Badge(text = className, color = Color(0xFF3B82F6))
                        Spacer(modifier = Modifier.width(6.dp))
                    }
                }
            }
        }
    }
}

@Composable
fun InfoBlock(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier = modifier) {
        Text(text = label, color = Color.Gray, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        Text(text = value, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun Badge(text: String, color: Color) {
    Surface(
        color = color.copy(alpha = 0.15f),
        shape = RoundedCornerShape(4.dp)
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold
        )
    }
}