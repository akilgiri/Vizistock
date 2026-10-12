# firebase_inference_service.py

# ---- Imports ----
import firebase_admin
from firebase_admin import credentials, storage, firestore
import time
import os
import ast
import json
import copy
from collections import Counter
from argparse import ArgumentParser
from mmengine.logging import print_log
from mmdet.apis import DetInferencer
from mmdet.evaluation import get_classes
from datetime import datetime

# ---- Global variable to hold the pristine class names ----
CLASS_NAMES = []

# ---- Argument Parsing Function ----
def parse_args():
    # Make sure the function knows it will modify the global variable
    global CLASS_NAMES
    
    parser = ArgumentParser()
    parser.add_argument(
        '--inputs', type=str, default='firebase',
        help='Placeholder for input. Actual inputs will come from Firebase.')
    parser.add_argument(
        'model', type=str,
        help='Config or checkpoint .pth file or the model name and alias.')
    parser.add_argument('--weights', default=None, help='Checkpoint file')
    parser.add_argument(
        '--out-dir', type=str, default='firebase_outputs',
        help='Output directory of images or prediction results.')
    parser.add_argument(
        '--texts', help='text prompt, such as "bench . car .", "$: coco"')
    parser.add_argument(
        '--device', default='cuda:0', help='Device used for inference')
    parser.add_argument(
        '--pred-score-thr', type=float, default=0.3,
        help='bbox score threshold')
    parser.add_argument(
        '--batch-size', type=int, default=1, help='Inference batch size.')
    parser.add_argument(
        '--show', action='store_true',
        help='Display the image in a popup window.')
    parser.add_argument(
        '--no-save-vis', action='store_true',
        help='Do not save detection vis results')
    parser.add_argument(
        '--no-save-pred', action='store_true',
        help='Do not save detection json results')
    parser.add_argument(
        '--print-result', action='store_true',
        help='Whether to print the results.')
    parser.add_argument(
        '--palette', default='none',
        choices=['coco', 'voc', 'citys', 'random', 'none'],
        help='Color palette used for visualization')
    parser.add_argument(
        '--custom-entities', '-c', action='store_true',
        help='Whether to customize entity names?')
    parser.add_argument(
        '--chunked-size', '-s', type=int, default=-1,
        help='Chunked size for large category prediction.')
    parser.add_argument(
        '--tokens-positive', '-p', type=str,
        help='Used to specify positive token locations.')

    call_args = vars(parser.parse_args())

    # --- Argument Post-processing ---
    # We need the prediction file for analysis, so force it to be saved.
    call_args['no_save_pred'] = False
    
    if call_args.get('no_save_vis') and call_args.get('no_save_pred'):
        call_args['out_dir'] = ''

    if call_args['model'].endswith('.pth'):
        call_args['weights'] = call_args['model']
        call_args['model'] = None
    
    # --- ✨ CORRECTED CLASS NAME LOGIC ✨ ---
    if call_args['texts'] is not None:
        class_names_list = []
        if call_args['texts'].startswith('$:'):
            dataset_name = call_args['texts'][3:].strip()
            class_names_list = get_classes(dataset_name)
        else:
            class_names_list = [name.strip() for name in call_args['texts'].split('.') if name.strip()]
        
        # This correctly populates the global variable for our analysis function
        CLASS_NAMES = class_names_list
        # This correctly formats the argument for the DetInferencer
        call_args['texts'] = class_names_list

    if call_args['tokens_positive'] is not None:
        call_args['tokens_positive'] = ast.literal_eval(
            call_args['tokens_positive'])

    init_kws = ['model', 'weights', 'device', 'palette']
    init_args = {kw: call_args.pop(kw) for kw in init_kws}
    return init_args, call_args

# ---- Function to Analyze and Upload Counts ----
def analyze_and_upload_counts(json_path, class_names, threshold, original_image_path):
    """
    Reads a prediction JSON, counts objects above a threshold,
    and uploads the result to Firestore.
    """
    print(f"📊 Analyzing predictions from: {json_path}")
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"🔥 Error: JSON file not found at '{json_path}'. Cannot process counts.")
        return
    except json.JSONDecodeError:
        print(f"🔥 Error: Could not decode JSON from '{json_path}'. It might be empty or malformed.")
        return

    labels = data.get('labels', [])
    scores = data.get('scores', [])

    print(f"🔍 Found {len(scores)} scores in JSON: {scores}")
    
    confident_labels = [label for label, score in zip(labels, scores) if score >= threshold]
    label_counts = Counter(confident_labels)
    
    counts_by_name = {class_names[label_id]: count for label_id, count in label_counts.items() if label_id < len(class_names)}

    print(f"📈 Confident Counts (Threshold >= {threshold}): {counts_by_name}")

    firestore_data = {
        'originalImage': original_image_path,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'confidenceThreshold': threshold,
        'objectCounts': counts_by_name,
        'totalObjectsFound': len(confident_labels)
    }

    try:
        db.collection('detectionCounts').add(firestore_data)
        print("✅ Object counts successfully uploaded to Firestore.")
    except Exception as e:
        print(f"🔥 Error uploading counts to Firestore: {e}")

