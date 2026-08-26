# Healthcare 5.0 Privacy-Preserving AI: Team Developer Guide

Welcome to the engineering guide for our **Privacy-Preserving Genomic AI Pipeline**. This document outlines the current state of our 3-party Functional Encryption (FHIPE) architecture, exactly what each file in the repository does, how the integration currently works, and what still needs to be built from our official Roadmap.

---

## 0. Setup & Installation

Since the `venv` and cache files are not included in the repository, you must set up the environment and install the required dependencies before running the demo.

1. **Install System Dependencies** (Required for the cryptography C++ headers):
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y build-essential python3-venv python3-pip python3-dev libssl-dev libgmp-dev git
   ```

2. **Create the Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Python Packages**:
   ```bash
   pip install --upgrade pip
   pip install --no-cache-dir numpy pandas scipy scikit-learn py_ecc matplotlib requests flask
   pip install --no-cache-dir pymife mclbn256
   ```

---

## 1. How to Run the Current Demo

Currently, the pipeline correctly evaluates Patient 1's real TCGA gene expressions against the Hospital's Adrenocortical Carcinoma (ACC) model, yielding the exact mathematical risk score in under 3 seconds per query.

Open three separate WSL terminals in the `capstone` directory and activate the virtual environment (`source venv/bin/activate`). Run them in this exact order:

1. **Terminal 1:** `python3 hospital.py`
   *(Wait ~20 seconds. The Hospital will dynamically scan the ACC model weights, locate the 139 active genes, invert a 139×139 matrix using raw integer Gaussian elimination, and boot the Flask server on port 5001.)*
2. **Terminal 2:** `python3 cloud.py`
   *(Starts the untrusted evaluator node on port 5002.)*
3. **Terminal 3:** `python3 clinic.py`
   *(The Clinic fetches the required 139 indices, subsets Patient 1's full vector, performs $139^2 = 19,321$ C++ curve multiplications to encrypt the data, and sends it to the Cloud. The Cloud returns the risk score `190984`.)*

---

## 2. Current System Architecture

We have successfully implemented **baseline inference** using the C++ `mclbn256` backend over a distributed network.

```text
┌─────────────┐     1. /get_active_indices     ┌─────────────┐
│   Hospital  │ ◄────────────────────────────► │    Clinic   │
│  (Trusted)  │     2. /get_ek (encryption)    │ (Has Patient)│
│             │ ◄────────────────────────────► │             │
└─────────────┘     3. /get_key (functional)   └──────┬──────┘
                                                      │ encrypted patient data (c) +
                                                      │ sealed functional key (sk_y)
                                                      ▼
                                               ┌─────────────┐
                                               │    Cloud    │
                                               │ (Untrusted) │
                                               │             │
                                               │  decrypts → │
                                               │  risk score │
                                               └─────────────┘
```

**What happens under the hood:**
1. The **Hospital** loads the model. It handles all master key generation.
2. The **Clinic** loads real patient data. It securely requests the model's active genes and the delegated encryption key (`ek`). The clinic does $O(n^2)$ curve exponentiations locally.
3. The **Cloud** receives the encrypted patient box ($c$) and the functional key ($sk_y$) sealed for it. It computes the dot product blindly and solves the discrete logarithm (Kangaroo search) to find the plaintext result.

---

## 3. Directory & File Reference

Here is what every relevant file in the workspace currently does:

### Core Architecture Nodes
- **`hospital.py`**: The trusted Key Generation Center (KGC). Loads the master weights, dynamically subsets the active features, generates the Master Secret Key, and hosts the endpoints for the Clinic to fetch keys and dimensions.
- **`clinic.py`**: The doctor's interface. Dynamically subsets `patient1_full.npy` based on the Hospital's indices, encrypts the patient vector using `delegated_crypto.py`, and posts the payload to the Cloud.
- **`cloud.py`**: The untrusted evaluator. Performs the heavy pairing cryptography to multiply the ciphertexts together. Expanded to search `[-1000000, 1000000]` to handle negative patient values.

### Cryptography & Speed Libraries
- **`mcl_backend.py`**: The C++ wrapper for `mclbn256`. Intercepts all `pymife` Python math and redirects it to C++, yielding a 500x speedup. Also contains `fast_feddh_generate()`, the raw integer matrix-inversion bypass.
- **`delegated_crypto.py`**: Implements $g_1^B$ delegated encryption so the Clinic can encrypt vectors without the Hospital having to stay online or hand over the master secret.
- **`fhipe_serializer.py`**: Handles base64 byte-array serialization for `mclbn256` objects, allowing complex cryptographic points to be transmitted as JSON payloads.
- **`parallel_eval.py`**: A multiprocessing script that bypasses Python's GIL using `os.fork()` to evaluate multiple clinical buckets simultaneously.

### Data & Machine Learning Files
- **`master_33_cancer_weights.npy`**: The massive $(33 \times 20531)$ matrix containing the L1-regularized Lasso weights for all 33 cancer types.
- **`patient1_full.npy`**: A fast-loading numpy array containing the exact 20,531 gene expression values for TCGA Patient 1.
- **`extract_patient.py`**: A utility script used to extract `patient1_full.npy` from the massive 1.1GB Xena TSV file.
- **`make_gene_list.py` / `check1_gene_union.py`**: Utility scripts to calculate union statistics (e.g., finding the 3,555 global active genes) across all 33 models.

---

## 4. Important Code Snippets (How Things Work)

### Dynamic Feature Subsetting (Hospital)
Instead of forcing the Clinic to encrypt 20,000 genes, the Hospital dynamically isolates the active ones:
```python
# hospital.py
active_indices = np.flatnonzero(selected_model_weights != 0)
FEASIBLE_DIM = len(active_indices)
trimmed_weights = selected_model_weights[active_indices]

