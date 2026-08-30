import argparse
import base64
import traceback
import numpy as np
import requests
from flask import Flask, jsonify
from mife.single.fhiding.ddh import FeDDH
from nacl.public import PublicKey, SealedBox

from fhipe_serializer import serialize_functional_key
from delegated_crypto import generate_ek, serialize_ek
from bucketing import get_cancer_type_name, get_bucket_info, pad_weights

# 1. Configurable Model Selection
parser = argparse.ArgumentParser(description="Hospital KGC Node")
parser.add_argument("--model", type=int, default=0, help="Cancer model index (0-32)")
args, unknown = parser.parse_known_args()
MODEL_INDEX = args.model

app = Flask(__name__)

# 2. Load Model Weights
print(f"Loading master 33-cancer weights for Model Index: {MODEL_INDEX}...")
raw_weights_data = np.load("master_33_cancer_weights.npy", allow_pickle=True)

if isinstance(raw_weights_data, np.ndarray) and raw_weights_data.ndim == 2:
    selected_model_weights = raw_weights_data[MODEL_INDEX]
else:
    selected_model_weights = list(raw_weights_data.item().values())[MODEL_INDEX]

# 3. Extract Active Non-Zero Features
active_indices = np.where(selected_model_weights != 0)[0]
if len(active_indices) == 0:
    active_indices = np.arange(min(8, len(selected_model_weights)))
filtered_weights = selected_model_weights[active_indices]

# 4. Quantize and Pad to Bucket Dimension[cite: 1]
SCALING_FACTOR = 100.0
raw_quantized = [int(abs(val)) + 1 for val in np.rint(filtered_weights * SCALING_FACTOR)]
RAW_DIM = len(raw_quantized)

BUCKET_NAME, BUCKET_DIM = get_bucket_info(MODEL_INDEX, RAW_DIM)
# Take active features that fit within the bucket, then pad to bucket_dim
ACTIVE_FEATURES_TO_USE = min(RAW_DIM, max(4, BUCKET_DIM - 3))
raw_feature_subset = raw_quantized[:ACTIVE_FEATURES_TO_USE]

quantized_weights = pad_weights(raw_feature_subset, BUCKET_DIM)
DIMENSION = len(quantized_weights)

CANCER_NAME = get_cancer_type_name(MODEL_INDEX)
print(f"Loaded: {CANCER_NAME} | Active Features: {len(raw_feature_subset)} | Bucket: '{BUCKET_NAME}' (Padded Dim: {DIMENSION})")

# 5. Initialize Keys at Bucket Dimension
master_key = FeDDH.generate(DIMENSION)
ek = generate_ek(master_key)

@app.route("/get_model_info", methods=["GET"])
def get_model_info():
    return jsonify({
        "model_index": MODEL_INDEX,
        "cancer_name": CANCER_NAME,
        "active_features_count": len(raw_feature_subset),
        "bucket_name": BUCKET_NAME,
        "bucket_dimension": DIMENSION
    })

@app.route("/get_dimension", methods=["GET"])
def get_dimension():
    return jsonify({"dimension": DIMENSION})

@app.route("/get_ek", methods=["GET"])
def get_ek():
    return jsonify({"ek": serialize_ek(ek)})

@app.route("/get_key", methods=["GET"])
def get_key():
    try:
        sk = FeDDH.keygen(quantized_weights, master_key)
        json_sk = serialize_functional_key(sk)
        
        # PyNaCl Sealed Key Delivery[cite: 1]
        cloud_resp = requests.get("http://127.0.0.1:5002/public_key").json()
        cloud_pk_bytes = base64.b64decode(cloud_resp["public_key"])
        cloud_pk = PublicKey(cloud_pk_bytes)
        
        sealed_box = SealedBox(cloud_pk)
        encrypted_sk = sealed_box.encrypt(json_sk.encode("utf-8"))
        encoded_sealed_sk = base64.b64encode(encrypted_sk).decode("utf-8")
        
        return jsonify({"functional_key": encoded_sealed_sk})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5001)