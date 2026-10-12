import cv2
import json
import numpy as np
import os
import glob
import time
import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = 'gemini-3-flash-preview' 

# PATHS
DATA_FOLDER = 'feb19_images_with_mask'      
REF_FOLDER = 'feb4_references'   
OUTPUT_DIR = 'feb19_results_v44'
DEBUG_DIR = 'feb19_debug_views_v44'

VALID_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']

PRODUCT_MAP = {
    "slot_1": "Compliments Cookies Chocolate Chip 300 g",
    "slot_2": "Compliments Peanut-Free Granola Bars S'mores 131 g",
    "slot_3": "Compliments Sparkling Water Fizzy Peach 1 L (bottle)",
    "slot_4": "Compliments Potato Chips All Dressed 200 g"
}

SHORT_NAMES = {
    "slot_1": "Cookies: Choc Chip",
    "slot_2": "Granola Bars: S'mores",
    "slot_3": "Sparkling Water: Peach",
    "slot_4": "Chips: All Dressed"
}

class Logger:
    def __init__(self):
        if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
        if not os.path.exists(DEBUG_DIR): os.makedirs(DEBUG_DIR)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = os.path.join(OUTPUT_DIR, f"audit_report_v41_{timestamp}.txt")
        self.file = open(self.filename, 'w', encoding='utf-8')
        print(f"📝 Logging to: {self.filename}")

    def log(self, message):
        print(message) 
        self.file.write(message + "\n") 
        self.file.flush()

    def close(self):
        self.file.close()

def clean_json_response(text):
    text = text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text.strip()

# --- ROBUST HSV COLOR EXTRACTION ---
def get_hsv_color_name(b, g, r):
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

def extract_dominant_color(img, mask=None, is_reference=False):
    if img is None: return "Unknown"
    
    if mask is not None:
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
        name = get_hsv_color_name(*centers[idx])
        if name not in ["Black/Dark", "White/Clear", "Grey/Neutral", "Unknown"]:
            best_color = name
            break
            
    if best_color == "Unknown":
        best_color = get_hsv_color_name(*centers[sorted_indices[0]])
        
    return best_color

def find_local_image(json_path, json_data):
    json_dir = os.path.dirname(json_path)
    base_name_json = os.path.splitext(os.path.basename(json_path))[0]
    candidates = [json_data.get('image', '').split('.')[0], base_name_json]
    if base_name_json.startswith("sam3_"): candidates.append(base_name_json.replace("sam3_", ""))
    for name in candidates:
        if not name: continue
        for ext in VALID_EXTENSIONS:
            path = os.path.join(json_dir, name + ext)
            if os.path.exists(path): return path
    return None

def find_reference_image(ref_folder, slot_id):
    if not os.path.exists(ref_folder): return None
    for ext in VALID_EXTENSIONS:
        path = os.path.join(ref_folder, f"{slot_id}{ext}")
        if os.path.exists(path): return path
    return None

