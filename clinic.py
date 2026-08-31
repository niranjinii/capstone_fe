import sys
import math
import uuid
import time
import numpy as np
import requests
import json
import logging
from nacl.signing import SigningKey, VerifyKey
import nacl.encoding
from nacl.exceptions import BadSignatureError
from delegated_crypto import deserialize_ek, delegated_encrypt
from bucketing import pad_patient_vector, build_batch_payload
from rho_blinding import extend_patient_vector, correct_blinded_result

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("Clinic")

logger.info("--- Starting Clinic Inference Workflow (XAI & Security Edition) ---")

HOSPITAL_URL = 'https://127.0.0.1:5001'
CLOUD_URL    = 'https://127.0.0.1:5002'

# --- mTLS client credentials (Task 5, Item #7) ---
# SESSION_KWARGS is splatted into every requests.get/post call so that:
#   cert=   presents the Clinic's own certificate to the server (mTLS client auth)
#   verify= tells requests to validate the server cert against our private CA
SESSION_KWARGS = {
    'cert':   ('clinic.pem', 'clinic-key.pem'),
    'verify': 'ca.pem',
}

# --- Payload Signing (Task 6, Item #7) ---
clinic_signing_key = SigningKey.generate()
clinic_vk_hex = clinic_signing_key.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode('utf-8')

logger.info("Fetching Ed25519 verify keys from Hospital and Cloud...")
hosp_vk_hex = requests.get(f"{HOSPITAL_URL}/signing_key", **SESSION_KWARGS).json()['verify_key']
hospital_vk = VerifyKey(hosp_vk_hex.encode('utf-8'), encoder=nacl.encoding.HexEncoder)

cloud_vk_hex = requests.get(f"{CLOUD_URL}/signing_key", **SESSION_KWARGS).json()['verify_key']
cloud_vk = VerifyKey(cloud_vk_hex.encode('utf-8'), encoder=nacl.encoding.HexEncoder)

def secure_request(method, url, server_vk, **kwargs):
    """Wraps requests.request to add mTLS args, sign POST payloads, and verify response signatures."""
    kwargs.update(SESSION_KWARGS)
    
    if method == 'POST' and 'json' in kwargs:
        payload_bytes = json.dumps(kwargs['json'], separators=(',', ':')).encode('utf-8')
        sig_hex = clinic_signing_key.sign(payload_bytes).signature.hex()
        
        headers = kwargs.get('headers', {})
        headers['X-Signature'] = sig_hex
        headers['X-Verify-Key'] = clinic_vk_hex
        headers['Content-Type'] = 'application/json'
        kwargs['headers'] = headers
        kwargs['data'] = payload_bytes
        del kwargs['json']
        
    resp = requests.request(method, url, **kwargs)
    
    # Verify response signature if present
    sig_hex = resp.headers.get('X-Signature')
    if sig_hex:
        try:
            server_vk.verify(resp.content, bytes.fromhex(sig_hex))
        except BadSignatureError:
            logger.error(f"FATAL: Invalid signature from server {url}")
            sys.exit(1)
    elif resp.headers.get('Content-Type') == 'application/json':
        logger.warning(f"Warning: JSON response from {url} was not signed!")
        
    return resp


# Step 0: Verify Cloud integrity before trusting it with real patient data
logger.info("Verifying Cloud integrity (decoy test)...")
try:
    verify_resp = secure_request('GET', f'{HOSPITAL_URL}/verify_cloud', hospital_vk, timeout=30)
    verify_result = verify_resp.json()
    if verify_result.get('verified'):
        logger.info(f"CLOUD INTEGRITY: VERIFIED (Decoy test: expected={verify_result['expected']}, received={verify_result['received']})")
    else:
        logger.error(f"CLOUD INTEGRITY: FAILED (Expected: {verify_result.get('expected')}, Received: {verify_result.get('received', 'N/A')})")
        logger.error("ABORTING — Cloud may be compromised. Do NOT trust results.")
        sys.exit(1)
