import cv2
import json
import numpy as np
import os
import glob
import time
import datetime
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = 'gemini-2.5-flash'

# PATHS
PLANOGRAM_FILE = 'planogram_config.json'
DATA_FOLDER = 'feb4_images'      # Folder containing detections JSONs AND source images
REF_FOLDER = 'feb4_references'   # Folder containing master product images (slot_1.jpg, etc.)
OUTPUT_DIR = 'feb4_results'      # Where to save the text report

# Image extensions to search for
VALID_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']

PRODUCT_MAP = {
    "slot_1": "Compliments Cookies Chocolate Chip 300 g",
    "slot_2": "MCompliments Peanut-Free Granola Bars S'mores 131 g",
    "slot_3": "Compliments Sparkling Water Fizzy Peach 1 L (bottle)",
    "slot_4": "Compliments Potato Chips All Dressed 200 g"
}

# --- HELPER CLASS FOR LOGGING ---
class Logger:
    def __init__(self):
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = os.path.join(OUTPUT_DIR, f"batch_results_{timestamp}.txt")
        self.file = open(self.filename, 'w', encoding='utf-8')
        print(f"📝 Logging output to: {self.filename}")

    def log(self, message):
        print(message)  # Print to console
        self.file.write(message + "\n") # Write to file

    def close(self):
        self.file.close()

def setup_gemini():
    genai.configure(api_key=API_KEY)
    return genai.GenerativeModel(MODEL_NAME, generation_config={"response_mime_type": "application/json"})

def map_to_slot(cx, cy, h_matrix, virtual_width, slots):
    point = np.array([[[cx, cy]]], dtype='float32')
    mapped = cv2.perspectiveTransform(point, h_matrix)
    norm_x = mapped[0][0][0] / virtual_width
    for s_id, data in slots.items():
        if data['x_start'] <= norm_x < data['x_end']: return s_id
    return None

def find_local_image(json_path, json_data):
    """
    Robustly finds the image associated with a JSON detection file.
    """
    json_dir = os.path.dirname(json_path)
    base_name_json = os.path.splitext(os.path.basename(json_path))[0]
    
    candidates = []
    if 'image' in json_data:
        candidates.append(os.path.splitext(json_data['image'])[0])
    candidates.append(base_name_json)
    if base_name_json.startswith("sam3_"):
        candidates.append(base_name_json.replace("sam3_", ""))

    for name in candidates:
        if not name: continue
        for ext in VALID_EXTENSIONS:
            full_name = name + ext
            path = os.path.join(json_dir, full_name)
            if os.path.exists(path):
                return path
    return None

def find_reference_image(ref_folder, slot_id):
    if not os.path.exists(ref_folder): return None
    for ext in VALID_EXTENSIONS:
        full_path = os.path.join(ref_folder, f"{slot_id}{ext}")
        if os.path.exists(full_path):
            return full_path
    return None

def verify_with_reference(model, crop_img, ref_img_path, category, product_name):
    success_crop, encoded_crop = cv2.imencode('.jpg', crop_img)
    if not success_crop: return None
    
    content = []
    has_ref = False
    
    # 1. Attach Reference Image (Image 1)
    if ref_img_path and os.path.exists(ref_img_path):
        ref_img = cv2.imread(ref_img_path)
        if ref_img is not None:
            success_ref, encoded_ref = cv2.imencode('.jpg', ref_img)
            content.append({'mime_type': 'image/jpeg', 'data': encoded_ref.tobytes()})
            has_ref = True
    
    # 2. Attach Live Crop (Image 2)
    content.append({'mime_type': 'image/jpeg', 'data': encoded_crop.tobytes()})
    
    # 3. Prompt (EXACTLY from single script)
    task_desc = "Task: Verify if 'Image 2' (Live Shelf Crop) matches the product shown in 'Image 1' (Reference Master)." if has_ref else "Task: Verify if the Image (Live Shelf Crop) matches the description."

    prompt = f"""
    Role: Retail Inventory Auditor.
    {task_desc}
    
    Product Info: {product_name} ({category})
    
    Instructions:
    1. Analyze the Reference (Image 1) to identify key visual features:
       - Dominant Colors (e.g., Red Label, Blue Liquid).
       - Cap/Lid Color (e.g., White Cap, Silver Tab).
       - Material/Texture (e.g., Cardboard Box, Metallic Can, Plastic Bottle).
       
    2. Analyze the Live Crop (Image 2). 
       - **WARNING:** Image 2 is likely a TOP-DOWN view from a shelf camera.
       
    3. Perform Visual Matching:
       - **Color Consistency:** Does the top of the object in Image 2 match the color palette of Image 1? 
         (e.g., If Reference is a Green Bottle, Image 2 should show a Green Cap or Green Liquid).
       - **Material Consistency:** Does the material look correct? (e.g., Metallic reflection for cans, Matte for cardboard).
       - **Specific Features:**
         - If Can: Look for colored rims or tabs that match the reference.
         - If Box/Pasta: Look for matching packaging color/patterns.
    
    Decision Logic:
    - **MATCH:** If the object in Image 2 plausibly looks like the "Top View" of the object in Image 1.
    - **MISMATCH:** If the colors, materials, or shapes are completely different.
    
    Output JSON: {{ "is_match": bool, "confidence_score": float, "reasoning": "brief explanation" }}
    """
    content.append(prompt)
    
    try:
        response = model.generate_content(content)
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

