import json
from collections import Counter

# --- Configuration ---
# 1. Set the path to your JSON annotation file
JSON_FILE_PATH = 'firebase_outputs/preds/03-01-10.json'

# 2. Set the confidence threshold (e.g., 0.3 means 30%)
#    The script will only count objects with a score higher than this value.
CONFIDENCE_THRESHOLD = 0.2

# 3. IMPORTANT: Map the integer labels from your model to class names.
#    Replace these placeholder names with your actual object classes.
CLASS_NAMES = {
    0: 'bottles',
    1: 'boxes',
    2: 'bags',
    3: 'jars',
    4: 'packaged snacks'
}
# ---------------------


# --- Load the Data ---
try:
    with open(JSON_FILE_PATH, 'r') as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"Error: The file '{JSON_FILE_PATH}' was not found.")
    exit()

labels = data['labels']
scores = data['scores']

print(f"Processing file: {JSON_FILE_PATH}\n")


# --- 1. Calculate the Total Number of Detections ---
total_detections = len(labels)
print(f"🔎 Total objects detected (before filtering): {total_detections}")
print("-" * 30)


# --- 2. Count All Detections by Class ---
print("📊 Counts for each class (all detections):")
unfiltered_counts = Counter(labels)
if not unfiltered_counts:
    print("  No objects found.")
else:
    for label_id, count in sorted(unfiltered_counts.items()):
        class_name = CLASS_NAMES.get(label_id, f"Unknown Label ({label_id})")
        print(f"  - {class_name}: {count}")
print("-" * 30)


# --- 3. Filter by Confidence Score and Count ---
confident_labels = []
for label, score in zip(labels, scores):
    if score >= CONFIDENCE_THRESHOLD:
        confident_labels.append(label)

print(f"🎯 Confident objects detected (score >= {CONFIDENCE_THRESHOLD}): {len(confident_labels)}")
print("📊 Counts for each confident class:")

filtered_counts = Counter(confident_labels)
if not filtered_counts:
    print("  No objects found above the confidence threshold.")
else:
    for label_id, count in sorted(filtered_counts.items()):
        class_name = CLASS_NAMES.get(label_id, f"Unknown Label ({label_id})")
        print(f"  - {class_name}: {count}")