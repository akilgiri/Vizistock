import firebase_admin
from firebase_admin import credentials, storage
from picamera2 import Picamera2
import time
import os
from datetime import datetime

# --- Firebase Configuration ---
# Path to your Firebase Admin SDK private key JSON file
CRED_PATH = os.getenv("FIREBASE_CREDENTIALS", "firebase-service-account.json")

# Your Firebase Storage bucket URL
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET")

# Initialize Firebase Admin SDK
try:
    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': BUCKET_NAME
    })
    bucket = storage.bucket(BUCKET_NAME)
    print("Firebase initialized successfully.")
except Exception as e:
    print(f"Firebase initialization failed: {e}")
    exit()

# --- Camera and Upload Functions ---
def capture_image():
    """Captures an image using Picamera2 and saves it."""
    try:

        # --- Create a dynamic filepath based on the current date and time ---
        now = datetime.now()
        date_folder = now.strftime("%Y-%m-%d") # e.g., "2025-07-19"
        time_filename = now.strftime("%H-%M-%S") + ".jpg" # e.g., "18-56-57.jpg"
        
        # Create the full directory path
        local_dir_path = os.path.join("results", date_folder)
        os.makedirs(local_dir_path, exist_ok=True) # Creates folders if they don't exist
        
        # Define the full path for the image file
        local_filepath = os.path.join(local_dir_path, time_filename)

        picam2 = Picamera2()
        # Configure the camera for still capture
        camera_config = picam2.create_still_configuration(main={"size": picam2.sensor_resolution})
        # camera_config = picam2.create_still_configuration(main={"size": (4608, 1728)})
        # camera_config = picam2.create_still_configuration(main={"size": (2560, 1440)})


        picam2.configure(camera_config)
        
        print("Starting camera...")
        picam2.start()
        time.sleep(2)  # Allow time for the camera to adjust to light levels
        
        print(f"Capturing image and saving as {local_filepath}...")
        picam2.capture_file(local_filepath)
        
        picam2.stop()
        print("Image captured.")
        return local_filepath
    except Exception as e:
        print(f"Camera operation failed: {e}")
        return None

def upload_to_firebase(local_filepath):
    """Uploads a file to the Firebase Storage bucket."""
    if not local_filepath:
        print("Upload skipped: Unable to find the image provided.")
        return

    try:
        # Create a unique filename for the cloud storage 
        now = datetime.now()
        date_folder = now.strftime("%Y-%m-%d") # e.g., "2025-07-19"
        # cloud_filename = f"images/{int(time.time())}_{os.path.basename(local_filepath)}"
        cloud_filename = f"images/{date_folder}/{os.path.basename(local_filepath)}"
        
        # Get a reference to the blob (file) in Firebase Storage
        blob = bucket.blob(cloud_filename)

        print(f"Uploading {local_filepath} to Firebase Storage as {cloud_filename}...")
        
        # Upload the file
        blob.upload_from_filename(local_filepath)
        
        print("Upload complete!")
        # Optional: Make the blob publicly viewable
        # blob.make_public()
        # print(f"Public URL: {blob.public_url}")

    except Exception as e:
        print(f"Upload failed: {e}")
    # finally:
    #     # Clean up the local image file after upload
    #     # DO WE WANT TO DELETE LOCAL FILES?
    #     if os.path.exists(local_filepath):
    #         os.remove(local_filepath)
    #         print(f"Local file {local_filepath} deleted.")


# --- Main execution block ---
if __name__ == "__main__":
    start_time = time.time()
    local_image_path = capture_image()
    upload_to_firebase(local_image_path)
    end_time = time.time()
    print(f"Time taken to capture and upload to firebase: {end_time-start_time}s")