import cv2
import time
import os
import sys
from datetime import datetime

# ================= CONFIGURATION =================
# Camera credentials come from env vars: TAPO_USERNAME, TAPO_PASSWORD, TAPO_IP
USERNAME = os.getenv("TAPO_USERNAME")
PASSWORD = os.getenv("TAPO_PASSWORD")
IP_ADDRESS = os.getenv("TAPO_IP")
STREAM_URL = f"rtsp://{USERNAME}:{PASSWORD}@{IP_ADDRESS}:554/stream1"

# Output settings
OUTPUT_DIR = "training_data"
SAMPLE_INTERVAL = 5  # 5 minutes in seconds
# =================================================

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"[INFO] Created directory: {directory}")

def capture_frame():
    print(f"[Attempting] Connecting to {IP_ADDRESS}...")
    
    # Open a FRESH connection
    cap = cv2.VideoCapture(STREAM_URL)
    
    if not cap.isOpened():
        print(f"[Error] Could not open RTSP stream. Check IP/Network.")
        return

    # Read a frame
    # Sometimes the first frame is empty/corrupt during handshake, so we read one, skip it, and read another
    cap.read() 
    ret, frame = cap.read()

    if ret:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{OUTPUT_DIR}/sample_{timestamp}.jpg"
        
        cv2.imwrite(filename, frame)
        print(f"[Success] Saved {filename}")
    else:
        print("[Error] Failed to grab frame (stream open, but no data).")

    # Explicitly release to free up the socket
    cap.release()

def main():
    ensure_dir(OUTPUT_DIR)
    print(f"[System] Starting capture loop. Interval: {SAMPLE_INTERVAL}s")

    try:
        while True:
            capture_frame()
            
            # Simple countdown (optional, mostly for debugging)
            # print(f"Sleeping for {SAMPLE_INTERVAL} seconds...")
            time.sleep(SAMPLE_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n[System] Stopped by user.")
        sys.exit(0)

if __name__ == "__main__":
    main()