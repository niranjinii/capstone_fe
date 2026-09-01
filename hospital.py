import argparse
import base64
import traceback
import threading
import json
import os
import uuid
import ssl
from collections import defaultdict
import numpy as np
import requests
import urllib3
urllib3.disable_warnings()
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
import time
from pathway_xai import load_hallmark_pathways, build_pathway_vectors
from audit_log import run_decoy_verification
from rho_blinding import generate_rho, extend_weight_vector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("Hospital")

app = Flask(__name__)

# --- Payload Signing Key (Item #7, Member C) ---
SIGNING_KEY_FILE = "hospital_signing.key"
if os.path.exists(SIGNING_KEY_FILE):
    with open(SIGNING_KEY_FILE, "rb") as f:
        hospital_signing_key = SigningKey(f.read())
else:
    hospital_signing_key = SigningKey.generate()
    with open(SIGNING_KEY_FILE, "wb") as f:
        f.write(hospital_signing_key.encode())
        
hospital_verify_key = hospital_signing_key.verify_key

# --- Admin Verify Key (for budget resets) ---
ADMIN_VERIFY_FILE = "admin_verify.pub"
if os.path.exists(ADMIN_VERIFY_FILE):
    with open(ADMIN_VERIFY_FILE, "rb") as f:
        admin_verify_key = VerifyKey(f.read())
    logger.info("[ADMIN] Admin verify key loaded — /reset_budget endpoint active.")
else:
    admin_verify_key = None
    logger.warning("[ADMIN] No admin_verify.pub found — /reset_budget will return 503.")

budget_epoch = 0

# --- Doctor Registry (per-doctor access control) ---
DOCTOR_REGISTRY_FILE = "doctor_registry.json"
doctor_registry = {}   # doctor_id -> {verify_key, budget, enabled}
doctor_budgets = {}    # doctor_id -> {spent: float, log: list}  (runtime, persisted in state)

def _load_doctor_registry():
    """Load and verify the signed doctor registry."""
    global doctor_registry
    if not os.path.exists(DOCTOR_REGISTRY_FILE):
        logger.warning("[DOCTORS] No doctor_registry.json — doctor-authenticated endpoints will reject all requests.")
        return

    with open(DOCTOR_REGISTRY_FILE) as f:
        wrapper = json.load(f)

    # 🛡️ Gap #2: NO unsigned fallback — missing signature is a hard failure
    if "signature" not in wrapper or "data_hex" not in wrapper:
        raise RuntimeError(
            f"FATAL: {DOCTOR_REGISTRY_FILE} is missing its signature wrapper. "
            "File may be tampered with or was written by an old version of register_doctor.py. "
            "Re-run register_doctor.py to regenerate a signed registry."
        )

    data_bytes = bytes.fromhex(wrapper["data_hex"])
    signature = bytes.fromhex(wrapper["signature"])
    hospital_verify_key.verify(data_bytes, signature)  # raises BadSignatureError if tampered

    doctor_registry = json.loads(data_bytes.decode("utf-8"))
    for doc_id in doctor_registry:
        if doc_id not in doctor_budgets:
            doctor_budgets[doc_id] = {"spent": 0.0, "log": []}
    logger.info(f"[DOCTORS] Loaded {len(doctor_registry)} doctors from signed registry.")

_load_doctor_registry()

# --- Doctor Nonce Tracking (prevents signature replay) ---
_seen_doctor_nonces = {}  # nonce_str -> expiry_timestamp


def _prune_expired_nonces():
    """Remove nonces older than 120 seconds. Called periodically."""
    now = time.time()
    expired = [n for n, exp in _seen_doctor_nonces.items() if now > exp]
    for n in expired:
        del _seen_doctor_nonces[n]


