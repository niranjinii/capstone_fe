import sys
import numpy as np
import requests
from delegated_crypto import deserialize_ek, delegated_encrypt

print("--- Starting Clinic Inference Workflow (XAI Edition) ---")

HOSPITAL_URL = 'http://127.0.0.1:5001'
CLOUD_URL = 'http://127.0.0.1:5002'

# Step 0: Verify Cloud integrity before trusting it with real patient data
print("Verifying Cloud integrity (decoy test)...")
try:
    verify_resp = requests.get(f'{HOSPITAL_URL}/verify_cloud', timeout=30)
    verify_result = verify_resp.json()
    if verify_result.get('verified'):
        print("  CLOUD INTEGRITY: VERIFIED")
        print(f"  Decoy test: expected={verify_result['expected']}, "
              f"received={verify_result['received']}")
    else:
        print("  CLOUD INTEGRITY: FAILED")
        print(f"  Expected: {verify_result.get('expected')}")
        print(f"  Received: {verify_result.get('received', 'N/A')}")
        print("  ABORTING — Cloud may be compromised. Do NOT trust results.")
        sys.exit(1)
except Exception as e:
    print(f"  CLOUD INTEGRITY: UNKNOWN (verification failed: {e})")
    print("  WARNING: Proceeding without verification.")

# 1. Get dimension dynamically from Hospital to match the model shape
dim_resp = requests.get(f'{HOSPITAL_URL}/get_dimension').json()
n = dim_resp['dimension']
print(f"Model dimension expected: {n}")

# 2. Dynamically fetch the required gene indices and load the patient data
indices_resp = requests.get(f'{HOSPITAL_URL}/get_active_indices').json()
active_indices = indices_resp['active_indices']

print(f"Loading full patient data and filtering to {len(active_indices)} active genes...")
patient_full_vector = np.load('patient1_full.npy')
raw_patient_vector = patient_full_vector[active_indices]

# Quantize patient data
SCALING_FACTOR = 100.0
quantized_patient_vector = np.rint(raw_patient_vector * SCALING_FACTOR).astype(np.int64).tolist()

# 3. Fetch the delegated encryption key (ek)
print("Fetching Delegated Encryption Key (ek)...")
ek_response = requests.get(f'{HOSPITAL_URL}/get_ek')
ek = deserialize_ek(ek_response.json()['ek'])

# 4. Encrypt patient data locally
print(f"Encrypting patient vector of size {n} using delegated crypto...")
json_ct = delegated_encrypt(ek, quantized_patient_vector)

# 5. Fetch the sealed functional keys
print("Fetching overall functional key...")
key_response = requests.get(f'{HOSPITAL_URL}/get_key')
json_sk = key_response.json()['functional_key']

print("\nFetching pathway-specific functional keys...")
pathway_keys_resp = requests.get(f'{HOSPITAL_URL}/get_pathway_keys')
if pathway_keys_resp.status_code == 429:
    budget_info = pathway_keys_resp.json()
    print(f"\n  XAI PRIVACY BUDGET EXHAUSTED")
    print(f"  Total budget: {budget_info.get('total_budget')} epsilon")
    print(f"  Spent: {budget_info.get('spent')} epsilon")
    print(f"  No further pathway explanations can be issued.")
    pathway_keys = {}
else:
    pathway_keys = pathway_keys_resp.json().get('pathway_keys', {})
    if not pathway_keys:
        print("Warning: No pathway keys received (maybe gene_names_20531.txt is missing).")

# 6. Send payload to Cloud for overall evaluation
print("\nSending payloads to Cloud for overall secure evaluation...")
payload = {
    "ciphertext": json_ct,
    "functional_key": json_sk
}
cloud_response = requests.post(f'{CLOUD_URL}/evaluate', json=payload)

shift_resp = requests.get(f'{HOSPITAL_URL}/get_weight_shift').json()
weight_shift = shift_resp['weight_shift']
raw_result = cloud_response.json()['encrypted_result']
correction = weight_shift * sum(quantized_patient_vector)
true_score = raw_result - correction

print(f"\n--- Final Clinical Prediction from Cloud ---")
print(f"Cloud returned (shifted): {raw_result}")
print(f"Weight shift correction:  -{correction} (C={weight_shift} * Sum(x)={sum(quantized_patient_vector)})")
print(f"True Risk Score:          {true_score}")

# 7. Send payload to Cloud for pathway evaluation
if pathway_keys:
    print(f"\nSending {len(pathway_keys)} pathway keys to Cloud for XAI evaluation...")
    pathway_payload = {
        "ciphertext": json_ct,
        "pathway_keys": pathway_keys
    }
    pathway_response = requests.post(f'{CLOUD_URL}/evaluate_pathways', json=pathway_payload)
    pathway_raw_results = pathway_response.json()['pathway_results']
    
    pathway_scores = {}
    for name, raw_score in pathway_raw_results.items():
        score = raw_score - correction
        pathway_scores[name] = score

    # Sort pathways by absolute contribution
    sorted_pathways = sorted(pathway_scores.items(), key=lambda item: abs(item[1]), reverse=True)
    
    # Load biological annotations
    try:
        from hallmark_descriptions import HALLMARK_DESCRIPTIONS
    except ImportError:
        HALLMARK_DESCRIPTIONS = {}

    print("\n--- Pathway-Level Explanation ---")
    print("Top contributing pathways:")
    for name, score in sorted_pathways[:15]:
        percentage = (score / true_score) * 100 if true_score != 0 else 0
        direction = "Risk-increasing" if score > 0 else "Risk-decreasing"
        print(f"  {name:45s} {score:+8d} ({percentage:+6.1f}% of total)")
        bio_desc = HALLMARK_DESCRIPTIONS.get(name)
        if bio_desc:
            print(f"    {direction}: {bio_desc}")

    print("\n  Source: MSigDB Hallmark Gene Sets, Broad Institute (Liberzon et al., Cell Systems, 2015)")
    print("  Note: Pathway annotations describe biological processes, not clinical diagnoses.")

    dp_epsilon = pathway_response.json().get('epsilon', 'N/A')
    print(f"\n--- Privacy Metadata ---")
    print(f"  Differential privacy: epsilon={dp_epsilon}")
    try:
        budget_resp = requests.get(f'{HOSPITAL_URL}/xai_privacy_budget').json()
        print(f"  XAI budget remaining: {budget_resp.get('remaining', 0):.1f}/{budget_resp.get('total_budget', 0)} epsilon")
        print(f"  Queries made: {budget_resp.get('queries_made', 0)}/{budget_resp.get('max_queries_allowed', 0)}")
    except Exception as e:
        print(f"  Failed to fetch budget metadata: {e}")

# Step 8: Verify audit chain integrity
print("\nVerifying audit chain integrity...")
try:
    chain_resp = requests.get(f'{CLOUD_URL}/verify_audit_chain')
    chain_result = chain_resp.json()
    if chain_result.get('valid'):
        print(f"  AUDIT CHAIN: VALID ({chain_result['entries_checked']} entries, "
              f"root={chain_result['merkle_root'][:16]}...)")
    else:
        print(f"  AUDIT CHAIN: TAMPERED at entry {chain_result['first_broken_index']}")
except Exception as e:
    print(f"  AUDIT CHAIN: Could not verify ({e})")