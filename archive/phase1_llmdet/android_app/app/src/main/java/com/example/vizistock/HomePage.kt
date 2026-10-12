package com.example.vizistock

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.material3.ButtonDefaults
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.navigation.NavController
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun HomePage(navController: NavController, onRefresh: () -> Unit) {
    var lastUpdated by remember { mutableStateOf(getCurrentTime()) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0D1B2A))
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(modifier = Modifier.height(40.dp))

        Text(
            text = "ViziStock",
            fontSize = 40.sp,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            modifier = Modifier.padding(top = 32.dp)
        )

        Text(
            text = "Smart Shelf Monitoring App",
            fontSize = 18.sp,
            color = Color.LightGray,
            modifier = Modifier.padding(bottom = 32.dp)
        )

        Spacer(modifier = Modifier.height(20.dp))

        GridSection(navController)

//        StatCard("Total Item on Shelf", "135", null)

        Spacer(modifier = Modifier.height(32.dp))

        Button(
            onClick = { lastUpdated = getCurrentTime()
                      onRefresh() },
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1B263B))
        ) {
            Text(text = "Refresh", color = Color.White)
        }

        Spacer(modifier = Modifier.height(10.dp))

        Text(
            text = "Last Updated: $lastUpdated",
            fontSize = 16.sp,
            color = Color.LightGray
        )
    }
}

@Composable
fun GridSection(navController: NavController) {
    Column(modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally) {

        StatCard(title = "Total Items on Shelf", value = "135", valueColor = Color.White, navController = navController, navigate = "shelfItemScreen")
        Spacer(modifier = Modifier.height(12.dp))

        StatCard(title = "Low Stock Alerts", value = "5", valueColor = Color.Red, subText = "Below restock threshold", alert = true, navController = navController, navigate = "LowStock") //add threshold in this section
        Spacer(modifier = Modifier.height(12.dp))

        StatCard(title = "Trends", value = "Stable", valueColor = Color.White, subText = "Past 24 hours", navController = navController, navigate = "Trends")
        Spacer(modifier = Modifier.height(12.dp))

        StatCard(title = "Total Shelves", valueColor = Color.White, value = "10", navController = navController, navigate = "NumShelves")

    }
}

@Composable
fun StatCard(title: String, value: String, subText: String? = null, valueColor: Color = Color.Black, alert: Boolean = false, navController: NavController, navigate: String) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 60.dp)
            .clickable { navController.navigate(navigate) },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF121212))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = title, color = Color.White, fontSize = 16.sp)
            Spacer(modifier = Modifier.padding(8.dp))
            Text(text = value, color = valueColor, fontWeight = FontWeight.Bold, fontSize = 18.sp)
            if (subText != null) {
                Spacer(modifier = Modifier.padding(8.dp))
                Text(text = subText, color = Color.LightGray, fontSize = 14.sp)
            }
        }
    }
}

fun getCurrentTime():String {
    val currTime = SimpleDateFormat("MM dd, yyyy hh:mm a", Locale.getDefault())
    return currTime.format(Date())
}