def authenticate_doctor(req) -> tuple[str | None, str | None]:
    """
    Verify doctor identity from request headers.
    Returns (doctor_id, None) on success, or (None, error_message) on failure.
    """
    doctor_id = req.headers.get("X-Doctor-ID")
    ts_str = req.headers.get("X-Doctor-Timestamp")
    nonce = req.headers.get("X-Doctor-Nonce")
    sig_hex = req.headers.get("X-Doctor-Signature")

    if not all([doctor_id, ts_str, nonce, sig_hex]):
        return None, "Missing doctor auth headers (need X-Doctor-ID, X-Doctor-Timestamp, X-Doctor-Nonce, X-Doctor-Signature)"

    try:
        ts = int(ts_str)
    except ValueError:
        return None, "Invalid X-Doctor-Timestamp"
    if abs(time.time() - ts) > 60:
        return None, "Stale or future-dated request (>60s drift)"

    _prune_expired_nonces()
    if nonce in _seen_doctor_nonces:
        return None, "Replayed nonce — possible replay attack"

    if doctor_id not in doctor_registry:
        return None, f"Unknown doctor: {doctor_id!r}"
    if not doctor_registry[doctor_id].get("enabled", False):
        return None, f"Doctor {doctor_id!r} is disabled"

    sig_payload = f"{req.method}|{req.path}|{ts_str}|{nonce}".encode()
    try:
        vk = VerifyKey(
            doctor_registry[doctor_id]["verify_key"].encode(),
            encoder=nacl.encoding.HexEncoder
        )
        vk.verify(sig_payload, bytes.fromhex(sig_hex))
    except BadSignatureError:
        return None, f"Invalid signature for doctor {doctor_id!r}"

    _seen_doctor_nonces[nonce] = time.time() + 120
    return doctor_id, None

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

# WARNING: This lock only synchronizes threads within a single process.
# If deployed via gunicorn with multiple workers (e.g., -w 4), this state is not shared,
# and attackers get 4x the budget. A Redis backend is required for multi-process deployments.
state_lock = threading.Lock()
STATE_FILE = "hospital_state.json"

def _save_state():
    state = {
        "xai_budget_spent": xai_budget_spent,
        "xai_query_log": xai_query_log,
        "key_issuance_log": {f"{k[0]}|{k[1]}": v for k, v in key_issuance_log.items()},
        "budget_epoch": budget_epoch,
        "doctor_budgets": doctor_budgets
    }
    state_bytes = json.dumps(state).encode("utf-8")
    signature = hospital_signing_key.sign(state_bytes).signature.hex()
    
    wrapper = {
        "signature": signature,
        "data_hex": state_bytes.hex()
    }
    tmp_file = STATE_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(wrapper, f)
    os.replace(tmp_file, STATE_FILE)

def _load_state():
    global xai_budget_spent, xai_query_log, key_issuance_log, budget_epoch, doctor_budgets
    if not os.path.exists(STATE_FILE):
        return
    with open(STATE_FILE, "r") as f:
        wrapper = json.load(f)
    
    data_bytes = bytes.fromhex(wrapper["data_hex"])
    signature = bytes.fromhex(wrapper["signature"])
    
    # Will throw nacl.exceptions.BadSignatureError and crash if tampered
    hospital_verify_key.verify(data_bytes, signature)
    
    state = json.loads(data_bytes.decode("utf-8"))
    xai_budget_spent = state.get("xai_budget_spent", 0.0)
    xai_query_log = state.get("xai_query_log", [])
    key_issuance_log.clear()
    
    for compound_key_str, v in state.get("key_issuance_log", {}).items():
        parts = compound_key_str.split("|", 1)
        if len(parts) == 2:
            key_issuance_log[(int(parts[0]), parts[1])] = v
        else:
            key_issuance_log[(int(parts[0]), "__legacy__")] = v

    budget_epoch = state.get("budget_epoch", 0)
    loaded_doc_budgets = state.get("doctor_budgets", {})
    for k, v in loaded_doc_budgets.items():
        doctor_budgets[k] = v

_load_state()