# ---- Helper function for uploading visualization ----
def upload_visualization(local_filepath):
    """Uploads the visualization image to Firebase Storage."""
    if not local_filepath or not os.path.exists(local_filepath):
        print(f"Upload skipped: Visualization file not found at {local_filepath}")
        return
    try:
        now = datetime.now()
        date_folder = now.strftime("%Y-%m-%d")
        cloud_filename = f"LLMDet_visualizations/{date_folder}/{os.path.basename(local_filepath)}"
        blob = bucket.blob(cloud_filename)
        print(f"Uploading {local_filepath} to Firebase Storage as {cloud_filename}...")
        blob.upload_from_filename(local_filepath)
        print("🖼️  Visualization upload complete!")
    except Exception as e:
        print(f"🔥 Upload failed: {e}")

# ===================================================================
# 1. ONE-TIME INITIALIZATION AT STARTUP
# ===================================================================

print("✅ Initializing Firebase...")
CRED_PATH = os.getenv("FIREBASE_CREDENTIALS", "firebase-service-account.json")
try:
    FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': f'{FIREBASE_PROJECT_ID}.appspot.com'
    })
    db = firestore.client()
    bucket = storage.bucket()
    print("Firebase initialized successfully.")
except Exception as e:
    print(f"🔥 Firebase initialization failed: {e}")
    exit()

print("🧠 Parsing model configuration from command line...")
init_args, call_args_template = parse_args()

print("🧠 Initializing DetInferencer (this will take some time)...")
start_init_time = time.time()
inferencer = DetInferencer(**init_args)
# Restoring user's original chunked_size logic
chunked_size = call_args_template.pop('chunked_size')
inferencer.model.test_cfg.chunked_size = chunked_size
end_init_time = time.time()
print(f"✅ Model initialized in {end_init_time - start_init_time:.2f} seconds. Ready for inference.")


# ===================================================================
# 2. DEFINE THE LISTENER CALLBACK FOR REPEATED INFERENCE
# ===================================================================

def on_snapshot(col_snapshot, changes, read_time):
    """This function runs every time a new image task appears in Firestore."""
    for change in changes:
        if change.type.name == 'ADDED':
            task_doc = change.document.to_dict()
            doc_id = change.document.id
            storage_path = task_doc.get("filePath")

            if not storage_path:
                print(f"⚠️ Task {doc_id} has no filePath. Skipping.")
                continue

            print(f"\n📥 New task received: {storage_path}")
            
            today_str = datetime.now().strftime("%Y-%m-%d")
            local_download_dir = os.path.join("downloads", today_str)
            os.makedirs(local_download_dir, exist_ok=True)
            
            local_filename = os.path.basename(storage_path)
            local_filepath = os.path.join(local_download_dir, local_filename)

            blob = bucket.blob(storage_path)
            blob.download_to_filename(local_filepath)
            print(f"Image downloaded to {local_filepath}")

            current_call_args = copy.deepcopy(call_args_template)
            current_call_args['inputs'] = local_filepath
            
            base_out_dir = call_args_template.get('out_dir', 'firebase_outputs')
            current_call_args['out_dir'] = os.path.join(base_out_dir, today_str)
            
            print("🚀 Starting inference...")
            start_inference_time = time.time()
            inferencer(**current_call_args)
            end_inference_time = time.time()

            print(f"⚡ Inference complete in {end_inference_time - start_inference_time:.2f} seconds.")
            
            if not current_call_args.get('no_save_vis'):
                visualization_path = os.path.join(current_call_args['out_dir'], "vis", local_filename)
                upload_visualization(visualization_path)

            json_filename = os.path.splitext(local_filename)[0] + '.json'
            prediction_json_path = os.path.join(current_call_args['out_dir'], "preds", json_filename)
            
            analyze_and_upload_counts(
                json_path=prediction_json_path,
                class_names=CLASS_NAMES,
                threshold=current_call_args['pred_score_thr'],
                original_image_path=storage_path
            )

            db.collection("imageQueue").document(doc_id).delete()
            print(f"✅ Task {doc_id} deleted from queue.")


# ===================================================================
# 3. START THE LISTENER AND WAIT FOR TASKS
# ===================================================================

query = db.collection("imageQueue")
query_watch = query.on_snapshot(on_snapshot)

print("\n👂 Service is running. Listening for new images in Firestore...")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Shutting down the inference service.")
