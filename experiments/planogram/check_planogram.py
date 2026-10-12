import json
import numpy as np
import cv2

# --- FILE PATHS ---
# Make sure these match your actual file names
PLANOGRAM_FILE = 'planogram_config.json'
DETECTION_FILE = 'sam3_images_2026-01-31_19-46-59.json'

def get_centroid(bbox):
    """
    Calculates the center (x, y) of a bounding box.
    """
    x1, y1, x2, y2 = bbox['x1'], bbox['y1'], bbox['x2'], bbox['y2']
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    return cx, cy

def map_to_planogram(px, py, h_matrix, virtual_width):
    """
    Applies Homography to map Pixel (u,v) -> Planogram (x,y).
    Returns the normalized x-coordinate (0.0 to 1.0).
    """
    # OpenCV requires point structure: [[[x, y]]]
    point = np.array([[[px, py]]], dtype='float32')
    
    # Apply the Matrix Transform
    mapped_point = cv2.perspectiveTransform(point, h_matrix)
    
    # Extract projected X coordinate
    virtual_x = mapped_point[0][0][0]
    
    # Normalize to 0.0 - 1.0 range based on the virtual width defined in calibration
    normalized_x = virtual_x / virtual_width
    return normalized_x

def main():
    # 1. Load Data
    try:
        with open(PLANOGRAM_FILE, 'r') as f:
            plano_data = json.load(f)
        with open(DETECTION_FILE, 'r') as f:
            detect_data = json.load(f)
    except FileNotFoundError as e:
        print(f"Error loading files: {e}")
        return

    # 2. Extract Calibration Data
    h_matrix = np.array(plano_data['calibration']['homography_matrix'], dtype='float32')
    virtual_width = plano_data['calibration']['destination_dim'][0]
    
    # 3. Inject Missing Product Classes (As requested)
    # Zone 1, 2, 4 -> Can/Bottle
    # Zone 3 -> Pasta/Spaghetti
    print("--- UPDATING PLANOGRAM RULES ---")
    slots = plano_data['planogram']
    
    # Define valid labels for each slot
    slots['slot_1']['valid_classes'] = ['cans', 'bottles']
    slots['slot_2']['valid_classes'] = ['cans', 'bottles']
    slots['slot_3']['valid_classes'] = ['spaghetti', 'pasta']
    slots['slot_4']['valid_classes'] = ['cans', 'bottles']

    for s_id, data in slots.items():
        print(f"{data['name']}: Expects {data['valid_classes']}")
    print("-" * 40)

    # 4. Process Detections
    print(f"\nProcessing {len(detect_data['detections'])} detections from SAM 3...\n")
    
    for i, detection in enumerate(detect_data['detections']):
        label = detection['label']
        conf = detection['confidence']
        bbox = detection['bbox']
        
        # A. Calculate Centroid
        cx, cy = get_centroid(bbox)
        
        # B. Map to Planogram Coordinates
        norm_x = map_to_planogram(cx, cy, h_matrix, virtual_width)
        
        # C. Find which Slot this falls into
        matched_slot = None
        status = "UNKNOWN LOCATION"
        
        for s_id, s_data in slots.items():
            # Check if norm_x is within this slot's range
            if s_data['x_start'] <= norm_x < s_data['x_end']:
                matched_slot = s_data
                
                # D. Check Compliance (Does Label match Valid Classes?)
                if label in s_data['valid_classes']:
                    status = "✅ CORRECT"
                else:
                    status = f"❌ MISPLACED (Found {label}, Expected {s_data['valid_classes']})"
                break
        
        # E. Report
        print(f"Item {i+1}: {label.upper()} (Conf: {conf:.2f})")
        print(f"  > Position: Camera ({cx:.0f}, {cy:.0f}) -> Planogram X: {norm_x*100:.1f}%")
        
        if matched_slot:
            print(f"  > Location: {matched_slot['name']}")
            print(f"  > Status:   {status}")
        else:
            print(f"  > Location: OUT OF BOUNDS (Not in any active slot)")
        
        print("-" * 20)

if __name__ == "__main__":
    main()