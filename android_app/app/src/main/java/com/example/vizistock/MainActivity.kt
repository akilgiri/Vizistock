package com.example.vizistock

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.vizistock.ui.HomeScreen
import com.example.vizistock.ui.ItemInventoryScreen
import com.example.vizistock.ui.MisplacedProductsScreen
import com.example.vizistock.ui.ShelfInventoryScreen
import com.example.vizistock.ui.ShelfOverviewScreen

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            // viewModel() requires: androidx.lifecycle.viewmodel.compose.viewModel
            val viewModel: ShelfViewModel = viewModel()

            // LaunchedEffect ensures syncing starts once when the composition begins
            LaunchedEffect(Unit) {
                viewModel.switchCamera("cam_0") // Default camera on launch; users can switch on the home screen
            }

            AppNavHost(viewModel)
        }
    }
}

@Composable
fun AppNavHost(viewModel: ShelfViewModel) {
    // rememberNavController requires: androidx.navigation.compose.rememberNavController
    val navController = rememberNavController()
    val activeCameraId = viewModel.currentCameraId

    // NavHost requires: androidx.navigation.compose.NavHost
    NavHost(navController = navController, startDestination = "home") {
        composable("home") {
            HomeScreen(navController, viewModel)
        }
        composable("shelfOverview") {
            ShelfOverviewScreen(
                viewModel = viewModel,
                navController = navController,
                cameraId = activeCameraId
            )
        }
        composable("misplacedProducts") {
            MisplacedProductsScreen(viewModel, navController)
        }
        composable("shelfInventory") {
            ShelfInventoryScreen(viewModel, navController)
        }
        composable("itemInventory") {
            ItemInventoryScreen(viewModel, navController)
        }

    }
}