def main():
    logger = Logger()
    model = setup_gemini()
    
    # 1. Load Planogram
    try:
        with open(PLANOGRAM_FILE) as f: plano = json.load(f)
    except:
        logger.log(f"❌ Error: Could not load {PLANOGRAM_FILE}")
        logger.close()
        return

    h_matrix = np.array(plano['calibration']['homography_matrix'], dtype='float32')
    v_width = plano['calibration']['destination_dim'][0]
    slots = plano['planogram']
    
    # 2. Find all JSON files
    json_files = glob.glob(os.path.join(DATA_FOLDER, "*.json"))
    json_files = [f for f in json_files if os.path.basename(f) != PLANOGRAM_FILE]
    
    logger.log(f"Found {len(json_files)} detection files in '{DATA_FOLDER}'.")

    for json_path in json_files:
        logger.log(f"\n{'='*60}")
        logger.log(f"📄 Processing: {os.path.basename(json_path)}")
        
        try:
            with open(json_path) as f: detections = json.load(f)
        except:
            logger.log("❌ Error reading JSON file. Skipping.")
            continue

        img_path = find_local_image(json_path, detections)
        
        if not img_path:
            logger.log(f"⚠️ SKIP: No matching image found for {os.path.basename(json_path)}")
            continue
            
        logger.log(f"📷 Found Image: {os.path.basename(img_path)}")
        
        original_img = cv2.imread(img_path)
        if original_img is None:
            logger.log("❌ Error: Image could not be read by OpenCV.")
            continue

        det_list = detections.get('detections', [])
        if not det_list:
            logger.log("   (No detections in file)")
            continue

        for i, det in enumerate(det_list):
            bbox = det['bbox']
            x1, y1, x2, y2 = int(bbox['x1']), int(bbox['y1']), int(bbox['x2']), int(bbox['y2'])
            
            # Safe Crop
            h, w = original_img.shape[:2]
            crop = original_img[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
            
            # Map to Slot
            cx, cy = (x1+x2)/2, (y1+y2)/2
            slot_id = map_to_slot(cx, cy, h_matrix, v_width, slots)
            
            if slot_id and slot_id in PRODUCT_MAP:
                expected = PRODUCT_MAP[slot_id]
                category = det['label'].rstrip('s') 
                
                ref_path = find_reference_image(REF_FOLDER, slot_id)
                ref_msg = f"(Ref: {os.path.basename(ref_path)})" if ref_path else "(No Ref)"

                logger.log(f"  [{i+1}] Slot {slot_id}: {category} vs {expected} {ref_msg}")
                
                time.sleep(1.0) 
                res = verify_with_reference(model, crop, ref_path, category, expected)
                
                if res and 'error' not in res:
                    icon = "✅" if res['is_match'] else "❌"
                    logger.log(f"      -> {icon} Conf: {res['confidence_score']:.2f} | {res['reasoning']}")
                else:
                    logger.log(f"      -> ⚠️ API Error or Invalid Response")
            else:
                pass # Out of bounds ignored

    logger.close()

if __name__ == "__main__":
    main()