import cv2
import numpy as np
from skimage.metrics import structural_similarity

# --- GLOBAL MOG2 INITIALIZATION ---
# A short history (100 frames) lets the background model be rebuilt quickly after each change
bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=100, varThreshold=50, detectShadows=False)

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

# --- MOG2 GAUSSIAN MIXTURE (idle tripwire + baseline check) ---
def get_diff_boxes_mog2(curr_img, roi_mask=None, threshold_area=1500, H_matrix=None, max_w=None, planogram_data=None, apply_cleanup=True, learning_rate=0.0):
    orig_h, orig_w = curr_img.shape[:2]
    
    # 1. Apply ROI Mask BEFORE resizing
    if roi_mask is not None:
        curr_img = cv2.bitwise_and(curr_img, curr_img, mask=roi_mask)

    # 2. Resize to 640x480
    img_small = cv2.resize(curr_img, (640, 480))
    scale_x, scale_y = orig_w / 640.0, orig_h / 480.0

    # 3. Apply MOG2
    # Uses the variable learning_rate so the camera node can toggle learning on/off dynamically
    fg_mask = bg_subtractor.apply(img_small, learningRate=learning_rate)
    
    # 4. Shadow removal & Morphology Toggle
    if apply_cleanup:
        _, clean_mask_small = cv2.threshold(fg_mask, 254, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 8))
        clean_mask_small = cv2.morphologyEx(clean_mask_small, cv2.MORPH_OPEN, kernel)
    else:
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

# --- SSIM (consecutive-frame settle check) ---
def get_diff_boxes_ssim(img1, img2, threshold_area=2000):
    """
    Runs purely on Grayscale SSIM to maximize speed, using Otsu thresholding.
    """
    # Convert images to grayscale
    first_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    second_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    # Compute SSIM between two images
    # Explicit data_range=255 to prevent divide-by-zero NaNs on black frames
    _, diff = structural_similarity(first_gray, second_gray, full=True, data_range=255)
    
    # Safely convert the float array to uint8 by clipping bounds
    diff = np.clip(diff * 255, 0, 255).astype("uint8")

    # Threshold the difference image (Otsu + Inverse Binary)
    thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    # Find contours directly on the SSIM threshold mask
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in contours:
        area = cv2.contourArea(c)
        if area > threshold_area:
            x, y, w, h = cv2.boundingRect(c)
            # No scaling needed since we process at whatever resolution is passed in
            boxes.append([int(x), int(y), int(w), int(h)])

    return boxes, thresh