import numpy as np
import requests
from delegated_crypto import deserialize_ek, delegated_encrypt
from bucketing import pad_patient_vector, build_batch_payload

print("=== Clinic Query & Inference Workflow ===")

# 1. Retrieve Model & Bucket Metadata from Hospital
info_resp = requests.get("http://127.0.0.1:5001/get_model_info").json()
cancer_name = info_resp["cancer_name"]
active_features_count = info_resp["active_features_count"]
bucket_name = info_resp["bucket_name"]
bucket_dim = info_resp["bucket_dimension"]

print(f"Target: {cancer_name} | Bucket: '{bucket_name}' (Dimension: {bucket_dim})")

# 2. Simulate & Pad Patient Expression Vector
np.random.seed(42)
raw_patient = np.random.randn(active_features_count)
SCALING_FACTOR = 5.0
raw_quantized_patient = [int(abs(val)) + 1 for val in np.rint(np.abs(raw_patient) * SCALING_FACTOR)]

padded_patient = pad_patient_vector(raw_quantized_patient, bucket_dim)

# 3. Fetch Delegated Encryption Key (ek)[cite: 1]
print("Fetching Delegated Encryption Key (ek)...")
ek_resp = requests.get("http://127.0.0.1:5001/get_ek").json()
ek = deserialize_ek(ek_resp["ek"])

# 4. Encrypt Padded Vector via Delegated Crypto[cite: 1]
print(f"Encrypting padded vector of size {bucket_dim} via delegated crypto...")
json_ct = delegated_encrypt(ek, padded_patient)

# 5. Fetch Sealed Functional Key[cite: 1]
print("Fetching sealed functional key from Hospital...")
key_resp = requests.get("http://127.0.0.1:5001/get_key").json()
json_sk = key_resp["functional_key"]

# 6. Evaluate Single Query
print("Dispatching evaluation to Cloud...")
single_payload = {"ciphertext": json_ct, "functional_key": json_sk}
cloud_resp = requests.post("http://127.0.0.1:5002/evaluate", json=single_payload).json()
print(f"Single Query Score: {cloud_resp.get('encrypted_result')}")

# 7. Test Parallel Batch Endpoint
print("\nTesting /evaluate_batch endpoint with duplicate parallel payload...")
batch_payload = build_batch_payload([json_ct, json_ct], [json_sk, json_sk])
batch_resp = requests.post("http://127.0.0.1:5002/evaluate_batch", json=batch_payload).json()
print(f"Batch Parallel Results: {batch_resp.get('results')}")