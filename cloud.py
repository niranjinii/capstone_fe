import base64
import multiprocessing
import traceback
import logging
import time
import ssl
from concurrent.futures import ProcessPoolExecutor
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("Cloud")
from mife.single.fhiding.ddh import FeDDH
from nacl.public import PrivateKey, SealedBox
from nacl.signing import SigningKey, VerifyKey
import nacl.encoding
from nacl.exceptions import BadSignatureError

from fhipe_serializer import deserialize_ciphertext, deserialize_functional_key
from mcl_backend import MclPairing
import hashlib
import uuid
import numpy as np
from audit_log import MerkleAuditLog
from bsgs import feddh_decrypt_bsgs

try:
    multiprocessing.set_start_method("fork")
except (RuntimeError, ValueError):
    pass

app = Flask(__name__)

# --- XAI Differential Privacy Configuration ---
XAI_EPSILON = 1.0           # Privacy parameter for pathway explanations
XAI_SENSITIVITY = 10000     # Max change in a pathway score from a single patient change

# --- XAI Setup ---
audit_chain = MerkleAuditLog(persistence_path='audit_chain.json')
print("[XAI] Audit chain initialized.")

# 1. Cloud generates its long-term X25519 keypair on boot
cloud_private_key = PrivateKey.generate()
cloud_public_key = cloud_private_key.public_key

# --- Payload Signing Key (Item #7) ---
cloud_signing_key = SigningKey.generate()
cloud_verify_key = cloud_signing_key.verify_key

@app.route('/signing_key', methods=['GET'])
def get_signing_key():
    """Expose the Cloud's Ed25519 verify key so the Clinic can verify responses."""
    vk_hex = cloud_verify_key.encode(encoder=nacl.encoding.HexEncoder).decode('utf-8')
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
    """Sign all outgoing JSON responses with the Cloud's Ed25519 signing key."""
    if response.is_json:
        payload_bytes = response.get_data()
        signature = cloud_signing_key.sign(payload_bytes).signature
        response.headers['X-Signature'] = signature.hex()
    return response

# --- Replay Attack Prevention State (Item #19) ---
# seen_queries: set of query_ids that have already been processed.
# Memory is bounded because we only store the UUID string (~36 bytes each).
# In production you'd prune entries older than MAX_AGE_SECONDS, but for the
# demo the set stays small enough that no pruning is needed.
seen_queries = set()
MAX_AGE_SECONDS = 300  # reject payloads older than 5 minutes

def validate_query(data: dict):
    """Check for replay attacks.
    Returns (valid: bool, reason: str).
    """
    qid = data.get('query_id')
    ts  = data.get('timestamp', 0)

    if not qid:
        # Backwards-compatible: if no query_id, skip replay check (old clients)
        return True, "no query_id present — skipping replay check"

    if qid in seen_queries:
        return False, f"Duplicate query_id '{qid}' — possible replay attack"

    age = abs(time.time() - ts)
    if age > MAX_AGE_SECONDS:
        return False, f"Query timestamp too old ({age:.0f}s > {MAX_AGE_SECONDS}s) — possible replay attack"

    seen_queries.add(qid)
    return True, "OK"

def decrypt_single_evaluation(eval_item: dict, private_key: PrivateKey) -> int:
    sealed_box = SealedBox(private_key)
    encrypted_sk_bytes = base64.b64decode(eval_item["functional_key"])
    decrypted_sk_json = sealed_box.decrypt(encrypted_sk_bytes).decode("utf-8")
    
    logger.info("Decrypting single evaluation...")
    ct = deserialize_ciphertext(eval_item["ciphertext"])
    sk = deserialize_functional_key(decrypted_sk_json)
    
    # Decrypt using O(sqrt(N)) BSGS over a massive range (-1M, 1M)
    logger.info("Executing BSGS discrete log solver over (-1,000,000 to 1,000,000)...")
    result = feddh_decrypt_bsgs(ct, sk, (-1000000, 1000000))
    logger.info(f"BSGS decryption successful. Encrypted inner product result: {result}")
    return result

def _worker_wrapper(args):
    item, priv_bytes = args
    priv_key = PrivateKey(priv_bytes)
    return decrypt_single_evaluation(item, priv_key)

@app.route("/public_key", methods=["GET"])
def get_public_key():
    encoded_pk = base64.b64encode(cloud_public_key.encode()).decode("utf-8")
    return jsonify({"public_key": encoded_pk})

