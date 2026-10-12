import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime

# 1. Configuration
JSON_FILE = "sam3_images_2026-02-11_16-25-37.json"
SERVICE_ACCOUNT = os.getenv("FIREBASE_CREDENTIALS", "firebase-service-account.json")
COLLECTION_NAME = "shelf_detections"
# The exact filename already in your Firebase Storage
STORAGE_FILENAME = "sam3_filtered_images_2026-02-11_16-25-37.jpg" 
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET")

# 2. Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT)
    firebase_admin.initialize_app(cred, {
        'storageBucket': BUCKET_NAME
    })

db = firestore.client()
bucket = storage.bucket()

def get_existing_public_url(filename):
    """Accesses the file already in Storage and makes it public"""
    blob = bucket.blob(f"testingimage/{filename}")
    
    # Check if the file actually exists in storage before trying to make it public
    if not blob.exists():
        print(f"❌ Error: {filename} was not found in the 'testingimage' folder in Storage.")
        return None

    # Make the existing file public and return the HTTPS link
    blob.make_public() 
    return blob.public_url

def upload_processed_json():
    # Load JSON detections
    with open(JSON_FILE, 'r') as f:
        data = json.load(f)

    # Get the HTTPS URL for the file already in the cloud
    print(f"Generating public link for existing image: {STORAGE_FILENAME}...")
    public_url = get_existing_public_url(STORAGE_FILENAME)

    if not public_url:
        return

    # --- EXTRACT PARAMETERS ---
    image_name = data.get("image", "unknown.jpg")
    camera_id = "cam_0" if "cam_0" in image_name else "cam_1"
    timestamp_str = image_name.split("images_")[1].replace(".jpg", "")

    filtered_detections = []
    for d in data.get("detections", []):
        if d.get("confidence", 0) > 0.5:
            x1, x2 = d["bbox"]["x1"], d["bbox"]["x2"]
            filtered_detections.append({
                "label": d["label"],
                "confidence": round(d["confidence"], 4),
                "center_x": round((x1 + x2) / 2, 2),
                "bbox": {"x1": x1, "x2": x2}
            })

    # --- FINAL PAYLOAD ---
    payload = {
        "camera_id": camera_id,
        "image_url": public_url, # Now an https:// link that the app can use
        "timestamp": timestamp_str,
        "total_count": len(filtered_detections),
        "detections": filtered_detections,
        "processed_at": firestore.SERVER_TIMESTAMP
    }

    # Update Firestore
    db.collection(COLLECTION_NAME).document(timestamp_str).set(payload)
    print(f"✅ Success! Firestore now has the public link: {public_url}")

if __name__ == "__main__":
    upload_processed_json()