def reserve_doctor_budget(doctor_id: str):
    with state_lock:
        quota = doctor_registry[doctor_id]["budget"]
        doc_state = doctor_budgets[doctor_id]
        remaining = quota - doc_state["spent"]
        if remaining < XAI_EPSILON_PER_QUERY:
            return False, remaining, None

        doc_state["spent"] += XAI_EPSILON_PER_QUERY
        remaining_after = quota - doc_state["spent"]
        entry_id = str(uuid.uuid4())
        doc_state["log"].append({
            "id": entry_id,
            "timestamp": time.time(),
            "epsilon_spent": XAI_EPSILON_PER_QUERY,
            "total_spent": doc_state["spent"],
            "remaining": remaining_after,
        })
        if remaining_after <= quota * 0.25:
            logger.warning(f"[BUDGET] Doctor {doctor_id}: {remaining_after:.1f}/{quota} epsilon remaining")
        _save_state()
        return True, remaining_after, entry_id


def rollback_doctor_budget(doctor_id: str, entry_id: str):
    with state_lock:
        doc_state = doctor_budgets[doctor_id]
        doc_state["spent"] -= XAI_EPSILON_PER_QUERY
        doc_state["log"] = [e for e in doc_state["log"] if e.get("id") != entry_id]
        _save_state()

