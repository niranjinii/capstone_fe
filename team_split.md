# Team Task Split: 1-Week Sprint (4 Members)

## Scope

**Included:** All crypto, security, architecture, XAI, and benchmark tasks from `remaining_work.md`.
**Excluded:** ML retraining (#8, #10), multi-model end-to-end demo (#15). These are on hold.
**Already done:** Weight sign bug (#20), truncation bug (#9).

---

## Member A — Result Privacy & Perturbation Analysis

*Areas: Cryptography, Security, Benchmarking*

### Day 1–2: Implement a Baby-Step Giant-Step (BSGS) Discrete-Log Solver
**remaining_work.md Item #1 (prerequisite)**

The Cloud's `FeDDH.decrypt()` in PyMIFE uses a linear brute-force scan to find the discrete log. This works at small ranges (`(-1000000, 1000000)`) but will be too slow once ρ blinding expands the search space.

**What to do:**
1. Create a new file `bsgs.py` in the project root.
2. Implement the BSGS algorithm:
   - Given a target element `T` in group GT and a generator `g`, find integer `x` such that `g^x = T`, where `x` is in range `[lo, hi]`.
   - **Baby step:** Precompute a lookup table of `g^j` for `j = 0, 1, ..., m-1` where `m = ceil(sqrt(hi - lo))`. Store as a Python `dict` mapping the serialised GT element → `j`.
   - **Giant step:** Compute `g^(-m)`. Then iterate: check if `T * (g^(-m))^i` is in the lookup table. If yes, `x = lo + i*m + j`.
   - Time complexity: `O(sqrt(N))` instead of `O(N)`. For a range of 2 billion, this is ~45,000 steps instead of 2 billion.
3. **GT group specifics for mclbn256:**
   - "Addition" in GT = field multiplication (`a * b` in Python)
   - "Scalar multiplication" in GT = exponentiation (`a ** fr` in Python)
   - Use `mclbn256.GT.serialize()` as the dict key (it returns a bytes object)
4. Expose a function: `def bsgs_discrete_log(target_gt, generator_gt, lo, hi) -> int`
5. **Test:** Compute `g^12345` manually, then call `bsgs_discrete_log(g^12345, g, 0, 100000)` and verify it returns `12345`.
6. **Integrate into `cloud.py`:** Replace the `FeDDH.decrypt(ct, pub, sk, (-1000000, 1000000))` call. You'll need to either monkey-patch PyMIFE's decrypt or write a thin wrapper that does the pairing step manually and then calls your BSGS solver.

**Libraries:** `mclbn256` (already installed), `math.isqrt` (stdlib).

---

### Day 3–4: Implement ρ Blinding (Design A Result Privacy)
**remaining_work.md Item #1**

The Cloud currently sees the raw risk score. With ρ blinding, it sees `<x, y> + ρ` which is meaningless without knowing ρ.

**What to do in `hospital.py`:**
1. After quantising the weight vector, generate a random blinding factor:
   ```python
   import secrets
   rho = secrets.randbelow(500000) - 250000  # random integer in [-250000, 250000]
   ```
2. Extend the weight vector by appending ρ:
   ```python
   blinded_weights = quantized_weights + [rho]  # dimension becomes n+1
   ```
3. Generate FeDDH keys for dimension `n+1` (not `n`).
4. Create a new endpoint `/get_rho` that returns ρ to the Clinic via a **sealed channel** (use the same NaCl SealedBox pattern used for the functional key — seal ρ with the Clinic's public key so only the Clinic can read it). This means the Clinic also needs an X25519 keypair.

**What to do in `clinic.py`:**
1. Generate a Clinic-side X25519 keypair using `nacl.public.PrivateKey.generate()`.
2. Extend the patient vector by appending `1`:
   ```python
   blinded_patient = quantized_patient_vector + [1]  # [x1, x2, ..., xn, 1]
   ```
3. Encrypt the `n+1` dimensional vector (not `n`).
4. After receiving the Cloud's result (which is `<x, y> + ρ·1 = <x,y> + ρ`), fetch ρ from Hospital, unseal it, and subtract:
   ```python
   true_score = cloud_result - rho
   ```

**What to do in `cloud.py`:**
- Replace the old linear decrypt with your BSGS solver from Days 1-2.
- Update the search bounds to accommodate the ρ range.

**Libraries:** `nacl` / `PyNaCl` (already installed), `secrets` (stdlib).

---

### Day 5: Combine ρ Blinding with Gaussian Perturbation
**remaining_work.md Item #4**

Instead of drawing ρ uniformly, draw it from a Gaussian distribution. This gives you perturbation (noise that slows extraction) AND result privacy (Cloud can't see the true score) in one mechanism.

**What to do:**
1. In `hospital.py`, replace the uniform ρ with:
   ```python
   import numpy as np
   sigma = 1000  # noise scale — tunable parameter
   rho = int(np.random.normal(0, sigma))
   ```
2. The rest of the pipeline stays exactly the same as Day 3-4.
3. Document the sigma parameter and its trade-off: higher sigma = more extraction resistance but slightly less accurate scores. The exact numbers come from `patients_until_recovery.py`.

---

### Day 6: Run Benchmark Scripts on Real Weights
**remaining_work.md Items #12, #16**

These are quick script runs to produce paper-ready tables and figures. No code changes needed.

1. **Perturbation analysis (Item #12):**
   ```bash
   # Run on 5-6 representative models spanning the dimension range
   python3 patients_until_recovery.py --weights master_33_cancer_weights.npy --model 0   # ACC (n=139)
   python3 patients_until_recovery.py --weights master_33_cancer_weights.npy --model 3   # BRCA (n=252)
   python3 patients_until_recovery.py --weights master_33_cancer_weights.npy --model 6   # smallest dim
   python3 patients_until_recovery.py --weights master_33_cancer_weights.npy --model 11  # mid-range
   python3 patients_until_recovery.py --weights master_33_cancer_weights.npy --model 24  # large
   ```
   Save each `.png` output. These are Figure 4 in the paper outline.

2. **Quantisation check (Item #16):**
   ```bash
   python3 quantization_check.py --weights master_33_cancer_weights.npy --models 33
   ```
   Copy-paste the terminal output into a text file for the paper.

### Day 7: Buffer / Testing

---

## Member B — Query Privacy & System Architecture

*Areas: Architecture, Cryptography, Benchmarking*

### Day 1: Make Model Selection Configurable + Run Gene Union Check
**NEW task (not in remaining_work.md) + remaining_work.md Item #2 prerequisite**

Right now `hospital.py` line 19 is hardcoded to `raw_weights_data[0]` (always loads ACC, the first cancer model). The Clinic/Doctor should be able to choose which cancer model to query.

**What to do for configurable model selection:**
1. In `hospital.py`, add a `MODEL_INDEX` variable at the top (or read from an environment variable / command-line argument):
   ```python
   import argparse
   parser = argparse.ArgumentParser()
   parser.add_argument('--model', type=int, default=0, help='Cancer model index (0-32)')
   args = parser.parse_args()
   MODEL_INDEX = args.model
   ```
2. Replace `raw_weights_data[0]` with `raw_weights_data[MODEL_INDEX]`.
3. Add a `/get_model_info` endpoint that returns the model index, dimension, and (if available) the cancer type name.
4. This also opens the door for a future UI where the doctor picks from a dropdown of available cancer types.

**What to do for gene union check:**
1. Run:
   ```bash
   python3 check1_gene_union.py master_33_cancer_weights.npy
   ```
2. Save the output — it tells you the exact per-cancer gene counts, global union size, and which branch of the FHIPE feasibility decision tree you land in.
3. Use the per-cancer counts to design the clinical bucket groupings for Days 2-3. Group cancers by similar dimension (e.g., all cancers with 100-200 active genes in one bucket, 200-300 in another).

---

### Day 2–3: Implement Query Privacy via Intermediate Bucketing
**remaining_work.md Item #2**

The Cloud can currently identify which cancer model is being queried just from the dimension of the encrypted vector (139 = ACC, 252 = BRCA, etc.). Bucketing pads all vectors within a clinical group to the same dimension, hiding the specific model.

**What to do:**
1. Create a `bucket_config.py` file that defines the bucket groupings:
   ```python
   # Example — actual groupings depend on check1_gene_union.py output
   BUCKETS = {
       'small': {'max_dim': 150, 'cancers': ['GBM', 'DLBC', ...]},
       'medium': {'max_dim': 300, 'cancers': ['ACC', 'KICH', ...]},
       'large': {'max_dim': 500, 'cancers': ['BRCA', 'SKCM', ...]},
   }
   ```
2. In `hospital.py`: After quantising the weight vector, pad it with zeros to the bucket's `max_dim`:
   ```python
   bucket_dim = BUCKETS[current_bucket]['max_dim']
   padded_weights = quantized_weights + [1] * (bucket_dim - len(quantized_weights))
   # Using 1 instead of 0 to avoid the PyMIFE k2=None bug on zero weights
   ```
3. In `clinic.py`: Pad the patient vector with zeros to match the bucket dimension:
   ```python
   padded_patient = quantized_patient_vector + [0] * (bucket_dim - len(quantized_patient_vector))
   ```
   The zeros ensure the padded positions contribute nothing to the dot product: `0 * w_pad = 0`.
4. Generate FeDDH keys at the bucket dimension, not the model dimension.
5. **Test:** Verify that the padded dot product equals the unpadded dot product (the padding should be mathematically neutral).

---

### Day 4–5: Wire Parallel Evaluation into the Live Flask Architecture
**remaining_work.md Item #17**

`parallel_eval.py` proves that `multiprocessing.Pool` with `fork()` can evaluate multiple buckets in parallel. But it's a standalone script, not integrated into the Flask demo. If a patient needs to be evaluated against multiple models/buckets, the Cloud needs parallel decryption.

**What to do in `cloud.py`:**
1. Add a new `/evaluate_batch` endpoint that accepts a list of `(ciphertext, functional_key)` pairs:
   ```python
   @app.route('/evaluate_batch', methods=['POST'])
   def evaluate_batch():
       items = request.json['evaluations']  # list of {ciphertext, functional_key}
       # Use concurrent.futures for thread-safe parallel execution
       from concurrent.futures import ProcessPoolExecutor
       with ProcessPoolExecutor(max_workers=len(items)) as pool:
           results = list(pool.map(decrypt_single, items))
       return jsonify({"results": results})
   ```
2. Extract the current `/evaluate` logic into a standalone `decrypt_single(item)` function.
3. **Important:** On Linux, use `multiprocessing.set_start_method('fork')` before creating the pool. On Python 3.14+, the default changed to `forkserver` which loses globals. Use `concurrent.futures.ProcessPoolExecutor` with an initializer if needed.

**What to do in `clinic.py`:**
1. Add a function that constructs a batch payload when querying multiple buckets and POSTs to `/evaluate_batch`.
2. The existing single-query flow (`/evaluate`) should still work for single-model queries.

**Libraries:** `concurrent.futures` (stdlib), `multiprocessing` (stdlib).

---

### Day 6: Extend Benchmark to Multiple Dimensions + Run Extraction Attack
**remaining_work.md Items #14, #11**

1. **Extend `benchmark.py` (Item #14):**
   - Currently only benchmarks at `n=20`. Modify to loop over `n = 20, 50, 100, 139, 200, 300, 500`.
   - Record: keygen time, encrypt time, decrypt time, and serialised ciphertext size at each dimension.
   - Output a CSV or table that can go directly into the paper.
   - If matplotlib is available, generate a line plot (Figure 5 in the paper outline).

2. **Run extraction attack (Item #11):**
   ```bash
   python3 extraction_attack.py --weights master_33_cancer_weights.npy --models 33
   ```
   Save the output table. This produces Table 4 in the paper outline.

### Day 7: Buffer / Testing

---

## Member C — Security Hardening

*Areas: Security, Infrastructure, Cryptography*

### Day 1: Implement Query Budget and Rate Limiting
**remaining_work.md Item #5**

After `n` queries for a given model, the Doctor can fully extract the model weights via Attack B. The Hospital must track and limit key issuances.

**What to do in `hospital.py`:**
1. Create an in-memory rate limiter (a dictionary tracking issuances):
   ```python
   from collections import defaultdict
   import time

   key_issuance_log = defaultdict(list)  # model_index -> list of timestamps
   MAX_KEYS_PER_MODEL = None  # set dynamically to n // 2

   def check_rate_limit(model_index, dimension):
       max_allowed = dimension // 2  # half the dimension = safety margin
       history = key_issuance_log[model_index]
       if len(history) >= max_allowed:
           return False, f"Rate limit reached: {len(history)}/{max_allowed} keys issued for model {model_index}"
       return True, "OK"
   ```
2. In the `/get_key` endpoint, call `check_rate_limit()` before generating a new functional key. Return HTTP 429 (Too Many Requests) if the limit is hit.
3. Log every key issuance with:
   - Timestamp
   - Model index
   - Requester IP (from `request.remote_addr`)
   - Current count vs limit
4. Add a `/query_log` endpoint (admin-only) that returns the full issuance history.
5. Add a warning threshold: when issuances reach 75% of the limit, print a console warning.

---

### Day 2: Implement Ciphertext Replay Attack Prevention
**remaining_work.md Item #19**

Nothing currently prevents the Cloud from saving an old ciphertext and replaying it against a different functional key, or vice versa.

**What to do:**
1. In `clinic.py`, generate a unique query ID for each request:
   ```python
   import uuid
   import time

   query_id = str(uuid.uuid4())
   query_timestamp = int(time.time())
   ```
2. Include `query_id` and `timestamp` in the JSON payload sent to the Cloud:
   ```python
   payload = {
       "ciphertext": json_ct,
       "functional_key": json_sk,
       "query_id": query_id,
       "timestamp": query_timestamp
   }
   ```
3. In `cloud.py`, add validation:
   ```python
   seen_queries = set()
   MAX_AGE_SECONDS = 300  # reject payloads older than 5 minutes

   def validate_query(data):
       qid = data.get('query_id')
       ts = data.get('timestamp', 0)
       if qid in seen_queries:
           return False, "Duplicate query ID — possible replay attack"
       if abs(time.time() - ts) > MAX_AGE_SECONDS:
           return False, "Query timestamp too old — possible replay attack"
       seen_queries.add(qid)
       return True, "OK"
   ```
4. Return HTTP 403 if validation fails.

**Libraries:** `uuid` (stdlib), `time` (stdlib).

---

### Day 3: Implement Delegated Encryption Key (ek) Rotation
**remaining_work.md Item #18**

The delegated encryption key `ek` is sent once to the Clinic and reused forever. If the Clinic is compromised, the attacker has permanent encryption capability.

**What to do in `hospital.py`:**
1. Add an `/rotate_keys` endpoint:
   ```python
   @app.route('/rotate_keys', methods=['POST'])
   def rotate_keys():
       global master_key, ek, quantized_weights, WEIGHT_SHIFT
       # Re-run the full key generation with a fresh random matrix B
       master_key = fast_feddh_generate(DIMENSION, F=MclPairing())
       ek = generate_ek(master_key)
       # Re-generate the functional key on next /get_key request
       return jsonify({"status": "rotated", "new_dimension": DIMENSION})
   ```
2. Add a key generation counter and timestamp:
   ```python
   key_generation_epoch = 0
   key_created_at = time.time()
   ```
3. In the `/get_ek` response, include the epoch number so the Clinic can detect stale keys.
4. Document the key lifetime policy in a comment: recommended rotation after every `n/4` queries or every 24 hours, whichever comes first.

---

### Day 4–6: Implement Transport Security (mTLS + Payload Signing)
**remaining_work.md Item #7**

All three Flask endpoints currently use plain `http://127.0.0.1` with zero authentication.

**Step 1: Create a self-signed Certificate Authority (Day 4)**
1. Use the `cryptography` Python library (install via `pip install cryptography`):
   ```python
   from cryptography import x509
   from cryptography.x509.oid import NameOID
   from cryptography.hazmat.primitives import hashes, serialization
   from cryptography.hazmat.primitives.asymmetric import rsa
   ```
2. Generate a root CA key + certificate.
3. Generate individual certificates for Hospital, Clinic, and Cloud, signed by the CA.
4. Save as PEM files: `ca.pem`, `hospital.pem`, `hospital-key.pem`, `clinic.pem`, `clinic-key.pem`, `cloud.pem`, `cloud-key.pem`.
5. Create a helper script `generate_certs.py` that automates this.

**Step 2: Enable HTTPS with mTLS on Flask (Day 5)**
1. In each Flask app (`hospital.py`, `cloud.py`), add SSL context:
   ```python
   import ssl
   context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
   context.load_cert_chain('hospital.pem', 'hospital-key.pem')
   context.load_verify_locations('ca.pem')
   context.verify_mode = ssl.CERT_REQUIRED  # mTLS: client must present a cert
   app.run(port=5001, ssl_context=context)
   ```
2. In `clinic.py`, update all `requests.get/post` calls to use client certificates:
   ```python
   requests.get('https://127.0.0.1:5001/get_dimension',
                cert=('clinic.pem', 'clinic-key.pem'),
                verify='ca.pem')
   ```

**Step 3: Implement Ed25519 Payload Signing (Day 6)**
1. Use `nacl.signing` (PyNaCl, already installed):
   ```python
   from nacl.signing import SigningKey, VerifyKey
   signing_key = SigningKey.generate()
   verify_key = signing_key.verify_key
   ```
2. Before sending a JSON payload, sign it:
   ```python
   import json
   payload_bytes = json.dumps(payload, sort_keys=True).encode()
   signed = signing_key.sign(payload_bytes)
   # Send signature alongside the payload
   ```
3. On the receiving end, verify:
   ```python
   verify_key.verify(signed)  # raises BadSignatureError if tampered
   ```
4. Exchange verify keys during the initial handshake (each party exposes a `/signing_key` endpoint).

**Libraries:** `cryptography` (pip install), `nacl.signing` (already installed via PyNaCl), `ssl` (stdlib).

### Day 7: Buffer / Testing

---

## Member D — Explainable AI & Audit Verification

*Areas: XAI, Cryptography, Security*

### Day 1: Run Pathway Rank Check and Study Hallmark Gene Sets
**remaining_work.md Item #13 + Item #3 prerequisite**

The MSigDB Hallmark gene set file (`h.all.v2026.1.Hs.symbols.gmt`) is already in the repo. You need to verify that pathway aggregation actually provides privacy (the incidence matrix must be rank-deficient).

**What to do:**
1. Run:
   ```bash
   python3 check2_pathway_rank.py h.all.v2026.1.Hs.symbols.gmt genes_cancer2.txt
   ```
   Save the output. It will tell you:
   - Number of active genes
   - Number of pathways with at least 1 gene overlap
   - Matrix rank
   - Number of free unknowns (this must be >> 0 for privacy to hold)

2. Study the GMT file format — each line is:
   ```
   PATHWAY_NAME<tab>URL<tab>GENE1<tab>GENE2<tab>...
   ```
   You need to understand how gene symbols in the GMT map to indices in the weight matrix.

3. **Important:** `genes_cancer2.txt` is generated by `make_gene_list.py` from the current weight matrix. If you're unsure whether it's up to date, regenerate it:
   ```bash
   python3 make_gene_list.py
   ```

---

### Day 2–3: Build the Pathway Aggregation Module
**remaining_work.md Item #3**

Create a new file `pathway_xai.py` that handles pathway-level explanations.

**What to do:**
1. **Load and parse the GMT file:**
   ```python
   def load_hallmark_pathways(gmt_path):
       pathways = {}
       with open(gmt_path) as f:
           for line in f:
               parts = line.strip().split('\t')
               name = parts[0]
               genes = set(parts[2:])  # skip the URL field
               pathways[name] = genes
       return pathways
   ```

2. **Build pathway weight sub-vectors:**
   For each of the 50 pathways, create a weight vector where:
   - Genes IN the pathway keep their original weight
   - Genes NOT in the pathway are set to 0
   
   ```python
   def build_pathway_vectors(pathways, active_gene_names, full_weight_vector):
       """Returns a dict: pathway_name -> weight sub-vector of length n"""
       pathway_vectors = {}
       for name, gene_set in pathways.items():
           sub_vec = []
           for i, gene in enumerate(active_gene_names):
               if gene in gene_set:
                   sub_vec.append(full_weight_vector[i])
               else:
                   sub_vec.append(0)
           if any(v != 0 for v in sub_vec):  # only include pathways with overlap
               pathway_vectors[name] = sub_vec
       return pathway_vectors
   ```

3. **Generate one functional key per pathway:**
   Each pathway sub-vector gets its own `FeDDH.keygen()` call using the same master key. The Hospital sends 50 sealed functional keys (one per pathway) instead of 1.

4. **Test locally:** For each pathway, verify that `<x, pathway_weights>` equals the sum of `w_i * x_i` for genes in that pathway. This is a pure math check.

---

### Day 4–5: Integrate Pathway Evaluation into the Live Demo
**remaining_work.md Item #3 (continued)**

**What to do in `hospital.py`:**
1. Add a `/get_pathway_keys` endpoint that:
   - Loads the GMT file
   - Builds pathway weight sub-vectors
   - Generates a functional key for each pathway (50 keys)
   - Seals each key with the Cloud's public key
   - Returns a JSON object: `{pathway_name: sealed_functional_key, ...}`

**What to do in `clinic.py`:**
1. After getting the overall risk score, optionally call `/get_pathway_keys`.
2. Send all 50 pathway keys + the same ciphertext to the Cloud.
3. Display the pathway-level breakdown to the doctor:
   ```
   Top contributing pathways:
     HALLMARK_APOPTOSIS:           +4,200 (32% of total)
     HALLMARK_P53_PATHWAY:         +2,100 (16% of total)
     HALLMARK_MYC_TARGETS_V1:      -1,800 (-14% of total)
     ...
   ```

**What to do in `cloud.py`:**
1. Add a `/evaluate_pathways` endpoint that accepts the ciphertext + a dict of pathway functional keys.
2. Decrypt each pathway key against the same ciphertext, returning a dict of pathway scores.
3. This can reuse the BSGS solver from Member A (if available by Day 4), or use the existing linear brute-force with smaller bounds (pathway scores are smaller than full scores).

---

### Day 6: Implement Audit Logging and Decoy Verification
**remaining_work.md Item #6**

A malicious Cloud could fabricate scores. The Hospital needs a way to verify the Cloud is computing honestly.

**What to do:**

1. **Hash-chained audit log in `cloud.py`:**
   ```python
   import hashlib
   import json
   
   audit_chain = []  # list of {query_id, timestamp, input_hash, result, prev_hash}
   
   def log_evaluation(query_id, ct_hash, result):
       prev_hash = audit_chain[-1]['chain_hash'] if audit_chain else '0' * 64
       entry = {
           'query_id': query_id,
           'timestamp': time.time(),
           'ciphertext_hash': ct_hash,
           'result': result,
           'prev_hash': prev_hash,
       }
       entry['chain_hash'] = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
       audit_chain.append(entry)
   ```
   Call `log_evaluation()` after every `/evaluate` call.

2. **Expose the audit log:**
   ```python
   @app.route('/audit_log', methods=['GET'])
   def get_audit_log():
       return jsonify({"log": audit_chain})
   ```

3. **Decoy query verification in `hospital.py`:**
   - The Hospital periodically generates a known-answer test: encrypt a patient vector for which it knows the correct dot product, send it to the Cloud, and check if the returned score matches.
   - Add a `/verify_cloud` endpoint that:
     1. Creates a random test vector
     2. Computes the expected dot product locally
     3. Encrypts and sends to Cloud
     4. Compares Cloud's answer to the expected value
     5. Returns `{"verified": true/false}`

**Libraries:** `hashlib` (stdlib), `json` (stdlib).

### Day 7: Buffer / Testing

---

## Coverage Checklist

Every item from `remaining_work.md` is accounted for:

| Item | Description | Assigned To | Day |
|---|---|---|---|
| #1 | ρ blinding + BSGS | Member A | 1–4 |
| #2 | Bucketing (intermediate) | Member B | 2–3 |
| #3 | Pathway XAI | Member D | 1–5 |
| #4 | Perturbation in live demo | Member A | 5 |
| #5 | Query budget / rate limit | Member C | 1 |
| #6 | Audit logs | Member D | 6 |
| #7 | Transport security (mTLS + Ed25519) | Member C | 4–6 |
| #11 | Run extraction attack | Member B | 6 |
| #12 | Run perturbation analysis | Member A | 6 |
| #13 | Run pathway rank check | Member D | 1 |
| #14 | Extend benchmark.py | Member B | 6 |
| #16 | Run quantisation check | Member A | 6 |
| #17 | Parallel eval integration | Member B | 4–5 |
| #18 | ek rotation | Member C | 3 |
| #19 | Replay attack prevention | Member C | 2 |
| NEW | Configurable model selection | Member B | 1 |

**Excluded (on hold):** #8 (imputation bug), #10 (separate Q_w/Q_x), #15 (multi-model demo).
**Already done:** #9 (truncation bug ✅), #20 (weight sign bug ✅).

---

## Workload Balance

| Member | Coding Days | Script-Run Days | Buffer |
|---|---|---|---|
| A | 5 | 0.5 | 1.5 |
| B | 5 | 0.5 | 1.5 |
| C | 6 | 0 | 1 |
| D | 5.5 | 0.5 | 1 |
