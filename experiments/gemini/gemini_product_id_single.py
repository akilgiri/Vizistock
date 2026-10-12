import cv2
import json
import numpy as np
import os
import time
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = 'gemini-2.5-flash'

# PATHS (Can be relative, e.g., 'test_data/my_file.json')
JSON_FILE = 'images/sam3_images_2026-01-31_19-46-59.json'
PLANOGRAM_FILE = 'planogram_config.json'
REF_FOLDER = 'references'

VALID_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']

PRODUCT_MAP = {
    "slot_1": "Gatorade Orange Sports Drink",
    "slot_2": "Muir Glen Crushed Tomatoes with Basil",
    "slot_3": "Antonio Amato Spaghetti",
    "slot_4": "Monster Energy Drink Ultra Fiesta"
}

def setup_gemini():
    genai.configure(api_key=API_KEY)
    return genai.GenerativeModel(MODEL_NAME, generation_config={"response_mime_type": "application/json"})

def find_local_image(filename_from_json, json_path):
    """
    Looks for the image in the SAME directory as the JSON file.
    """
    # 1. Determine the directory where the JSON lives
    json_dir = os.path.dirname(json_path)
    
    # 2. Candidate filenames (original, and without 'sam3_')
    base_name = os.path.splitext(filename_from_json)[0]
    clean_name = base_name.replace("sam3_", "")
    
    candidates = [base_name, clean_name]
    
    # 3. Search Loop
    for name in candidates:
        for ext in VALID_EXTENSIONS:
            full_name = name + ext
            
            # Check Location A: Next to the JSON file (Best Practice)
            path_a = os.path.join(json_dir, full_name)
            if os.path.exists(path_a): return path_a
            
            # Check Location B: Current Working Directory (Fallback)
            if os.path.exists(full_name): return full_name
            
    return None

def map_to_slot(cx, cy, h_matrix, virtual_width, slots):
    point = np.array([[[cx, cy]]], dtype='float32')
    mapped = cv2.perspectiveTransform(point, h_matrix)
    norm_x = mapped[0][0][0] / virtual_width
    for s_id, data in slots.items():
        if data['x_start'] <= norm_x < data['x_end']: return s_id
    return None

def verify_with_reference(model, crop_img, ref_img_path, category, product_name):
    # (Same verification logic as before)
    success_crop, encoded_crop = cv2.imencode('.jpg', crop_img)
    if not success_crop: return None
    
    content = []
    if os.path.exists(ref_img_path):
        ref_img = cv2.imread(ref_img_path)
        if ref_img is not None:
            success_ref, encoded_ref = cv2.imencode('.jpg', ref_img)
            content.append({'mime_type': 'image/jpeg', 'data': encoded_ref.tobytes()})
            print(f"    (Ref: {os.path.basename(ref_img_path)} attached)")
    
    content.append({'mime_type': 'image/jpeg', 'data': encoded_crop.tobytes()})
    
    prompt = f"""
    Role: Retail Inventory Auditor.
    Task: Verify if 'Image 2' (Live Shelf Crop) matches the product shown in 'Image 1' (Reference Master).
    
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
    except: return None

def find_reference_image(ref_folder, slot_id):
    """ Finds the reference image regardless of extension (.png, .jpg, etc.) """
    # Check all common extensions
    for ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
        full_path = os.path.join(ref_folder, f"{slot_id}{ext}")
        if os.path.exists(full_path):
            return full_path
    return None

def main():
    model = setup_gemini()
    
    # Load Configs
    try:
        with open(PLANOGRAM_FILE) as f: plano = json.load(f)
        with open(JSON_FILE) as f: detections = json.load(f)
    except Exception as e:
        print(f"Error loading files: {e}"); return

    # --- UPDATED IMAGE FINDING ---
    json_img_name = detections.get('image', '')
    # We now pass 'JSON_FILE' so it knows where to look!
    img_path = find_local_image(json_img_name.replace("sam3_", ""), JSON_FILE) 
    
    if not img_path:
        print(f"Error: Could not find image '{json_img_name}'")
        print(f"Checked in: {os.path.dirname(JSON_FILE) or '.'}")
        return

    print(f"--- Processing: {JSON_FILE} ---")
    print(f"--- Found Image: {img_path} ---")

    original_img = cv2.imread(img_path)
    h_matrix = np.array(plano['calibration']['homography_matrix'], dtype='float32')
    v_width = plano['calibration']['destination_dim'][0]
    slots = plano['planogram']

    for i, det in enumerate(detections.get('detections', [])):
        bbox = det['bbox']
        x1, y1, x2, y2 = int(bbox['x1']), int(bbox['y1']), int(bbox['x2']), int(bbox['y2'])
        
        h, w = original_img.shape[:2]
        crop = original_img[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
        
        cx, cy = (x1+x2)/2, (y1+y2)/2
        slot_id = map_to_slot(cx, cy, h_matrix, v_width, slots)
        
        if slot_id and slot_id in PRODUCT_MAP:
            expected = PRODUCT_MAP[slot_id]
            category = det['label'].rstrip('s')
            ref_path = find_reference_image(REF_FOLDER, slot_id)

            print(f"\nItem {i+1} [{category}] in {slot_id}:")
            print(f"  > Expecting: {expected}")
            
            time.sleep(1.0) 
            result = verify_with_reference(model, crop, ref_path, category, expected)
            
            if result:
                icon = "✅" if result['is_match'] else "❌"
                print(f"  > Result: {icon} (Conf: {result['confidence_score']:.2f})")
                print(f"  > Reasoning: {result['reasoning']}")
        else:
            print(f"\nItem {i+1}: Skipped (Out of bounds)")

if __name__ == "__main__":
    main()