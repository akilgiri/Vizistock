# Camera Node

Scripts that run on each shelf's Raspberry Pi. In our prototype, each node was a **Raspberry Pi 5** with a **Freenove 8MP wide-angle camera** (IMX219, 4:3, ~120° FOV) on the CSI-2 port, mounted about 30 cm above the shelf and looking down. The node captures shelf images, uploads them to Firebase Storage, and sends them to the [inference server](../inference_server).

## Files

| File | Description |
|---|---|
| `polling_node.py` | **Used in the final demo.** Captures a frame every `POLL_INTERVAL` seconds and sends it for processing. |
| `motion_node.py` | Event-driven alternative: uses MOG2 + SSIM motion detection to send frames only after the shelf changes. |
| `motion_detection.py` | The MOG2 and SSIM change-detection functions used by `motion_node.py`. |
| `common.py` | Shared code: environment config, camera setup, Firebase upload, and the request to the inference server. |
| `capture_server.py` | A small Flask server that returns a still photo on demand. The [planogram tool](../planogram_tool) calls it during shelf setup. |
| `planogram_config.json` | Planogram/calibration config (same file as the inference server's), used by `motion_node.py`. |

## Setup

```bash
sudo apt install -y python3-picamera2
pip install -r requirements.txt
cp .env.example .env
```

| Variable | Description |
|---|---|
| `CAMERA_ID` | Unique ID for this Pi (`cam_0`, `cam_1`, …). Must match a key in `planogram_config.json`. |
| `INFERENCE_SERVER_URL` | e.g. `http://<inference-server-ip>:5000/process_inventory` |
| `FIREBASE_CREDENTIALS` | Path to your Firebase service account JSON |
| `FIREBASE_STORAGE_BUCKET` | e.g. `your-project-id.firebasestorage.app` |
| `POLL_INTERVAL` | Optional, seconds between captures for the polling node (default `20`) |
| `PLANOGRAM_CONFIG` | Optional, defaults to `planogram_config.json` |
| `FLIP_CAMERA` | Optional, `true` if the camera is mounted upside down (default `true`) |

We connected the Pis and the inference server with [Tailscale](https://tailscale.com/), so they could reach each other securely across networks.

---

## Polling node: `polling_node.py`

```bash
python polling_node.py
```

Each cycle it:

1. Captures a full-resolution still (3280×2464) with `picamera2`.
2. Saves it to `results/YYYY-MM-DD/HH-MM-SS.jpg`.
3. Uploads it to Firebase Storage at `raw_images/{CAMERA_ID}/{date}/{time}.jpg`.
4. POSTs the image to the inference server's `/process_inventory` endpoint (5 attempts, 2 s apart).
5. Sleeps for the rest of the polling interval.

The first frame is sent with `is_first_frame=true`. Every frame sends `diff_boxes=[]`, so the server verifies every item with Gemini each cycle. Stop with `Ctrl+C`; the camera is released cleanly.

---

## Motion-triggered node: `motion_node.py`

Instead of sending a frame on a timer, this node watches the shelf and sends a frame only after a change is confirmed and the shopper's hand has left the frame.

```bash
python motion_node.py
```

```
Startup
  └─ Warm up the MOG2 background model (100 frames)
  └─ Send a first frame with is_first_frame=true

Idle (every 5 s)
  └─ MOG2 background subtraction: motion? → Active

Active (every 0.5 s)
  └─ SSIM between consecutive frames, until the shelf stops changing (hand removed)

Confirm
  └─ MOG2 against the background model: what actually changed?
  └─ Changed → upload frame + changed regions (diff_boxes) → inference server
  └─ Rebuild the background model (100 frames) so the change isn't detected again
```

Sending `diff_boxes` lets the server skip Gemini for items outside the changed regions. On a change, debug images (frame with boxes, MOG2 mask) are saved to `debug_frames/`.

Tuning constants at the top of `motion_node.py`:

```python
IDLE_POLL_INTERVAL = 5.0         # Seconds between idle checks
ACTIVE_MOTION_INTERVAL = 0.5     # Seconds between SSIM checks during active motion
MOG2_THRESHOLD = 1500            # Min contour area (px²) to count as motion at 640x480
SSIM_THRESHOLD = 275000          # Min contour area (px²) for SSIM at full 8MP resolution
```

> **Why the demo used polling:** pixel-based differencing proved unreliable in our test environment. Glare from glossy packaging and lighting changes caused false changes that were hard to threshold consistently. Polling costs more Gemini calls but tracks the shelf reliably. In our report, we proposed *semantic* differencing (comparing SAM3 detections between frames instead of pixels) as future work.

---

## Capture server: `capture_server.py`

```bash
python capture_server.py      # serves on :5000
curl http://<pi-ip>:5000/capture -o shelf.jpg
```

`GET /capture` opens the camera, waits 2 s for auto-exposure and white balance, captures a full-resolution JPEG, and releases the camera. The [planogram tool](../planogram_tool) uses it to get a fresh photo of the shelf for calibration.
