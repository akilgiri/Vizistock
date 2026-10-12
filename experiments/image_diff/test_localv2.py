import cv2
import time
import os
import argparse
import json
import numpy as np
import test_image_diff as diff_lib

# --- CONFIGURATION ---
CAMERA_ID = "shelf_1_offline"

AREA_THRESHOLDS = {
    'custom': 2500,
    'ssim': 2500,       
    'mog2': 1500,       
    'orb': 2000,       
    'semantic': 300    
}

def load_shelf_mask_points(config_path="local_master_config.json", cam_id="cam_1"):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        raw_points = config[cam_id]["calibration"]["source_points"]
        return np.array(raw_points).reshape(-1, 2).astype(np.int32)
    except Exception as e:
        print(f"Warning: Could not load shelf mask from config: {e}")
        return None

def load_planogram_config(config_path="local_master_config.json", cam_id="cam_1"):
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
    if pts is None:
        return img
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    return cv2.bitwise_and(img, img, mask=mask)

def get_diff(img1, img2, active_algo, pts=None, H_matrix=None, virtual_w=None, planogram_data=None):
    """Router function parsing the correct library call."""
    thresh = AREA_THRESHOLDS.get(active_algo, 2000)
    
    if active_algo == 'custom':
        roi_mask = np.zeros(img1.shape[:2], dtype=np.uint8)
        if pts is not None:
             cv2.fillPoly(roi_mask, [pts], 255)
        else:
             roi_mask.fill(255)
             
        boxes, raw_mask, slots = diff_lib.get_diff_boxes_custom(
            img1, img2, roi_mask, threshold_area=thresh, 
            H_matrix=H_matrix, max_w=virtual_w, planogram_data=planogram_data
        )
        
        # Optional: Print out mapped planogram slots if they were found
        if slots:
             names = [s['product_name'] for s in slots]
             print(f"   -> Planogram mapping detected changes in: {names}")
             
        return boxes, raw_mask

    elif active_algo == 'ssim':
        return diff_lib.get_diff_boxes_ssim(img1, img2, threshold_area=thresh)
    elif active_algo == 'mog2':
        return diff_lib.get_diff_boxes_mog2(img2, threshold_area=thresh)
    elif active_algo == 'orb':
        return diff_lib.get_diff_boxes_orb(img1, img2, threshold_area=thresh)
    elif active_algo == 'semantic':
        return diff_lib.get_diff_boxes_semantic(img1, img2, threshold_area=thresh)
    
    return [], np.zeros(img1.shape[:2], dtype=np.uint8)

def save_debug_images(image, boxes, mask, suffix, output_dir, frame_idx, active_algo):
    debug_img = image.copy()
    for (x, y, w, h) in boxes:
        cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 0, 255), 4)
        
    img_filename = os.path.join(output_dir, f"{CAMERA_ID}_{active_algo}_{suffix}_F{frame_idx:04d}_IMG.jpg")
    mask_filename = os.path.join(output_dir, f"{CAMERA_ID}_{active_algo}_{suffix}_F{frame_idx:04d}_MASK.jpg")
    
    cv2.imwrite(img_filename, debug_img)
    cv2.imwrite(mask_filename, mask)
    print(f"📸 Saved Event for Frame {frame_idx}")

def get_frame_generator(input_source):
    if os.path.isdir(input_source):
        valid_exts = ('.jpg', '.jpeg', '.png', '.bmp')
        files = sorted([os.path.join(input_source, f) for f in os.listdir(input_source) if f.lower().endswith(valid_exts)])
        print(f"Found {len(files)} images in directory '{input_source}'.")
        for f in files:
            yield cv2.imread(f)
    elif os.path.isfile(input_source):
        if input_source.lower().endswith(('.mp4', '.avi', '.mov')):
            cap = cv2.VideoCapture(input_source)
            while True:
                ret, frame = cap.read()
                if not ret: break
                yield frame
        else:
            img = cv2.imread(input_source)
            yield img
            yield img 

def main():
    parser = argparse.ArgumentParser(description="Offline test harness for diffing algorithms.")
    parser.add_argument("-i", "--input", required=True, help="Path to directory of sequential images.")
    parser.add_argument("-o", "--output", default="local_tests_offlinev2", help="Directory to save output debug images.")
    parser.add_argument("-a", "--algorithm", default="custom", choices=['custom', 'ssim', 'mog2', 'orb', 'semantic'], help="Algorithm to test.")
    parser.add_argument("-d", "--delay", type=float, default=0.0, help="Delay between frames in seconds.")
    parser.add_argument("-c", "--config", default="local_master_config.json", help="Path to master config file.")
    args = parser.parse_args()

    if not os.path.exists(args.output):
        os.makedirs(args.output, exist_ok=True)

    frame_gen = get_frame_generator(args.input)
    
    shelf_points = load_shelf_mask_points(args.config)
    H_matrix, virtual_w, planogram_data = load_planogram_config(args.config)
    
    try:
        raw_baseline = next(frame_gen)
    except StopIteration:
        print("No frames could be loaded. Exiting.")
        return
    
    baseline_img = apply_poly_mask(raw_baseline, shelf_points)

    if args.algorithm == 'mog2':
        print("Warming up MOG2 background model...")
        for _ in range(100):
            # Pass through the router, MOG2 will handle its state inside diff_lib
            get_diff(baseline_img, baseline_img, args.algorithm)

    prev_img = baseline_img.copy()
    print(f"[{CAMERA_ID}] Offline Test Mode: {args.algorithm.upper()} | Threshold: {AREA_THRESHOLDS[args.algorithm]}")

    frame_count = 1

    for raw_curr_img in frame_gen:
        frame_count += 1
        if args.delay > 0: time.sleep(args.delay)

        curr_img = apply_poly_mask(raw_curr_img, shelf_points)

        # --- FAST ACTIVE MOTION LOOP ---
        motion_boxes, _ = get_diff(prev_img, curr_img, args.algorithm, shelf_points, 
                                   H_matrix, virtual_w, planogram_data)
        
        if len(motion_boxes) > 0:
            print(f"[{CAMERA_ID}] Frame {frame_count}: Motion detected! Entering active fast-polling...")
            
            for raw_fast_curr in frame_gen:
                frame_count += 1
                if args.delay > 0: time.sleep(args.delay)
                
                fast_curr = apply_poly_mask(raw_fast_curr, shelf_points)
                
                fast_motion, _ = get_diff(curr_img, fast_curr, args.algorithm, shelf_points,
                                          H_matrix, virtual_w, planogram_data)
                curr_img = fast_curr.copy()
                
                if len(fast_motion) == 0:
                    print(f"[{CAMERA_ID}] Frame {frame_count}: Hand removed. Shelf has settled.")
                    break
                else:
                    print(f"   ...Frame {frame_count}: still moving...")

        # --- SETTLED CHECK VS BASELINE ---
        diff_boxes, raw_mask = get_diff(baseline_img, curr_img, args.algorithm, shelf_points,
                                        H_matrix, virtual_w, planogram_data)
        
        if len(diff_boxes) > 0:
            print(f"[{CAMERA_ID}] Frame {frame_count}: Inventory change confirmed by {args.algorithm.upper()}!")
            save_debug_images(raw_curr_img, diff_boxes, raw_mask, "CHANGE_DETECTED", args.output, frame_count, args.algorithm)
            baseline_img = curr_img.copy()

        prev_img = curr_img.copy()
        
    print(f"[{CAMERA_ID}] Testing complete.")

if __name__ == "__main__":
    main()