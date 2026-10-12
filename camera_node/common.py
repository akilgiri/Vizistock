"""Shared helpers for the Raspberry Pi camera nodes: config, Firebase upload, inference server push, camera setup."""
import json
import os
import time
from datetime import datetime

import requests
import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, storage
from picamera2 import Picamera2
from libcamera import Transform

load_dotenv()

# --- Node Configuration (set via environment or .env) ---
CAMERA_ID = os.getenv("CAMERA_ID", "cam_0")  # Unique per Pi: "cam_0", "cam_1", ...
INFERENCE_SERVER_URL = os.getenv("INFERENCE_SERVER_URL", "http://localhost:5000/process_inventory")
CRED_PATH = os.getenv("FIREBASE_CREDENTIALS", "firebase-service-account.json")
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET")
FLIP_CAMERA = os.getenv("FLIP_CAMERA", "true").lower() == "true"  # Camera mounted upside down

bucket = None


def init_firebase():
    global bucket
    try:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred, {'storageBucket': BUCKET_NAME})
        bucket = storage.bucket()
        print(f"[{CAMERA_ID}] Firebase initialized successfully.")
    except Exception as e:
        raise SystemExit(f"[{CAMERA_ID}] Firebase initialization failed: {e}")


def start_camera():
    """Starts the Pi camera at full sensor resolution and waits for auto-exposure to settle."""
    picam2 = Picamera2()
    transform = Transform(vflip=True, hflip=True) if FLIP_CAMERA else Transform()
    camera_config = picam2.create_still_configuration(
        main={"size": picam2.sensor_resolution},
        transform=transform
    )
    picam2.configure(camera_config)
    print(f"[{CAMERA_ID}] Starting camera...")
    picam2.start()
    time.sleep(2)  # Sensor warmup
    return picam2


def get_timestamped_filepath():
    """Generates a dynamic local file path like results/YYYY-MM-DD/HH-MM-SS.jpg"""
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    time_filename = now.strftime("%H-%M-%S") + ".jpg"

    local_dir_path = os.path.join("results", date_folder)
    os.makedirs(local_dir_path, exist_ok=True)

    return os.path.join(local_dir_path, time_filename)


def upload_to_firebase(local_filepath):
    """Uploads the local file to Firebase Storage, mirroring the date/time structure."""
    if not local_filepath or not os.path.exists(local_filepath):
        print(f"[{CAMERA_ID}] Upload skipped: Local image file not found.")
        return None

    try:
        # Extract the date folder and filename from the local path safely
        path_parts = os.path.normpath(local_filepath).split(os.sep)
        if len(path_parts) >= 2:
            date_folder = path_parts[-2]
            filename = path_parts[-1]
        else:
            date_folder = datetime.now().strftime("%Y-%m-%d")
            filename = os.path.basename(local_filepath)

        # Organize storage by camera ID, then date, then timestamp
        cloud_path = f"raw_images/{CAMERA_ID}/{date_folder}/{filename}"

        blob = bucket.blob(cloud_path)
        print(f"[{CAMERA_ID}] Uploading to Firebase Storage as {cloud_path}...")

        blob.upload_from_filename(local_filepath)
        print(f"[{CAMERA_ID}] Firebase upload complete!")
        return cloud_path

    except Exception as e:
        print(f"[{CAMERA_ID}] Firebase upload failed: {e}")
        return None


def send_to_inference_server(image_path, diff_boxes, is_first_frame, cloud_path):
    print(f"[{CAMERA_ID}] Pushing to inference server. First Frame: {is_first_frame}")

    # 5 attempts with a 2-second backoff
    for attempt in range(5):
        try:
            with open(image_path, 'rb') as f:
                files = {'image': (image_path, f, 'image/jpeg')}
                data = {
                    'camera_id': CAMERA_ID,
                    'is_first_frame': str(is_first_frame).lower(),
                    'diff_boxes': json.dumps(diff_boxes),
                    'cloud_path': cloud_path if cloud_path else ""
                }

                response = requests.post(INFERENCE_SERVER_URL, files=files, data=data, timeout=10)
                if response.status_code == 200:
                    print(f"[{CAMERA_ID}] Successfully queued on inference server.")
                    return
                else:
                    print(f"[{CAMERA_ID}] Inference server rejected payload: {response.status_code}")

        except Exception as e:
            print(f"[{CAMERA_ID}] Network error reaching inference server (Attempt {attempt + 1}/5): {e}")

        time.sleep(2)

    print(f"[{CAMERA_ID}] FATAL: Failed to reach inference server after 5 attempts. Frame dropped.")
