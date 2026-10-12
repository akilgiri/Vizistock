import os
import json
import torch
import torchvision
import cv2
import numpy as np
import argparse
from pathlib import Path
from ultralytics.models.sam import SAM3SemanticPredictor

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Run SAM3 with Planogram Filtering")
parser.add_argument("--camera", type=str, default="cam_1", choices=["cam_0", "cam_1"], help="Camera ID to load the correct planogram config.")
args = parser.parse_args()

# --- 1. Configuration & Paths ---
SCRIPT_DIR = Path(__file__).parent.resolve()
input_root = SCRIPT_DIR / "feb19_images" / "freenove_rotated"
output_root = SCRIPT_DIR / "feb19_freenove_results35"
output_root.mkdir(parents=True, exist_ok=True)

prompts = [
    "bottle", 
    "can", 
    "box", 
    "chip bag", 
    "potato chip bag", 
    "snack bag"
]

LABEL_MAP = {
    "bottle": "bottle",
    "can": "can",
    "box": "box",
    "chip bag": "bag",
    "potato chip bag": "bag",
    "snack bag": "bag"
}

# Dynamically map synonyms to a single Canonical ID for merging
CANONICAL_IDS = {}
for i, prompt_name in enumerate(prompts):
    base_label = LABEL_MAP.get(prompt_name, prompt_name)
    if base_label not in CANONICAL_IDS:
        CANONICAL_IDS[base_label] = i 

config_path = SCRIPT_DIR / "local_master_config.json"
with open(config_path, "r") as f:
    planogram_config = json.load(f)[args.camera]

H = np.array(planogram_config["calibration"]["homography_matrix"], dtype=np.float32).reshape(3, 3)
virtual_w, virtual_h = planogram_config["calibration"]["virtual_dim"]
planogram_data = planogram_config["planogram"]

# --- 2. Initialize SAM 3 Predictor ---
overrides = dict(
    conf=0.60,      
    task="segment",
    mode="predict",
    model="sam3.pt",
    half=True, 
    save=False,     
)
predictor = SAM3SemanticPredictor(overrides=overrides)

def is_on_shelf(box, H_matrix, max_w, max_h, margin=0.40):
    x_point = (box[0] + box[2]) / 2.0
    y_point = box[3] 
    pt = np.array([[[x_point, y_point]]], dtype=np.float32)
    transformed_pt = cv2.perspectiveTransform(pt, H_matrix)
    proj_x, proj_y = transformed_pt[0][0]
    
    allowable_x_min = - (max_w * margin)
    allowable_x_max = max_w + (max_w * margin)
    allowable_y_min = - (max_h * margin)
    allowable_y_max = max_h + (max_h * margin)
    
    return (allowable_x_min <= proj_x <= allowable_x_max) and (allowable_y_min <= proj_y <= allowable_y_max)

def merge_masks_in_place(boxes, scores, cls, masks, bag_class_id, default_iou=0.50, bag_iou=0.05):
    """
    Class-aware mask merging. Strict threshold for boxes (0.50), loose for bags (0.05).
    """
    keep = torch.ones(len(boxes), dtype=torch.bool, device=boxes.device)
    for i in range(len(boxes)):
        if not keep[i]: continue
        for j in range(i + 1, len(boxes)):
            if not keep[j] or cls[i] != cls[j]: continue
            
            intersection = torch.logical_and(masks[i], masks[j]).sum().float()
            union = torch.logical_or(masks[i], masks[j]).sum().float()
            
            current_threshold = bag_iou if cls[i] == bag_class_id else default_iou
            
            if union > 0 and (intersection / union) > current_threshold:
                masks[i] = torch.logical_or(masks[i], masks[j])
                boxes[i][0] = torch.min(boxes[i][0], boxes[j][0])
                boxes[i][1] = torch.min(boxes[i][1], boxes[j][1])
                boxes[i][2] = torch.max(boxes[i][2], boxes[j][2])
                boxes[i][3] = torch.max(boxes[i][3], boxes[j][3])
                scores[i] = torch.max(scores[i], scores[j])
                keep[j] = False
    return keep

def get_planogram_slot(box, H_matrix, max_w, planogram):
    x_point = (box[0] + box[2]) / 2.0
    y_point = box[3] 
    pt = np.array([[[x_point, y_point]]], dtype=np.float32)
    transformed_pt = cv2.perspectiveTransform(pt, H_matrix)
    proj_x = transformed_pt[0][0][0]
    x_ratio = max(0.0, min(1.0, proj_x / max_w))
    
    for slot_id, slot_info in planogram.items():
        if slot_info["x_start"] <= x_ratio <= slot_info["x_end"]:
            return slot_id, slot_info["name"]
    return "unknown_slot", "Unknown Product"

