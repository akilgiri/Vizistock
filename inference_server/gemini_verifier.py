import cv2
import json
import numpy as np
import os
import time
from google import genai
from google.genai import types

class VizistockGeminiAuditor:
    def __init__(self, api_key, ref_folder='product_references', product_map_path='product_descriptions.json'):
        print("Initializing Gemini Auditor...")
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-3-flash-preview'
        self.ref_folder = ref_folder
        self.valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']

        # Load the local product map
        self.product_map = {}
        try:
            if os.path.exists(product_map_path):
                with open(product_map_path, 'r') as f:
                    self.product_map = json.load(f)
                print(f"Loaded product map with {len(self.product_map)} definitions.")
        except Exception as e:
            print(f"[WARNING] Could not load product map: {e}")
        

    def _get_hsv_color_name(self, b, g, r):
        hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0][0]
        h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
        
        if v < 40: return "Black/Dark"
        if s < 40 and v > 200: return "White/Clear"
        if s < 40: return "Grey/Neutral"
        
        if h < 10 or h > 165: return "Red"
        elif h < 25: return "Orange"
        elif h < 35: return "Yellow"
        elif h < 85: return "Green"
        elif h < 135: return "Blue"
        else: return "Purple/Pink"

    def _extract_dominant_color(self, img, mask=None, is_reference=False):
        if img is None: return "Unknown"
        
        # Only use the mask if it has actual pixel data
        if mask is not None and mask.size > 0:
            if mask.shape[:2] != img.shape[:2]:
                mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
            pixels = img[mask > 127]
        else:
            h, w = img.shape[:2]
            if is_reference:
                pixels = img[int(h*0.1):int(h*0.9), int(w*0.1):int(w*0.9)].reshape(-1, 3)
            else:
                pixels = img.reshape(-1, 3)
                
        if len(pixels) == 0: return "Unknown"
        
        pixels = np.float32(pixels)
        if len(pixels) > 10000:
            np.random.shuffle(pixels)
            pixels = pixels[:10000]
            
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(pixels, 3, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        counts = np.bincount(labels.flatten())
        sorted_indices = np.argsort(counts)[::-1]
        
        best_color = "Unknown"
        for idx in sorted_indices:
            name = self._get_hsv_color_name(*centers[idx])
            if name not in ["Black/Dark", "White/Clear", "Grey/Neutral", "Unknown"]:
                best_color = name
                break
                
        if best_color == "Unknown":
            best_color = self._get_hsv_color_name(*centers[sorted_indices[0]])
            
        return best_color

    def _find_reference_image(self, slot_id):
        if not os.path.exists(self.ref_folder): return None
        for ext in self.valid_extensions:
            path = os.path.join(self.ref_folder, f"{slot_id}{ext}")
            if os.path.exists(path): return path
        return None

    def verify_item(self, full_shelf_img, bbox_normalized, expected_product, slot_id, mask_crop=None):
        expected_product_verbose = self.product_map.get(expected_product, expected_product)
        img_h, img_w = full_shelf_img.shape[:2]
        
        x1 = int(bbox_normalized['x1'] * img_w)
        y1 = int(bbox_normalized['y1'] * img_h)
        x2 = int(bbox_normalized['x2'] * img_w)
        y2 = int(bbox_normalized['y2'] * img_h)
        
        # 1. Image Formatting
        crop_img = full_shelf_img[max(0, y1):min(img_h, y2), max(0, x1):min(img_w, x2)]
        
        w_box, h_box = x2 - x1, y2 - y1
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        px, py = int(w_box * 0.5), int(h_box * 0.5)
        sx1, sy1 = max(0, cx - w_box//2 - px), max(0, cy - h_box//2 - py)
        sx2, sy2 = min(img_w, cx + w_box//2 + px), min(img_h, cy + h_box//2 + py)
        
        raw_scene_img = full_shelf_img[sy1:sy2, sx1:sx2].copy()
        annotated_scene_img = raw_scene_img.copy()
        
        lx1, ly1, lx2, ly2 = int(x1-sx1), int(y1-sy1), int(x2-sx1), int(y2-sy1)
        cv2.rectangle(annotated_scene_img, (lx1, ly1), (lx2, ly2), (0, 255, 0), 4)
        
        # Truncate long product names so the label fits on the crop
        label_text = (expected_product[:22] + '...') if len(expected_product) > 25 else expected_product
        cv2.putText(annotated_scene_img, label_text, (lx1, max(30, ly1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        # 2. Color Extraction & References
        ref_path = self._find_reference_image(slot_id)
        ref_img = cv2.imread(ref_path) if ref_path else None
        ref_color = self._extract_dominant_color(ref_img, is_reference=True)
        obj_color = self._extract_dominant_color(crop_img, mask=mask_crop)

        # 3. Build API Payload
        # Apply the mask visually so Gemini only sees the isolated item
        if mask_crop is not None and mask_crop.size > 0:
            ch, cw = crop_img.shape[:2]
            mask_resized = cv2.resize(mask_crop, (cw, ch), interpolation=cv2.INTER_NEAREST)
            mask_3d = cv2.cvtColor(mask_resized, cv2.COLOR_GRAY2BGR)
            crop_img = cv2.bitwise_and(crop_img, mask_3d)

        _, e_crop = cv2.imencode('.jpg', crop_img)
        _, e_anno = cv2.imencode('.jpg', annotated_scene_img)
        _, e_raw = cv2.imencode('.jpg', raw_scene_img)
        
        parts = [
            types.Part.from_bytes(data=e_crop.tobytes(), mime_type='image/jpeg'),
            types.Part.from_bytes(data=e_anno.tobytes(), mime_type='image/jpeg')
        ]
        
        if ref_img is not None:
            _, e_ref = cv2.imencode('.jpg', ref_img)
            parts.append(types.Part.from_bytes(data=e_ref.tobytes(), mime_type='image/jpeg'))

        parts.append(types.Part.from_bytes(data=e_raw.tobytes(), mime_type='image/jpeg'))

        prompt = f"""
        Role: Objective Retail Quality Assurance Auditor.
        Hypothesis: The item inside the GREEN BOX is EXACTLY "{expected_product_verbose}".
        
        # HARDWARE SENSOR FACTS:
        - Official Reference Expected Color: "{ref_color}"
        - Masked Shelf Item Detected Color: "{obj_color}"
        
        # VISUAL INPUT KEY:
        - IMAGE 1 (Detail Crop): Use strictly for reading TEXT and verifying visual design.
        - IMAGE 2 (Annotated Map): Shows spatial context (the Green Box).
        - IMAGE 3 (Reference Truth): Use this to compare the shape and design. (May be omitted if unavailable)
        - IMAGE 4 (Raw Context): Use if the Green Box hides details.
        
        # UNIVERSAL AUDIT RULES:
        1. IGNORE BRANDING: Disregard universal brand names, overarching parent company logos, or store brand names that appear on all products from a manufacturer. Base your text evaluation strictly on distinguishing variant names, flavors, or specific sizes.
        2. THE HARDWARE COLOR GAVEL: Compare the 'Reference Expected Color' against the 'Shelf Item Detected Color'. 
           - Stark Mismatch: If they are fundamentally opposed colors (e.g., Expected 'Green' but Detected 'Red', or Expected 'Blue' but Detected 'Orange'), it is an undeniable MISMATCH. You MUST NOT apply the structural fallback.
           - Adjacent Color Forgiveness: Allow for minor lighting shifts between adjacent colors on the color wheel (e.g., 'Purple/Pink' vs 'Blue', or 'Red' vs 'Orange'). If the colors are adjacent, treat them as a valid color match.
           - Exception: If the expected product is a clear bottle, completely ignore the color rule.
        3. THE STRUCTURAL FALLBACK: Packaging that is transparent (like water bottles) acts as a lens and will reflect vibrant colors from neighboring products, or show the 'Black/Dark' shelf. If the expected product is a transparent bottle, completely ignore the hardware color. If the text is also 'Unreadable', fall back to structural geometry. If the overall physical shape, proportions, and prominent features (like caps or seals) match the Reference Truth, approve it as a MATCH.
        4. THE PARTIAL TEXT RULE (FORGIVING OCR): Camera crops, reflections, and wrinkles often cut off letters. You must evaluate partial text based on logical implication:
           - Positive Match: If the visible text logically implies the expected product (e.g., seeing "ORIGI" for "Original" or "JALAP" for "Jalapeno"), treat it as a perfect text match.
           - Negative Override: If the visible text clearly contradicts the expected product (e.g., seeing "Spicy" instead of "Mild", or "Diet" instead of "Regular"), this immediately overrides all other rules and results in a MISMATCH.

        Output EXACTLY this JSON schema. Do not use Markdown formatting outside the JSON block.
        {{
            "step_1_evidence": {{
                "expected_color": "{ref_color}",
                "detected_color": "{obj_color}",
                "image_1_variant_text": "Transcribe the specific distinguishing flavor/variant text. Write 'Unreadable' if obscured."
            }},
            "step_2_evaluation": {{
                "is_stark_color_mismatch": true/false,
                "hardware_colors_match": true/false,
                "text_match": true/false/null,
                "structural_fallback_applied": true/false
            }},
            "conclusion": "Briefly summarize the logic.",
            "status": "MATCH" | "MISMATCH" | "UNKNOWN",
            "confidence": 0-100
        }}
        """
        parts.append(prompt)

        # 4. Execute API Call with Retries
        for attempt in range(3):
            try:
                resp = self.client.models.generate_content(
                    model=self.model_name,
                    contents=parts,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0
                    )
                )
                
                clean_text = resp.text.strip()
                if clean_text.startswith("```json"): clean_text = clean_text[7:]
                elif clean_text.startswith("```"): clean_text = clean_text[3:]
                if clean_text.endswith("```"): clean_text = clean_text[:-3]
                
                return json.loads(clean_text.strip())
            except Exception as e:
                print(f"      [!] Gemini API Exception for {slot_id} (Attempt {attempt+1}): {e}")
                time.sleep(4)
                
        return {"status": "ERROR", "conclusion": "API Max Retries Reached due to rate limits."}