package com.example.vizistock

import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import com.example.vizistock.model.ActivityLog
import com.example.vizistock.model.BBox
import com.example.vizistock.model.CameraConfig
import com.example.vizistock.model.Detection
import com.example.vizistock.model.MasterConfig
import com.example.vizistock.model.SlotData
import com.google.firebase.Firebase
import com.google.firebase.firestore.ListenerRegistration
import com.google.firebase.firestore.Query
import com.google.firebase.firestore.firestore
import com.google.firebase.firestore.toObject

class ShelfViewModel : ViewModel() {
    private val db = Firebase.firestore
    var currentCameraId by mutableStateOf("cam_0")
    private var isInitialSync = true

    var recentActivities = mutableStateListOf<ActivityLog>()
        private set

    var isLive by mutableStateOf(false)
        private set

    var slotCounts = mutableStateMapOf<String, Int>()
        private set

    var totalItemsRaw by mutableStateOf(0)
        private set

    var misplacedCount by mutableStateOf(0)
        private set

    var alerts by mutableStateOf<List<String>>(emptyList())
        private set

    var currentDetections by mutableStateOf<List<Detection>>(emptyList())
        private set

    var currentImageUrl by mutableStateOf<String?>(null)
        private set

    var shelfConfig by mutableStateOf<CameraConfig?>(null)
    var allCameras by mutableStateOf<MasterConfig?>(null)

    var latestImageUrl by mutableStateOf<String?>(null)
        private set

    //track listeners
    private var inventoryListener: ListenerRegistration? = null
    private var planogramListener: ListenerRegistration? = null
    private var logsListener: ListenerRegistration? = null

    fun switchCamera(cameraId: String) {
        if (currentCameraId == cameraId && inventoryListener != null) return

        Log.d("VIZI_DEBUG", "Switching to camera: $cameraId")

        // 1. Stop all current listeners
        inventoryListener?.remove()
        planogramListener?.remove()
        logsListener?.remove()

        // 2. Reset UI state to prevent flickering of old data
        currentDetections = emptyList()
        totalItemsRaw = 0
        misplacedCount = 0
        alerts = emptyList()
        recentActivities.clear()
        isLive = false

        // 3. Restart syncing with new ID
        startSyncing(cameraId)
    }

