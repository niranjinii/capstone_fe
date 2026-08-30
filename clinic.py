import math
import numpy as np
import requests
import logging
from delegated_crypto import deserialize_ek, delegated_encrypt
from bucketing import pad_patient_vector, build_batch_payload
from rho_blinding import extend_patient_vector, correct_blinded_result

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("Clinic")

logger.info("=== Clinic Query & Inference Workflow ===")

# 1. Retrieve Model & Bucket Metadata from Hospital
logger.info("Fetching model metadata from Hospital...")
info_resp = requests.get("http://127.0.0.1:5001/get_model_info").json()
cancer_name = info_resp["cancer_name"]
active_features_count = info_resp["active_features_count"]
active_indices = info_resp["active_indices"]
bucket_name = info_resp["bucket_name"]
bucket_dim = info_resp["bucket_dimension"]

logger.info(f"Target: {cancer_name} | Bucket: '{bucket_name}' (Dimension: {bucket_dim})")

# 2. Load & Pad Real Patient Expression Vector
logger.info("Loading real patient data from 'patient1_full.npy'...")
full_patient = np.load("patient1_full.npy")
# Filter down to just the genes active in this specific cancer model
raw_patient = full_patient[active_indices]

SCALING_FACTOR = 5.0
raw_quantized_patient = [int(val) for val in np.rint(raw_patient * SCALING_FACTOR)]

padded_patient = pad_patient_vector(raw_quantized_patient, bucket_dim)
extended_patient = extend_patient_vector(padded_patient)

# 3. Fetch Delegated Encryption Key (ek)[cite: 1]
logger.info("Fetching Delegated Encryption Key (ek)...")
ek_resp = requests.get("http://127.0.0.1:5001/get_ek").json()
ek = deserialize_ek(ek_resp["ek"])

# 4. Encrypt Extended Vector via Delegated Crypto[cite: 1]
logger.info(f"Encrypting extended vector of size {len(extended_patient)} via delegated crypto...")
json_ct = delegated_encrypt(ek, extended_patient)

# 5. Fetch Sealed Functional Key[cite: 1]
logger.info("Fetching sealed functional key from Hospital...")
key_resp = requests.get("http://127.0.0.1:5001/get_key").json()
if "error" in key_resp:
    logger.error(f"Hospital returned an error: {key_resp['error']}")
    logger.error("Is the Cloud node running? (The Hospital needs to fetch the Cloud's public key).")
    exit(1)
json_sk = key_resp["functional_key"]

# 6. Evaluate Single Query
logger.info("Dispatching single evaluation to Cloud...")
single_payload = {"ciphertext": json_ct, "functional_key": json_sk}
cloud_resp = requests.post("http://127.0.0.1:5002/evaluate", json=single_payload).json()

# 6.5. Fetch shift and rho, and correct result
logger.info("Fetching weight shift and rho unblinding parameter from Hospital...")
shift_resp = requests.get("http://127.0.0.1:5001/get_weight_shift").json()
weight_shift = shift_resp["weight_shift"]
rho_resp = requests.get("http://127.0.0.1:5001/get_rho").json()
rho_val = rho_resp["rho"]

raw_result = cloud_resp.get("encrypted_result")
unblinded_result = correct_blinded_result(raw_result, rho_val)
correction = weight_shift * sum(padded_patient)
true_score = unblinded_result - correction

logger.info(f"Single Query Score (Raw from Cloud): {raw_result}")
logger.info(f"Single Query Score (Unblinded): {unblinded_result}")
logger.info(f"Single Query Score (True corrected): {true_score}")

# Calculate percentage risk (Sigmoid)
# The true score is scaled by Hospital (100x) and Clinic (5x) = 500x total.
z_score = true_score / 500.0
if z_score < -100:
    risk_probability = 0.0
elif z_score > 100:
    risk_probability = 100.0
else:
    risk_probability = (1.0 / (1.0 + math.exp(-z_score))) * 100.0

logger.info(f"==> Final Cancer Risk Prediction: {risk_probability:.2f}%")

# 7. Test Parallel Batch Endpoint
logger.info("Testing /evaluate_batch endpoint with duplicate parallel payload...")
batch_payload = build_batch_payload([json_ct, json_ct], [json_sk, json_sk])
batch_resp = requests.post("http://127.0.0.1:5002/evaluate_batch", json=batch_payload).json()
raw_batch_results = batch_resp.get("results", [])
true_batch_results = [correct_blinded_result(res, rho_val) - correction for res in raw_batch_results]
logger.info(f"Batch Parallel Results (Raw): {raw_batch_results}")
logger.info(f"Batch Parallel Results (True): {true_batch_results}")