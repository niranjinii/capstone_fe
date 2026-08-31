import argparse
import base64
import traceback
import numpy as np
import requests
import logging
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("Hospital")
from mife.single.fhiding.ddh import FeDDH
from nacl.public import PublicKey, SealedBox

from fhipe_serializer import serialize_functional_key
from delegated_crypto import generate_ek, serialize_ek
from bucketing import get_cancer_type_name, get_bucket_info, pad_weights
from mcl_backend import MclPairing, fast_feddh_generate
import time as _time
from flask import request
from pathway_xai import load_hallmark_pathways, build_pathway_vectors
from audit_log import run_decoy_verification
from rho_blinding import generate_rho, extend_weight_vector

# 1. Configurable Model Selection
parser = argparse.ArgumentParser(description="Hospital KGC Node")
parser.add_argument("--model", type=int, default=None, help="Cancer model index (0-32)")
args, unknown = parser.parse_known_args()

if args.model is None:
    from bucket_config import CANCER_TYPES
    print("\nAvailable Cancer Types:")
    for i, c in enumerate(CANCER_TYPES):
        print(f"{i:2d}: {c:5s}", end="  " if (i+1)%6!=0 else "\n")
    print("\n")
    
    while True:
        val = input("Enter the name or index of the cancer type to load: ").strip().upper()
        if val in CANCER_TYPES:
            MODEL_INDEX = CANCER_TYPES.index(val)
            break
        try:
            idx = int(val)
            if 0 <= idx < len(CANCER_TYPES):
                MODEL_INDEX = idx
                break
            print("Index out of range.")
        except ValueError:
            print("Invalid input. Please enter a valid name (e.g. 'BRCA') or index.")
else:
    MODEL_INDEX = args.model

app = Flask(__name__)

# 2. Load Model Weights
logger.info(f"Loading master 33-cancer weights for Model Index: {MODEL_INDEX}...")
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
raw_quantized = [int(val) for val in np.rint(filtered_weights * SCALING_FACTOR)]
RAW_DIM = len(raw_quantized)

BUCKET_NAME, BUCKET_DIM = get_bucket_info(MODEL_INDEX, RAW_DIM)
# Take active features that fit within the bucket, then pad to bucket_dim
ACTIVE_FEATURES_TO_USE = min(RAW_DIM, max(4, BUCKET_DIM - 3))
raw_feature_subset = raw_quantized[:ACTIVE_FEATURES_TO_USE]

WEIGHT_SHIFT = int(max(0, -min(raw_feature_subset)) + 1) if len(raw_feature_subset) > 0 else 1
shifted_features = [w + WEIGHT_SHIFT for w in raw_feature_subset]

quantized_weights = pad_weights(shifted_features, BUCKET_DIM)

RHO_VAL = generate_rho(sigma=1000.0)
quantized_weights = extend_weight_vector(quantized_weights, RHO_VAL)
DIMENSION = len(quantized_weights)

CANCER_NAME = get_cancer_type_name(MODEL_INDEX)
logger.info(f"Loaded: {CANCER_NAME} | Active Features: {len(raw_feature_subset)} | Bucket: '{BUCKET_NAME}' (Padded Dim: {DIMENSION})")
logger.info(f"Blinding noise (rho) generated: {RHO_VAL}")

# 5. Initialize Keys at Bucket Dimension
logger.info(f"Generating FeDDH Master Key for dimension {DIMENSION}...")
master_key = fast_feddh_generate(DIMENSION, F=MclPairing())
logger.info("Master Key generated. Deriving Delegated Encryption Key (ek)...")
ek = generate_ek(master_key)
logger.info("Delegated Encryption Key generated and ready for distribution.")

# --- XAI Setup ---
# Load gene names and map active indices to symbols
try:
    with open('gene_names_20531.txt', 'r') as f:
        all_genes = [line.strip() for line in f]
    active_gene_names = [all_genes[i] for i in active_indices[:ACTIVE_FEATURES_TO_USE]]
    print(f"[XAI] Loaded {len(active_gene_names)} active gene names.")
except FileNotFoundError:
    print("[XAI] Warning: gene_names_20531.txt not found. Run extract_gene_names.py first.")
    active_gene_names = []

# Load Hallmark pathways
try:
    pathways = load_hallmark_pathways('h.all.v2026.1.Hs.symbols.gmt')
    print(f"[XAI] Loaded {len(pathways)} Hallmark pathways.")
except FileNotFoundError:
    print("[XAI] Warning: GMT file not found.")
    pathways = {}

# Build pathway sub-vectors using the un-shifted quantized weights
pathway_vectors_raw = build_pathway_vectors(pathways, active_gene_names, raw_feature_subset)
print(f"[XAI] Built {len(pathway_vectors_raw)} pathway sub-vectors with gene overlap.")

# --- XAI Privacy Budget ---
XAI_EPSILON_PER_QUERY = 1.0    # Epsilon cost per pathway explanation request
XAI_TOTAL_BUDGET = 10.0        # Total epsilon budget before lockout
xai_budget_spent = 0.0
xai_query_log = []              # List of {timestamp, ip, epsilon_spent, remaining}

def check_xai_budget(request_ip):
    """Check if there is remaining XAI privacy budget."""
    global xai_budget_spent
    remaining = XAI_TOTAL_BUDGET - xai_budget_spent
    if remaining < XAI_EPSILON_PER_QUERY:
        return False, remaining
    return True, remaining

