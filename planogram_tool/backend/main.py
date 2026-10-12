from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import json
import logging
import calibration
import os
import firebase_admin
from firebase_admin import credentials, firestore
import cv2
import base64
import requests

# --- FIREBASE INITIALIZATION ---
if not firebase_admin._apps:
    cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS", "firebase-service-account.json"))
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DEBUGGING HANDLER ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation Error: {exc.errors()}")
    logger.error(f"Body: {await request.body()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": str(exc)},
    )

# --- DATA MODELS ---
class Slot(BaseModel):
    name: str
    valid_classes: List[str]
    threshold: int
    x_start: float
    x_end: float

class SaveRequest(BaseModel):
    shelf_id: str
    real_dimensions: dict 
    calibration: dict
    slots: Dict[str, Slot]
    destination: str  # 'local', 'firestore', or 'both'

# --- RASPBERRY PI NETWORK CONFIG ---
PI_ENDPOINTS = {
    "cam_0": os.getenv("CAM_0_HOST", "<cam-0-pi-ip>"), # Top Shelf Pi
    "cam_1": os.getenv("CAM_1_HOST", "<cam-1-pi-ip>") # Bottom Shelf Pi
}

# --- ENDPOINTS ---
@app.get("/api/cameras")
def get_cameras():
    return [
        {"id": "cam_0", "name": "Aisle 0 - Top Shelf"},
        {"id": "cam_1", "name": "Aisle 0 - Bottom Shelf"}
    ]

@app.get("/api/capture")
def capture_live_image(shelf_id: str):
    """Triggers the specific Pi hardware to take a fresh photo."""
    try:
        pi_ip = PI_ENDPOINTS.get(shelf_id)
        
        if pi_ip:
            try:
                res = requests.get(f"http://{pi_ip}:5000/capture", timeout=5)
                if res.status_code == 200:
                    img_b64 = base64.b64encode(res.content).decode('utf-8')
                    return {"image": f"data:image/jpeg;base64,{img_b64}"}
            except Exception as req_err:
                logger.warning(f"Could not reach Pi at {pi_ip}: {req_err}. Falling back to local camera.")

        cap = cv2.VideoCapture(0)
        for _ in range(5): cap.read() # Warm up sensor
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            raise HTTPException(status_code=500, detail="Failed to grab frame from local camera fallback.")
            
        _, buffer = cv2.imencode('.jpg', frame)
        img_b64 = base64.b64encode(buffer).decode('utf-8')
        return {"image": f"data:image/jpeg;base64,{img_b64}"}
        
    except Exception as e:
        logger.error(f"Live capture error: {str(e)}")
        raise HTTPException(status_code=500, detail="Camera hardware not accessible.")

@app.post("/api/calibrate")
async def calibrate(image: UploadFile = File(...), points: str = Form(...)):
    try:
        pts_list = json.loads(points)
        if len(pts_list) != 4:
            raise HTTPException(status_code=400, detail="Need exactly 4 points")
        contents = await image.read()
        warped_b64, matrix = calibration.process_calibration(contents, pts_list)
        return {
            "warped_image": f"data:image/jpeg;base64,{warped_b64}",
            "homography_matrix": matrix
        }
    except Exception as e:
        logger.error(f"Calibration Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save")
def save_config(req: SaveRequest):
    try:
        logger.info(f"Saving config for {req.shelf_id}")
        
        # 1. CLEAN DATA 
        clean_calibration = req.calibration.copy()
        
        if "source_points" in clean_calibration:
            raw_pts = clean_calibration["source_points"]
            flattened_pts = []
            for pt in raw_pts:
                if isinstance(pt, (list, tuple)):
                    flattened_pts.extend([float(x) for x in pt])
                else:
                    flattened_pts.append(float(pt))
            clean_calibration["source_points"] = flattened_pts

        if "homography_matrix" in clean_calibration:
            matrix = clean_calibration["homography_matrix"]
            if isinstance(matrix, list) and len(matrix) > 0 and isinstance(matrix[0], list):
                clean_calibration["homography_matrix"] = [float(item) for sublist in matrix for item in sublist]

        # 2. EXACT JSON STRUCTURE
        camera_data = {
            "meta": {
                "shelf_id": req.shelf_id,
                "real_dimensions": req.real_dimensions
            },
            "calibration": clean_calibration,
            "planogram": {k: v.model_dump() for k, v in req.slots.items()}
        }

        # 3. SAVE TO FIRESTORE (COMPLETE OVERWRITE PER CAMERA)
        if req.destination in ["firestore", "both"]:
            if db:
                doc_ref = db.collection("planograms").document("master_config")
                
                # Using merge=[req.shelf_id] commands Firestore to completely replace 
                # this specific camera's map (wiping old slots), while leaving other cameras alone.
                doc_ref.set({req.shelf_id: camera_data}, merge=[req.shelf_id])
                logger.info(f"Successfully replaced {req.shelf_id} in Firestore.")
        
        # 4. SAVE LOCALLY
        if req.destination in ["local", "both"]:
            local_filepath = "planogram_config.json"
            local_db = {}
            if os.path.exists(local_filepath):
                try:
                    with open(local_filepath, "r") as f:
                        local_db = json.load(f)
                except json.JSONDecodeError:
                    pass

            local_db[req.shelf_id] = camera_data
            with open(local_filepath, "w") as f:
                json.dump(local_db, f, indent=4)
            logger.info(f"Successfully saved {req.shelf_id} to local file: {local_filepath}")
            
        return {"status": "saved", "shelf_id": req.shelf_id}
        
    except Exception as e:
        logger.error(f"Save failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)