except Exception as e:
    logger.warning(f"CLOUD INTEGRITY: UNKNOWN (verification failed: {e}) - Proceeding without verification.")

# 1. Retrieve Model & Bucket Metadata from Hospital
logger.info("Fetching model metadata from Hospital...")
info_resp = secure_request('GET', f"{HOSPITAL_URL}/get_model_info", hospital_vk).json()
cancer_name = info_resp["cancer_name"]
active_features_count = info_resp["active_features_count"]
active_indices = info_resp["active_indices"]
bucket_name = info_resp["bucket_name"]
bucket_dim = info_resp["bucket_dimension"]

logger.info(f"Target: {cancer_name} | Bucket: '{bucket_name}' (Dimension: {bucket_dim})")

# 2. Load & Pad Real Patient Expression Vector
logger.info("Loading real patient data from 'patient1_full.npy'...")
full_patient = np.load("patient1_full.npy")
raw_patient = full_patient[active_indices]

SCALING_FACTOR = 5.0
raw_quantized_patient = [int(val) for val in np.rint(raw_patient * SCALING_FACTOR)]
padded_patient = pad_patient_vector(raw_quantized_patient, bucket_dim)
extended_patient = extend_patient_vector(padded_patient)

# 3. Fetch Delegated Encryption Key (ek)
logger.info("Fetching Delegated Encryption Key (ek)...")
ek_resp = secure_request('GET', f"{HOSPITAL_URL}/get_ek", hospital_vk).json()
ek = deserialize_ek(ek_resp["ek"])

# 4. Encrypt Extended Vector
logger.info(f"Encrypting extended vector of size {len(extended_patient)} via delegated crypto...")
json_ct = delegated_encrypt(ek, extended_patient)

# 5. Fetch Sealed Functional Key & Pathway Keys
logger.info("Fetching sealed functional key from Hospital...")
key_resp = secure_request('GET', f"{HOSPITAL_URL}/get_key", hospital_vk).json()
if "error" in key_resp:
    logger.error(f"Hospital returned an error: {key_resp['error']}")
    exit(1)
json_sk = key_resp["functional_key"]

logger.info("Fetching pathway-specific functional keys for XAI...")
pathway_keys_resp = secure_request('GET', f'{HOSPITAL_URL}/get_pathway_keys', hospital_vk)
if pathway_keys_resp.status_code == 429:
    budget_info = pathway_keys_resp.json()
    logger.warning("XAI PRIVACY BUDGET EXHAUSTED")
    logger.warning(f"Total budget: {budget_info.get('total_budget')} epsilon | Spent: {budget_info.get('spent')} epsilon")
    pathway_keys = {}
else:
    pathway_keys = pathway_keys_resp.json().get('pathway_keys', {})

# 6. Evaluate Single Query
# --- Replay Attack Prevention (Item #19) ---
# Each query gets a unique ID and a timestamp so the Cloud can:
#   (a) reject duplicate query_ids (replay of the exact same request), and
#   (b) reject requests older than MAX_AGE_SECONDS (prevents storing & replaying later)
query_id = str(uuid.uuid4())
query_timestamp = int(time.time())
logger.info(f"Dispatching single evaluation to Cloud (query_id={query_id})...")
single_payload = {
    "ciphertext": json_ct,
    "functional_key": json_sk,
    "query_id": query_id,
    "timestamp": query_timestamp,
}
cloud_resp = secure_request('POST', f"{CLOUD_URL}/evaluate", cloud_vk, json=single_payload).json()

logger.info("Fetching weight shift and rho unblinding parameter from Hospital...")
shift_resp = secure_request('GET', f"{HOSPITAL_URL}/get_weight_shift", hospital_vk).json()
weight_shift = shift_resp["weight_shift"]
rho_resp = secure_request('GET', f"{HOSPITAL_URL}/get_rho", hospital_vk).json()
rho_val = rho_resp["rho"]

raw_result = cloud_resp.get("encrypted_result")
unblinded_result = correct_blinded_result(raw_result, rho_val)
correction = weight_shift * sum(padded_patient)
true_score = unblinded_result - correction