@app.route('/get_active_indices', methods=['GET'])
def get_active_indices():
    return jsonify({"active_indices": active_indices.tolist()})
```

### Dynamic Encryption (Clinic)
The Clinic uses the indices to perfectly subset the patient's data, ensuring $100\%$ model accuracy while drastically reducing encryption time:
```python
# clinic.py
indices_resp = requests.get('http://127.0.0.1:5001/get_active_indices').json()
active_indices = indices_resp['active_indices']

patient_full_vector = np.load('patient1_full.npy')
raw_patient_vector = patient_full_vector[active_indices] # Precisely the 139 genes needed
```

---

## 5. What's Left Out (Roadmap Features Not Yet Built)

While the mathematical baseline works perfectly, we have **not** implemented the primary privacy controls from our Roadmap. Currently, the architecture leaks the cancer type being queried and the final patient diagnosis to the Cloud.

Here is what remains to be built:

### 1. Query Privacy via Bucketing / Padding (Roadmap §5.4a)
- **The Flaw:** Because `clinic.py` dynamically requests exactly 139 genes, the Cloud can deduce that the Clinic is evaluating the Adrenocortical Carcinoma (ACC) model, destroying query privacy.
- **The Fix:** We must implement a shared `FEASIBLE_DIM` across all models (e.g., padding all queries to $N=300$ or using the global $N=3555$ union). The Clinic will pad patient queries with zero-values, and the Hospital will pad weights with zero-weights, ensuring the Cloud cannot identify the cancer based on vector size.

### 2. Result Privacy via $\rho$ Blinding (Roadmap §5.4b / Design A)
- **The Flaw:** `cloud.py` learns the exact mathematical risk score (`190984`). It should never learn the diagnosis.
- **The Fix:** The Hospital must inject a random blinding noise ($\rho$) into the model setup. The Cloud will decrypt `Score + ρ`, rendering the result useless to the server. The Clinic will receive `Score + ρ` and locally subtract $\rho$ to reveal the true risk.

### 3. Pathway Explainable AI (XAI) (Roadmap §6)
- **The Feature:** Clinicians need explanations (SHAP values). Providing per-gene explanations leaks the exact model weights over multiple queries.
- **The Fix:** We need to implement MSigDB Hallmark aggregation, grouping genes into 50 functional biological pathways (e.g., DNA Repair). The Cloud will evaluate one key per pathway rather than the global model, protecting the weights via rank deficiency.

### 4. Cryptographic Result Integrity / Audit Logs (Roadmap §5.5)
- **The Flaw:** A malicious Cloud can return random numbers, and the Doctor has no way to verify if the math was correct.
- **The Fix:** Implement linear auditing (submitting decoy queries) and hash-chained verifiable audit logs to guarantee the Cloud is honestly executing the pairings.

### 5. ML Pipeline Data Imputation (Roadmap §4.1)
- **The Flaw:** The original `Capstone_Final.ipynb` ML training script filled missing genes with `0`. In standardized RNA-seq data, a raw `0` becomes a massive negative Z-score, injecting a "fake signal" of severe suppression into the model.
- **The Fix:** The ML script must be updated to impute missing genes using `scaler.mean_` instead, ensuring missing data evaluates to exactly `0` after standardization, neutralizing its impact on the dot product.
