import os
import time

import cv2

from common import (
    CAMERA_ID, init_firebase, start_camera,
    get_timestamped_filepath, upload_to_firebase, send_to_inference_server,
)

POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "20"))  # Seconds between captures


def main():
    init_firebase()
    picam2 = start_camera()

    print(f"[{CAMERA_ID}] Polling started. Capturing every {POLL_INTERVAL} seconds.")

    # The first frame triggers a full Gemini pass on the inference server
    is_first_frame = True

    try:
        while True:
            loop_start_time = time.time()
            print(f"[{CAMERA_ID}] Time triggered! Capturing and pushing to pipeline. First frame: {is_first_frame}")

            img_filename = get_timestamped_filepath()

            try:
                img_array = picam2.capture_array()
                bgr_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                cv2.imwrite(img_filename, bgr_img)

                uploaded_path = upload_to_firebase(img_filename)

                send_to_inference_server(img_filename, diff_boxes=[], is_first_frame=is_first_frame, cloud_path=uploaded_path)
                is_first_frame = False

            except Exception as e:
                print(f"[{CAMERA_ID}] Failed to capture or process frame: {e}")

            elapsed_time = time.time() - loop_start_time
            sleep_duration = POLL_INTERVAL - elapsed_time
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            else:
                print(f"[{CAMERA_ID}] Warning: Cycle took longer ({elapsed_time:.2f}s) than the interval.")

    finally:
        picam2.stop()
        print(f"[{CAMERA_ID}] Camera stopped cleanly.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down node...")
