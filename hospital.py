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

# 3. Quantize and ensure weights are strictly positive integers (avoiding PyMIFE k2 None bugs)
SCALING_FACTOR = 100.0
# Using absolute value or shifting ensures keygen never returns None elements in k2
quantized_weights = [int(abs(val)) + 1 for val in np.rint(trimmed_weights * SCALING_FACTOR)]

DIMENSION = len(quantized_weights)
print(f"Configuring FeDDH for dimension n={DIMENSION} using mclbn256 C++ backend...")

# 4. Initialize FeDDH Master Key using the fast optimized generator
print(f"Running fast matrix keygen for n={DIMENSION}...")
master_key = fast_feddh_generate(DIMENSION, F=MclPairing())
ek = generate_ek(master_key)

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

if __name__ == '__main__':
    app.run(port=5001)