def spend_xai_budget(request_ip):
    """Deduct epsilon from the XAI budget and log the access."""
    global xai_budget_spent
    xai_budget_spent += XAI_EPSILON_PER_QUERY
    remaining = XAI_TOTAL_BUDGET - xai_budget_spent
    xai_query_log.append({
        'timestamp': _time.time(),
        'ip': request_ip,
        'epsilon_spent': XAI_EPSILON_PER_QUERY,
        'total_spent': xai_budget_spent,
        'remaining': remaining,
    })
    if remaining <= XAI_TOTAL_BUDGET * 0.25:
        print(f"[XAI] WARNING: Privacy budget at {remaining:.1f}/{XAI_TOTAL_BUDGET} epsilon")
    return remaining

@app.route("/get_model_info", methods=["GET"])
def get_model_info():
    return jsonify({
        "model_index": MODEL_INDEX,
        "cancer_name": CANCER_NAME,
        "active_features_count": len(raw_feature_subset),
        "active_indices": active_indices[:ACTIVE_FEATURES_TO_USE].tolist(),
        "bucket_name": BUCKET_NAME,
        "bucket_dimension": BUCKET_DIM
    })

@app.route("/get_dimension", methods=["GET"])
def get_dimension():
    return jsonify({"dimension": DIMENSION})

@app.route("/get_weight_shift", methods=["GET"])
def get_weight_shift():
    return jsonify({"weight_shift": WEIGHT_SHIFT})

@app.route("/get_rho", methods=["GET"])
def get_rho():
    # In production this must be sealed with the Clinic's public key.
    return jsonify({"rho": RHO_VAL})

@app.route("/get_ek", methods=["GET"])
def get_ek():
    return jsonify({"ek": serialize_ek(ek)})

@app.route("/get_key", methods=["GET"])
def get_key():
    logger.info("Received request for Functional Key (sk).")
    try:
        sk = FeDDH.keygen(quantized_weights, master_key)
        json_sk = serialize_functional_key(sk)
        
        # PyNaCl Sealed Key Delivery[cite: 1]
        logger.info("Fetching Cloud Public Key for sealed delivery...")
        cloud_resp = requests.get("http://127.0.0.1:5002/public_key").json()
        cloud_pk_bytes = base64.b64decode(cloud_resp["public_key"])
        cloud_pk = PublicKey(cloud_pk_bytes)
        
        sealed_box = SealedBox(cloud_pk)
        encrypted_sk = sealed_box.encrypt(json_sk.encode("utf-8"))
        encoded_sealed_sk = base64.b64encode(encrypted_sk).decode("utf-8")
        
        logger.info("Successfully generated and sealed Functional Key.")
        return jsonify({"functional_key": encoded_sealed_sk})
    except Exception as e:
        logger.error(f"Error generating Functional Key: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/get_pathway_keys', methods=['GET'])
def get_pathway_keys():
    # Check XAI privacy budget BEFORE generating any keys
    allowed, remaining = check_xai_budget(request.remote_addr)
    if not allowed:
        return jsonify({
            "error": "XAI privacy budget exhausted",
            "total_budget": XAI_TOTAL_BUDGET,
            "spent": xai_budget_spent,
            "remaining": remaining,
        }), 429  # HTTP 429 Too Many Requests

    try:
        cloud_resp = requests.get('http://127.0.0.1:5002/public_key').json()
        cloud_pk_bytes = base64.b64decode(cloud_resp['public_key'])
        cloud_pk = PublicKey(cloud_pk_bytes)
        sealed_box = SealedBox(cloud_pk)

        sealed_pathway_keys = {}
        for name, sub_vec_raw in pathway_vectors_raw.items():
            # Add WEIGHT_SHIFT to every element to avoid FeDDH keygen failure on 0
            sub_vec_shifted = [w + WEIGHT_SHIFT for w in sub_vec_raw]
            # Since BSGS expects padded arrays in evaluating pathways too (wait, no)
            # Actually evaluate_pathways sends ct which has DIMENSION length.
            # So the pathway keys must ALSO be padded to DIMENSION!
            sub_vec_padded = pad_weights(sub_vec_shifted, BUCKET_DIM)
            sub_vec_extended = extend_weight_vector(sub_vec_padded, RHO_VAL)

            sk = FeDDH.keygen(sub_vec_extended, master_key)
            json_sk = serialize_functional_key(sk)
            encrypted_sk = sealed_box.encrypt(json_sk.encode('utf-8'))
            sealed_pathway_keys[name] = base64.b64encode(encrypted_sk).decode('utf-8')

        # Deduct from budget only AFTER successful key generation
        spend_xai_budget(request.remote_addr)

        return jsonify({"pathway_keys": sealed_pathway_keys})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/xai_privacy_budget', methods=['GET'])
def get_xai_privacy_budget():
    """Returns current XAI privacy budget status and access log."""
    return jsonify({
        "total_budget": XAI_TOTAL_BUDGET,
        "spent": xai_budget_spent,
        "remaining": XAI_TOTAL_BUDGET - xai_budget_spent,
        "queries_made": len(xai_query_log),
        "max_queries_allowed": int(XAI_TOTAL_BUDGET / XAI_EPSILON_PER_QUERY),
        "access_log": xai_query_log,
    })

@app.route('/verify_cloud', methods=['GET'])
def verify_cloud():
    result = run_decoy_verification(
        cloud_url='http://127.0.0.1:5002',
        master_key=master_key,
        quantized_weights=quantized_weights,
        weight_shift=WEIGHT_SHIFT
    )
    return jsonify(result)

if __name__ == "__main__":
    app.run(port=5001)