@app.route("/evaluate", methods=["POST"])
def evaluate():
    logger.info("Received POST /evaluate request.")
    try:
        data = request.json

        # --- Replay Attack Prevention (Item #19) ---
        valid, reason = validate_query(data)
        if not valid:
            logger.warning(f"[REPLAY BLOCKED] {reason}")
            return jsonify({"error": reason}), 403
        logger.info(f"[REPLAY CHECK] OK — query_id={data.get('query_id')}")

        result = decrypt_single_evaluation(data, cloud_private_key)
        logger.info("Single evaluation complete.")

        # Log to audit chain
        ct_json = data['ciphertext']
        query_id = data.get('query_id', str(uuid.uuid4()))
        ct_hash = hashlib.sha256(ct_json.encode('utf-8')).hexdigest()
        audit_chain.log_evaluation(query_id, ct_hash, result)

        return jsonify({"encrypted_result": result})
    except Exception as e:
        logger.error(f"Evaluation error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/evaluate_pathways', methods=['POST'])
def evaluate_pathways():
    try:
        data = request.json

        # Replay check
        valid, reason = validate_query(data)
        if not valid:
            logger.warning(f"[REPLAY BLOCKED] {reason}")
            return jsonify({"error": reason}), 403

        logger.info(f"[REPLAY CHECK] OK — query_id={data.get('query_id')}")
        ct_json = data['ciphertext']
        pathway_keys = data['pathway_keys']

        results = {}
        for name, sealed_sk in pathway_keys.items():
            # Use teammate's fast BSGS solver for XAI too!
            eval_item = {"ciphertext": ct_json, "functional_key": sealed_sk}
            raw_score = decrypt_single_evaluation(eval_item, cloud_private_key)
            
            # Add calibrated Laplace noise for epsilon-differential privacy
            noise = int(np.random.laplace(0, XAI_SENSITIVITY / XAI_EPSILON))
            results[name] = raw_score + noise
        
        # Audit log
        query_id = data.get('query_id', str(uuid.uuid4()))
        ct_hash = hashlib.sha256(ct_json.encode('utf-8')).hexdigest()
        audit_chain.log_evaluation(query_id, ct_hash, results)

        return jsonify({
            "pathway_results": results,
            "dp_applied": True,
            "epsilon": XAI_EPSILON
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/verify_audit_chain', methods=['GET'])
def verify_audit_chain():
    """Recompute all hashes and verify Merkle root integrity."""
    result = audit_chain.verify_chain()
    return jsonify(result)

@app.route('/audit_log', methods=['GET'])
def get_audit_log():
    return jsonify({"log": audit_chain.get_log()})

@app.route("/evaluate_batch", methods=["POST"])
def evaluate_batch():
    logger.info("Received POST /evaluate_batch request.")
    try:
        data = request.json

        # Replay check
        valid, reason = validate_query(data)
        if not valid:
            logger.warning(f"[REPLAY BLOCKED] {reason}")
            return jsonify({"error": reason}), 403
        logger.info(f"[REPLAY CHECK] OK — query_id={data.get('query_id')}")
        
        items = data.get("evaluations", [])
        if not items:
            logger.warning("No evaluation items provided in batch request.")
            return jsonify({"error": "No evaluation items provided"}), 400
            
        logger.info(f"Processing batch of {len(items)} evaluations...")
        priv_bytes = bytes(cloud_private_key)
        worker_args = [(item, priv_bytes) for item in items]
        
        with ProcessPoolExecutor(max_workers=min(len(items), 8)) as executor:
            results = list(executor.map(_worker_wrapper, worker_args))
            
        # Audit log
        query_id = data.get('query_id', str(uuid.uuid4()))
        for item, result in zip(items, results):
            ct_json = item['ciphertext']
            ct_hash = hashlib.sha256(ct_json.encode('utf-8')).hexdigest()
            audit_chain.log_evaluation(query_id, ct_hash, result)

        logger.info("Batch evaluation complete.")
        return jsonify({"results": results})
    except Exception as e:
        logger.error(f"Batch evaluation error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # --- mTLS (Task 5, Item #7) ---
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('cloud.pem', 'cloud-key.pem')
    context.load_verify_locations('ca.pem')
    context.verify_mode = ssl.CERT_REQUIRED  # mTLS: reject clients without a valid cert
    print("[mTLS] Cloud starting with mutual TLS on port 5002...")
    app.run(port=5002, ssl_context=context)