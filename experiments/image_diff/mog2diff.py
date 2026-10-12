import cv2
import numpy as np
import glob
import os
from skimage.metrics import structural_similarity

# --- CONFIGURATION ---
SHELF1_CAM_RESOLUTION = 3280 * 2464
MOG_IMG_PATH = "mog_imgs/Sample 5/2026-02-28" 
#image_num = 3

# --- GLOBAL MOG2 INITIALIZATION ---
bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=50, detectShadows=True)

# ==========================================
# UTILITY FUNCTIONS
# ==========================================
def _scale_contours(contours, scale_x, scale_y, threshold_area):
    """Scales bounding boxes from the 640x480 image back to the original resolution."""
    boxes = []
    for c in contours:
        if cv2.contourArea(c) > threshold_area:
            x, y, w, h = cv2.boundingRect(c)
            boxes.append([int(x * scale_x), int(y * scale_y), int(w * scale_x), int(h * scale_y)])
    return boxes

def _get_planogram_slot_for_diff(bbox, H_matrix, max_w, planogram_data):
    """Projects the bounding box into the planogram to identify the product."""
    x, y, w, h = bbox
    x_point = x + (w / 2.0)
    y_point = y + h
    pt = np.array([[[x_point, y_point]]], dtype=np.float32)
    
    try:
        transformed_pt = cv2.perspectiveTransform(pt, H_matrix)
        proj_x = transformed_pt[0][0][0]
        x_ratio = max(0.0, min(1.0, proj_x / max_w))
        
        for slot_id, slot_info in planogram_data.items():
            if slot_info["x_start"] <= x_ratio <= slot_info["x_end"]:
                return slot_id, slot_info["name"]
        return "unknown_slot", "Unknown Product"
    except Exception:
        return "error_slot", "Error"

# ==========================================
# MOG2 + CUSTOM CAPABILITIES
# ==========================================
def get_diff_boxes_mog2(curr_img, roi_mask=None, threshold_area=500, H_matrix=None, max_w=None, planogram_data=None, apply_cleanup=True):
    """
    Method 2 (MOG2 with Resize) upgraded to be fully compatible with Method 5 (Planograms & ROI).
    Added `apply_cleanup` toggle for debugging raw MOG2 output.
    """
    orig_h, orig_w = curr_img.shape[:2]
    
    # 1. Apply ROI Mask BEFORE resizing
    if roi_mask is not None:
        curr_img = cv2.bitwise_and(curr_img, curr_img, mask=roi_mask)

    # 2. Resize to 640x480
    img_small = cv2.resize(curr_img, (640, 480))
    scale_x, scale_y = orig_w / 640.0, orig_h / 480.0

    # 3. Apply MOG2
    fg_mask = bg_subtractor.apply(img_small, learningRate=0.0)
    
    # 4. Shadow removal & Morphology Toggle
    if apply_cleanup:
        _, clean_mask_small = cv2.threshold(fg_mask, 254, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 8))
        clean_mask_small = cv2.morphologyEx(clean_mask_small, cv2.MORPH_OPEN, kernel)
    else:
        # Bypasses all filters, leaving shadows and noise intact
        clean_mask_small = fg_mask.copy()
    
    # 5. Find contours on the small mask and scale them up
    contours, _ = cv2.findContours(clean_mask_small, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = _scale_contours(contours, scale_x, scale_y, threshold_area)

    # 6. Planogram Mapping
    changed_slots = []
    for bbox in boxes:
        if H_matrix is not None and max_w is not None and planogram_data is not None:
            slot_id, product_name = _get_planogram_slot_for_diff(bbox, H_matrix, max_w, planogram_data)
            changed_slots.append({
                "slot_id": slot_id,
                "product_name": product_name,
                "bbox": bbox
            })

    # 7. Resize the mask back to full resolution
    clean_mask_large = cv2.resize(clean_mask_small, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)

    return boxes, clean_mask_large, changed_slots

# ==========================================
# MAIN EXECUTION (diff.py)
# ==========================================
if __name__ == "__main__":
    
    CURRENT_TEST_DIR = MOG_IMG_PATH
    
    image_paths = sorted(glob.glob(f"{CURRENT_TEST_DIR}/*.jpg"))
    
    if len(image_paths) < 2:
        print(f"Error: Need at least 2 images in {CURRENT_TEST_DIR}")
        exit()
        
    before_paths = image_paths[:-1] 
    after_img_path = image_paths[-1] 
    
    print(f"Found {len(before_paths)} history frames and 1 target frame: {after_img_path}")
    
    after_img = cv2.imread(after_img_path)

    # --- REAL MOG2 WARMUP ---
    print("Warming up MOG2...")
    
    for i, img_path in enumerate(before_paths):
        frame = cv2.imread(img_path)
        if frame is None: continue
        
        frame_small = cv2.resize(frame, (640, 480))
        bg_subtractor.apply(frame_small)
        
        if i % 20 == 0:
            print(f"  ...processed {i} frames...")

    print("Warmup complete. Checking 'After' image for differences...")

    # --- EXECUTE ON THE AFTER IMAGE ---
    # Toggle apply_cleanup to False to see the raw mask with shadows and noise
    mog_boxes, mog_mask, planogram_slots = get_diff_boxes_mog2(
        curr_img=after_img, 
        roi_mask=None,       
        threshold_area=1500, 
        H_matrix=None,       
        max_w=None, 
        planogram_data=None,
        apply_cleanup=True 
    )

    # --- DRAWING ---
    last_before_img = cv2.imread(before_paths[-1])
    
    before_display = last_before_img.copy()
    after_display = after_img.copy()
    
    for (x, y, w, h) in mog_boxes:
        cv2.rectangle(before_display, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.rectangle(after_display, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.putText(after_display, "MOG2 Change", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)

    # --- SAVE IMAGES TO DISK ---
    output_dir = "output_imgs"
    
    # Automatically create the folder if it doesn't exist yet
    os.makedirs(output_dir, exist_ok=True)
    
    # Save the images inside the new folder
    cv2.imwrite(os.path.join(output_dir, "output_1_before.jpg"), before_display)
    cv2.imwrite(os.path.join(output_dir, "output_2_after.jpg"), after_display)
    cv2.imwrite(os.path.join(output_dir, "output_3_mask.jpg"), mog_mask)
    
    print(f"Saved output images to the '{output_dir}' folder successfully!")

    # --- DISPLAY OUTPUT ---
    # cv2.namedWindow('Last Before Image', cv2.WINDOW_NORMAL)
    # cv2.namedWindow('After Image (MOG2 Boxes)', cv2.WINDOW_NORMAL)
    # cv2.namedWindow('MOG2 Mask (Scaled Up)', cv2.WINDOW_NORMAL)

    # cv2.imshow('Last Before Image', before_display)
    # cv2.imshow('After Image (MOG2 Boxes)', after_display)
    # cv2.imshow('MOG2 Mask (Scaled Up)', mog_mask)

    # cv2.waitKey()
    # cv2.destroyAllWindows()

    #learning rate 0.0 - saying don't add the "after image to the history"
    # motion detected -> reset history start new history - maybe set threshold of 
    # like of atleast 30seconds to not spam reset
    # 