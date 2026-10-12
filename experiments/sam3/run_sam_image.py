import json
import torch
import torchvision  # Used for robust NMS across all labels
from pathlib import Path
from ultralytics.models.sam import SAM3SemanticPredictor

# 1. Configuration & Single Image Path
img_path = Path(__file__).parent / "test_images" / Path("images_2026-01-31_19-46-59.jpg") 
output_root = Path("results/single_test")
output_root.mkdir(parents=True, exist_ok=True)

prompts = ["bottles", "cans", "boxes", "bags", "person", "chocolates", "spaghetti"]

# 2. Initialize SAM 3 Predictor
overrides = dict(
    conf=0.25,      
    task="segment",
    mode="predict",
    model="sam3.pt",
    half=True,      
    save=False,     
)
predictor = SAM3SemanticPredictor(overrides=overrides)
# 3. Run Inference
if img_path.exists():
    print(f"Processing: {img_path.name}")
    predictor.set_image(str(img_path))
    results = predictor(text=prompts)
    
    image_detections = []
    
    for result in results:
        if result.boxes is not None:
            boxes = result.boxes.xyxy 
            scores = result.boxes.conf 
            
            # 1. Apply Class-Agnostic NMS
            keep_indices = torchvision.ops.nms(boxes, scores, iou_threshold=0.45)
            
            # 2. SYNCHRONIZE DATA STRUCTURES
            # We must filter both boxes and masks to avoid the Shape Mismatch Error
            result.boxes = result.boxes[keep_indices]
            if result.masks is not None:
                result.masks.data = result.masks.data[keep_indices]
            
            # 3. Prepare data for JSON output
            final_boxes = result.boxes.xyxy.cpu().numpy()
            final_scores = result.boxes.conf.cpu().numpy()
            final_cls = result.boxes.cls.cpu().numpy()
            
            for box, score, class_id in zip(final_boxes, final_scores, final_cls):
                label = prompts[int(class_id)]
                image_detections.append({
                    "label": label,
                    "confidence": round(float(score), 4),
                    "bbox": {
                        "x1": float(box[0]), "y1": float(box[1]),
                        "x2": float(box[2]), "y2": float(box[3])
                    }
                })
        
        # 4. Save visual result (Now masks and boxes match in size)
        img_output_path = output_root / f"sam3_fixed_{img_path.stem}.jpg"
        result.save(filename=str(img_output_path))

    # 5. Save to JSON
    json_output_path = output_root / f"sam3_{img_path.stem}.json"
    with open(json_output_path, "w") as f:
        json.dump({
            "image": img_path.name,
            "detections": image_detections,
            "total_count": len(image_detections)
        }, f, indent=4)

    print(f"Success! Filtered results saved to {output_root}")