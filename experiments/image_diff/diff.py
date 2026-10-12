# Source - https://stackoverflow.com/a/71634759
# Posted by nathancy, modified by community. See post 'Timeline' for change history
# Retrieved 2026-02-03, License - CC BY-SA 4.0

from skimage.metrics import structural_similarity
import cv2
import numpy as np

#camera resolution
#3280 x 2464 - rasppi - shelf1
#1920x1080 - webcam - shelf2

SHELF1_CAM_RESOLUTION = 3280 * 2464
SHELF2_CAM_RESOLUTION = 1920 * 1080

image_num = 3

first = cv2.imread (f'imgs/{image_num}-1.jpg')
second = cv2.imread(f'imgs/{image_num}-2.jpg')

# Convert images to grayscale
first_gray = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
second_gray = cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)

# Compute SSIM between two images
score, diff = structural_similarity(first_gray, second_gray, full=True)
print("Similarity Score: {:.3f}%".format(score * 100))

diff = (diff * 255).astype("uint8")

# Threshold the difference image, followed by finding contours to
# obtain the regions that differ between the two images
thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

# -------------------------------
# Lab CHROMA DIFF 
# -------------------------------
lab1 = cv2.cvtColor(first, cv2.COLOR_BGR2LAB)
lab2 = cv2.cvtColor(second, cv2.COLOR_BGR2LAB)

a1, b1 = lab1[:, :, 1], lab1[:, :, 2]
a2, b2 = lab2[:, :, 1], lab2[:, :, 2]

da = cv2.absdiff(a1, a2)
db = cv2.absdiff(b1, b2)

chroma_diff = cv2.addWeighted(da, 0.5, db, 0.5, 0.0)

# color sensitivity threshold (tune if needed) 14-30
#22
CHROMA_THRESH = 30
color_mask = cv2.threshold(chroma_diff, CHROMA_THRESH, 255, cv2.THRESH_BINARY)[1]

# Combine STRUCTURE (SSIM) + COLOR (Lab chroma)
thresh = cv2.bitwise_or(thresh, color_mask)
# -------------------------------

contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
contours = contours[0] if len(contours) == 2 else contours[1]

# Highlight differences
mask = np.zeros(first.shape, dtype='uint8')
filled = second.copy()

# how many pixels diff to highlight - depedent on camera 
# from intial testing min_area = 40k is desireable 
# 40000/ (3280*2464) = 0.00494931897
# 50000/(3280*2464) = 0.00618664871

min_area_const = 0.00494931897
min_area = SHELF1_CAM_RESOLUTION * min_area_const



for c in contours:
    area = cv2.contourArea(c)
    if area > 200000:
        x,y,w,h = cv2.boundingRect(c)
        cv2.rectangle(first, (x, y), (x + w, y + h), (36,255,12), 2)
        cv2.rectangle(second, (x, y), (x + w, y + h), (36,255,12), 2)
        cv2.drawContours(mask, [c], 0, (0,255,0), -1)
        cv2.drawContours(filled, [c], 0, (0,255,0), -1)


cv2.namedWindow('first', cv2.WINDOW_NORMAL)
cv2.namedWindow('second', cv2.WINDOW_NORMAL)
cv2.namedWindow('diff', cv2.WINDOW_NORMAL)
cv2.namedWindow('mask', cv2.WINDOW_NORMAL)
cv2.namedWindow('filled', cv2.WINDOW_NORMAL)

cv2.imshow('first', first)
cv2.imshow('second', second)
cv2.imshow('diff', diff)
cv2.imshow('mask', mask)
cv2.imshow('filled', filled)


cv2.waitKey()
