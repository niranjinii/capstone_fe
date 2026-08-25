import numpy as np
import pandas as pd
import requests
from delegated_crypto import deserialize_ek, delegated_encrypt

print("--- Starting Clinic Inference Workflow ---")

# 1. Get dimension dynamically from Hospital to match the model shape
dim_resp = requests.get('http://127.0.0.1:5001/get_dimension').json()
n = dim_resp['dimension']
print(f"Model dimension expected: {n}")

# 2. Dynamically fetch the required gene indices and load the patient data
indices_resp = requests.get('http://127.0.0.1:5001/get_active_indices').json()
active_indices = indices_resp['active_indices']

print(f"Loading full patient data and filtering to {len(active_indices)} active genes...")
patient_full_vector = np.load('patient1_full.npy')
raw_patient_vector = patient_full_vector[active_indices]

# Quantize patient data using the exact same scaling factor
SCALING_FACTOR = 100.0
quantized_patient_vector = np.rint(raw_patient_vector * SCALING_FACTOR).astype(np.int64).tolist()

# 3. Fetch the delegated encryption key (ek) from the Hospital[cite: 1]
print("Fetching Delegated Encryption Key (ek)...")
ek_response = requests.get('http://127.0.0.1:5001/get_ek')
ek = deserialize_ek(ek_response.json()['ek'])

# 4. Encrypt patient data locally using O(n^2) delegated exponentiation[cite: 1]
print(f"Encrypting patient vector of size {n} using delegated crypto...")
json_ct = delegated_encrypt(ek, quantized_patient_vector)

# 5. Fetch the sealed functional key from the Hospital[cite: 1]
print("Fetching sealed functional key...")
key_response = requests.get('http://127.0.0.1:5001/get_key')
json_sk = key_response.json()['functional_key']

# 6. Send payload to Cloud for secure evaluation
print("Sending payloads to Cloud for secure evaluation...")
payload = {
    "ciphertext": json_ct,
    "functional_key": json_sk
}
cloud_response = requests.post('http://127.0.0.1:5002/evaluate', json=payload)

# 7. Correct for the constant weight shift applied during quantisation
#    Cloud computed: <x, w+C> = <x, w> + C * sum(x)
#    We recover:     <x, w>   = result - C * sum(x)
shift_resp = requests.get('http://127.0.0.1:5001/get_weight_shift').json()
weight_shift = shift_resp['weight_shift']
raw_result = cloud_response.json()['encrypted_result']
correction = weight_shift * sum(quantized_patient_vector)
true_score = raw_result - correction

print(f"\n--- Final Clinical Prediction from Cloud ---")
print(f"Cloud returned (shifted): {raw_result}")
print(f"Weight shift correction:  -{correction} (C={weight_shift} × Σx={sum(quantized_patient_vector)})")
print(f"True Risk Score:          {true_score}")