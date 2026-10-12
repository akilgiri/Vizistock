import cv2
import numpy as np
import torch
import torchvision.models as models
from skimage.metrics import structural_similarity
from sklearn.cluster import KMeans

# --- METHOD 1: ORIGINAL SSIM ---
def get_diff_boxes_ssim(img1, img2, threshold_area=500):
    orig_h, orig_w = img1.shape[:2]
    img1_small = cv2.resize(img1, (640, 480))
    img2_small = cv2.resize(img2, (640, 480))

    img1_small = cv2.GaussianBlur(img1_small, (15, 15), 0)
    img2_small = cv2.GaussianBlur(img2_small, (15, 15), 0)

    scale_x, scale_y = orig_w / 640.0, orig_h / 480.0

    gray1 = cv2.cvtColor(img1_small, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2_small, cv2.COLOR_BGR2GRAY)
    _, diff = structural_similarity(gray1, gray2, full=True)
    diff = (diff * 255).astype("uint8")
    thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    lab1 = cv2.cvtColor(img1_small, cv2.COLOR_BGR2LAB)
    lab2 = cv2.cvtColor(img2_small, cv2.COLOR_BGR2LAB)
    chroma_diff = cv2.addWeighted(cv2.absdiff(lab1[:, :, 1], lab2[:, :, 1]), 0.5, 
                                  cv2.absdiff(lab1[:, :, 2], lab2[:, :, 2]), 0.5, 0.0)
    color_mask = cv2.threshold(chroma_diff, 30, 255, cv2.THRESH_BINARY)[1]

    combined_mask = cv2.bitwise_or(thresh, color_mask)
    contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = _scale_contours(contours, scale_x, scale_y, threshold_area)
    return boxes, combined_mask

# --- METHOD 2: MOG2 GAUSSIAN MIXTURE ---
# Maintained at module level to preserve state history automatically
bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=50, detectShadows=True)

