import argparse
import base64
import traceback
import time
import ssl
from collections import defaultdict
import numpy as np
import requests
import logging
from flask import Flask, jsonify, request

from mife.single.fhiding.ddh import FeDDH
from nacl.public import PublicKey, SealedBox
from nacl.signing import SigningKey, VerifyKey
import nacl.encoding
from nacl.exceptions import BadSignatureError

from fhipe_serializer import serialize_functional_key
from delegated_crypto import generate_ek, serialize_ek
from bucketing import get_cancer_type_name, get_bucket_info, pad_weights
from mcl_backend import MclPairing, fast_feddh_generate
import time as _time
from pathway_xai import load_hallmark_pathways, build_pathway_vectors
from audit_log import run_decoy_verification
from rho_blinding import generate_rho, extend_weight_vector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("Hospital")

app = Flask(__name__)

# --- Payload Signing Key (Item #7, Member C) ---
hospital_signing_key = SigningKey.generate()
hospital_verify_key = hospital_signing_key.verify_key

@app.route('/signing_key', methods=['GET'])
def get_signing_key():
    """Expose the Hospital's Ed25519 verify key so the Clinic can verify responses."""
    vk_hex = hospital_verify_key.encode(encoder=nacl.encoding.HexEncoder).decode('utf-8')
    return jsonify({"verify_key": vk_hex})

@app.before_request
def verify_incoming_payload():
    """Verify Ed25519 signature on all incoming POST JSON payloads."""
    if request.method == 'POST' and request.is_json:
        sig_hex = request.headers.get('X-Signature')
        vk_hex = request.headers.get('X-Verify-Key')
        
        if not sig_hex or not vk_hex:
            logger.warning("Rejected payload: missing signature headers")
            return jsonify({"error": "Missing signature headers"}), 403
            
        try:
            vk = VerifyKey(vk_hex.encode('utf-8'), encoder=nacl.encoding.HexEncoder)
            sig_bytes = bytes.fromhex(sig_hex)
            payload_bytes = request.get_data()
            vk.verify(payload_bytes, sig_bytes)
        except BadSignatureError:
            logger.error("Rejected payload: invalid signature!")
            return jsonify({"error": "Invalid signature"}), 403
        except Exception as e:
            return jsonify({"error": f"Signature verification failed: {str(e)}"}), 403

@app.after_request
def sign_outgoing_payload(response):
    """Sign all outgoing JSON responses with the Hospital's Ed25519 signing key."""
    if response.is_json:
        payload_bytes = response.get_data()
        signature = hospital_signing_key.sign(payload_bytes).signature
        response.headers['X-Signature'] = signature.hex()
    return response

# 1. Configurable Model Selection (Member B)
parser = argparse.ArgumentParser(description="Hospital KGC Node")
parser.add_argument("--model", type=int, default=0, help="Cancer model index (0-32)")
args, unknown = parser.parse_known_args()
MODEL_INDEX = args.model

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

# 4. Quantize and Pad to Bucket Dimension (Member B + Member A)
SCALING_FACTOR = 100.0
raw_quantized = [int(val) for val in np.rint(filtered_weights * SCALING_FACTOR)]
RAW_DIM = len(raw_quantized)

BUCKET_NAME, BUCKET_DIM = get_bucket_info(MODEL_INDEX, RAW_DIM)
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

# --- Key Rotation State (Item #18, Member C) ---
key_generation_epoch = 0
key_created_at = time.time()

# --- Rate Limiting State (Item #5, Member C) ---
key_issuance_log = defaultdict(list)

# --- XAI Setup (Member D) ---
try:
    with open('gene_names_20531.txt', 'r') as f:
        all_genes = [line.strip() for line in f]
    active_gene_names = [all_genes[i] for i in active_indices[:ACTIVE_FEATURES_TO_USE]]
    logger.info(f"[XAI] Loaded {len(active_gene_names)} active gene names.")
except FileNotFoundError:
    logger.warning("[XAI] Warning: gene_names_20531.txt not found.")
    active_gene_names = []

try:
    pathways = load_hallmark_pathways('h.all.v2026.1.Hs.symbols.gmt')
    logger.info(f"[XAI] Loaded {len(pathways)} Hallmark pathways.")
except FileNotFoundError:
    logger.warning("[XAI] Warning: GMT file not found.")
    pathways = {}

pathway_vectors_raw = build_pathway_vectors(pathways, active_gene_names, raw_feature_subset)
logger.info(f"[XAI] Built {len(pathway_vectors_raw)} pathway sub-vectors with gene overlap.")

# --- XAI Privacy Budget (Member D) ---
XAI_EPSILON_PER_QUERY = 1.0
XAI_TOTAL_BUDGET = 10.0
xai_budget_spent = 0.0
xai_query_log = []

def check_xai_budget(request_ip):
    global xai_budget_spent
    remaining = XAI_TOTAL_BUDGET - xai_budget_spent
    if remaining < XAI_EPSILON_PER_QUERY:
        return False, remaining
    return True, remaining

def spend_xai_budget(request_ip):
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
        logger.warning(f"[XAI] WARNING: Privacy budget at {remaining:.1f}/{XAI_TOTAL_BUDGET} epsilon")
    return remaining

