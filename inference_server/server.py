import asyncio
import json
import cv2
import numpy as np
import os
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, Form
import uvicorn
from dotenv import load_dotenv
import urllib.parse

import firebase_admin
from firebase_admin import credentials, firestore, storage

from sam3_segmenter import VizistockSAM3Gatekeeper
from gemini_verifier import VizistockGeminiAuditor

load_dotenv()

app = FastAPI(title="ViziStock Inference Server")

# --- CENTRALIZED STATE & QUEUES ---
lock = asyncio.Lock()
latest_frames = {}           # Holds raw incoming frames from Raspberry Pi
pending_gemini_tasks = {}    # Holds ONLY the latest SAM3 output for Gemini
gemini_trigger = asyncio.Event()

# The Single Source of Truth for what is currently on the shelf
master_inventory_state = {}

gemini_rate_limiter = asyncio.Semaphore(2)
ENABLE_DEBUG_STORAGE = os.getenv("ENABLE_DEBUG_STORAGE", "true").lower() == "true"

# --- INITIALIZE FIREBASE & MODELS ---
CRED_PATH = os.getenv("FIREBASE_CREDENTIALS", "firebase-service-account.json")
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET")
try:
    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred, {'storageBucket': BUCKET_NAME})
    db = firestore.client()
    bucket = storage.bucket()
    print("[SYSTEM] Connected to Firestore and Storage.")
except Exception as e:
    raise SystemExit(f"[SYSTEM] Firebase init failed: {e}")

CONFIG_PATH = os.getenv("PLANOGRAM_CONFIG", "planogram_config.json")
sam3_gatekeeper = VizistockSAM3Gatekeeper(CONFIG_PATH)
gemini_auditor = VizistockGeminiAuditor(api_key=os.getenv("GEMINI_API_KEY"))


# --- UNIFIED FIRESTORE SYNC ---

def sync_state_to_firestore(camera_id):
    """Mirrors the internal master state to Firestore and logs history with timestamp IDs."""
    if camera_id not in master_inventory_state:
        return
        
    now_utc = datetime.now(timezone.utc)
    state_copy = master_inventory_state[camera_id].copy()
    state_copy["last_updated"] = now_utc.isoformat()
    
    # 1. Overwrite current state (for the live dashboard)
    db.collection('inventory_current').document(camera_id).set(state_copy)
    
    # 2. Append to historical log using a readable Timestamp ID
    # Format: cam_1_20260304_184530
    timestamp_id = now_utc.strftime("%Y%m%d_%H%M%S")
    doc_id = f"{camera_id}_{timestamp_id}"
    
    db.collection('inventory_history').document(doc_id).set(state_copy)
    
    print(f"[FIRESTORE] Synced state & history ({doc_id}). Status: {state_copy['pipeline_status']}")

def log_cycle_to_firestore(camera_id, class_mismatches, variant_mismatches):
    if not class_mismatches and not variant_mismatches:
        return 
        
    now_utc = datetime.now(timezone.utc)
    timestamp_id = now_utc.strftime("%Y%m%d_%H%M%S")
    doc_id = f"{camera_id}_errors_{timestamp_id}"

    db.collection('inventory_logs').document(doc_id).set({
        "camera_id": camera_id,
        "timestamp": now_utc.isoformat(),
        "total_errors": len(class_mismatches) + len(variant_mismatches),
        "class_mismatches": [{"slot_id": i['slot_id'], "detected": i['label'], "expected": i['expected_product']} for i in class_mismatches],
        "variant_mismatches": [{"slot_id": i['slot_id'], "expected": i['expected_product'], "conclusion": i.get('conclusion', '')} for i in variant_mismatches]
    })


# --- DEBUG STORAGE ---