def get_diff_boxes_mog2(curr_img, threshold_area=500):
    orig_h, orig_w = curr_img.shape[:2]
    img_small = cv2.resize(curr_img, (640, 480))
    scale_x, scale_y = orig_w / 640.0, orig_h / 480.0

    fg_mask = bg_subtractor.apply(img_small)
    
    _, clean_mask = cv2.threshold(fg_mask, 254, 255, cv2.THRESH_BINARY)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    clean_mask = cv2.morphologyEx(clean_mask, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = _scale_contours(contours, scale_x, scale_y, threshold_area)
    return boxes, clean_mask

# --- METHOD 3: ORB FEATURE MATCHING ---
def get_diff_boxes_orb(img1, img2, threshold_area=500):
    orig_h, orig_w = img1.shape[:2]
    img1_small = cv2.resize(img1, (640, 480))
    img2_small = cv2.resize(img2, (640, 480))
    scale_x, scale_y = orig_w / 640.0, orig_h / 480.0

    orb = cv2.ORB_create(nfeatures=1000)
    kp1, des1 = orb.detectAndCompute(img1_small, None)
    kp2, des2 = orb.detectAndCompute(img2_small, None)

    mask = np.zeros((480, 640), dtype=np.uint8)

    if des1 is not None and des2 is not None:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        
        matched_kp1_indices = {m.queryIdx for m in matches if m.distance < 50}
        
        for i, kp in enumerate(kp1):
            if i not in matched_kp1_indices:
                x, y = int(kp.pt[0]), int(kp.pt[1])
                cv2.circle(mask, (x, y), 20, 255, -1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = _scale_contours(contours, scale_x, scale_y, threshold_area)
    return boxes, mask

# --- METHOD 4: DEEP FEATURE (Siamese Proxy) ---
feature_extractor = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT).features
feature_extractor.eval()

def get_diff_boxes_semantic(img1, img2, threshold_area=500):
    orig_h, orig_w = img1.shape[:2]
    scale_x, scale_y = orig_w / 224.0, orig_h / 224.0

    def preprocess(img):
        img_rgb = cv2.cvtColor(cv2.resize(img, (224, 224)), cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(img_rgb).permute(2, 0, 1).float() / 255.0
        tensor[0] = (tensor[0] - 0.485) / 0.229
        tensor[1] = (tensor[1] - 0.456) / 0.224
        tensor[2] = (tensor[2] - 0.406) / 0.225
        return tensor.unsqueeze(0)

    with torch.no_grad():
        f1 = feature_extractor(preprocess(img1))
        f2 = feature_extractor(preprocess(img2))

    diff_tensor = torch.abs(f1 - f2).mean(dim=1).squeeze()
    diff_np = diff_tensor.numpy()
    diff_np = np.uint8(255 * (diff_np - diff_np.min()) / (diff_np.max() - diff_np.min() + 1e-8))
    
    _, mask = cv2.threshold(diff_np, 100, 255, cv2.THRESH_BINARY)
    mask_large = cv2.resize(mask, (224, 224), interpolation=cv2.INTER_NEAREST)
    
    contours, _ = cv2.findContours(mask_large, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = _scale_contours(contours, scale_x, scale_y, threshold_area)
    return boxes, mask_large

# --- HELPER UTILITY ---
def _scale_contours(contours, scale_x, scale_y, threshold_area):
    boxes = []
    for c in contours:
        if cv2.contourArea(c) > threshold_area:
            x, y, w, h = cv2.boundingRect(c)
            boxes.append([int(x * scale_x), int(y * scale_y), int(w * scale_x), int(h * scale_y)])
    return boxes

# --- METHOD 5: NEW CUSTOM PIPELINE (SSIM + Chroma + Morphology + Planogram) ---
def _get_planogram_slot_for_diff(bbox, H_matrix, max_w, planogram_data):
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

def get_diff_boxes_custom(img1, img2, roi_mask, threshold_area=2500, H_matrix=None, max_w=None, planogram_data=None, pixel_thresh=100):
    img1_roi = cv2.bitwise_and(img1, img1, mask=roi_mask)
    img2_roi = cv2.bitwise_and(img2, img2, mask=roi_mask)

    gray1 = cv2.GaussianBlur(cv2.cvtColor(img1_roi, cv2.COLOR_BGR2GRAY), (11, 11), 0)
    gray2 = cv2.GaussianBlur(cv2.cvtColor(img2_roi, cv2.COLOR_BGR2GRAY), (11, 11), 0)
    
    _, diff_ssim = structural_similarity(gray1, gray2, full=True, data_range=255)
    diff_ssim = (diff_ssim * 255).astype("uint8")
    diff_ssim = cv2.bitwise_not(diff_ssim)

    lab1 = cv2.cvtColor(img1_roi, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab2 = cv2.cvtColor(img2_roi, cv2.COLOR_BGR2LAB).astype(np.float32)
    chroma_diff = np.linalg.norm(lab1[:, :, 1:] - lab2[:, :, 1:], axis=2)
    chroma_diff = np.uint8(np.clip(chroma_diff, 0, 255))

    combined_diff = cv2.addWeighted(diff_ssim, 0.5, chroma_diff, 0.5, 0)
    _, thresh_diff = cv2.threshold(combined_diff, pixel_thresh, 255, cv2.THRESH_BINARY)
    
    # Crucial Morphology to fix false-positive reflections
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    thresh_diff = cv2.morphologyEx(thresh_diff, cv2.MORPH_OPEN, kernel)
    thresh_diff = cv2.morphologyEx(thresh_diff, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh_diff = cv2.dilate(thresh_diff, kernel, iterations=2)
    
    contours, _ = cv2.findContours(thresh_diff, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    boxes = []
    changed_slots = []
    
    for c in contours:
        if cv2.contourArea(c) > threshold_area:
            bbox = cv2.boundingRect(c)
            boxes.append(bbox)
            
            if H_matrix is not None and max_w is not None and planogram_data is not None:
                slot_id, product_name = _get_planogram_slot_for_diff(bbox, H_matrix, max_w, planogram_data)
                changed_slots.append({
                    "slot_id": slot_id,
                    "product_name": product_name,
                    "bbox": bbox
                })
                
    return boxes, thresh_diff, changed_slots

# --- METHOD 6: HAND-TUNED ORIGINAL (from diff.py) ---
def get_diff_boxes_handtuned(img1, img2, threshold_area=200000, chroma_thresh=30):
    """
    Direct port of the hand-tuned script. 
    Runs on full resolution images without blur or planogram mapping.
    """
    # Convert images to grayscale
    first_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    second_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    # Compute SSIM between two images
    _, diff = structural_similarity(first_gray, second_gray, full=True)
    diff = (diff * 255).astype("uint8")

    # Threshold the difference image (Otsu + Inverse Binary)
    thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    # Lab CHROMA DIFF
    lab1 = cv2.cvtColor(img1, cv2.COLOR_BGR2LAB)
    lab2 = cv2.cvtColor(img2, cv2.COLOR_BGR2LAB)

    # Extract a and b channels
    a1, b1 = lab1[:, :, 1], lab1[:, :, 2]
    a2, b2 = lab2[:, :, 1], lab2[:, :, 2]

    da = cv2.absdiff(a1, a2)
    db = cv2.absdiff(b1, b2)

    # Combine a and b differences equally
    chroma_diff = cv2.addWeighted(da, 0.5, db, 0.5, 0.0)

    # Threshold the color mask
    color_mask = cv2.threshold(chroma_diff, chroma_thresh, 255, cv2.THRESH_BINARY)[1]

    # Combine STRUCTURE (SSIM) + COLOR (Lab chroma)
    combined_mask = cv2.bitwise_or(thresh, color_mask)

    contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in contours:
        area = cv2.contourArea(c)
        if area > threshold_area:
            x, y, w, h = cv2.boundingRect(c)
            # No scaling needed since we processed at full resolution
            boxes.append([int(x), int(y), int(w), int(h)])

    return boxes, combined_mask