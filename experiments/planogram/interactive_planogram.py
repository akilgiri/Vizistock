import cv2
import numpy as np
import json
import tkinter as tk
from tkinter import simpledialog
import os
import sys

# --- CONFIGURATION ---
# MAKE SURE THIS MATCHES YOUR FILENAME EXACTLY
IMAGE_PATH = 'images_2026-01-31_19-08-28.jpg' 
OUTPUT_FILE = 'interactive_planogram_config.json'
DEFAULT_SLOTS = 4

# --- STATE VARIABLES ---
ref_points = []
slot_dividers = []
slot_data = {}
dragging_idx = -1
calibration_done = False
VIRTUAL_WIDTH = 1000
VIRTUAL_HEIGHT = 400 # Default, will be updated dynamically

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)] # TL
    rect[2] = pts[np.argmax(s)] # BR
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] # TR
    rect[3] = pts[np.argmax(diff)] # BL
    return rect

def get_slot_rects():
    boundaries = [0.0] + sorted(slot_dividers) + [1.0]
    rects = []
    for i in range(len(boundaries) - 1):
        x1 = int(boundaries[i] * VIRTUAL_WIDTH)
        x2 = int(boundaries[i+1] * VIRTUAL_WIDTH)
        rects.append((x1, 0, x2, VIRTUAL_HEIGHT))
    return rects

def mouse_callback(event, x, y, flags, param):
    global ref_points, slot_dividers, dragging_idx, slot_data, calibration_done

    if not calibration_done:
        if event == cv2.EVENT_LBUTTONDOWN and len(ref_points) < 4:
            ref_points.append((x, y))
        return

    # Editor Mode Logic
    x_pct = np.clip(x / VIRTUAL_WIDTH, 0.01, 0.99)
    
    # Hit Test
    hover_idx = -1
    for i, div_pct in enumerate(slot_dividers):
        div_px = int(div_pct * VIRTUAL_WIDTH)
        if abs(x - div_px) < 15:
            hover_idx = i
            break

    if event == cv2.EVENT_LBUTTONDOWN:
        if hover_idx != -1:
            dragging_idx = hover_idx

    elif event == cv2.EVENT_MOUSEMOVE:
        if dragging_idx != -1:
            slot_dividers[dragging_idx] = x_pct
            
    elif event == cv2.EVENT_LBUTTONUP:
        dragging_idx = -1
        slot_dividers.sort()

    elif event == cv2.EVENT_RBUTTONDOWN:
        # Calculate clicked slot
        boundaries = [0.0] + slot_dividers + [1.0]
        clicked_slot = -1
        for i in range(len(boundaries)-1):
            if boundaries[i] <= x_pct < boundaries[i+1]:
                clicked_slot = i
                break
        
        if clicked_slot != -1:
            # We need a new Tkinter root for this specific popup
            # because the main one was destroyed
            popup_root = tk.Tk()
            popup_root.withdraw()
            
            curr_prod = slot_data.get(clicked_slot, {}).get('product', 'Unknown')
            new_prod = simpledialog.askstring("Edit Slot", f"Product Name for Slot {clicked_slot+1}:", initialvalue=curr_prod, parent=popup_root)
            
            if new_prod:
                curr_cls = slot_data.get(clicked_slot, {}).get('class', 'Product')
                new_cls = simpledialog.askstring("Edit Class", f"Class (can/bottle/box):", initialvalue=curr_cls, parent=popup_root)
                
                if clicked_slot not in slot_data: slot_data[clicked_slot] = {}
                slot_data[clicked_slot]['product'] = new_prod
                slot_data[clicked_slot]['class'] = new_cls or "Product"
                print(f"Updated Slot {clicked_slot+1}: {new_prod}")
            
            popup_root.destroy()

