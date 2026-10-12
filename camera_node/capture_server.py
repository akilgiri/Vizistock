from flask import Flask, Response
import cv2
import time
from picamera2 import Picamera2
from libcamera import Transform

app = Flask(__name__)

@app.route('/capture', methods=['GET'])
def capture():
    print("Capture requested...")

    try:
        picam2 = Picamera2()

        # Camera is mounted upside down; remove the transform if yours isn't
        t = Transform(vflip=True, hflip=True)

        # Configure camera to use the full sensor resolution
        camera_config = picam2.create_still_configuration(
            main={"size": picam2.sensor_resolution},
            transform=t
        )
        picam2.configure(camera_config)

        # Start the camera and warm up the sensor (auto-exposure/white balance)
        picam2.start()
        time.sleep(2)

        frame = picam2.capture_array()

        # Stop and release the camera hardware
        picam2.stop()
        picam2.close()

    except Exception as e:
        print(f"Error: Camera operation failed - {e}")
        return "Camera not accessible", 500

    if frame is None:
        return "Failed to grab frame", 500

    # Picamera2 returns RGB, but OpenCV expects BGR
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    ret, buffer = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])

    if not ret:
        return "Failed to encode image", 500

    print("Image captured and sent successfully!")
    return Response(buffer.tobytes(), mimetype='image/jpeg')

if __name__ == '__main__':
    # host='0.0.0.0' accepts connections from other machines on the network (e.g. over Tailscale)
    app.run(host='0.0.0.0', port=5000)
