import cv2
import numpy as np
import base64

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)] 
    rect[2] = pts[np.argmax(s)] 
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] 
    rect[3] = pts[np.argmax(diff)] 
    return rect

def process_calibration(file_bytes, points):
    # 1. Decode Image
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # 2. Compute Homography
    V_W, V_H = 1000, 400
    src = order_points(np.array(points, dtype="float32"))
    dst = np.array([[0,0], [V_W,0], [V_W,V_H], [0,V_H]], dtype="float32")
    
    H = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, H, (V_W, V_H))
    
    # 3. Encode Warped Image to Base64 for Frontend
    _, buffer = cv2.imencode('.jpg', warped)
    img_base64 = base64.b64encode(buffer).decode('utf-8')
    
    return img_base64, H.tolist()