def main():
    global calibration_done, slot_dividers, VIRTUAL_WIDTH, VIRTUAL_HEIGHT, slot_data
    
    # 1. FILE CHECK
    if not os.path.exists(IMAGE_PATH):
        print(f"\n[ERROR] Image not found at: {IMAGE_PATH}")
        print("Please check the filename and try again.")
        input("Press Enter to exit...") # Keeps window open so you can see error
        return

    img = cv2.imread(IMAGE_PATH)
    print(f"Loaded image: {img.shape}")

    # 2. SETUP DIALOGS (Tkinter)
    print("--- Launching Setup Dialogs ---")
    root = tk.Tk()
    root.withdraw() 
    
    # Unit Choice
    unit_choice = simpledialog.askstring("Units", "Type 'in' for Inches or 'cm' for Centimeters:", initialvalue="cm")
    if unit_choice is None: # User clicked Cancel
        print("Setup cancelled.")
        return
        
    if unit_choice and unit_choice.lower().strip() in ['in', 'inch', 'inches', '"']:
        unit_label = "in"
        default_w, default_h = 40.0, 16.0
    else:
        unit_label = "cm"
        default_w, default_h = 100.0, 40.0

    # Dimensions
    real_width = simpledialog.askfloat("Shelf Setup", f"Enter Shelf Physical WIDTH ({unit_label}):", 
                                     minvalue=1.0, maxvalue=1000.0, initialvalue=default_w)
    real_depth = simpledialog.askfloat("Shelf Setup", f"Enter Shelf Physical DEPTH ({unit_label}):", 
                                     minvalue=1.0, maxvalue=1000.0, initialvalue=default_h)
    
    # DESTROY ROOT after getting inputs to prevent OpenCV conflicts
    root.destroy()

    if not real_width or not real_depth:
        print("Invalid dimensions. Defaulting.")
        real_width, real_depth = default_w, default_h
    
    # Calculate Ratio
    aspect_ratio = real_width / real_depth
    VIRTUAL_WIDTH = 1000
    VIRTUAL_HEIGHT = int(VIRTUAL_WIDTH / aspect_ratio)
    
    print(f"Setup Complete. Virtual Size: {VIRTUAL_WIDTH}x{VIRTUAL_HEIGHT}")

    # 3. OPENCV LOOP
    cv2.namedWindow("Editor")
    cv2.setMouseCallback("Editor", mouse_callback)

    # --- CALIBRATION PHASE ---
    while not calibration_done:
        display = img.copy()
        for i, pt in enumerate(ref_points):
            cv2.circle(display, pt, 5, (0, 255, 0), -1)
            cv2.putText(display, str(i+1), (pt[0]+10, pt[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        msg = f"Click 4 Corners ({len(ref_points)}/4)"
        cv2.putText(display, msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        cv2.imshow("Editor", display)
        
        # WAITKEY IS CRITICAL
        key = cv2.waitKey(20) & 0xFF
        if key == ord('q'):
            print("Exiting...")
            cv2.destroyAllWindows()
            return
        
        if len(ref_points) == 4:
            src = order_points(np.array(ref_points))
            dst = np.array([
                [0, 0], [VIRTUAL_WIDTH, 0], 
                [VIRTUAL_WIDTH, VIRTUAL_HEIGHT], [0, VIRTUAL_HEIGHT]
            ], dtype="float32")
            
            H_matrix = cv2.getPerspectiveTransform(src, dst)
            warped_view = cv2.warpPerspective(img, H_matrix, (VIRTUAL_WIDTH, VIRTUAL_HEIGHT))
            slot_dividers = [i/DEFAULT_SLOTS for i in range(1, DEFAULT_SLOTS)]
            calibration_done = True
            print("Calibration Done. Entering Editor.")

    # --- EDITOR PHASE ---
    while True:
        display = warped_view.copy()
        rects = get_slot_rects()
        
        for i, (x1, y1, x2, y2) in enumerate(rects):
            prod_name = slot_data.get(i, {}).get('product', f"Slot {i+1}")
            cls_name = slot_data.get(i, {}).get('class', "Type?")
            
            # Divider
            if i < len(slot_dividers):
                div_x = int(slot_dividers[i] * VIRTUAL_WIDTH)
                cv2.line(display, (div_x, 0), (div_x, VIRTUAL_HEIGHT), (0, 255, 255), 3)

            # Info
            center_x = x1 + (x2 - x1) // 2
            slot_pixel_width = x2 - x1
            slot_real_width = (slot_pixel_width / VIRTUAL_WIDTH) * real_width
            
            cv2.putText(display, f"{slot_real_width:.1f} {unit_label}", (center_x-30, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.putText(display, prod_name, (center_x-40, VIRTUAL_HEIGHT//2), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(display, f"[{cls_name}]", (center_x-30, VIRTUAL_HEIGHT//2 + 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        cv2.imshow("Editor", display)
        key = cv2.waitKey(20) & 0xFF

        if key == ord('s'):
            final_slots = {}
            boundaries = [0.0] + slot_dividers + [1.0]
            for i in range(len(boundaries)-1):
                s_id = f"slot_{i+1}"
                final_slots[s_id] = {
                    "name": slot_data.get(i, {}).get('product', f"Slot {i+1}"),
                    "valid_classes": [slot_data.get(i, {}).get('class', 'product')],
                    "x_start": boundaries[i],
                    "x_end": boundaries[i+1]
                }
            
            config = {
                "calibration": {
                    "source_points": [pt for pt in ref_points],
                    "destination_dim": [VIRTUAL_WIDTH, VIRTUAL_HEIGHT],
                    "real_dimensions": [real_width, real_depth],
                    "units": unit_label,
                    "homography_matrix": H_matrix.tolist()
                },
                "planogram": final_slots
            }
            
            with open(OUTPUT_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"Saved to {OUTPUT_FILE}!")
            break

        elif key == ord('r'):
            slot_dividers = [i/DEFAULT_SLOTS for i in range(1, DEFAULT_SLOTS)]
            slot_data = {}
            print("Reset slots.")
            
        elif key == ord('q'):
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()