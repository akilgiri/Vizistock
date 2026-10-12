# Experiments

Research and prototyping scripts from designing ViziStock. They're a record of the approaches we evaluated. They are **not** part of the final system and are not maintained.

The image datasets and result dumps these scripts used are not in the repo. Most scripts expect you to supply your own input folders; the paths are set at the top of each script.

| Folder | What it explores | Outcome |
|---|---|---|
| `yolo/` | Real-time YOLO detection from a webcam | Fast, but poor from a top-down angle without fine-tuning |
| `sam/` | Real-time SAM / FastSAM segmentation from a webcam | Too heavy to run on the Raspberry Pi |
| `sam3/` | Batch SAM3 text-prompted segmentation with planogram slot mapping | Became `inference_server/sam3_segmenter.py` |
| `gemini/` | Gemini product verification against reference images; prompt iterations | Became `inference_server/gemini_verifier.py`. See [`gemini/README.md`](gemini/README.md) |
| `qwen/` | Client for a university-hosted Qwen 2.5-VL (VPN only; set `VLM_BASE_URL`) | 20–60 s per request, too slow next to Gemini |
| `planogram/` | OpenCV desktop tools for shelf corners, homography and slot layout | Replaced by the [planogram tool](../planogram_tool) |
| `image_diff/` | Change detection with SSIM, MOG2 and a hybrid of both | Became `camera_node/motion_detection.py`; not used in the final demo (sensitive to lighting) |
| `tapo_camera/` | Pulling frames from a TP-Link Tapo IP camera over RTSP (set `TAPO_USERNAME`, `TAPO_PASSWORD`, `TAPO_IP`) | Replaced by a Pi CSI camera, whose 4:3 sensor covers the full shelf depth |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Scripts that use Firebase read `FIREBASE_CREDENTIALS` and `FIREBASE_STORAGE_BUCKET` from the environment. Gemini scripts read `GEMINI_API_KEY`.