    fun startSyncing(cameraId: String) {
        this.currentCameraId = cameraId
        this.isInitialSync = true
        Log.d("VIZI_DEBUG", "Starting sync for $cameraId")

        // 1. Sync Planogram (master_config)
        planogramListener = db.collection("planograms").document("master_config")
            .addSnapshotListener { snapshot, error ->
                if (error != null) return@addSnapshotListener
                val master = snapshot?.toObject<MasterConfig>()
                allCameras = master

                // Map the camera ID to the correct field in master_config
                shelfConfig = when (cameraId) {
                    "cam_0", "shelf_0" -> master?.cam0
                    "cam_1", "shelf_1" -> master?.cam1
                    else -> null
                }
                refreshStockStatus(currentDetections, shelfConfig)
            }

        // 2. Sync Inventory Data
        inventoryListener = db.collection("inventory_current")
            .document(cameraId)
            .addSnapshotListener { snapshot, error ->
                if (error != null || snapshot == null || !snapshot.exists()) {
                    isLive = false
                    return@addSnapshotListener
                }

                isLive = true
                currentImageUrl = snapshot.getString("raw_image_url")
                latestImageUrl = currentImageUrl

                val slotsData = snapshot.get("slots") as? Map<String, Any> ?: emptyMap()
                val detectionsList = mutableListOf<Detection>()
                var totalCount = 0

                slotsData.forEach { (slotKey, slotValue) ->
                    val slotMap = slotValue as? Map<String, Any> ?: emptyMap()
                    val itemsMap = slotMap["items"] as? Map<String, Any> ?: emptyMap()

                    itemsMap.forEach { (itemKey, itemValue) ->
                        val details = itemValue as? Map<String, Any> ?: emptyMap()
                        val bboxMap = details["bbox"] as? Map<String, Any> ?: emptyMap()
                        val isResolved = details["status"] == "resolved"

                        val x1 = (bboxMap["x1"] as? Number)?.toFloat() ?: 0f
                        val x2 = (bboxMap["x2"] as? Number)?.toFloat() ?: 0f
                        val y1 = (bboxMap["y1"] as? Number)?.toFloat() ?: 0f
                        val y2 = (bboxMap["y2"] as? Number)?.toFloat() ?: 0f

                        val tempDetection = Detection(
                            label = details["sam3_detected_class"] as? String ?: "Unknown",
                            centerX = (x1 + x2) / 2.0,
                            confidence = 1.0,
                            bbox = BBox(x1 = x1, x2 = x2, y1 = y1, y2 = y2), // Simplified
                            slotKey = slotKey,
                            itemKey = itemKey
                        )

                        // Resolution logic
                        if (isResolved) {
                            detectionsList.add(tempDetection.copy(isMisplaced = false, expectedSlotProduct = "Resolved"))
                        } else {
                            val slot = findSlotForDetection(tempDetection)
                            val labelLower = tempDetection.label.lowercase()
                            val isAuthorized = slot?.validClasses?.any { it.lowercase().contains(labelLower) } ?: true
                            detectionsList.add(tempDetection.copy(isMisplaced = !isAuthorized, expectedSlotProduct = slot?.validClasses?.firstOrNull() ?: "Correct Product"))
                        }
                        totalCount++
                    }
                }
                currentDetections = detectionsList
                totalItemsRaw = totalCount
                refreshStockStatus(detectionsList, shelfConfig)
            }

        // 3. Sync Logs
        logsListener = db.collection("activity_logs")
            .document(cameraId)
            .collection("logs")
            .orderBy("timestamp", Query.Direction.DESCENDING)
            .limit(10)
            .addSnapshotListener { snapshot, error ->
                if (error != null) return@addSnapshotListener
                val newLogs = snapshot?.documents?.mapNotNull { it.toObject<ActivityLog>() } ?: emptyList()
                recentActivities.clear()
                recentActivities.addAll(newLogs)
            }

    }
    fun clearActivities() {
        // 1. Target the correct path: activity_logs -> [shelf_id] -> logs
        val logsCollection = db.collection("activity_logs")
            .document(currentCameraId)
        val subCollection = logsCollection.collection("logs")

        subCollection.get()
            .addOnSuccessListener { snapshot ->
                // 2. Delete each document in the sub-collection
                val batch = db.batch()
                for (document in snapshot.documents) {
                    batch.delete(document.reference)
                }

                // 3. Commit the changes to Firestore
                batch.commit().addOnSuccessListener {
                    Log.d("VIZI_DEBUG", "Logs cleared for $currentCameraId")
                    // No need to manually clear the list;
                    // the SnapshotListener will see the deletion and update the UI automatically.
                }
            }
            .addOnFailureListener { e ->
                Log.e("VIZI_DEBUG", "Failed to clear logs: ${e.message}")
            }
    }

    fun findSlotForDetection(det: Detection): SlotData? {
        val config = shelfConfig ?: return null
        // centerX is already normalized (0.0 - 1.0) by the GPU server
        val normalizedX = det.centerX

        return config.planogram.values.find { slot ->
            normalizedX >= slot.xStart && normalizedX <= slot.xEnd
        }
    }

    fun updateThreshold(cameraId: String, slotKey: String, newThreshold: Int) {
        // Path: planograms/master_config -> cameraID.planogram.slotKey.threshold
        val docRef = db.collection("planograms").document("master_config")

        val dbKey = when (cameraId) {
            "shelf_0", "cam_0" -> "cam_0"
            "shelf_1", "cam_1" -> "cam_1"
            else -> cameraId
        }

        // 2. Build the path using the correct Database Key
        val fieldPath = "$dbKey.planogram.$slotKey.threshold"

        Log.d("VIZI_DEBUG", "Updating Firestore path: $fieldPath to $newThreshold")

        docRef.update(fieldPath, newThreshold)
            .addOnSuccessListener {
                Log.d("VIZI_DEBUG", "Successfully updated $slotKey!")
            }
            .addOnFailureListener { e ->
                Log.e("VIZI_DEBUG", "Update failed for $fieldPath", e)
            }
    }