def check_rate_limit(model_index, dimension):
    max_allowed = max(1, dimension // 2)
    history = key_issuance_log[model_index]
    count = len(history)
    if count >= max_allowed:
        return False, f"Rate limit reached: {count}/{max_allowed} keys issued for model {model_index}"
    if count >= int(0.75 * max_allowed):
        logger.warning(f"Model {model_index}: {count}/{max_allowed} keys issued — approaching extraction threshold!")
    return True, "OK"

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
    return jsonify({"rho": RHO_VAL})

@app.route("/get_ek", methods=["GET"])
def get_ek():
    return jsonify({
        "ek": serialize_ek(ek),
        "epoch": key_generation_epoch,
        "key_created_at": key_created_at,
    })

@app.route("/get_key", methods=["GET"])
def get_key():
    allowed, msg = check_rate_limit(MODEL_INDEX, DIMENSION)
    if not allowed:
        logger.warning(f"[RATE LIMIT] {msg}")
        return jsonify({"error": msg}), 429

    try:
        sk = FeDDH.keygen(quantized_weights, master_key)
        json_sk = serialize_functional_key(sk)
        
        # PyNaCl Sealed Key Delivery via mTLS to Cloud
        cloud_resp = requests.get("https://127.0.0.1:5002/public_key", cert=('hospital.pem', 'hospital-key.pem'), verify='ca.pem').json()
        cloud_pk_bytes = base64.b64decode(cloud_resp["public_key"])
        cloud_pk = PublicKey(cloud_pk_bytes)
        
        sealed_box = SealedBox(cloud_pk)
        encrypted_sk = sealed_box.encrypt(json_sk.encode("utf-8"))
        encoded_sealed_sk = base64.b64encode(encrypted_sk).decode("utf-8")
        
        entry = {
            "timestamp": time.time(),
            "model_index": MODEL_INDEX,
            "requester_ip": request.remote_addr,
            "count": len(key_issuance_log[MODEL_INDEX]) + 1,
            "limit": DIMENSION // 2,
        }
        key_issuance_log[MODEL_INDEX].append(entry)
        return jsonify({"functional_key": encoded_sealed_sk})
    except Exception as e:
        logger.error(f"Error generating Functional Key: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/get_pathway_keys', methods=['GET'])
def get_pathway_keys():
    allowed, remaining = check_xai_budget(request.remote_addr)
    if not allowed:
        return jsonify({
            "error": "XAI privacy budget exhausted",
            "total_budget": XAI_TOTAL_BUDGET,
            "spent": xai_budget_spent,
            "remaining": remaining,
        }), 429

    try:
        cloud_resp = requests.get('https://127.0.0.1:5002/public_key', cert=('hospital.pem', 'hospital-key.pem'), verify='ca.pem').json()
        cloud_pk_bytes = base64.b64decode(cloud_resp['public_key'])
        cloud_pk = PublicKey(cloud_pk_bytes)
        sealed_box = SealedBox(cloud_pk)

        sealed_pathway_keys = {}
        for name, sub_vec_raw in pathway_vectors_raw.items():
            sub_vec_shifted = [w + WEIGHT_SHIFT for w in sub_vec_raw]
            sub_vec_padded = pad_weights(sub_vec_shifted, BUCKET_DIM)
            sub_vec_extended = extend_weight_vector(sub_vec_padded, RHO_VAL)

            sk = FeDDH.keygen(sub_vec_extended, master_key)
            json_sk = serialize_functional_key(sk)
            encrypted_sk = sealed_box.encrypt(json_sk.encode('utf-8'))
            sealed_pathway_keys[name] = base64.b64encode(encrypted_sk).decode('utf-8')

        spend_xai_budget(request.remote_addr)
        return jsonify({"pathway_keys": sealed_pathway_keys})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/xai_privacy_budget', methods=['GET'])
def get_xai_privacy_budget():
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
        cloud_url='https://127.0.0.1:5002',
        master_key=master_key,
        quantized_weights=quantized_weights,
        weight_shift=WEIGHT_SHIFT,
        cert=('hospital.pem', 'hospital-key.pem'),
        verify='ca.pem',
        signing_key=hospital_signing_key
    )
    return jsonify(result)

@app.route('/rotate_keys', methods=['POST'])
def rotate_keys():
    global master_key, ek, key_generation_epoch, key_created_at
    logger.info(f"[KEY ROTATION] Rotating keys (epoch {key_generation_epoch} -> {key_generation_epoch + 1})...")
    master_key = fast_feddh_generate(DIMENSION, F=MclPairing())
    ek = generate_ek(master_key)
    key_generation_epoch += 1
    key_created_at = time.time()
    return jsonify({
        "status": "rotated",
        "new_epoch": key_generation_epoch,
        "new_dimension": DIMENSION,
    })

@app.route('/query_log', methods=['GET'])
def query_log():
    summary = {}
    for model_idx, history in key_issuance_log.items():
        summary[str(model_idx)] = {
            "issued": len(history),
            "limit": DIMENSION // 2,
            "entries": history,
        }
    return jsonify({"key_issuance_log": summary})

if __name__ == "__main__":
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('hospital.pem', 'hospital-key.pem')
    context.load_verify_locations('ca.pem')
    context.verify_mode = ssl.CERT_REQUIRED
    logger.info("[mTLS] Hospital starting with mutual TLS on port 5001...")
    app.run(port=5001, ssl_context=context)