import cv2
import time
import os
import json
import numpy as np
import test_image_diffv2 as diff_lib
from picamera2 import Picamera2
from libcamera import Transform


# --- CONFIGURATION ---
CAMERA_ID = "shelf_1"
IDLE_POLL_INTERVAL = 5.0
ACTIVE_MOTION_INTERVAL = 0.5 

# Options: 'custom' (Advanced SSIM + Morphology), 'ssim' (Raw SSIM), 'mog2'
ACTIVE_ALGORITHM = 'handtuned' 

# Tune these values based on your physical testing
AREA_THRESHOLDS = {
    'custom': 2500,    # Higher threshold + morphology fixes the fragmented glare boxes
    'ssim': 2500,      
    'mog2': 1500, 
    'handtuned': 200000, # Native resolution means much bigger contour areas     
}

# Use your specific username pathing if running on a local desktop/laptop
OUTPUT_DIR = "local_tests"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- CONFIGURATION LOADERS ---
def load_shelf_mask_points(config_path="local_master_config2.json", cam_id="cam_1"):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        raw_points = config[cam_id]["calibration"]["source_points"]
        return np.array(raw_points).reshape(-1, 2).astype(np.int32)
    except Exception as e:
        print(f"Warning: Could not load shelf mask from config: {e}")
        return None

def load_planogram_config(config_path="local_master_config2.json", cam_id="cam_1"):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        calib = config[cam_id]["calibration"]
        H_matrix = np.array(calib["homography_matrix"], dtype=np.float32).reshape(3, 3)
        virtual_w, _ = calib["virtual_dim"]
        planogram_data = config[cam_id]["planogram"]
        return H_matrix, virtual_w, planogram_data
    except Exception as e:
        return None, None, None

def apply_poly_mask(img, pts):
    """Blacks out everything outside the 4-point shelf polygon to ignore background room motion."""
    if pts is None:
        return img
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    return cv2.bitwise_and(img, img, mask=mask)

# --- ROUTER ---
def get_diff(img1, img2, pts=None, H_matrix=None, virtual_w=None, planogram_data=None):
    """Router function passing the dynamic threshold to the selected algorithm."""
    thresh = AREA_THRESHOLDS.get(ACTIVE_ALGORITHM, 1500)
    
    if ACTIVE_ALGORITHM == 'custom':
        # Create a boolean mask of the ROI for the custom pipeline
        roi_mask = np.zeros(img1.shape[:2], dtype=np.uint8)
        if pts is not None:
             cv2.fillPoly(roi_mask, [pts], 255)
        else:
             roi_mask.fill(255)
             
        boxes, raw_mask, slots = diff_lib.get_diff_boxes_custom(
            img1, img2, roi_mask, 
            threshold_area=thresh, 
            pixel_thresh=40,  # Add this line to increase sensitivity
            H_matrix=H_matrix, max_w=virtual_w, planogram_data=planogram_data
        )
        # Print detected planogram slots if available
        if slots:
             names = [s['product_name'] for s in slots]
             print(f"   -> Planogram mapped changes: {names}")
             
        return boxes, raw_mask

    elif ACTIVE_ALGORITHM == 'ssim':
        return diff_lib.get_diff_boxes_ssim(img1, img2, threshold_area=thresh)
        
    elif ACTIVE_ALGORITHM == 'mog2':
        return diff_lib.get_diff_boxes_mog2(img2, threshold_area=thresh)

    elif ACTIVE_ALGORITHM == 'handtuned':
        # NEW: Route directly to your hand-tuned method
        return diff_lib.get_diff_boxes_handtuned(img1, img2, threshold_area=thresh)
        
    return [], np.zeros(img1.shape[:2], dtype=np.uint8)

def save_debug_images(image, boxes, mask, suffix):
    """Saves the camera frame with bounding boxes AND the algorithm's raw mask."""
    debug_img = image.copy()
    for (x, y, w, h) in boxes:
        cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 0, 255), 4)
        
    timestamp = int(time.time())
    
    img_filename = os.path.join(OUTPUT_DIR, f"{CAMERA_ID}_{ACTIVE_ALGORITHM}_{suffix}_{timestamp}_IMG.jpg")
    mask_filename = os.path.join(OUTPUT_DIR, f"{CAMERA_ID}_{ACTIVE_ALGORITHM}_{suffix}_{timestamp}_MASK.jpg")
    
    cv2.imwrite(img_filename, debug_img)
    cv2.imwrite(mask_filename, mask)
    
    print(f"📸 Saved Event: {timestamp}")
    print(f"   -> Image: {img_filename}")
    print(f"   -> Mask:  {mask_filename}")