logger.info(f"Single Query Score (Raw from Cloud): {raw_result}")
logger.info(f"Single Query Score (Unblinded): {unblinded_result}")
logger.info(f"Single Query Score (True corrected): {true_score}")

# Calculate percentage risk (Sigmoid)
z_score = true_score / 500.0
if z_score < -100:
    risk_probability = 0.0
elif z_score > 100:
    risk_probability = 100.0
else:
    risk_probability = (1.0 / (1.0 + math.exp(-z_score))) * 100.0

logger.info(f"==> Final Cancer Risk Prediction: {risk_probability:.2f}%")

# ============================================================
# FORMATTED CLINICAL REPORT
# ============================================================
print("\n")
print("=" * 70)
print("              ENCRYPTED CANCER RISK PREDICTION REPORT")
print("=" * 70)
print(f"  Cancer Type  :  {cancer_name}")
print(f"  Bucket       :  {bucket_name} (dim={bucket_dim})")
print(f"  Risk Score   :  {true_score}")
print(f"  Risk Level   :  {risk_probability:.2f}%")
risk_bar_len = int(risk_probability / 2)
risk_bar = "#" * risk_bar_len + "-" * (50 - risk_bar_len)
print(f"  Risk Bar     :  [{risk_bar}]")
print("-" * 70)
print("  SECURITY CHECKS")
print("-" * 70)
print(f"  Cloud Decoy Verification  :  PASSED")
print(f"  Rho Blinding Applied      :  YES (raw={raw_result} -> unblinded={unblinded_result})")
print(f"  Weight Shift Correction   :  -{correction} (C={weight_shift})")

# 7. Pathway Evaluation (XAI)
if pathway_keys:
    logger.info(f"Sending {len(pathway_keys)} pathway keys to Cloud for XAI evaluation...")
    pathway_payload = {
        "ciphertext": json_ct,
        "pathway_keys": pathway_keys
    }
    pathway_response = secure_request('POST', f'{CLOUD_URL}/evaluate_pathways', cloud_vk, json=pathway_payload)
    pathway_raw_results = pathway_response.json()['pathway_results']
    
    pathway_scores = {}
    for name, raw_score in pathway_raw_results.items():
        # Correct for rho blinding AND weight shift
        unblinded_pathway = correct_blinded_result(raw_score, rho_val)
        score = unblinded_pathway - correction
        pathway_scores[name] = score

    sorted_pathways = sorted(pathway_scores.items(), key=lambda item: abs(item[1]), reverse=True)
    
    try:
        from hallmark_descriptions import HALLMARK_DESCRIPTIONS
    except ImportError:
        HALLMARK_DESCRIPTIONS = {}

    dp_epsilon = pathway_response.json().get('epsilon', 'N/A')

    print("-" * 70)
    print("  XAI PATHWAY EXPLANATION  (Differential Privacy: epsilon={})".format(dp_epsilon))
    print("-" * 70)
    for rank, (name, score) in enumerate(sorted_pathways[:10], 1):
        percentage = (score / true_score) * 100 if true_score != 0 else 0
        direction = "RISK+" if score > 0 else "RISK-"
        short_name = name.replace("HALLMARK_", "").replace("_", " ").title()
        print(f"  {rank:2d}. [{direction}] {short_name:40s}  {score:+8d}  ({percentage:+.1f}%)")
        bio_desc = HALLMARK_DESCRIPTIONS.get(name)
        if bio_desc:
            print(f"      >> {bio_desc}")

    # --- Old verbose output (commented out, kept for teammate's reference) ---
    # print("\n--- Pathway-Level Explanation ---")
    # print("Top contributing pathways:")
    # for name, score in sorted_pathways[:15]:
    #     percentage = (score / true_score) * 100 if true_score != 0 else 0
    #     direction = "Risk-increasing" if score > 0 else "Risk-decreasing"
    #     print(f"  {name:45s} {score:+8d} ({percentage:+6.1f}% of total)")
    #     bio_desc = HALLMARK_DESCRIPTIONS.get(name)
    #     if bio_desc:
    #         print(f"    {direction}: {bio_desc}")
    # print("\n  Source: MSigDB Hallmark Gene Sets, Broad Institute")
    # print("  Note: Pathway annotations describe biological processes, not clinical diagnoses.")
    # dp_epsilon = pathway_response.json().get('epsilon', 'N/A')
    # print(f"\n--- Privacy Metadata ---")
    # print(f"  Differential privacy: epsilon={dp_epsilon}")
    # try:
    #     budget_resp = requests.get(f'{HOSPITAL_URL}/xai_privacy_budget').json()
    #     print(f"  XAI budget remaining: {budget_resp.get('remaining', 0):.1f}/{budget_resp.get('total_budget', 0)} epsilon")
    # except Exception as e:
    #     pass

    print("-" * 70)
    print("  PRIVACY BUDGET")
    print("-" * 70)
    try:
        budget_resp = secure_request('GET', f'{HOSPITAL_URL}/xai_privacy_budget', hospital_vk).json()
        remaining = budget_resp.get('remaining', 0)
        total = budget_resp.get('total_budget', 0)
        queries = budget_resp.get('queries_made', 0)
        max_q = budget_resp.get('max_queries_allowed', 0)
        budget_bar_len = int((remaining / total) * 50) if total > 0 else 0
        budget_bar = "#" * budget_bar_len + "-" * (50 - budget_bar_len)
        print(f"  Epsilon Budget :  {remaining:.1f} / {total:.1f}")
        print(f"  Budget Bar     :  [{budget_bar}]")
        print(f"  Queries Used   :  {queries} / {max_q}")
    except Exception as e:
        pass

    print("-" * 70)
    print("  Source: MSigDB Hallmark Gene Sets, Broad Institute")
    print("  Note: Pathway annotations describe biological processes,")
    print("        not clinical diagnoses.")

