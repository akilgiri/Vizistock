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
output_root = SCRIPT_DIR / "feb19_freenove_results24"
output_root.mkdir(parents=True, exist_ok=True)

prompts = ["bottles", "cans", "boxes", "bags", "folded bags", "crinkled bags"]

LABEL_MAP = {
    "bottles": "bottle",
    "cans": "can",
    "boxes": "box",
    "bags": "bag",
    "crinkled bags": "bag",
    "folded bags": "bag"
}

# Load Planogram Config
config_path = SCRIPT_DIR / "local_master_config.json"
with open(config_path, "r") as f:
    planogram_config = json.load(f)[args.camera]

# Extract Homography Matrix and Virtual Dimensions
H = np.array(planogram_config["calibration"]["homography_matrix"], dtype=np.float32).reshape(3, 3)
virtual_w, virtual_h = planogram_config["calibration"]["virtual_dim"]
planogram_data = planogram_config["planogram"]

# --- 2. Initialize SAM 3 Predictor ---
overrides = dict(
    conf=0.60,      # Increased from 0.25 based on minimum observed confidences
    task="segment",
    mode="predict",
    model="sam3.pt",
    half=True, 
    save=False,     
)
predictor = SAM3SemanticPredictor(overrides=overrides)

def is_on_shelf(box, H_matrix, max_w, max_h, margin=0.40):
    """
    Calculates if the bounding box base falls within the virtual shelf limits,
    using a large margin to account for perspective distortion and frame spillover.
    """
    # Bottom-center coordinate (most accurate physical anchor point)
    x_point = (box[0] + box[2]) / 2.0
    y_point = box[3] 
    
    # Reshape for cv2.perspectiveTransform
    pt = np.array([[[x_point, y_point]]], dtype=np.float32)
    transformed_pt = cv2.perspectiveTransform(pt, H_matrix)
    proj_x, proj_y = transformed_pt[0][0]
    
    # Calculate allowable bounds with the 40% margin included
    allowable_x_min = - (max_w * margin)
    allowable_x_max = max_w + (max_w * margin)
    allowable_y_min = - (max_h * margin)
    allowable_y_max = max_h + (max_h * margin)
    
    # Check if projected point is within the expanded bounds
    return (allowable_x_min <= proj_x <= allowable_x_max) and (allowable_y_min <= proj_y <= allowable_y_max)

def merge_masks_in_place(boxes, scores, cls, masks, iou_threshold=0.05):
    """
    Merges detections based on pixel-perfect Mask IoU.
    Updates the tensors in-place and returns a boolean mask of which indices to keep.
    """
    keep = torch.ones(len(boxes), dtype=torch.bool, device=boxes.device)
    
    for i in range(len(boxes)):
        if not keep[i]: 
            continue
            
        for j in range(i + 1, len(boxes)):
            if not keep[j] or cls[i] != cls[j]: 
                continue
            
            # Pixel-perfect Mask IoU
            intersection = torch.logical_and(masks[i], masks[j]).sum().float()
            union = torch.logical_or(masks[i], masks[j]).sum().float()
            
            if union > 0 and (intersection / union) > iou_threshold:
                # Merge mask 'j' into mask 'i'
                masks[i] = torch.logical_or(masks[i], masks[j])
                
                # Expand bounding box 'i' to encompass 'j'
                boxes[i][0] = torch.min(boxes[i][0], boxes[j][0])
                boxes[i][1] = torch.min(boxes[i][1], boxes[j][1])
                boxes[i][2] = torch.max(boxes[i][2], boxes[j][2])
                boxes[i][3] = torch.max(boxes[i][3], boxes[j][3])
                
                # Keep the highest confidence score
                scores[i] = torch.max(scores[i], scores[j])
                
                # Mark 'j' for deletion
                keep[j] = False
                
    return keep

def get_planogram_slot(box, H_matrix, max_w, planogram):
    """
    Projects the base coordinate to the virtual shelf, calculates its X-ratio,
    and returns the matching slot ID and product name.
    """
    # Bottom-center coordinate (physical anchor point)
    x_point = (box[0] + box[2]) / 2.0
    y_point = box[3] 
    
    # Project to virtual space
    pt = np.array([[[x_point, y_point]]], dtype=np.float32)
    transformed_pt = cv2.perspectiveTransform(pt, H_matrix)
    proj_x = transformed_pt[0][0][0]
    
    # Calculate ratio and clamp between 0 and 1
    x_ratio = max(0.0, min(1.0, proj_x / max_w))
    
    # Match to planogram
    for slot_id, slot_info in planogram.items():
        if slot_info["x_start"] <= x_ratio <= slot_info["x_end"]:
            return slot_id, slot_info["name"]
            
    return "unknown_slot", "Unknown Product"

