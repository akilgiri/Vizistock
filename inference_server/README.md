# Inference Server

The compute backbone of ViziStock. It receives shelf images from the [camera nodes](../camera_node), runs a two-stage vision pipeline (SAM3 → Gemini) to count stock and find misplaced products, and syncs the results to Firebase for the [Android app](../android_app).

## Overview

```
Camera node (Raspberry Pi)
       |
       | POST /process_inventory (image + metadata)
       v
  [ Inference server (FastAPI) ]
       |
       |--- Stage 1: SAM3 segmenter ---------> Segments every product on the shelf
       |          (sam3_segmenter.py)          Maps each one to a planogram slot
       |                                       Routes each item:
       |                                         CLASS_MISMATCH → immediate alert
       |                                         NEEDS_GEMINI   → send to Stage 2
       |                                         UNCHANGED      → reuse cached result
       |
       |--- Stage 2: Gemini verifier --------> Verifies the product variant/flavour
       |          (gemini_verifier.py)         Multi-image chain-of-thought prompt
       |                                       Colour analysis + reference images
       v
  [ Firebase Firestore + Storage ]
       - inventory_current/{camera_id}   (live state for the app)
       - inventory_history/{doc_id}      (timestamped snapshots)
       - inventory_logs/{doc_id}         (mismatch records)
       - sam3_results/, gemini_results/  (debug images + JSON)
```

## Files

| File | Description |
|---|---|
| `server.py` | FastAPI app: receives frames, runs the async SAM3 and Gemini workers, holds shelf state, syncs Firestore |
| `sam3_segmenter.py` | Stage 1: SAM3 segmentation, mask merging, planogram slot mapping, routing |
| `gemini_verifier.py` | Stage 2: Gemini multimodal product-variant verification |
| `planogram_config.json` | Per-camera calibration (homography) and slot definitions, from the [planogram tool](../planogram_tool) |
| `product_descriptions.json` | Maps slot product names to longer descriptions given to Gemini |
| `sam3_prompts.json` | Text prompts (aliases) SAM3 uses for each product class (`bag`, `box`, `bottle`, `can`) |
| `product_references/` | One reference photo per planogram slot (`slot_1.jpg`, `slot_2.jpg`, …) |
| `.env.example` | Template for the environment variables |

## Pipeline details

### Stage 1: SAM3 segmenter

`VizistockSAM3Gatekeeper` runs SAM3 with text prompts to segment every product on the shelf, then:

1. **Filters** detections to the shelf area, using the camera's homography to project each item into a top-down "virtual shelf".
2. **Merges** overlapping masks of the same class on the GPU. Deformable bags often get split into several segments, so bags use a much lower IoU threshold (0.05) than other classes (0.50).
3. **Maps** each item to a planogram slot from the projected x-position of its bottom-centre point.
4. **Routes** each item:
   - `CLASS_MISMATCH`: the product type doesn't match the slot (e.g. a bag in a box slot). Flagged immediately, without calling Gemini.
   - `NEEDS_GEMINI`: the right type of product, which needs its variant checked.
   - `UNCHANGED`: the item didn't overlap any motion region reported by the camera node, so its previous Gemini result is reused (matched by IoU).

> `UNCHANGED` only applies with the motion-triggered camera node. The polling node, used for the final demo, sends no motion regions, so every item goes to Gemini on every frame.

### Stage 2: Gemini verifier

`VizistockGeminiAuditor` checks whether each `NEEDS_GEMINI` item is the exact product the planogram expects:

1. Crops and masks the item, and annotates a zoomed-out scene with a green box around it.
2. Finds the dominant colour of the item and of the slot's reference photo (k-means, then an HSV colour name).
3. Sends Gemini 3 Flash four images (masked crop, annotated scene, reference photo, raw scene) and a structured chain-of-thought prompt.
4. Parses the JSON verdict: `MATCH`, `MISMATCH` or `UNKNOWN`.

The prompt's rules are:
- Ignore brand names shared by every product; judge only variant or flavour text.
- Stark colour mismatches (e.g. expected green, detected red) are always a mismatch, but adjacent colours are forgiven for lighting.
- Transparent bottles skip the colour check and fall back to comparing shape.
- Partial text counts if it implies the expected product (e.g. "JALAP" → "Jalapeño"), but contradicting text ("Spicy" vs "Mild") always means a mismatch.

### Async architecture

- **`sam3_worker`** processes only the most recent frame per camera. Frames that arrive while it's busy are overwritten, not queued.
- **`gemini_worker`** wakes when SAM3 queues items, verifies them concurrently (`asyncio.gather`, at most 2 calls at a time), and merges the results back into the shelf state, skipping any item that a newer frame has replaced.

