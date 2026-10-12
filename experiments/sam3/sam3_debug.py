import argparse
from pathlib import Path
from ultralytics.models.sam import SAM3SemanticPredictor

# The purpose of this script is to test out prompts on SAM3 and analyze which ones provide higher confidence output


# --- 1. Configuration ---
SCRIPT_DIR = Path(__file__).parent.resolve()
# Update this to point directly to the image where the boxes merge
test_image_path = str(SCRIPT_DIR / "feb19_images" / "freenove_rotated" / "raw_images_freenove_2026-02-19_18-54-03.jpg") 
test_image_path = str(SCRIPT_DIR / "feb19_images" / "freenove_rotated" / "raw_images_freenove_2026-02-19_18-52-49.jpg") 

# prompts = ["bottles", "cans", "boxes", "bags", "folded bags", "crinkled bags"]
# prompts = ["bottle", "can", "box", "bag", "folded bag", "crinkled bag"]
# prompts = ["bottle", "can", "box", "bag", "folded bag", "crinkled bag", "bags", "folded bags", "crinkled bags"]

prompts = [
    # Boxes
    "box", "boxes", "cardboard box", "carton", "snack box", "rectangular box", "package", "food box", "paperboard box",
    # Bottles
    "bottle", "bottles", "water bottle", "plastic bottle", "clear bottle", "beverage bottle", "drink bottle",
    # Cans
    "can", "cans", "aluminum can", "soda can", "beverage can", "tin can", "drink can",
    # Bags
    "bag", "bags", "folded bag", "crinkled bag", "folded bags", "crinkled bags",
    "chip bag", "potato chip bag", "bag of chips", "snack bag", "chips",
    "foil bag", "foil pouch", "mylar bag", "plastic wrapper", "shiny bag",
    "pouch", "packet", "snack packet", "crumpled pouch", "wrapper"
]


# --- 2. Initialize SAM 3 Predictor ---
# We'll use your original 0.60 confidence threshold
overrides = dict(
    conf=0.50,      
    task="segment",
    mode="predict",
    model="sam3.pt",
    half=True, 
    save=False, # We'll save manually to control the filename
)
predictor = SAM3SemanticPredictor(overrides=overrides)

# --- 3. Run Inference ---
print(f"Running raw inference on: {test_image_path}")
predictor.set_image(test_image_path)
results = predictor(text=prompts)

# --- 4. Analyze and Save ---
for result in results:
    if result.boxes is not None:
        print(f"\n--- Raw SAM3 Detections ---")
        print(f"Total raw boxes found: {len(result.boxes)}")
        
        # Print out exactly what the model sees
        for i, (box, conf, cls) in enumerate(zip(result.boxes.xyxy, result.boxes.conf, result.boxes.cls)):
            class_name = prompts[int(cls)]
            print(f"Detection {i}: [{class_name}] - Conf: {conf:.3f} - Box: {box.cpu().numpy().astype(int)}")
            
        # Save the raw output image
        output_path = SCRIPT_DIR / "debug_raw_sam3_output2.jpg"
        result.save(filename=str(output_path))
        print(f"\nSaved raw visual output to: {output_path}")
    else:
        print("No boxes detected by SAM3 at this confidence level.")