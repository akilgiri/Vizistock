import cv2
from ultralytics import SAM, FastSAM

# Load the SAM model
model = FastSAM("FastSAM-s.pt")

# Open webcam and set resolution
cap = cv2.VideoCapture(0) # 0 is the default camera
cap.set(3, 1920)
cap.set(4, 1080)

if not cap.isOpened():
    print("Cannot open camera")
    exit()

# classNames = ["person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck", "boat",
#               "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
#               "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
#               "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat",
#               "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
#               "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli",
#               "carrot", "hot dog", "pizza", "donut", "cake", "chair", "sofa", "pottedplant", "bed",
#               "diningtable", "toilet", "tvmonitor", "laptop", "mouse", "remote", "keyboard", "cell phone",
#               "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
#               "teddy bear", "hair drier", "toothbrush"
#               ]

while True:
    # read the frames
    ret, frame = cap.read()

    # check if frame was read correctly
    if not ret:
        print("Error reading frame.")
        break

    # run inference on the frame
    results = model(frame, imgsz=320, device='cpu') # set device='cpu' for CPU, device='cuda' for Nvidia GPU and device='mps' for Apple Silicon

    # visualize the results on the frame
    annotated_frame = results[0].plot()

    # display the resulting frame
    cv2.imshow('FastSAM Real-Time Segmentation', annotated_frame)


    # press q to quit the opencv viewer
    if cv2.waitKey(1) == ord('q'):
        break

# release the capture
cap.release()
cv2.destroyAllWindows()