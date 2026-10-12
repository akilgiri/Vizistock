import cv2
import time
import os
import json
import numpy as np
import motion_detection as diff_lib
from common import (
    CAMERA_ID, init_firebase, start_camera,
    get_timestamped_filepath, upload_to_firebase, send_to_inference_server,
)

# --- CONFIGURATION ---
IDLE_POLL_INTERVAL = 5.0
ACTIVE_MOTION_INTERVAL = 0.5
CONFIG_PATH = os.getenv("PLANOGRAM_CONFIG", "planogram_config.json")

# Algorithm specific area thresholds
MOG2_THRESHOLD = 1500
SSIM_THRESHOLD = 275000  # SSIM runs on native 8MP, so the area is much larger

# Local directory for saving debug images
OUTPUT_DIR = "debug_frames"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# CONFIGURATION LOADERS & MASKS
# ==========================================
def load_shelf_mask_points(config_path, cam_id):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        raw_points = config[cam_id]["calibration"]["source_points"]
        return np.array(raw_points).reshape(-1, 2).astype(np.int32)
    except Exception as e:
        print(f"Warning: Could not load shelf mask from config: {e}")
        return None

def load_planogram_config(config_path, cam_id):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        calib = config[cam_id]["calibration"]
        H_matrix = np.array(calib["homography_matrix"], dtype=np.float32).reshape(3, 3)
        virtual_w, _ = calib["virtual_dim"]
        planogram_data = config[cam_id]["planogram"]
        return H_matrix, virtual_w, planogram_data
    except Exception as e:
        print(f"Warning: Could not load planogram from config: {e}")
        return None, None, None

def apply_poly_mask(img, pts):
    if pts is None:
        return img
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    return cv2.bitwise_and(img, img, mask=mask)

def save_debug_images(image, boxes, mask, suffix):
    debug_img = image.copy()
    for (x, y, w, h) in boxes:
        cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 0, 255), 4)
        
    timestamp = int(time.time())
    
    img_filename = os.path.join(OUTPUT_DIR, f"{CAMERA_ID}_HYBRID_{suffix}_{timestamp}_IMG.jpg")
    mask_filename = os.path.join(OUTPUT_DIR, f"{CAMERA_ID}_HYBRID_{suffix}_{timestamp}_MASK.jpg")
    
    cv2.imwrite(img_filename, debug_img)
    cv2.imwrite(mask_filename, mask)
    
    print(f"📸 Saved Event: {timestamp}")
    print(f"   -> Image: {img_filename}")
    print(f"   -> Mask:  {mask_filename}")

