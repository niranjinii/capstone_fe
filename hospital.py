import base64
import traceback
import numpy as np
import requests
from flask import Flask, jsonify
from mife.single.fhiding.ddh import FeDDH
from nacl.public import PublicKey, SealedBox
from fhipe_serializer import serialize_functional_key
from delegated_crypto import generate_ek, serialize_ek
from mcl_backend import MclPairing, fast_feddh_generate
import time as _time
from flask import request
from pathway_xai import load_hallmark_pathways, build_pathway_vectors
from audit_log import run_decoy_verification
app = Flask(__name__)

# 1. Load real model weights from the .npy artifact
print("Loading master 33-cancer weights...")
raw_weights_data = np.load('master_33_cancer_weights.npy', allow_pickle=True)

if isinstance(raw_weights_data, np.ndarray) and raw_weights_data.ndim == 2:
    selected_model_weights = raw_weights_data[0]
else:
    selected_model_weights = list(raw_weights_data.item().values())[0]

# 2. Dynamically extract the exact active features for the selected model
active_indices = np.flatnonzero(selected_model_weights != 0)
FEASIBLE_DIM = len(active_indices)
trimmed_weights = selected_model_weights[active_indices]

# 3. Quantize weights, preserving sign (negative Lasso coefficients indicate suppression)
SCALING_FACTOR = 100.0
raw_quantized = [int(val) for val in np.rint(trimmed_weights * SCALING_FACTOR)]

# Constant shift: PyMIFE's FeDDH.keygen() returns None in k2 for zero-valued weights.
# Instead of abs() (which destroys sign), we shift ALL weights by a constant C so they
# are all strictly positive. The Clinic corrects for this after decryption:
#   Cloud computes: <x, w+C> = <x, w> + C * sum(x)
#   Clinic recovers: <x, w> = result - C * sum(x)
WEIGHT_SHIFT = max(0, -min(raw_quantized)) + 1
quantized_weights = [w + WEIGHT_SHIFT for w in raw_quantized]
print(f"Quantized {len(quantized_weights)} weights (shift C={WEIGHT_SHIFT} to ensure all > 0)")

DIMENSION = len(quantized_weights)
print(f"Configuring FeDDH for dimension n={DIMENSION} using mclbn256 C++ backend...")

# 4. Initialize FeDDH Master Key using the fast optimized generator
print(f"Running fast matrix keygen for n={DIMENSION}...")
master_key = fast_feddh_generate(DIMENSION, F=MclPairing())
ek = generate_ek(master_key)

# --- XAI Setup ---
# Load gene names and map active indices to symbols
try:
    with open('gene_names_20531.txt', 'r') as f:
        all_genes = [line.strip() for line in f]
    active_gene_names = [all_genes[i] for i in active_indices]
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
pathway_vectors_raw = build_pathway_vectors(pathways, active_gene_names, raw_quantized)
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

@app.route('/get_dimension', methods=['GET'])
def get_dimension():
    """Clinic: Returns the exact number of active genes required."""
    return jsonify({"dimension": FEASIBLE_DIM})

@app.route('/get_active_indices', methods=['GET'])
def get_active_indices():
    """Clinic: Returns the exact array indices of the active genes for the current model."""
    return jsonify({"active_indices": active_indices.tolist()})

@app.route('/get_ek', methods=['GET'])
def get_ek():
    return jsonify({"ek": serialize_ek(ek)})

@app.route('/get_weight_shift', methods=['GET'])
def get_weight_shift():
    """Clinic: Returns the constant shift C applied to weights during quantisation.
    The Clinic must subtract C * sum(x) from the Cloud's result to recover the true score."""
    return jsonify({"weight_shift": WEIGHT_SHIFT})

@app.route('/get_key', methods=['GET'])
def get_key():
    try:
        # Generate functional key using valid positive quantized weights
        sk = FeDDH.keygen(quantized_weights, master_key)
        json_sk = serialize_functional_key(sk)
        
        # Fetch Cloud public key and seal the key securely (PyNaCl Sealed Box)
        cloud_resp = requests.get('http://127.0.0.1:5002/public_key').json()
        cloud_pk_bytes = base64.b64decode(cloud_resp['public_key'])
        cloud_pk = PublicKey(cloud_pk_bytes)
        
        sealed_box = SealedBox(cloud_pk)
        encrypted_sk = sealed_box.encrypt(json_sk.encode('utf-8'))
        
        encoded_sealed_sk = base64.b64encode(encrypted_sk).decode('utf-8')
        return jsonify({"functional_key": encoded_sealed_sk})
    except Exception as e:
        print("\n--- ERROR IN /get_key ---")
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
            sk = FeDDH.keygen(sub_vec_shifted, master_key)
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

if __name__ == '__main__':
    app.run(port=5001)