def main():
    # Load required configurations
    shelf_points = load_shelf_mask_points()
    H_matrix, virtual_w, planogram_data = load_planogram_config()

    # --- Initialize Picamera2 ---
    picam2 = Picamera2()
    
    # Note: Using video config here instead of still config. 
    # Fast polling (0.5s) on a 12MP still config might cause memory/latency issues on a Pi.
    # If your diff_lib requires full sensor resolution, you can swap this to create_still_configuration
    t = Transform(vflip=True, hflip=True)        # Configure the camera for still capture
    camera_config = picam2.create_still_configuration(
        main={"size": picam2.sensor_resolution},
        transform=t
    )

    picam2.configure(camera_config)
    picam2.start()
    
    time.sleep(2) # Allow camera sensor to warm up/auto-expose
    
    print("Capturing initial baseline...")
    try:
        raw_baseline_rgb = picam2.capture_array()
        raw_baseline = cv2.cvtColor(raw_baseline_rgb, cv2.COLOR_RGB2BGR) # Convert Picam RGB to OpenCV BGR
    except Exception as e:
        print(f"Failed to grab initial frame: {e}")
        picam2.stop()
        return

    # Apply the shelf mask immediately so algorithms don't register background noise
    baseline_img = apply_poly_mask(raw_baseline, shelf_points)

    # If using MOG2, feed the first masked frame repeatedly to initialize the background state
    if ACTIVE_ALGORITHM == 'mog2':
        print("Warming up MOG2 background model...")
        for _ in range(50):
            get_diff(baseline_img, baseline_img)

    prev_img = baseline_img.copy()
    print(f"[{CAMERA_ID}] Test Mode Started. Using Algorithm: {ACTIVE_ALGORITHM.upper()}")
    print(f"[{CAMERA_ID}] Current Area Threshold: {AREA_THRESHOLDS.get(ACTIVE_ALGORITHM, 'Default')}")


    print("STARTING MAIN LOOP")
    try:
        while True:
            time.sleep(IDLE_POLL_INTERVAL)
            
            # Capture frame as numpy array
            raw_curr_rgb = picam2.capture_array()
            raw_curr = cv2.cvtColor(raw_curr_rgb, cv2.COLOR_RGB2BGR)
            
            curr_img = apply_poly_mask(raw_curr, shelf_points)

            # --- FAST ACTIVE MOTION LOOP ---
            motion_boxes, _ = get_diff(prev_img, curr_img, shelf_points, H_matrix, virtual_w, planogram_data)
            
            if len(motion_boxes) > 0:
                print(f"[{CAMERA_ID}] Motion detected! Entering active fast-polling ({ACTIVE_MOTION_INTERVAL}s)...")
                
                while True:
                    time.sleep(ACTIVE_MOTION_INTERVAL)
                    raw_fast_curr_rgb = picam2.capture_array()
                    raw_fast_curr = cv2.cvtColor(raw_fast_curr_rgb, cv2.COLOR_RGB2BGR)
                    
                    fast_curr = apply_poly_mask(raw_fast_curr, shelf_points)
                    
                    fast_motion, _ = get_diff(curr_img, fast_curr, shelf_points, H_matrix, virtual_w, planogram_data)
                    curr_img = fast_curr.copy()
                    
                    if len(fast_motion) == 0:
                        print(f"[{CAMERA_ID}] Hand removed. Shelf has settled.")
                        break
                    else:
                        print("   ...still moving...")

            # --- SETTLED CHECK VS BASELINE ---
            diff_boxes, raw_mask = get_diff(baseline_img, curr_img, shelf_points, H_matrix, virtual_w, planogram_data)
            
            if len(diff_boxes) > 0:
                print(f"[{CAMERA_ID}] Inventory change confirmed by {ACTIVE_ALGORITHM.upper()}!")
                # Save the UNMASKED raw frame so you can see the whole room in the debug output
                save_debug_images(raw_curr, diff_boxes, raw_mask, "CHANGE_DETECTED")
                
                baseline_img = curr_img.copy()

            prev_img = curr_img.copy()

    except KeyboardInterrupt:
        print("\nStopping camera node...")
    finally:
        # Ensure the camera hardware releases cleanly if the script crashes or is killed
        picam2.stop()

if __name__ == "__main__":
    main()