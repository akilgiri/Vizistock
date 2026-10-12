import os
import json
import torch
import torchvision
import time
from datetime import datetime
from pathlib import Path
from ultralytics.models.sam import SAM3SemanticPredictor
import firebase_admin
from firebase_admin import credentials, firestore

# 1. Configuration & Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
input_root = SCRIPT_DIR / "feb4_images"
output_root = SCRIPT_DIR / "feb4_results_test_v2"
output_root.mkdir(parents=True, exist_ok=True)

cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS", "firebase-service-account.json"))
firebase_admin.initialize_app(cred)
db = firestore.client()
# Set your destination collection name here
FIRESTORE_COLLECTION = "inventory_detections" 

# Prompts for SAM 3
prompts = ["cookie box", "granola bar box", "sparkling water bottle", "bag of chips", "bottles", "cans", "boxes", "bags"]

LABEL_MAP = {
    "cookie box": "box", "granola bar box": "box", "sparkling water bottle": "bottle",
    "bag of chips": "bag", "bottles": "bottle", "cans": "can", "boxes": "box", "bags": "bag"
}

# 2. Initialize SAM 3 Predictor
predictor = SAM3SemanticPredictor(overrides=dict(
    conf=0.25, task="segment", mode="predict", model="sam3.pt", half=False, save=False
))

# 3. Process Folders
if not input_root.exists():
    print(f"Error: {input_root} not found.")
else:
    for date_folder in input_root.iterdir():
        if date_folder.is_dir():
            save_dir = output_root / date_folder.name
            save_dir.mkdir(parents=True, exist_ok=True)
            
            current_camera_id = "cam_0" if "cam_0" in date_folder.name.lower() else "cam_1"
            
            for img_path in date_folder.glob("*.[jJ][pP][gG]"):
                predictor.set_image(str(img_path))
                results = predictor(text=prompts)
                
                image_detections = []
                
                for result in results:
                    if result.boxes is not None:
                        # ... [Logic for NMS and Box calculation remains same] ...
                        boxes = result.boxes.xyxy 
                        scores = result.boxes.conf 
                        keep_indices = torchvision.ops.nms(boxes, scores, iou_threshold=0.45)
                        result.boxes = result.boxes[keep_indices]
                        
                        for box, score, class_id in zip(result.boxes.xyxy.cpu().numpy(), 
                                                       result.boxes.conf.cpu().numpy(), 
                                                       result.boxes.cls.cpu().numpy()):
                            if score < 0.5: continue
                            
                            x1, x2 = float(box[0]), float(box[2])
                            raw_label = prompts[int(class_id)]
                            
                            image_detections.append({
                                "label": raw_label,
                                "mapped_class": LABEL_MAP.get(raw_label, "other"),
                                "confidence": round(float(score), 4),
                                "center_x": round((x1 + x2) / 2, 2),
                                "timestamp": datetime.now().isoformat()
                            })
                
                # --- PREPARE DATA PAYLOAD ---
                payload = {
                    "image_name": img_path.name,
                    "camera_id": current_camera_id,
                    "timestamp": firestore.SERVER_TIMESTAMP, # Better for Firebase
                    "total_count": len(image_detections),
                    "detections": image_detections
                }

                # --- NEW: SAVE TO FIRESTORE ---
                try:
                    # Use a unique ID based on image name to avoid duplicates
                    doc_id = f"{current_camera_id}_{img_path.stem}"
                    db.collection(FIRESTORE_COLLECTION).document(doc_id).set(payload)
                    print(f"✅ Uploaded {img_path.name} to Firestore.")
                except Exception as e:
                    print(f"❌ Firestore Error: {e}")

                # [Optional] Still save local JSON as backup
                with open(save_dir / f"sam3_{img_path.stem}.json", "w") as f:
                    json.dump(payload, f, default=str, indent=4)

    print(f"Inference and Upload complete.")