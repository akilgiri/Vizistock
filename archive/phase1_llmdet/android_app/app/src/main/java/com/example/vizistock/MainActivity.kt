package com.example.vizistock

import android.os.Bundle
import android.util.Log
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.runtime.*
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.google.firebase.Timestamp
import com.google.firebase.firestore.DocumentChange
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.toObject

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val db = FirebaseFirestore.getInstance()

        setContent {
            val shelfData = remember { mutableStateListOf<Data>() }
            var triggerRefresh by remember { mutableStateOf(0) }

            // Manual refresh data from Firestore
            LaunchedEffect(triggerRefresh) {
                db.collection("detectionData").get().addOnSuccessListener { snapshots ->
                    val newItems = snapshots.map { doc ->
                        val baseData = doc.toObject(Data::class.java)
                        val timestamp = doc.getTimestamp("timestamp")
                        baseData.copy(id = doc.id, timeStamp = timestamp)
                    }

                    for (item in newItems) {
                        val index = shelfData.indexOfFirst { it.id == item.id }
                        if (index == -1) {
                            shelfData.add(item)
                        } else {
                            shelfData[index] = item
                        }
                    }
                    val currentIds = newItems.map { it.id }.toSet()
                    shelfData.removeAll { it.id !in currentIds }
                }
            }

            // Real-time listener
            LaunchedEffect(Unit) {
                db.collection("detectionData").addSnapshotListener { snapshots, e ->
                    if (e != null) {
                        Log.w("Firestore", "Listen failed.", e)
                        return@addSnapshotListener
                    }

                    if (snapshots != null) {
                        for (change in snapshots.documentChanges) {
                            val doc = change.document
                            val baseData = doc.toObject(Data::class.java)
                            val timestamp = doc.getTimestamp("timestamp")
                            val newData = baseData.copy(id = doc.id, timeStamp = timestamp)

                            when (change.type) {
                                DocumentChange.Type.ADDED -> {
                                    if (shelfData.none { it.id == newData.id }) {
                                        shelfData.add(newData)
                                    }
                                }
                                DocumentChange.Type.MODIFIED -> {
                                    val index = shelfData.indexOfFirst { it.id == newData.id }
                                    if (index != -1) shelfData[index] = newData
                                }
                                DocumentChange.Type.REMOVED -> {
                                    shelfData.removeAll { it.id == newData.id }
                                }
                            }
                        }
                    }
                }
            }

            AppNavHost(
                db = db,
                shelfData = shelfData.sortedByDescending { it.timeStamp?.toDate() },
                onRefresh = { triggerRefresh++ }
            )
        }
    }
}

@Composable
fun AppNavHost(db: FirebaseFirestore, shelfData: List<Data>, onRefresh: () -> Unit) {
    val navController = rememberNavController()

    NavHost(
        navController = navController,
        startDestination = "homePage"
    ) {
        composable("homePage") { HomePage(navController, onRefresh) }
//        composable("productListScreen") { ProductListScreen(navController, sampleProducts) }
        composable("shelfItemScreen") { ShelfItemsDetected(navController, shelfData) }
    }
}