def upload_gemini_debug_artifacts(camera_id, image_np, gemini_results):
    if not ENABLE_DEBUG_STORAGE: return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_img = image_np.copy()
    img_h, img_w = report_img.shape[:2]
    
    for res in gemini_results:
        status = res.get('api_status', 'ERROR')
        if status == "MATCH": continue 
            
        bbox = res['bbox'] 
        x1, y1 = int(bbox['x1'] * img_w), int(bbox['y1'] * img_h)
        x2, y2 = int(bbox['x2'] * img_w), int(bbox['y2'] * img_h)
        
        color = (0, 0, 255) if status == "MISMATCH" else (0, 165, 255)
        cv2.rectangle(report_img, (x1, y1), (x2, y2), color, 4)
        label = f"{status}: {res['expected_product'][:15]}"
        cv2.putText(report_img, label, (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    _, buffer = cv2.imencode('.jpg', report_img)
    bucket.blob(f"gemini_results/{camera_id}_{timestamp}_audit.jpg").upload_from_string(buffer.tobytes(), content_type='image/jpeg')
    bucket.blob(f"gemini_results/{camera_id}_{timestamp}_audit.json").upload_from_string(json.dumps(gemini_results, indent=4), content_type='application/json')

def upload_sam3_debug_artifacts(camera_id, image_np, items):
    if not ENABLE_DEBUG_STORAGE: return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    debug_img = image_np.copy()
    img_h, img_w = debug_img.shape[:2]

    # 1. Draw Bounding Boxes (NO MASKS)
    for item in items:
        bbox = item['bbox']
        x1, y1 = int(bbox['x1'] * img_w), int(bbox['y1'] * img_h)
        x2, y2 = int(bbox['x2'] * img_w), int(bbox['y2'] * img_h)
        cv2.rectangle(debug_img, (x1, y1), (x2, y2), (255, 0, 0), 2)
        label = f"{item['label']} ({item['confidence']:.2f})"
        cv2.putText(debug_img, label, (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    # 2. Draw Planogram Boundaries (Yellow Lines)
    try:
        cam_config = sam3_gatekeeper.planogram_config.get(camera_id)
        if cam_config:
            H = np.array(cam_config["calibration"]["homography_matrix"]).reshape(3, 3)
            H_inv = np.linalg.inv(H)
            virtual_w, virtual_h = cam_config["calibration"]["virtual_dim"]

            for slot_id, slot_info in cam_config["planogram"].items():
                x_start = slot_info["x_start"] * virtual_w
                x_end = slot_info["x_end"] * virtual_w

                # Define the top and bottom points of the shelf divider in virtual space
                pts = np.array([
                    [[x_start, 0]], [[x_start, virtual_h]],  # Left line
                    [[x_end, 0]], [[x_end, virtual_h]]       # Right line
                ], dtype=np.float32)

                # Project back to the camera's distorted view
                img_pts = cv2.perspectiveTransform(pts, H_inv)

                # Draw the left line
                cv2.line(debug_img, (int(img_pts[0][0][0]), int(img_pts[0][0][1])), 
                                    (int(img_pts[1][0][0]), int(img_pts[1][0][1])), (0, 255, 255), 3)
                # Draw the right line
                cv2.line(debug_img, (int(img_pts[2][0][0]), int(img_pts[2][0][1])), 
                                    (int(img_pts[3][0][0]), int(img_pts[3][0][1])), (0, 255, 255), 3)
    except Exception as e:
        print(f"Could not draw planogram lines for debug: {e}")

    _, buffer = cv2.imencode('.jpg', debug_img)
    bucket.blob(f"sam3_results/{camera_id}_{timestamp}_annotated.jpg").upload_from_string(buffer.tobytes(), content_type='image/jpeg')

def get_cached_gemini_state(state, slot_id, current_bbox):
    """Finds the identical item from the previous frame to cache its Gemini result."""
    if not state or slot_id not in state.get("slots", {}): 
        return None
    
    best_iou = 0.50 # Minimum overlap to consider it the "same" item
    cached_item = None
    
    cx1, cy1 = current_bbox['x1'], current_bbox['y1']
    cx2, cy2 = current_bbox['x2'], current_bbox['y2']
    
    for item_id, prev_item in state["slots"][slot_id]["items"].items():
        pb = prev_item['bbox']
        px1, py1, px2, py2 = pb['x1'], pb['y1'], pb['x2'], pb['y2']
        
        ix1, iy1 = max(cx1, px1), max(cy1, py1)
        ix2, iy2 = min(cx2, px2), min(cy2, py2)
        inter_area = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        
        if inter_area > 0:
            box1_area = (cx2 - cx1) * (cy2 - cy1)
            box2_area = (px2 - px1) * (py2 - py1)
            iou = inter_area / float(box1_area + box2_area - inter_area)
            
            if iou > best_iou:
                best_iou = iou
                cached_item = prev_item
                
    return cached_item

# --- ASYNC WORKERS ---

async def process_single_gemini_item(image_np, item):
    async with gemini_rate_limiter:
        api_result = await asyncio.to_thread(
            gemini_auditor.verify_item, 
            image_np, item['bbox'], item['expected_product'], item['slot_id'], item.get('mask_crop')  
        )
        item['api_status'] = api_result.get('status', 'ERROR')
        item['conclusion'] = api_result.get('conclusion', '')
        if 'mask_crop' in item: del item['mask_crop']
        return item

async def sam3_worker():
    print("Stage 1 (SAM3) worker started...")
    while True:
        camera_to_process = None
        payload = None

        async with lock:
            if latest_frames:
                camera_to_process, payload = latest_frames.popitem()

        if camera_to_process and payload:
            nparr = np.frombuffer(payload['image_bytes'], np.uint8)
            image_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            items = sam3_gatekeeper.process_frame(
                image_np=image_np, camera_id=camera_to_process,
                diff_boxes=payload['diff_boxes'], is_first_frame=payload['is_first_frame']
            )

            if ENABLE_DEBUG_STORAGE:
                await asyncio.to_thread(upload_sam3_debug_artifacts, camera_to_process, image_np, items)

            # 1. Update the Master State
            slots_data = {}
            prev_state = master_inventory_state.get(camera_to_process, {})

            for idx, item in enumerate(items):
                item['item_id'] = f"item_{idx}"
                slot_id = item['slot_id']
                if slot_id == "unknown_slot": continue

                if slot_id not in slots_data:
                    slots_data[slot_id] = {"expected_product": item['expected_product'], "items": {}}
                
                gemini_api_status = "SKIPPED"
                final_alert = "NONE"
                gemini_conclusion = ""

                # Evaluate Routing Status
                if item['routing_status'] == "CLASS_MISMATCH":
                    final_alert = "CLASS_MISMATCH"
                elif item['routing_status'] == "NEEDS_GEMINI":
                    gemini_api_status = "PENDING"
                elif item['routing_status'] == "UNCHANGED":
                    # It didn't move! Pull the old Gemini data using spatial matching.
                    cached = get_cached_gemini_state(prev_state, slot_id, item['bbox'])
                    if cached and cached["gemini_api_status"] != "PENDING":
                        gemini_api_status = cached["gemini_api_status"]
                        final_alert = cached["final_alert"]
                        gemini_conclusion = cached.get("gemini_conclusion", "Cached from previous scan.")
                    else:
                        # Fallback if tracking lost
                        item['routing_status'] = "NEEDS_GEMINI"
                        gemini_api_status = "PENDING"

                slots_data[slot_id]["items"][item['item_id']] = {
                    "sam3_detected_class": item['label'],
                    "routing_status": item['routing_status'],
                    "bbox": item['bbox'],
                    "gemini_api_status": gemini_api_status,
                    "final_alert": final_alert,
                    "gemini_conclusion": gemini_conclusion
                }

            pipeline_status = "AWAITING_GEMINI" if any(i['routing_status'] == 'NEEDS_GEMINI' for i in items) else "COMPLETED"
            
            master_inventory_state[camera_to_process] = {
                "camera_id": camera_to_process,
                "pipeline_status": pipeline_status,
                "raw_image_url": payload["raw_image_url"],
                "slots": slots_data
            }

            # Sync baseline state to Firestore immediately
            await asyncio.to_thread(sync_state_to_firestore, camera_to_process)

            # 2. Replace any pending Gemini task for this camera with the latest frame
            needs_gemini = [i for i in items if i['routing_status'] == "NEEDS_GEMINI"]
            if needs_gemini:
                async with lock:
                    pending_gemini_tasks[camera_to_process] = {
                        "image_np": image_np,
                        "needs_gemini": needs_gemini,
                        "class_mismatches": [i for i in items if i['routing_status'] == "CLASS_MISMATCH"]
                    }
                    gemini_trigger.set() # Wake up the Gemini worker
        else:
            await asyncio.sleep(0.05)

async def gemini_worker():
    print("Stage 2 (Gemini) worker started...")
    while True:
        await gemini_trigger.wait() # Wait until SAM3 drops a task
        
        camera_id = None
        payload = None
        
        async with lock:
            if not pending_gemini_tasks:
                gemini_trigger.clear()
                continue
            # Pop one camera's latest task. The intermediate frames are effectively deleted!
            camera_id, payload = pending_gemini_tasks.popitem()
            if not pending_gemini_tasks:
                gemini_trigger.clear()

        needs_gemini = payload['needs_gemini']
        image_np = payload['image_np']
        class_mismatches = payload['class_mismatches']

        print(f"\n[{camera_id}] [STAGE 2] Fanning out Gemini CoT for {len(needs_gemini)} products...")
        tasks = [process_single_gemini_item(image_np, item) for item in needs_gemini]
        results = await asyncio.gather(*tasks)
        
        # 3. Safely update the Master State (Check if item still exists!)
        state = master_inventory_state.get(camera_id)
        if state:
            for res in results:
                slot_id = res['slot_id']
                item_id = res['item_id']
                
                # If SAM3 overwrote the shelf and this item is gone, we gracefully skip updating it
                if slot_id in state["slots"] and item_id in state["slots"][slot_id]["items"]:
                    target_item = state["slots"][slot_id]["items"][item_id]
                    target_item["gemini_api_status"] = res['api_status']
                    target_item["final_alert"] = "PRODUCT_MISMATCH" if res['api_status'] == "MISMATCH" else "NONE"
                    target_item["gemini_conclusion"] = res.get('conclusion', '')
            
            # Check if any items are still pending; if not, mark pipeline as completed
            still_pending = any(
                item.get("gemini_api_status") == "PENDING"
                for slot in state["slots"].values()
                for item in slot["items"].values()
            )
            state["pipeline_status"] = "AWAITING_GEMINI" if still_pending else "COMPLETED"

            # Sync the finalized state to Firestore
            await asyncio.to_thread(sync_state_to_firestore, camera_id)

        variant_mismatches = [res for res in results if res['api_status'] == "MISMATCH"]

        if ENABLE_DEBUG_STORAGE and results:
            await asyncio.to_thread(upload_gemini_debug_artifacts, camera_id, image_np, results)

        await asyncio.to_thread(log_cycle_to_firestore, camera_id, class_mismatches, variant_mismatches)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(sam3_worker())
    asyncio.create_task(gemini_worker())

@app.post("/process_inventory")
async def process_inventory(
    camera_id: str = Form(...), 
    is_first_frame: str = Form(...),
    diff_boxes: str = Form(...),
    cloud_path: str = Form(...),
    image: UploadFile = File(...)
):
    image_bytes = await image.read()
    is_first = is_first_frame.lower() == 'true'
    parsed_boxes = json.loads(diff_boxes)
    
    # Safely encode the path to create a standard Firebase Storage Download URL
    encoded_path = urllib.parse.quote(cloud_path, safe='')
    raw_image_url = f"https://firebasestorage.googleapis.com/v0/b/{BUCKET_NAME}/o/{encoded_path}?alt=media"
    
    async with lock:
        latest_frames[camera_id] = {
            "image_bytes": image_bytes,
            "is_first_frame": is_first,
            "diff_boxes": parsed_boxes,
            "raw_image_url": raw_image_url
        }
        
    return {"status": "success"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))