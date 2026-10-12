import cv2
import numpy as np
import json
import os

# --- CONFIGURATION ---
IMAGE_PATH = 'images_2026-01-31_19-08-28.jpg'
OUTPUT_FILE = 'planogram_config.json'

# Global variables for mouse callbacks
ref_points = []
window_name = "Calibration: Click 4 Corners (Order doesn't matter!)"

def order_points(pts):
    """
    Sorts 4 points into a specific order: [TL, TR, BR, BL].
    This ensures the 'Long Edge' of the shelf always maps to the Width.
    """
    # Initialize a list of coordinates that will be ordered
    # such that the first entry in the list is the top-left,
    # the second entry is the top-right, the third is the
    # bottom-right, and the fourth is the bottom-left
    rect = np.zeros((4, 2), dtype="float32")

    # The top-left point will have the smallest sum, whereas
    # the bottom-right point will have the largest sum
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)] # Top-Left
    rect[2] = pts[np.argmax(s)] # Bottom-Right

    # The top-right point will have the smallest difference,
    # whereas the bottom-left will have the largest difference
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] # Top-Right
    rect[3] = pts[np.argmax(diff)] # Bottom-Left

    return rect

def click_event(event, x, y, flags, params):
    """
    Mouse callback to capture the 4 corners of the shelf.
    """
    global ref_points
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(ref_points) < 4:
            ref_points.append((x, y))
            
            # BUG FIX: Removed the "+1" so the first click shows "1"
            click_count = len(ref_points)
            
            # Visual feedback
            cv2.circle(params['img'], (x, y), 10, (0, 255, 0), -1)
            cv2.putText(params['img'], f"{click_count}", (x, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(window_name, params['img'])

def main():
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: Could not find image at {IMAGE_PATH}")
        return

    original_img = cv2.imread(IMAGE_PATH)
    display_img = original_img.copy()

    # 1. Capture Corners
    print("--- STEP 1: CALIBRATION ---")
    print("Please click the 4 corners of the SHELF GRID.")
    print("Order doesn't matter (the script will fix it).")
    print("Press any key after clicking 4 points.")

    cv2.imshow(window_name, display_img)
    cv2.setMouseCallback(window_name, click_event, {'img': display_img})
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    if len(ref_points) != 4:
        print("Error: You didn't select 4 points. Exiting.")
        return

    # 2. Sort Points (The "Hardcoded" Orientation Fix)
    # This forces the points into TL, TR, BR, BL order
    src_pts = np.array(ref_points, dtype="float32")
    src_pts = order_points(src_pts)

    # 3. Compute Homography
    # We force the output to be a horizontal rectangle (Landscape)
    VIRTUAL_WIDTH = 1000
    VIRTUAL_HEIGHT = 400

    dst_pts = np.float32([
        [0, 0],                 # TL
        [VIRTUAL_WIDTH, 0],     # TR
        [VIRTUAL_WIDTH, VIRTUAL_HEIGHT], # BR
        [0, VIRTUAL_HEIGHT]     # BL
    ])

    H_matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)

    # 4. Verify
    warped_img = cv2.warpPerspective(original_img, H_matrix, (VIRTUAL_WIDTH, VIRTUAL_HEIGHT))
    
    print("\n--- STEP 2: VERIFICATION ---")
    print("Check the 'Rectified' view.")
    print("It should look like a flat, horizontal grid.")
    print("Press any key to accept. Press 'q' to quit.")
    
    cv2.imshow("Rectified View", warped_img)
    key = cv2.waitKey(0)
    cv2.destroyAllWindows()

    if key == ord('q'):
        return

    # 5. Define Slots (Hardcoded as Columns along the Long Edge)
    # x_start/x_end are percentages of the WIDTH (Long Edge)
    slots = {
        "slot_1": {"name": "Slot 1 (Left)",   "x_start": 0.00, "x_end": 0.25},
        "slot_2": {"name": "Slot 2 (Mid-L)",  "x_start": 0.25, "x_end": 0.50},
        "slot_3": {"name": "Slot 3 (Mid-R)",  "x_start": 0.50, "x_end": 0.75},
        "slot_4": {"name": "Slot 4 (Right)",  "x_start": 0.75, "x_end": 1.00}
    }

    # 6. Visualize AR Overlay (Proof that it worked)
    H_inverse = np.linalg.inv(H_matrix)
    debug_original = original_img.copy()

    for slot_id, data in slots.items():
        x1 = data["x_start"] * VIRTUAL_WIDTH
        x2 = data["x_end"] * VIRTUAL_WIDTH
        
        # Create virtual box points
        virtual_corners = np.array([
            [[x1, 0]], [[x2, 0]], [[x2, VIRTUAL_HEIGHT]], [[x1, VIRTUAL_HEIGHT]]
        ], dtype='float32')

        # Map back to real camera view
        camera_corners = cv2.perspectiveTransform(virtual_corners, H_inverse)
        pts = camera_corners.astype(int)
        
        # Draw
        cv2.polylines(debug_original, [pts], isClosed=True, color=(0, 255, 0), thickness=3)
        lbl_pt = tuple(pts[0][0])
        cv2.putText(debug_original, data["name"], (lbl_pt[0], lbl_pt[1]-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imshow("Final AR Planogram", debug_original)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    # 7. Save
    config_data = {
        "calibration": {
            "source_points": src_pts.tolist(),
            "destination_dim": [VIRTUAL_WIDTH, VIRTUAL_HEIGHT],
            "homography_matrix": H_matrix.tolist()
        },
        "planogram": slots
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()