# --- 3. Process Images ---
if not input_root.exists():
    print(f"Error: {input_root} not found.")
else:
    # Find all JPGs recursively (handles both flat and nested folders)
    image_paths = list(input_root.rglob("*.[jJ][pP][gG]"))
    
    if not image_paths:
        print(f"No images found in {input_root}.")
        
    for img_path in image_paths:
        # Recreate the folder structure in the output directory
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
                
                # 1. Apply Class-Agnostic NMS (IoU Threshold 0.45)
                nms_indices = torchvision.ops.nms(boxes, scores, iou_threshold=0.75)
                boxes = boxes[nms_indices]
                scores = scores[nms_indices]
                cls = result.boxes.cls[nms_indices]
                if result.masks is not None:
                    masks = result.masks.data[nms_indices]
                
                # 2. Apply Planogram Shelf Filtering
                on_shelf_indices = []
                for i, box in enumerate(boxes.cpu().numpy()):
                    if is_on_shelf(box, H, virtual_w, virtual_h):
                        on_shelf_indices.append(i)
                
                # Synchronize the result object so the saved image only shows valid boxes
                # ... (Right after 2. Apply Planogram Shelf Filtering) ...
                if len(on_shelf_indices) > 0:
                    # Slice tensors to keep only items on the shelf
                    result.boxes = result.boxes[nms_indices][on_shelf_indices]
                    boxes = result.boxes.xyxy 
                    scores = result.boxes.conf 
                    cls = result.boxes.cls 
                    if result.masks is not None:
                        masks = result.masks.data[nms_indices][on_shelf_indices]
                    
                    # 3. Normalize Class IDs for Merging (e.g., make 'crinkled bags' into 'bags')
                    bag_id = prompts.index("bags")
                    for idx in range(len(cls)):
                        raw_name = prompts[int(cls[idx])]
                        if LABEL_MAP.get(raw_name) == "bag":
                            cls[idx] = bag_id
                    
                    # 4. Pixel-Perfect Mask Merging
                    if result.masks is not None:
                        keep_mask = merge_masks_in_place(boxes, scores, cls, masks, iou_threshold=0.05)
                        
                        # Apply the boolean mask to the Ultralytics object so drawing is correct
                        result.boxes = result.boxes[keep_mask]
                        result.masks.data = masks[keep_mask]
                    
                    # Prepare data for JSON
                    final_boxes = result.boxes.xyxy.cpu().numpy()
                    final_scores = result.boxes.conf.cpu().numpy()
                    final_cls = result.boxes.cls.cpu().numpy()
                    
                    for box, score, class_id in zip(final_boxes, final_scores, final_cls):
                        raw_label = prompts[int(class_id)] if int(class_id) < len(prompts) else "unknown"
                        
                        # Dynamically get the base class name (falls back to raw_label if not in map)
                        normalized_label = LABEL_MAP.get(raw_label, raw_label)
                        
                        # Fetch the mapped slot data
                        slot_id, product_name = get_planogram_slot(box, H, virtual_w, planogram_data)
                        
                        image_detections.append({
                            "label": normalized_label,
                            "confidence": round(float(score), 4),
                            "slot_id": slot_id,
                            "product_name": product_name,
                            "bbox": {
                                "x1": float(box[0]), "y1": float(box[1]),
                                "x2": float(box[2]), "y2": float(box[3])
                            }
                        })
                else:
                    # Clear boxes if nothing passed
                    result.boxes = None
                    if result.masks is not None:
                        result.masks = None
            
            # Save the filtered visual output
            img_output_path = save_dir / f"sam3_filtered_{img_path.stem}.jpg"
            result.save(filename=str(img_output_path))
        
        # Write detections to JSON
        json_output_path = save_dir / f"sam3_{img_path.stem}.json"
        with open(json_output_path, "w") as f:
            json.dump({
                "image": img_path.name,
                "camera": args.camera,
                "detections": image_detections,
                "total_count": len(image_detections)
            }, f, indent=4)

print(f"Inference complete. Filtered results saved to {output_root}")