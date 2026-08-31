import base64
import traceback
from flask import Flask, request, jsonify
from mife.single.fhiding.ddh import FeDDH, _FeDDH_MK
from mife.data.zmod_r import ZmodR
from nacl.public import PrivateKey, SealedBox
from fhipe_serializer import deserialize_ciphertext, deserialize_functional_key
from mcl_backend import MclPairing
import hashlib
import uuid
import numpy as np
from audit_log import MerkleAuditLog

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

@app.route('/public_key', methods=['GET'])
def get_public_key():
    """Expose the Cloud's public key so the Hospital can seal payloads for it."""
    encoded_pk = base64.b64encode(cloud_public_key.encode()).decode('utf-8')
    return jsonify({"public_key": encoded_pk})

def _decrypt_single(ciphertext_json, sealed_functional_key):
    """Helper to unseal and decrypt a single functional key against a ciphertext."""
    sealed_box = SealedBox(cloud_private_key)
    encrypted_sk_bytes = base64.b64decode(sealed_functional_key)
    decrypted_sk_json = sealed_box.decrypt(encrypted_sk_bytes).decode('utf-8')

    ct = deserialize_ciphertext(ciphertext_json)
    sk = deserialize_functional_key(decrypted_sk_json)

    _backend = MclPairing()
    pub = _FeDDH_MK.__new__(_FeDDH_MK)
    pub.n = len(sk.k2)
    pub.F = _backend
    pub.G = ZmodR(_backend.order())
    pub.msk = None

    return FeDDH.decrypt(ct, pub, sk, (-1000000, 1000000))

@app.route('/evaluate', methods=['POST'])
def evaluate():
    try:
        data = request.json
        ct_json = data['ciphertext']
        result = _decrypt_single(ct_json, data['functional_key'])

        # Log to audit chain
        query_id = data.get('query_id', str(uuid.uuid4()))
        ct_hash = hashlib.sha256(ct_json.encode('utf-8')).hexdigest()
        audit_chain.log_evaluation(query_id, ct_hash, result)

        return jsonify({"encrypted_result": result})
    except Exception as e:
        print("\n--- ERROR IN /evaluate ---")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/evaluate_pathways', methods=['POST'])
def evaluate_pathways():
    try:
        data = request.json
        ct_json = data['ciphertext']
        pathway_keys = data['pathway_keys']

        results = {}
        for name, sealed_sk in pathway_keys.items():
            raw_score = _decrypt_single(ct_json, sealed_sk)
            # Add calibrated Laplace noise for epsilon-differential privacy
            noise = int(np.random.laplace(0, XAI_SENSITIVITY / XAI_EPSILON))
            results[name] = raw_score + noise

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

if __name__ == '__main__':
    app.run(port=5002)