Splitting the stages means the ~0.65 s SAM3 stage never waits on the ~14 s Gemini stage, so the server absorbs network jitter and API latency without dropping frames.

## Setup

### Requirements

- Python 3.10+
- NVIDIA GPU with CUDA (SAM3 needs about 8 GB of VRAM)
- A Firebase project with Firestore and Storage enabled
- A Gemini API key

### Install

```bash
pip install -r requirements.txt
cp .env.example .env
```

### Environment variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `FIREBASE_CREDENTIALS` | Path to your Firebase service account JSON (default `firebase-service-account.json`) |
| `FIREBASE_STORAGE_BUCKET` | Firebase Storage bucket, e.g. `your-project-id.firebasestorage.app` |
| `PLANOGRAM_CONFIG` | Optional, defaults to `planogram_config.json` |
| `SAM3_WEIGHTS` | Optional, defaults to `sam3.pt` |
| `ENABLE_DEBUG_STORAGE` | Optional, `true`/`false` (default `true`): upload annotated debug images |
| `PORT` | Optional, defaults to `5000` |

### Files you need to provide

| File | How to get it |
|---|---|
| `sam3.pt` | SAM3 weights are gated: request access on [Hugging Face](https://huggingface.co/facebook/sam3), then see the [Ultralytics SAM3 docs](https://docs.ultralytics.com/models/sam-3/) |
| Firebase service account JSON | Firebase Console → Project Settings → Service Accounts → Generate new private key |
| `planogram_config.json` | Generate it with the [planogram tool](../planogram_tool). The included file matches our demo shelves. |
| `product_references/slot_N.jpg` | One reference photo per slot, named by slot ID |

### Run

```bash
python server.py
```

## API

**`POST /process_inventory`**: multipart form sent by the camera nodes. It returns `{"status": "success"}` immediately and processes the frame asynchronously.

| Field | Type | Description |
|---|---|---|
| `camera_id` | string | Camera identifier, e.g. `cam_0` |
| `is_first_frame` | string | `"true"` on a node's first frame |
| `diff_boxes` | string | JSON array of motion regions `[[x, y, w, h], ...]` (empty when polling) |
| `cloud_path` | string | Firebase Storage path of the uploaded raw image |
| `image` | file | The shelf image (JPEG) |

## Firestore data

| Collection | Document ID | Contents |
|---|---|---|
| `inventory_current` | `{camera_id}` | Latest shelf state, read live by the app |
| `inventory_history` | `{camera_id}_{YYYYMMDD_HHMMSS}` | Snapshot of every pipeline run |
| `inventory_logs` | `{camera_id}_errors_{YYYYMMDD_HHMMSS}` | Class and product mismatch records |

Shelf state document:

```json
{
  "camera_id": "cam_1",
  "pipeline_status": "COMPLETED",
  "raw_image_url": "https://...",
  "last_updated": "2026-03-09T18:45:30+00:00",
  "slots": {
    "slot_1": {
      "expected_product": "Compliments Cookies: Chocolate Chip",
      "items": {
        "item_0": {
          "sam3_detected_class": "box",
          "routing_status": "NEEDS_GEMINI",
          "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.9},
          "gemini_api_status": "MATCH",
          "final_alert": "NONE",
          "gemini_conclusion": "Color and text match confirmed."
        }
      }
    }
  }
}
```

## Planogram config format

```json
{
  "cam_1": {
    "meta": { "shelf_id": "cam_1", "real_dimensions": { "width": 32, "depth": 17, "unit": "in" } },
    "calibration": {
      "source_points": [...],      // 4 shelf corners in the camera image (flattened x, y)
      "homography_matrix": [...],  // 3x3 matrix, flattened
      "virtual_dim": [1000, 400]   // size of the top-down virtual shelf
    },
    "planogram": {
      "slot_1": {
        "name": "Compliments Cookies: Chocolate Chip",
        "valid_classes": ["box"],  // SAM3 classes allowed in this slot
        "threshold": 1,            // low-stock threshold
        "x_start": 0.0,            // slot's horizontal range (0–1) on the virtual shelf
        "x_end": 0.5
      }
    }
  }
}
```

## Debug artifacts

When `ENABLE_DEBUG_STORAGE=true`, each cycle uploads to Firebase Storage:

- `sam3_results/{camera_id}_{timestamp}_annotated.jpg`: SAM3 boxes with planogram slot boundaries drawn on.
- `gemini_results/{camera_id}_{timestamp}_audit.jpg` and `_audit.json`: the Gemini verdicts, with mismatches highlighted.