# ==========================================
# MAIN HARDWARE LOOP
# ==========================================
def main():
    init_firebase()
    shelf_points = load_shelf_mask_points(CONFIG_PATH, CAMERA_ID)
    H_matrix, virtual_w, planogram_data = load_planogram_config(CONFIG_PATH, CAMERA_ID)

    picam2 = start_camera()

    print("Capturing initial baseline...")
    try:
        raw_baseline_rgb = picam2.capture_array()
        raw_baseline = cv2.cvtColor(raw_baseline_rgb, cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"Failed to grab initial frame: {e}")
        picam2.stop()
        return

    # --- PHASE 1: COLD START WARMUP ---
    print(f"[{CAMERA_ID}] Warming up MOG2 background model (100 frames)...")
    for _ in range(100):
        warmup_rgb = picam2.capture_array()
        warmup_bgr = cv2.cvtColor(warmup_rgb, cv2.COLOR_RGB2BGR)
        warmup_masked = apply_poly_mask(warmup_bgr, shelf_points)
        diff_lib.get_diff_boxes_mog2(warmup_masked, threshold_area=MOG2_THRESHOLD, learning_rate=-1.0)

    # Send the first mapped image to the inference server
    print(f"[{CAMERA_ID}] Sending initial frame for baseline planogram mapping...")
    init_filename = get_timestamped_filepath()
    cv2.imwrite(init_filename, raw_baseline)

    cloud_path = upload_to_firebase(init_filename)
    send_to_inference_server(init_filename, diff_boxes=[], is_first_frame=True, cloud_path=cloud_path)

    print(f"[{CAMERA_ID}] Monitoring started. Using Hybrid (MOG2 + SSIM)")
    print(f"[{CAMERA_ID}] Polling every {IDLE_POLL_INTERVAL} seconds.")

    try:
        while True:
            # --- PHASE 2: IDLE POLLING (Frozen Memory - MOG2) ---
            time.sleep(IDLE_POLL_INTERVAL)
            
            raw_curr_rgb = picam2.capture_array()
            raw_curr = cv2.cvtColor(raw_curr_rgb, cv2.COLOR_RGB2BGR)
            curr_img = apply_poly_mask(raw_curr, shelf_points)

            motion_boxes, _, _ = diff_lib.get_diff_boxes_mog2(curr_img, threshold_area=MOG2_THRESHOLD)
            
            # --- PHASE 3: ACTIVE MOTION DETECTED (Consecutive SSIM) ---
            if len(motion_boxes) > 0:
                print(f"[{CAMERA_ID}] Tripwire triggered! Entering active SSIM fast-polling...")
                
                # Snapshot the initial moving frame to start the T vs T-1 chain
                prev_fast_curr = curr_img.copy()
                while True:
                    time.sleep(ACTIVE_MOTION_INTERVAL)
                    raw_fast_curr_rgb = picam2.capture_array()
                    raw_fast_curr = cv2.cvtColor(raw_fast_curr_rgb, cv2.COLOR_RGB2BGR)
                    fast_curr = apply_poly_mask(raw_fast_curr, shelf_points)
                    
                    # Compare T against T-1 with SSIM
                    fast_motion, _ = diff_lib.get_diff_boxes_ssim(
                        prev_fast_curr, 
                        fast_curr, 
                        threshold_area=SSIM_THRESHOLD
                    )
                    
                    # Update curr_img so Phase 4 grades the final settled state against the baseline
                    curr_img = fast_curr.copy()
                    
                    if len(fast_motion) == 0:
                        print(f"[{CAMERA_ID}] Hand removed. SSIM confirms shelf has settled.")
                        break
                    else:
                        print("   ...SSIM still detecting structural movement...")

                    # Push the current frame back to be the "previous" frame for the next loop
                    prev_fast_curr = fast_curr.copy()

            # --- PHASE 4: CONFIRMED MISSING (MOG2 Baseline Check) ---
            diff_boxes, raw_mask, changed_slots = diff_lib.get_diff_boxes_mog2(
                curr_img, 
                threshold_area=MOG2_THRESHOLD,
                H_matrix=H_matrix,
                max_w=virtual_w,
                planogram_data=planogram_data
            )
            
            if len(diff_boxes) > 0:
                names = [s['product_name'] for s in changed_slots]
                print(f"[{CAMERA_ID}] Inventory change confirmed: {names}. Triggering pipeline.")
                
                save_debug_images(raw_curr, diff_boxes, raw_mask, "CHANGE_DETECTED")
                
                img_filename = get_timestamped_filepath()
                cv2.imwrite(img_filename, raw_curr) 
                
                cloud_path = upload_to_firebase(img_filename)
                send_to_inference_server(img_filename, diff_boxes, is_first_frame=False, cloud_path=cloud_path)
                
                # --- PHASE 5: THE BACKGROUND RESET (Eraser) ---
                print(f"[{CAMERA_ID}] Rebuilding MOG2 background to erase ghost. Please do not touch shelf...")
                for _ in range(100):
                    reset_rgb = picam2.capture_array()
                    reset_bgr = cv2.cvtColor(reset_rgb, cv2.COLOR_RGB2BGR)
                    reset_masked = apply_poly_mask(reset_bgr, shelf_points)
                    
                    diff_lib.get_diff_boxes_mog2(reset_masked, threshold_area=MOG2_THRESHOLD, learning_rate=-1.0)
                    
                print(f"[{CAMERA_ID}] Reset complete. Returning to Idle Polling.")

    except KeyboardInterrupt:
        print("\nStopping camera node...")
    finally:
        picam2.stop()

if __name__ == "__main__":
    main()