# Phase 1 Prototype (archived)

Our first end-to-end prototype, built in summer 2025 and kept for reference. It used [LLMDet](https://github.com/iSEE-Laboratory/LLMDet), an open-vocabulary detector built on MMDetection. LLMDet beat YOLO from a top-down camera angle, but it struggled with partial occlusion and glare, so we replaced it with the SAM3 + Gemini pipeline in the main repo.

```
Raspberry Pi  ──upload──▶  Firebase Storage  ──poll──▶  LLMDet inference  ──▶  Firestore  ──▶  Android app
```

| Folder | Description |
|---|---|
| `raspberry_pi/` | Pi scripts that capture shelf photos on a timer and upload them to Firebase Storage. |
| `llmdet/` | `firebase_inference_service.py` watches Firebase Storage for new images, runs LLMDet with text prompts and writes the detections to Firestore. `count_objects.py` counts detections per class from a prediction JSON. |
| `android_app/` | First version of the Android app: shows the latest shelf image and detected item counts. |

These scripts read `FIREBASE_CREDENTIALS`, `FIREBASE_STORAGE_BUCKET` and (for LLMDet) `FIREBASE_PROJECT_ID` from the environment. The Android app needs your own `app/google-services.json`.