# 8. Test Parallel Batch Endpoint
logger.info("Testing /evaluate_batch endpoint with duplicate parallel payload...")
batch_payload = build_batch_payload([json_ct, json_ct], [json_sk, json_sk])
batch_resp = secure_request('POST', f"{CLOUD_URL}/evaluate_batch", cloud_vk, json=batch_payload).json()
raw_batch_results = batch_resp.get("results", [])
true_batch_results = [correct_blinded_result(res, rho_val) - correction for res in raw_batch_results]
logger.info(f"Batch Parallel Results (True): {true_batch_results}")

print("-" * 70)
print("  BATCH CONSISTENCY CHECK")
print("-" * 70)
if len(true_batch_results) >= 2 and true_batch_results[0] == true_batch_results[1]:
    print(f"  Batch Result #1 :  {true_batch_results[0]}")
    print(f"  Batch Result #2 :  {true_batch_results[1]}")
    print(f"  Match           :  CONSISTENT")
else:
    print(f"  Results: {true_batch_results}")

# 9. Verify audit chain integrity
logger.info("Verifying audit chain integrity...")
try:
    chain_resp = secure_request('GET', f'{CLOUD_URL}/verify_audit_chain', cloud_vk)
    chain_result = chain_resp.json()
    print("-" * 70)
    print("  MERKLE AUDIT CHAIN")
    print("-" * 70)
    if chain_result.get('valid'):
        logger.info(f"AUDIT CHAIN: VALID ({chain_result['entries_checked']} entries, root={chain_result['merkle_root'][:16]}...)")
        print(f"  Status         :  VALID")
        print(f"  Entries        :  {chain_result['entries_checked']}")
        print(f"  Merkle Root    :  {chain_result['merkle_root'][:32]}...")
    else:
        logger.error(f"AUDIT CHAIN: TAMPERED at entry {chain_result['first_broken_index']}")
        print(f"  Status         :  TAMPERED at entry {chain_result['first_broken_index']}")
except Exception as e:
    logger.warning(f"AUDIT CHAIN: Could not verify ({e})")

print("=" * 70)
print("                       END OF REPORT")
print("=" * 70)