def reserve_key_issuance(model_index, dimension, doctor_id):
    with state_lock:
        compound_key = (model_index, doctor_id)
        max_allowed = max(1, dimension // 2)
        history = key_issuance_log[compound_key]
        count = len(history)
        if count >= max_allowed:
            return False, f"Key rate limit: {count}/{max_allowed} keys for model {model_index}, doctor {doctor_id}", None
        if count >= int(0.75 * max_allowed):
            logger.warning(f"[RATE LIMIT] Model {model_index}, doctor {doctor_id}: {count}/{max_allowed} keys — approaching limit")

        entry_id = str(uuid.uuid4())
        entry = {
            "id": entry_id,
            "timestamp": time.time(),
            "model_index": model_index,
            "doctor_id": doctor_id,
            "count": count + 1,
            "limit": max_allowed,
        }
        key_issuance_log[compound_key].append(entry)
        _save_state()
        return True, "OK", entry_id

def rollback_key_issuance(model_index, doctor_id, entry_id):
    with state_lock:
        compound_key = (model_index, doctor_id)
        key_issuance_log[compound_key] = [
            e for e in key_issuance_log[compound_key] if e.get("id") != entry_id
        ]
        _save_state()

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
    logger.info("Received request for Functional Key (sk).")
    # Doctor authentication gate
    doctor_id, err = authenticate_doctor(request)
    if err:
        return jsonify({"error": err}), 403

    allowed, msg, entry_id = reserve_key_issuance(MODEL_INDEX, DIMENSION, doctor_id)
    if not allowed:
        logger.warning(f"[RATE LIMIT] {msg}")
        return jsonify({"error": msg}), 429

    try:
        sk = FeDDH.keygen(quantized_weights, master_key)
        json_sk = serialize_functional_key(sk)
        
        # PyNaCl Sealed Key Delivery via mTLS to Cloud
        cloud_resp = requests.get("https://127.0.0.1:5002/public_key", cert=('hospital.pem', 'hospital-key.pem'), verify=False).json()
        cloud_pk_bytes = base64.b64decode(cloud_resp["public_key"])
        cloud_pk = PublicKey(cloud_pk_bytes)
        
        sealed_box = SealedBox(cloud_pk)
        encrypted_sk = sealed_box.encrypt(json_sk.encode("utf-8"))
        encoded_sealed_sk = base64.b64encode(encrypted_sk).decode("utf-8")
        logger.info("Successfully generated and sealed Functional Key.")
        return jsonify({"functional_key": encoded_sealed_sk})
    except Exception as e:
        rollback_key_issuance(MODEL_INDEX, doctor_id, entry_id)
        logger.error(f"Error generating Functional Key: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/get_pathway_keys', methods=['GET'])
def get_pathway_keys():
    # Doctor authentication gate
    doctor_id, err = authenticate_doctor(request)
    if err:
        return jsonify({"error": err}), 403

    allowed, remaining, entry_id = reserve_doctor_budget(doctor_id)
    if not allowed:
        return jsonify({
            "error": "XAI privacy budget exhausted for this doctor",
            "doctor_id": doctor_id,
            "remaining": remaining,
        }), 429

    try:
        cloud_resp = requests.get('https://127.0.0.1:5002/public_key', cert=('hospital.pem', 'hospital-key.pem'), verify=False).json()
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

        return jsonify({"pathway_keys": sealed_pathway_keys})
    except Exception as e:
        rollback_doctor_budget(doctor_id, entry_id)
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
        verify=False,
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

@app.route('/debug/force_reload_state', methods=['POST'])
def force_reload_state():
    if os.environ.get("TEST_MODE") != "1":
        return jsonify({"error": "Not Found"}), 404
    _load_state()
    return jsonify({"status": "State reloaded from disk"})

@app.route('/reset_budget', methods=['POST'])
def reset_budget():
    global xai_budget_spent, xai_query_log, budget_epoch

    if admin_verify_key is None:
        return jsonify({"error": "Budget reset not configured (no admin_verify.pub)"}), 503

    token_b64 = request.json.get("token")
    if not token_b64:
        return jsonify({"error": "Missing 'token' field"}), 400

    # Verify admin signature
    try:
        token_signed = base64.b64decode(token_b64)
        payload_bytes = admin_verify_key.verify(token_signed)
        token = json.loads(payload_bytes)
    except BadSignatureError:
        logger.error("[ADMIN] Budget reset REJECTED: invalid admin signature")
        return jsonify({"error": "Invalid admin signature"}), 403
    except Exception as e:
        return jsonify({"error": f"Malformed token: {e}"}), 400

    # Validate token fields
    if token.get("action") != "reset_budget":
        return jsonify({"error": "Wrong token action"}), 400
    if token["target_epoch"] != budget_epoch + 1:
        return jsonify({
            "error": f"Epoch mismatch: expected {budget_epoch + 1}, got {token['target_epoch']}"
        }), 409
    if time.time() - token["issued_at"] > 300:
        return jsonify({"error": "Token expired (>5 min old)"}), 410

    scope = token.get("scope", "global")

    # 🛡️ Gap #4: validate scope target BEFORE incrementing epoch
    if scope.startswith("doctor:"):
        target_doc = scope.split(":", 1)[1]
        if target_doc not in doctor_budgets:
            return jsonify({"error": f"Unknown doctor '{target_doc}' in scope"}), 404

    with state_lock:
        if scope == "global":
            xai_budget_spent = 0.0
            xai_query_log = []
            for doc_state in doctor_budgets.values():
                doc_state["spent"] = 0.0
                doc_state["log"] = []
            # Also reset global key issuance log
            key_issuance_log.clear()
        elif scope.startswith("doctor:"):
            target_doc = scope.split(":", 1)[1]
            doctor_budgets[target_doc]["spent"] = 0.0
            doctor_budgets[target_doc]["log"] = []
            # Reset that doctor's key issuance entries too
            keys_to_clean = [k for k in key_issuance_log if k[1] == target_doc]
            for k in keys_to_clean:
                del key_issuance_log[k]

        budget_epoch += 1
        _save_state()

    logger.info(f"[ADMIN] Budget reset OK. scope={scope}, new_epoch={budget_epoch}")
    return jsonify({"status": "reset", "scope": scope, "new_epoch": budget_epoch})

@app.route('/doctor_budget', methods=['GET'])
def get_doctor_budget():
    doctor_id, err = authenticate_doctor(request)
    if err:
        return jsonify({"error": err}), 403

    quota = doctor_registry[doctor_id]["budget"]
    doc_state = doctor_budgets.get(doctor_id, {"spent": 0.0, "log": []})
    return jsonify({
        "doctor_id": doctor_id,
        "total_budget": quota,
        "spent": doc_state["spent"],
        "remaining": quota - doc_state["spent"],
        "queries_made": len(doc_state["log"]),
        "budget_epoch": budget_epoch,
    })

if __name__ == "__main__":
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('hospital.pem', 'hospital-key.pem')
    context.load_verify_locations('ca.pem')
    context.verify_mode = ssl.CERT_REQUIRED
    logger.info("[mTLS] Hospital starting with mutual TLS on port 5001...")
    try:
        app.run(port=5001, ssl_context=context)
    except KeyboardInterrupt:
        pass
    finally:
        import os
        os._exit(0)