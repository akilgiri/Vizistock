import os
import json
import torch
import torchvision
from pathlib import Path
from ultralytics.models.sam import SAM3SemanticPredictor

# 1. Configuration & Paths
# Using SCRIPT_DIR to ensure it finds the folder relative to the script location
SCRIPT_DIR = Path(__file__).parent.resolve()
input_root = SCRIPT_DIR / "feb4_images"
output_root = SCRIPT_DIR / "feb4_results_test5"
output_root.mkdir(parents=True, exist_ok=True)

# prompts = ["bottles", "cans", "boxes", "bags"]
prompts = ["cookie box", "granola bar box", "sparkling water bottle", "bag of chips", "bottles", "cans", "boxes", "bags"]

# 2. Initialize SAM 3 Predictor
overrides = dict(
    conf=0.25,      # Lowered to match your single-test script for better recall
    task="segment",
    mode="predict",
    model="sam3.pt",
    half=True, 
    save=False,     # We handle saving manually after NMS
)
predictor = SAM3SemanticPredictor(overrides=overrides)

# 3. Process Folders
if not input_root.exists():
    print(f"Error: {input_root} not found.")
else:
    for date_folder in input_root.iterdir():
        if date_folder.is_dir():
            save_dir = output_root / date_folder.name
            save_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"Processing folder: {date_folder.name}")
            
            for img_path in date_folder.glob("*.[jJ][pP][gG]"):
                predictor.set_image(str(img_path))
                results = predictor(text=prompts)
                
                image_detections = []
                
                for result in results:
                    if result.boxes is not None:
                        boxes = result.boxes.xyxy 
                        scores = result.boxes.conf 
                        
                        # Apply Class-Agnostic NMS (IoU Threshold 0.45)
                        keep_indices = torchvision.ops.nms(boxes, scores, iou_threshold=0.45)
                        
                        # Synchronize boxes and masks to prevent shape mismatch
                        result.boxes = result.boxes[keep_indices]
                        if result.masks is not None:
                            result.masks.data = result.masks.data[keep_indices]
                        
                        # Prepare data for JSON
                        final_boxes = result.boxes.xyxy.cpu().numpy()
                        final_scores = result.boxes.conf.cpu().numpy()
                        final_cls = result.boxes.cls.cpu().numpy()
                        
                        for box, score, class_id in zip(final_boxes, final_scores, final_cls):
                            label = prompts[int(class_id)] if int(class_id) < len(prompts) else "unknown"
                            image_detections.append({
                                "label": label,
                                "confidence": round(float(score), 4),
                                "bbox": {
                                    "x1": float(box[0]), "y1": float(box[1]),
                                    "x2": float(box[2]), "y2": float(box[3])
                                }
                            })
                    
                    # Save the filtered visual output
                    img_output_path = save_dir / f"sam3_filtered_{img_path.stem}.jpg"
                    result.save(filename=str(img_output_path))
                
                # Write detections to JSON
                json_output_path = save_dir / f"sam3_{img_path.stem}.json"
                with open(json_output_path, "w") as f:
                    json.dump({
                        "image": img_path.name,
                        "detections": image_detections,
                        "total_count": len(image_detections)
                    }, f, indent=4)

    print(f"Inference complete. Filtered results saved to {output_root}")