    fun resolveDetection(cameraId: String, detection: Detection) {
        val fieldPath = "slots.${detection.slotKey}.items.${detection.itemKey}.app_misplaced_status"

        Log.d("VIZI_DEBUG", "Resolving item in Firestore: $fieldPath")

        db.collection("inventory_current")
            .document(cameraId)
            .update(fieldPath, "resolved")
            .addOnSuccessListener {
                logActivity("Resolved misplaced item: ${detection.label}")
                Log.d("VIZI_DEBUG", "Successfully resolved ${detection.label} in cloud.")
            }
            .addOnFailureListener { e ->
                Log.e("VIZI_DEBUG", "Cloud resolution failed", e)
            }
    }

    private fun refreshStockStatus(detections: List<Detection>, config: CameraConfig?) {
        val newCounts = mutableMapOf<String, Int>()
        val activeAlerts = mutableListOf<String>()
        var tempMisplacedCount = 0

        // 1. Calculate counts (Always do this)
        detections.forEach { det ->
            val slot = findSlotForDetection(det)
            if (slot != null) {
                if (det.isMisplaced) {
                    tempMisplacedCount++
                } else {
                    // If it's NOT misplaced (either correct OR resolved),
                    // count it as valid stock for that slot.
                    newCounts[slot.name] = (newCounts[slot.name] ?: 0) + 1
                }
            }
        }

        // 2. ONLY Process Alerts and Logging if the system is Live
        // This prevents "Connecting..." noise from appearing in your logs
        if (isLive) {
            config?.planogram?.values?.forEach { slot ->
                val currentCount = newCounts[slot.name] ?: 0
                val alertMessage = "${slot.name} is below threshold!"

                val isCurrentlyBelow = currentCount < slot.threshold
                val wasAlreadyAlerting = alerts.contains(alertMessage)

                if (isCurrentlyBelow) {
                    activeAlerts.add(alertMessage)

                    if (!wasAlreadyAlerting && !isInitialSync) {
                        logActivity("Low stock alert: ${slot.name}")
                    }
                } else if (wasAlreadyAlerting && !isInitialSync) {
                    logActivity("Restocked: ${slot.name}")
                }
            }

            if (isInitialSync && config != null) {
                isInitialSync = false
                Log.d("VIZI_DEBUG", "Initial sync complete. Logging enabled.")
            }

            // Only update the global alerts state when live
            alerts = activeAlerts
        }

        // 3. Always update counts and misplaced state
        slotCounts.clear()
        slotCounts.putAll(newCounts)
        misplacedCount = tempMisplacedCount
    }

    private fun logActivity(message: String) {
        val log = ActivityLog(message = message)

        // We store logs under the specific camera so they stay organized
        db.collection("activity_logs")
            .document(currentCameraId)
            .collection("logs")
            .add(log)
            .addOnSuccessListener {
                Log.d("VIZI_DEBUG", "Log saved to activity_logs/$currentCameraId/logs")
            }
            .addOnFailureListener { e ->
                Log.e("VIZI_DEBUG", "Failed to save log: ${e.message}")
            }
    }

    var inventorySearchQuery by mutableStateOf("")
    var appliedAisleFilter by mutableStateOf("")
    var appliedShelfFilter by mutableStateOf("")

    val filteredInventory: List<SlotData>
        get() {
            val allSlots = shelfConfig?.planogram?.values?.toList() ?: emptyList()

            return allSlots.filter { slot ->
                // 1. Text Search Logic (Quick Search)
                val matchesSearch = if (inventorySearchQuery.isEmpty()) {
                    true
                } else {
                    slot.name.contains(inventorySearchQuery, ignoreCase = true) ||
                            slot.validClasses.any { it.contains(inventorySearchQuery, ignoreCase = true) }
                }

                // 2. Advanced Aisle Logic
                val matchesAisle = if (appliedAisleFilter.isEmpty()) {
                    true
                } else {
                    (slot.aisle ?: "").contains(appliedAisleFilter, ignoreCase = true)
                }

                // 3. Advanced Shelf Logic
                val matchesShelf = if (appliedShelfFilter.isEmpty()) {
                    true
                } else {
                    (slot.shelfNumber ?: "").contains(appliedShelfFilter, ignoreCase = true)
                }

                // An item must match ALL active criteria to be shown
                matchesSearch && matchesAisle && matchesShelf
            }
        }
}