# --- 3. Process Images ---
if not input_root.exists():
    print(f"Error: {input_root} not found.")
else:
    image_paths = list(input_root.rglob("*.[jJ][pP][gG]"))
    
    for img_path in image_paths:
        relative_path = img_path.parent.relative_to(input_root)
        save_dir = output_root / relative_path
        save_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Processing image: {img_path.name} for {args.camera}")
        
        predictor.set_image(str(img_path))
        results = predictor(text=prompts)
        
        image_detections = []
        
        for result in results:
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes.xyxy 
                scores = result.boxes.conf 
                
                # 1. Standard NMS
                nms_indices = torchvision.ops.nms(boxes, scores, iou_threshold=0.75)
                boxes = boxes[nms_indices]
                scores = scores[nms_indices]
                cls = result.boxes.cls[nms_indices]
                if result.masks is not None:
                    masks = result.masks.data[nms_indices]
                
                # 2. Planogram Shelf Filtering
                on_shelf_indices = []
                for i, box in enumerate(boxes.cpu().numpy()):
                    if is_on_shelf(box, H, virtual_w, virtual_h):
                        on_shelf_indices.append(i)
                
                if len(on_shelf_indices) > 0:
                    result.boxes = result.boxes[nms_indices][on_shelf_indices]
                    boxes = result.boxes.xyxy 
                    scores = result.boxes.conf 
                    cls = result.boxes.cls 
                    if result.masks is not None:
                        result.masks.data = result.masks.data[nms_indices][on_shelf_indices]
                        masks = result.masks.data
                    
                    # 3. Dynamic ID Normalization for Merging
                    for idx in range(len(cls)):
                        raw_name = prompts[int(cls[idx])]
                        base_label = LABEL_MAP.get(raw_name, raw_name)
                        cls[idx] = CANONICAL_IDS[base_label]
                    
                    # 4. Class-Aware Mask Merging (This fixes the chip fragments!)
                    if result.masks is not None:
                        bag_canonical_id = CANONICAL_IDS.get("bag", -1)
                        keep_mask = merge_masks_in_place(boxes, scores, cls, masks, bag_class_id=bag_canonical_id)
                        
                        result.boxes = result.boxes[keep_mask]
                        result.masks.data = masks[keep_mask]
                    
                    # Force the visual output to use your clean mapped names
                    result.names = {i: LABEL_MAP.get(p, p) for i, p in enumerate(prompts)}

                    final_boxes = result.boxes.xyxy.cpu().numpy()
                    final_scores = result.boxes.conf.cpu().numpy()
                    final_cls = result.boxes.cls.cpu().numpy()
                    final_masks = result.masks.data.cpu().numpy() if result.masks is not None else [None] * len(final_boxes)
                    
                    for idx, (box, score, class_id, mask_data) in enumerate(zip(final_boxes, final_scores, final_cls, final_masks)):
                        raw_label = prompts[int(class_id)] if int(class_id) < len(prompts) else "unknown"
                        normalized_label = LABEL_MAP.get(raw_label, raw_label)
                        
                        slot_id, product_name = get_planogram_slot(box, H, virtual_w, planogram_data)
                        
                        mask_filename = None
                        if mask_data is not None:
                            mask_img = (mask_data * 255).astype(np.uint8)
                            mask_filename = f"mask_{img_path.stem}_obj{idx}_{normalized_label}.png"
                            cv2.imwrite(str(save_dir / mask_filename), mask_img)

                        image_detections.append({
                            "label": normalized_label,
                            "confidence": round(float(score), 4),
                            "slot_id": slot_id,
                            "product_name": product_name,
                            "bbox": {
                                "x1": float(box[0]), "y1": float(box[1]),
                                "x2": float(box[2]), "y2": float(box[3])
                            },
                            "mask_file": mask_filename
                        })
                        
                    if result.masks is not None:
                        combined_mask = np.max(final_masks, axis=0) 
                        cv2.imwrite(str(save_dir / f"combined_mask_{img_path.stem}.png"), (combined_mask * 255).astype(np.uint8))
                else:
                    result.boxes = None
                    if result.masks is not None:
                        result.masks = None
            
            img_output_path = save_dir / f"sam3_filtered_{img_path.stem}.jpg"
            result.save(filename=str(img_output_path))
        
        json_output_path = save_dir / f"sam3_{img_path.stem}.json"
        with open(json_output_path, "w") as f:
            json.dump({
                "image": img_path.name,
                "camera": args.camera,
                "detections": image_detections,
                "total_count": len(image_detections)
            }, f, indent=4)

print(f"Inference complete. Filtered results saved to {output_root}")