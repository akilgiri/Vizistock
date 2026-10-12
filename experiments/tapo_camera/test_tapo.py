import os
import cv2

# Use the local device account credentials you created
username = os.getenv("TAPO_USERNAME")
password = os.getenv("TAPO_PASSWORD")
ip_address = os.getenv("TAPO_IP") # Assign a Static IP via your router for stability

# URL Construction
url = f"rtsp://{username}:{password}@{ip_address}:554/stream1"

cap = cv2.VideoCapture(url)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Run your CV model inference here
    # results = model(frame)

    cv2.imshow('Tapo Stream', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()