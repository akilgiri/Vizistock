import firebase_admin
from firebase_admin import credentials, storage
from picamera2 import Picamera2
import time
import os
from datetime import datetime

# --- Configuration ---
# Capture an image every 60 seconds
CAPTURE_INTERVAL_SECONDS = 5

# --- Firebase Configuration ---
# Path to your Firebase Admin SDK private key JSON file
CRED_PATH = os.getenv("FIREBASE_CREDENTIALS", "firebase-service-account.json")

# Your Firebase Storage bucket URL
# Note: The bucket name is usually just the part before ".appspot.com" or ".firebasestorage.app"
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET")

# Initialize Firebase Admin SDK
try:
    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': BUCKET_NAME
    })
    bucket = storage.bucket() # Get bucket reference
    print("Firebase initialized successfully.")
except Exception as e:
    print(f"Firebase initialization failed: {e}")
    exit()

# --- Camera and Upload Functions ---

def capture_image(picam2_instance):
    """Captures an image using an initialized Picamera2 instance and saves it."""
    try:
        # --- Create a dynamic filepath based on the current date and time ---
        now = datetime.now()
        date_folder = now.strftime("%Y-%m-%d")  # e.g., "2025-07-21"
        time_filename = now.strftime("%H-%M-%S") + ".jpg"  # e.g., "14-30-05.jpg"
        
        # Create the full directory path
        local_dir_path = os.path.join("results", date_folder)
        os.makedirs(local_dir_path, exist_ok=True)  # Creates folders if they don't exist
        
        # Define the full path for the image file
        local_filepath = os.path.join(local_dir_path, time_filename)

        print(f"Capturing image and saving as {local_filepath}...")
        picam2_instance.capture_file(local_filepath)
        
        print("Image captured.")
        return local_filepath
    except Exception as e:
        print(f"Camera operation failed: {e}")
        return None

def upload_to_firebase(local_filepath):
    """Uploads a file to the Firebase Storage bucket."""
    if not local_filepath or not os.path.exists(local_filepath):
        print("Upload skipped: Local image file not found.")
        return

    try:
        # Create a unique filename for the cloud storage using the local directory structure
        cloud_path = os.path.join("images", os.path.basename(os.path.dirname(local_filepath)), os.path.basename(local_filepath))
        # On Windows, convert backslashes to forward slashes for the cloud path
        cloud_path = cloud_path.replace("\\", "/")
        
        # Get a reference to the blob (file) in Firebase Storage
        blob = bucket.blob(cloud_path)

        print(f"Uploading {local_filepath} to Firebase Storage as {cloud_path}...")
        
        # Upload the file
        blob.upload_from_filename(local_filepath)
        
        print("Upload complete!")

    except Exception as e:
        print(f"Upload failed: {e}")
    # finally:
    #     # Uncomment this block if you want to delete the local file after uploading
    #     if os.path.exists(local_filepath):
    #         os.remove(local_filepath)
    #         print(f"Local file {local_filepath} deleted.")


# --- Main execution block ---
if __name__ == "__main__":
    print(f"Starting image capture loop. Interval: {CAPTURE_INTERVAL_SECONDS} seconds.")
    print("Press Ctrl+C to exit.")

    # Initialize the camera ONCE before the loop for efficiency
    picam2 = Picamera2()
    # Configure the camera for still capture
    camera_config = picam2.create_still_configuration(main={"size": (2560, 1440)})
    picam2.configure(camera_config)
    picam2.start()
    print("Camera started. Allowing 2 seconds for sensor to adjust...")
    time.sleep(2)  # Allow time for the camera to adjust to light levels

    try:
        # Main loop for capturing and uploading images
        while True:
            loop_start_time = time.time()
            
            # --- Perform one cycle of capture and upload ---
            local_image_path = capture_image(picam2)
            upload_to_firebase(local_image_path)
            
            # --- Wait for the next interval ---
            elapsed_time = time.time() - loop_start_time
            print(f"Cycle completed in {elapsed_time:.2f} seconds.")
            
            sleep_duration = CAPTURE_INTERVAL_SECONDS - elapsed_time
            if sleep_duration > 0:
                print(f"Waiting for {sleep_duration:.2f} seconds...")
                time.sleep(sleep_duration)
            else:
                print("Warning: Capture and upload process took longer than the interval.")

    except KeyboardInterrupt:
        print("\nScript interrupted by user. Shutting down.")
    
    finally:
        # Ensure the camera is stopped and resources are released
        if picam2.started:
            picam2.stop()
            print("Camera stopped.")