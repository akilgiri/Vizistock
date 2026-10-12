import cv2
import numpy as np
import json
import tkinter as tk
from tkinter import simpledialog, ttk, messagebox
import os
import sys

# --- GLOBAL CONFIGURATION ---
OUTPUT_FILE = 'interactive_planogram_config.json'

# EDIT THIS LIST to match the classes your ML model can detect
VALID_PRODUCT_CLASSES = ["can", "bottle", "box", "bag", "other"]

MAX_DISPLAY_WIDTH = 1280
MAX_DISPLAY_HEIGHT = 800

class PlanogramEditor:
    def __init__(self, shelf_id, image_path, existing_config=None, force_recalibrate=False):
        self.shelf_id = shelf_id
        self.image_path = image_path
        self.config = existing_config or {}
        
        # Load Image
        self.original_img = cv2.imread(image_path)
        if self.original_img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")
            
        self.h_orig, self.w_orig = self.original_img.shape[:2]
        
        # Display Scaling
        self.scale_factor = 1.0
        if self.w_orig > MAX_DISPLAY_WIDTH or self.h_orig > MAX_DISPLAY_HEIGHT:
            self.scale_factor = min(MAX_DISPLAY_WIDTH / self.w_orig, MAX_DISPLAY_HEIGHT / self.h_orig)
        
        self.w_disp = int(self.w_orig * self.scale_factor)
        self.h_disp = int(self.h_orig * self.scale_factor)
        self.img_disp = cv2.resize(self.original_img, (self.w_disp, self.h_disp))
        
        # State
        self.ref_points = [] 
        self.slot_dividers = [0.25, 0.5, 0.75]
        self.slot_data = {}
        self.dragging_idx = -1
        self.calibration_done = False
        
        # Default Dimensions
        self.virtual_width = 1000
        self.virtual_height = 400 
        self.real_width = 100.0 
        self.real_depth = 30.0
        self.unit_label = "cm"
        
        # LOGIC: Only restore config if we are NOT forcing a recalibration
        # AND if the config actually has data.
        if 'planogram' in self.config and not force_recalibrate:
            print(f"[{self.shelf_id}] Restoring existing configuration...")
            self.restore_config()
        else:
            if force_recalibrate:
                print(f"[{self.shelf_id}] Force Recalibrate selected. Starting fresh.")
            else:
                print(f"[{self.shelf_id}] No existing config found. Starting fresh.")

    def restore_config(self):
        saved_slots = self.config['planogram']
        self.slot_dividers = []
        for k, v in saved_slots.items():
            if v['x_end'] < 1.0:
                self.slot_dividers.append(v['x_end'])
        self.slot_dividers.sort()
        
        for i, (k, v) in enumerate(saved_slots.items()):
            classes = v.get('valid_classes', [])
            self.slot_data[i] = {'product': v['name'], 'classes': classes}
            
        self.calibration_done = True
        
        if 'calibration' in self.config:
            cal = self.config['calibration']
            self.real_width = cal.get('real_dimensions', [100])[0]
            self.real_depth = cal.get('real_dimensions', [30])[1]
            self.unit_label = cal.get('units', 'cm')
            
            # Restore points so we can re-warp immediately
            points = cal.get('source_points', [])
            self.ref_points = [tuple(p) for p in points]
            
            aspect = self.real_width / self.real_depth
            self.virtual_height = int(self.virtual_width / aspect)

    def get_user_dimensions(self):
        # Skip if we already have valid calibration data
        if self.calibration_done and len(self.ref_points) == 4: 
            return
            
        root = tk.Tk(); root.withdraw()
        
        u = simpledialog.askstring("Setup", f"Shelf {self.shelf_id}\n\nUnits (cm/in):", initialvalue="cm")
        self.unit_label = u if u else "cm"
        
        w = simpledialog.askfloat("Setup", f"Width ({self.unit_label}):", initialvalue=100.0, minvalue=1.0)
        if w: self.real_width = w
        
        d = simpledialog.askfloat("Setup", f"Depth ({self.unit_label}):", initialvalue=30.0, minvalue=1.0)
        if d: self.real_depth = d
        
        aspect = self.real_width / self.real_depth
        self.virtual_height = int(self.virtual_width / aspect)
        root.destroy()

    def get_slot_details(self, current_name, current_classes):
        """Custom Popup for Name and Multi-Select Checkboxes"""
        result = {'name': current_name, 'classes': [], 'saved': False}
        
        root = tk.Tk()
        root.title("Edit Slot Details")
        
        # Center Window
        x = (root.winfo_screenwidth() // 2) - 150
        y = (root.winfo_screenheight() // 2) - 150
        root.geometry(f"300x350+{x}+{y}")
        
        # 1. Name Input
        tk.Label(root, text="Product Name:", font=("Arial", 10, "bold")).pack(pady=(10, 5))
        name_entry = tk.Entry(root, width=30)
        name_entry.insert(0, current_name)
        name_entry.pack(pady=5)
        
        # 2. Multi-Select Classes
        tk.Label(root, text="Valid Product Types:", font=("Arial", 10, "bold")).pack(pady=(15, 5))
        
        check_vars = {}
        frame_checks = tk.Frame(root)
        frame_checks.pack()
        
        for cls_name in VALID_PRODUCT_CLASSES:
            var = tk.BooleanVar(value=(cls_name in current_classes))
            check_vars[cls_name] = var
            chk = tk.Checkbutton(frame_checks, text=cls_name, variable=var, onvalue=True, offvalue=False)
            chk.pack(anchor='w')

        def on_save():
            selected = [cls for cls, var in check_vars.items() if var.get()]
            if not selected:
                tk.messagebox.showwarning("Warning", "Please select at least one valid class.")
                return
            
            result['name'] = name_entry.get()
            result['classes'] = selected
            result['saved'] = True
            root.destroy()
            
        tk.Button(root, text="SAVE", command=on_save, bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(pady=20, fill='x', padx=20)
        root.bind('<Return>', lambda e: on_save())
        
        name_entry.focus_set()
        root.mainloop()
        return result

    def mouse_callback(self, event, x, y, flags, param):
        # --- MODE 1: CALIBRATION ---
        if not self.calibration_done:
            real_x = int(x / self.scale_factor)
            real_y = int(y / self.scale_factor)
            
            # Magnifier
            zoom_rad = 40; zoom_scale = 3
            x1 = max(0, real_x - zoom_rad); y1 = max(0, real_y - zoom_rad)
            x2 = min(self.w_orig, real_x + zoom_rad); y2 = min(self.h_orig, real_y + zoom_rad)
            
            patch = self.original_img[y1:y2, x1:x2]
            if patch.size > 0:
                patch_resized = cv2.resize(patch, None, fx=zoom_scale, fy=zoom_scale, interpolation=cv2.INTER_NEAREST)
                h_z, w_z = patch_resized.shape[:2]
                cv2.line(patch_resized, (w_z//2, 0), (w_z//2, h_z), (0,0,255), 1)
                cv2.line(patch_resized, (0, h_z//2), (w_z, h_z//2), (0,0,255), 1)
                cv2.imshow("Magnifier", patch_resized)

            if event == cv2.EVENT_LBUTTONDOWN and len(self.ref_points) < 4:
                self.ref_points.append((real_x, real_y))
            return

        # --- MODE 2: EDITOR ---
        x_pct = x / self.virtual_width
        
        hover_idx = -1
        for i, div_pct in enumerate(self.slot_dividers):
            div_px = int(div_pct * self.virtual_width)
            if abs(x - div_px) < 15:
                hover_idx = i; break

        if event == cv2.EVENT_LBUTTONDOWN:
            if hover_idx != -1: self.dragging_idx = hover_idx

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.dragging_idx != -1:
                self.slot_dividers[self.dragging_idx] = np.clip(x_pct, 0.01, 0.99)

        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging_idx = -1
            self.slot_dividers.sort()

        elif event == cv2.EVENT_RBUTTONDOWN:
            boundaries = [0.0] + self.slot_dividers + [1.0]
            clicked_slot = -1
            for i in range(len(boundaries)-1):
                if boundaries[i] <= x_pct < boundaries[i+1]:
                    clicked_slot = i; break
            
            if clicked_slot != -1:
                curr_p = self.slot_data.get(clicked_slot, {}).get('product', f"Slot {clicked_slot+1}")
                curr_c = self.slot_data.get(clicked_slot, {}).get('classes', [VALID_PRODUCT_CLASSES[0]])
                
                res = self.get_slot_details(curr_p, curr_c)
                
                if res['saved']:
                    if clicked_slot not in self.slot_data: self.slot_data[clicked_slot] = {}
                    self.slot_data[clicked_slot] = {'product': res['name'], 'classes': res['classes']}
                    print(f"Updated Slot {clicked_slot+1}: {res['name']} ({res['classes']})")

    def order_points(self, pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]; rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]; rect[3] = pts[np.argmax(diff)]
        return rect

    def run(self):
        self.get_user_dimensions()
        win_name = f"Editor: {self.shelf_id}"
        cv2.namedWindow(win_name)
        cv2.setMouseCallback(win_name, self.mouse_callback)
        H_matrix = None; warped_view = None

        # --- PRE-WARP IF LOADING CONFIG ---
        if self.calibration_done and len(self.ref_points) == 4:
            src = self.order_points(np.array(self.ref_points, dtype="float32"))
            dst = np.array([[0, 0], [self.virtual_width, 0], [self.virtual_width, self.virtual_height], [0, self.virtual_height]], dtype="float32")
            H_matrix = cv2.getPerspectiveTransform(src, dst)
            warped_view = cv2.warpPerspective(self.original_img, H_matrix, (self.virtual_width, self.virtual_height))
            cv2.resizeWindow(win_name, self.virtual_width, self.virtual_height)

        while True:
            if not self.calibration_done:
                display = self.img_disp.copy()
                for i, pt in enumerate(self.ref_points):
                    disp_pt = (int(pt[0] * self.scale_factor), int(pt[1] * self.scale_factor))
                    cv2.circle(display, disp_pt, 5, (0, 255, 0), -1)
                    cv2.putText(display, str(i+1), (disp_pt[0]+10, disp_pt[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                
                cv2.putText(display, f"Click 4 Corners ({len(self.ref_points)}/4)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                if len(self.ref_points) == 4:
                    try: cv2.destroyWindow("Magnifier")
                    except: pass
                    
                    src = self.order_points(np.array(self.ref_points, dtype="float32"))
                    dst = np.array([[0, 0], [self.virtual_width, 0], [self.virtual_width, self.virtual_height], [0, self.virtual_height]], dtype="float32")
                    H_matrix = cv2.getPerspectiveTransform(src, dst)
                    warped_view = cv2.warpPerspective(self.original_img, H_matrix, (self.virtual_width, self.virtual_height))
                    self.calibration_done = True
                    cv2.resizeWindow(win_name, self.virtual_width, self.virtual_height)
            else:
                if warped_view is None: pass
                display = warped_view.copy()
                boundaries = [0.0] + sorted(self.slot_dividers) + [1.0]
                rects = []
                for i in range(len(boundaries) - 1):
                    x1 = int(boundaries[i] * self.virtual_width)
                    x2 = int(boundaries[i+1] * self.virtual_width)
                    rects.append((x1, x2))

                for i, (x1, x2) in enumerate(rects):
                    if i < len(self.slot_dividers):
                        dx = int(self.slot_dividers[i] * self.virtual_width)
                        cv2.line(display, (dx, 0), (dx, self.virtual_height), (0, 255, 255), 2)
                    
                    prod = self.slot_data.get(i, {}).get('product', f"Slot {i+1}")
                    classes = self.slot_data.get(i, {}).get('classes', ['?'])
                    cls_str = classes[0] + ("..." if len(classes)>1 else "")
                    
                    real_slot_w = ((x2 - x1) / self.virtual_width) * self.real_width
                    cx = x1 + (x2 - x1) // 2
                    cy = self.virtual_height // 2
                    
                    cv2.putText(display, f"{real_slot_w:.1f}{self.unit_label}", (cx-20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    cv2.putText(display, prod, (cx-30, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    cv2.putText(display, f"[{cls_str}]", (cx-20, cy+25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

            cv2.imshow(win_name, display)
            key = cv2.waitKey(20) & 0xFF
            
            if key == ord('s') and self.calibration_done: return self.generate_result(H_matrix)
            elif key == ord('c'): self.calibration_done = False; self.ref_points = []
            elif key == ord('r'): self.slot_dividers = [0.25, 0.5, 0.75]
            elif key == ord('q'): return None

    def generate_result(self, H_matrix):
        final = {}
        boundaries = [0.0] + self.slot_dividers + [1.0]
        for i in range(len(boundaries)-1):
            s_id = f"slot_{i+1}"
            final[s_id] = {
                "name": self.slot_data.get(i, {}).get('product', f"Slot {i+1}"),
                "valid_classes": self.slot_data.get(i, {}).get('classes', [VALID_PRODUCT_CLASSES[0]]),
                "x_start": boundaries[i],
                "x_end": boundaries[i+1]
            }
        
        return {
            "calibration": {
                "source_points": self.ref_points,
                "destination_dim": [self.virtual_width, self.virtual_height],
                "real_dimensions": [self.real_width, self.real_depth],
                "units": self.unit_label,
                "homography_matrix": H_matrix.tolist() if H_matrix is not None else []
            },
            "planogram": final
        }

def select_cameras_dialog(shelves):
    """Startup dialog to select cameras AND mode"""
    root = tk.Tk()
    root.title("Setup")
    
    # Center
    x = (root.winfo_screenwidth() // 2) - 175
    y = (root.winfo_screenheight() // 2) - 200
    root.geometry(f"350x400+{x}+{y}")
    
    tk.Label(root, text="1. Select Cameras:", font=("Arial", 12, "bold")).pack(pady=(10,5))
    
    listbox = tk.Listbox(root, selectmode=tk.MULTIPLE, height=6)
    listbox.pack(padx=20, fill='both', expand=True)
    
    for s in shelves:
        listbox.insert(tk.END, s['id'])
    listbox.select_set(0, tk.END) # Default select all
    
    tk.Label(root, text="2. Select Action:", font=("Arial", 12, "bold")).pack(pady=(20,5))
    
    mode_var = tk.StringVar(value="edit")
    
    # Radio Buttons for Mode
    r_edit = tk.Radiobutton(root, text="Edit Planogram (Keep Calibration)", 
                            variable=mode_var, value="edit", font=("Arial", 10))
    r_edit.pack(anchor='w', padx=30)
    
    r_calib = tk.Radiobutton(root, text="Recalibrate (Reset Corners)", 
                             variable=mode_var, value="calibrate", font=("Arial", 10))
    r_calib.pack(anchor='w', padx=30)
    
    selected_indices = []
    selected_mode = "edit"
    
    def on_go():
        nonlocal selected_indices, selected_mode
        selected_indices = listbox.curselection()
        selected_mode = mode_var.get()
        root.destroy()
        
    tk.Button(root, text="START", command=on_go, bg="#2196F3", fg="white", font=("Arial", 11, "bold")).pack(pady=20, fill='x', padx=20)
    
    root.mainloop()
    
    return [shelves[i] for i in selected_indices], selected_mode

def main():
    # --- CAMERA CONFIGURATION ---
    all_shelves = [
        {"id": "shelf_1_pi",  "image": "images_2026-01-31_19-08-28.jpg"}, 
        {"id": "shelf_2_usb", "image": "images_2026-01-31_19-08-28.jpg"} 
    ]
    
    # 1. Startup Selection
    selected_shelves, mode = select_cameras_dialog(all_shelves)
    
    if not selected_shelves:
        print("No cameras selected.")
        return

    full_conf = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r') as f: full_conf = json.load(f)
        except: pass

    force_recalibrate = (mode == "calibrate")

    for s in selected_shelves:
        sid, path = s['id'], s['image']
        print(f"\n>>> Processing {sid} (Mode: {mode})...")
        
        if not os.path.exists(path):
            print(f"Skipping {sid} (Image not found: {path})")
            continue
            
        existing = full_conf.get(sid, {})
        
        # If mode is edit but no config exists, it will naturally fall back to calibrate
        # inside the class logic, which is exactly what we want.
        
        try:
            editor = PlanogramEditor(sid, path, existing, force_recalibrate)
            res = editor.run()
            
            if res:
                full_conf[sid] = res
                with open(OUTPUT_FILE, 'w') as f: json.dump(full_conf, f, indent=4)
                print(f"Saved {sid}")
            else:
                print(f"Skipped {sid}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            
    cv2.destroyAllWindows()
    print("Done.")

if __name__ == "__main__":
    main()