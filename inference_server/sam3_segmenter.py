import os
import json
import torch
import torchvision
import cv2
import numpy as np
from ultralytics.models.sam import SAM3SemanticPredictor

class VizistockSAM3Gatekeeper:
    def __init__(self, config_path, prompts_path="sam3_prompts.json"):
        print("Initializing SAM3 Gatekeeper & Loading Planogram...")
        with open(prompts_path, "r") as f:
            prompt_data = json.load(f)["aliases"]
            
        self.prompts = []
        self.LABEL_MAP = {}
        self.CANONICAL_IDS = {}
        
        # Dynamically build the canonical maps
        for canonical_name, aliases in prompt_data.items():
            canonical_id = len(self.CANONICAL_IDS)
            self.CANONICAL_IDS[canonical_name] = canonical_id
            for alias in aliases:
                self.prompts.append(alias)
                self.LABEL_MAP[alias] = canonical_name
                
        self.ID_TO_LABEL = {v: k for k, v in self.CANONICAL_IDS.items()}

        # Load Planogram
        with open(config_path, "r") as f:
            self.planogram_config = json.load(f)

        # Load Model
        weights = os.getenv("SAM3_WEIGHTS", "sam3.pt")
        overrides = dict(conf=0.60, task="segment", mode="predict", model=weights, half=True, save=False)
        self.predictor = SAM3SemanticPredictor(overrides=overrides)
        print("SAM3 Model loaded into VRAM.")

    def _merge_masks_in_place(self, boxes, scores, cls, masks, bag_class_id, default_iou=0.50, bag_iou=0.05):
        """Class-aware mask merging running on the GPU."""
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

    def _check_overlap(self, sam_box, diff_boxes):
        """Returns True if overlapping. Allows bypass if polling with empty diff_boxes."""
        if not diff_boxes:
            return True
            
        sx1, sy1, sx2, sy2 = sam_box
        for (dx, dy, dw, dh) in diff_boxes:
            dx1, dy1 = dx, dy
            dx2, dy2 = dx + dw, dy + dh
            if sx1 < dx2 and sx2 > dx1 and sy1 < dy2 and sy2 > dy1:
                return True
        return False

    def _get_planogram_slot(self, box, H_matrix, max_w, planogram):
        x_point = (box[0] + box[2]) / 2.0
        y_point = box[3] 
        pt = np.array([[[x_point, y_point]]], dtype=np.float32)
        transformed_pt = cv2.perspectiveTransform(pt, H_matrix)
        proj_x = transformed_pt[0][0][0]
        x_ratio = max(0.0, min(1.0, proj_x / max_w))
        
        for slot_id, slot_info in planogram.items():
            if slot_info["x_start"] <= x_ratio <= slot_info["x_end"]:
                return slot_id, slot_info["name"], slot_info.get("valid_classes", [])
        return "unknown_slot", "Unknown Product", []

    def _is_on_shelf(self, box, H_matrix, max_w, max_h, margin=0.40):
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

    def process_frame(self, image_np, camera_id, diff_boxes, is_first_frame):
        img_h, img_w = image_np.shape[:2]
        cam_config = self.planogram_config.get(camera_id)
        if not cam_config:
            print(f"Error: No planogram config for {camera_id}")
            return []

        H = np.array(cam_config["calibration"]["homography_matrix"], dtype=np.float32).reshape(3, 3)
        virtual_w, virtual_h = cam_config["calibration"]["virtual_dim"]
        planogram_data = cam_config["planogram"]

        self.predictor.set_image(image_np)
        results = self.predictor(text=self.prompts)
        
        processed_items = []

        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                continue

            # Load PyTorch Tensors on GPU
            boxes = result.boxes.xyxy
            scores = result.boxes.conf
            cls = result.boxes.cls
            masks = result.masks.data if result.masks is not None else None

            # 1. Standard NMS
            nms_indices = torchvision.ops.nms(boxes, scores, iou_threshold=0.75)
            boxes = boxes[nms_indices]
            scores = scores[nms_indices]
            cls = cls[nms_indices]
            if masks is not None: 
                masks = masks[nms_indices]

            # 2. Planogram Shelf Filtering (all on-shelf items are kept; diffs only affect routing)
            keep_indices = [
                i for i, box in enumerate(boxes.cpu().numpy())
                if self._is_on_shelf(box, H, virtual_w, virtual_h)
            ]

            if not keep_indices:
                continue

            boxes = boxes[keep_indices]
            scores = scores[keep_indices]
            cls = cls[keep_indices]
            if masks is not None:
                masks = masks[keep_indices]

            # 3. Dynamic ID Normalization for Merging
            for idx in range(len(cls)):
                raw_name = self.prompts[int(cls[idx])]
                base_label = self.LABEL_MAP.get(raw_name, raw_name)
                cls[idx] = self.CANONICAL_IDS[base_label]

            # 4. Class-Aware Mask Merging 
            if masks is not None:
                bag_canonical_id = self.CANONICAL_IDS.get("bag", -1)
                keep_mask = self._merge_masks_in_place(boxes, scores, cls, masks, bag_class_id=bag_canonical_id)
                
                boxes = boxes[keep_mask]
                scores = scores[keep_mask]
                cls = cls[keep_mask]
                masks = masks[keep_mask]

            # Convert final cleaned tensors back to CPU for Firestore parsing
            final_boxes = boxes.cpu().numpy()
            final_scores = scores.cpu().numpy()
            final_cls = cls.cpu().numpy()
            final_masks = masks.cpu().numpy() if masks is not None else [None] * len(final_boxes)

            for idx, (box, score, class_id, mask_data) in enumerate(zip(final_boxes, final_scores, final_cls, final_masks)):
                
                normalized_label = self.ID_TO_LABEL.get(int(class_id), "unknown")
                slot_id, product_name, valid_classes = self._get_planogram_slot(box, H, virtual_w, planogram_data)

                # Check if this specific item intersects with the motion diff
                is_changed = is_first_frame or self._check_overlap(box, diff_boxes)

                if slot_id == "unknown_slot":
                    routing_status = "IGNORE"
                elif valid_classes and normalized_label not in valid_classes:
                    routing_status = "CLASS_MISMATCH"
                elif is_changed:
                    # It moved! Send it to Gemini.
                    routing_status = "NEEDS_GEMINI"
                else:
                    # It's a valid class, but it didn't move. Cache it!
                    routing_status = "UNCHANGED"

                mask_crop = None
                if mask_data is not None:
                    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
                    full_mask = (mask_data * 255).astype(np.uint8)
                    mask_crop = full_mask[y1:y2, x1:x2]

                processed_items.append({
                    "label": normalized_label,
                    "confidence": float(score),
                    "slot_id": slot_id,
                    "expected_product": product_name,
                    "routing_status": routing_status,
                    "mask_crop": mask_crop, 
                    "bbox": {
                        "x1": round(float(box[0]) / img_w, 4),
                        "y1": round(float(box[1]) / img_h, 4),
                        "x2": round(float(box[2]) / img_w, 4),
                        "y2": round(float(box[3]) / img_h, 4)
                    }
                })

        return processed_items