def generate_visual_report(original_img, all_results, output_path):
    report_img = original_img.copy()
    for res in all_results:
        status = res.get('status', 'ERROR')
        
        # --- FEATURE: Skip successful matches to declutter the visual report ---
        if status == "MATCH":
            continue
            
        x1, y1, x2, y2 = res['bbox']
        conf = res.get('confidence', 0)
        
        color = (0, 0, 255) if status == "MISMATCH" else (0, 165, 255)
        thick = 4 if status == "MISMATCH" else 2
        
        cv2.rectangle(report_img, (x1, y1), (x2, y2), color, thick)
        label = f"{status} {conf}%"
        y_text = max(20, y1 - 10)
        (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(report_img, (x1, y_text - 20), (x1 + w + 10, y_text + 5), color, -1)
        cv2.putText(report_img, label, (x1 + 5, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
    cv2.imwrite(output_path, report_img)

# --- GEMINI API CALL ---
def verify_item_advanced(client, full_shelf_img, crop_img, bbox, ref_img_path, expected_product, slot_id, logger, debug_prefix, ref_color, obj_color):
    x1, y1, x2, y2 = bbox
    h_img, w_img = full_shelf_img.shape[:2]
    w_box, h_box = x2 - x1, y2 - y1
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    px, py = int(w_box * 0.5), int(h_box * 0.5)
    sx1, sy1 = max(0, cx - w_box//2 - px), max(0, cy - h_box//2 - py)
    sx2, sy2 = min(w_img, cx + w_box//2 + px), min(h_img, cy + h_box//2 + py)
    
    raw_scene_img = full_shelf_img[sy1:sy2, sx1:sx2].copy()
    annotated_scene_img = raw_scene_img.copy()
    
    lx1, ly1, lx2, ly2 = int(x1-sx1), int(y1-sy1), int(x2-sx1), int(y2-sy1)
    cv2.rectangle(annotated_scene_img, (lx1, ly1), (lx2, ly2), (0, 255, 0), 4)
    label_text = SHORT_NAMES.get(slot_id, "Unknown")
    cv2.putText(annotated_scene_img, label_text, (lx1, max(30, ly1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    cv2.imwrite(f"{debug_prefix}_01_crop.jpg", crop_img)
    cv2.imwrite(f"{debug_prefix}_02_annotated.jpg", annotated_scene_img)
    cv2.imwrite(f"{debug_prefix}_03_raw.jpg", raw_scene_img)

    _, e_crop = cv2.imencode('.jpg', crop_img)
    _, e_anno = cv2.imencode('.jpg', annotated_scene_img)
    _, e_raw = cv2.imencode('.jpg', raw_scene_img)
    
    parts = [
        types.Part.from_bytes(data=e_crop.tobytes(), mime_type='image/jpeg'),
        types.Part.from_bytes(data=e_anno.tobytes(), mime_type='image/jpeg')
    ]
    
    has_ref = False
    if ref_img_path and os.path.exists(ref_img_path):
        ref_img = cv2.imread(ref_img_path)
        if ref_img is not None:
            _, e_ref = cv2.imencode('.jpg', ref_img)
            parts.append(types.Part.from_bytes(data=e_ref.tobytes(), mime_type='image/jpeg'))
            has_ref = True

    parts.append(types.Part.from_bytes(data=e_raw.tobytes(), mime_type='image/jpeg'))
            
    # --- UPDATED PROMPT: GENERALIZED EXAMPLES ---
    prompt = f"""
    Role: Objective Retail Quality Assurance Auditor.
    Hypothesis: The item inside the GREEN BOX is EXACTLY "{expected_product}".
    
    # HARDWARE SENSOR FACTS:
    - Official Reference Expected Color: "{ref_color}"
    - Masked Shelf Item Detected Color: "{obj_color}"
    
    # VISUAL INPUT KEY:
    - IMAGE 1 (Detail Crop): Use strictly for reading TEXT and verifying visual design.
    - IMAGE 2 (Annotated Map): Shows spatial context (the Green Box).
    - IMAGE 3 (Reference Truth): Use this to compare the shape and design.
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
        "conclusion": "Briefly summarize the logic. Verify that your final status matches the booleans above.",
        "status": "MATCH" | "MISMATCH" | "UNKNOWN",
        "confidence": 0-100
    }}
    """
    parts.append(prompt)

    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=parts,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            parsed = json.loads(clean_json_response(resp.text))
            
            if isinstance(parsed, list) and len(parsed) > 0: parsed = parsed[0]
            if isinstance(parsed, dict): return parsed
            else:
                logger.log("      [!] API Error: Model returned invalid JSON structure.")
                time.sleep(5)
                
        except Exception as e: 
            logger.log(f"      [!] API Exception (Attempt {attempt+1}): {e}")
            time.sleep(15) 
            
    return {"status": "ERROR", "conclusion": "API Max Retries Reached."}

# --- MAIN EXECUTION ---
def main():
    logger = Logger()
    client = genai.Client(api_key=API_KEY)
    
    json_files = glob.glob(os.path.join(DATA_FOLDER, "*.json"))
    
    logger.log(f"🔍 Found {len(json_files)} JSON files in '{DATA_FOLDER}'")
    if len(json_files) == 0: 
        logger.log(f"🛑 CRITICAL ERROR: Found 0 JSON files in '{DATA_FOLDER}'. Exiting.")
        return
    
    for j_path in json_files:
        if "planogram" in j_path: continue
        
        with open(j_path) as f: data = json.load(f)
        
        img_path = find_local_image(j_path, data)
        if not img_path: 
            logger.log(f"\n⚠️ SKIPPING: {os.path.basename(j_path)} - JPG not found.")
            continue
            
        img = cv2.imread(img_path)
        img_h, img_w = img.shape[:2]
        base_fn = os.path.splitext(os.path.basename(img_path))[0]
        
        frame_debug_dir = os.path.join(DEBUG_DIR, base_fn)
        if not os.path.exists(frame_debug_dir):
            os.makedirs(frame_debug_dir)
            
        logger.log(f"\n{'='*60}")
        logger.log(f"📄 Processing: {base_fn}")
        
        all_results_flat = []
        slot_results = {k: [] for k in PRODUCT_MAP.keys()}
        detections = data.get('detections', [])
        
        for i, det in enumerate(detections):
            slot_id = det.get('slot_id')
            if not slot_id or slot_id not in PRODUCT_MAP: continue
                
            b = det['bbox']
            x1, y1, x2, y2 = int(b['x1']), int(b['y1']), int(b['x2']), int(b['y2'])
            
            debug_prefix = os.path.join(frame_debug_dir, f"item_{i:02d}_{slot_id}")
            
            # 1. Get Reference Color
            ref_path = find_reference_image(REF_FOLDER, slot_id)
            ref_img = cv2.imread(ref_path) if ref_path and os.path.exists(ref_path) else None
            ref_color = extract_dominant_color(ref_img, is_reference=True)
            
            # 2. Get Masked Object Color
            mask_filename = det.get('mask_file')
            mask_path = os.path.join(DATA_FOLDER, mask_filename) if mask_filename else None
            
            mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE) if mask_path and os.path.exists(mask_path) else None
            if mask is not None and mask.shape[:2] != img.shape[:2]:
                mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
                
            if mask is not None:
                debug_img = img.copy()
                debug_img[mask < 127] = [0, 255, 0] 
                debug_crop = debug_img[max(0, y1):min(img.shape[0], y2), max(0, x1):min(img.shape[1], x2)]
                cv2.imwrite(f"{debug_prefix}_04_debug_mask.jpg", debug_crop)
                
            obj_color = extract_dominant_color(img, mask=mask)
            
            # 3. Process API
            crop_img = img[max(0, y1):min(img_h, y2), max(0, x1):min(img_w, x2)]
            expected_product = PRODUCT_MAP[slot_id]
            
            res = verify_item_advanced(
                client, img, crop_img, (x1, y1, x2, y2), 
                ref_path, expected_product, slot_id, logger, debug_prefix, ref_color, obj_color
            )
            
            full_res = {**res, 'bbox': (x1, y1, x2, y2), 'slot': slot_id, 'expected_product': expected_product}
            all_results_flat.append(full_res)
            slot_results[slot_id].append(full_res)
            
            logger.log(f"      Item {i+1} -> {slot_id}: {full_res.get('status', 'ERROR')} ({full_res.get('confidence', 0)}%)")
            logger.log(f"           Logic: {full_res.get('conclusion', 'No reasoning provided.')}")
            time.sleep(6) 

        # --- FEATURE: Export to Firestore JSON ---
        firestore_payload = {
            "image_id": base_fn,
            "timestamp": datetime.datetime.now().isoformat(),
            "detections": all_results_flat
        }
        
        json_output_path = os.path.join(OUTPUT_DIR, f"{base_fn}_firestore_audit.json")
        with open(json_output_path, 'w', encoding='utf-8') as jf:
            json.dump(firestore_payload, jf, indent=4)
        logger.log(f"💾 Firestore JSON saved to: {json_output_path}")

        vis_path = os.path.join(OUTPUT_DIR, f"{base_fn}_visual_audit.jpg")
        generate_visual_report(img, all_results_flat, vis_path)
        logger.log(f"📸 Visual Audit saved to: {vis_path}")

    logger.close()
    print("Done.")

if __name__ == "__main__": 
    main()