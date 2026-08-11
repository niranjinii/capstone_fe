# Complete Remaining Work: Roadmap vs Current State

Everything that's been discussed in the roadmap but **not yet implemented** in the live 3-party demo (`hospital.py` / `clinic.py` / `cloud.py`). Cross-referenced against the actual codebase.

---

## Status Legend
- ✅ **Done** — fully implemented and tested in the live demo
- 🔬 **Script exists, not integrated** — standalone script works, but not wired into the 3-party architecture
- ❌ **Not started** — no code exists yet

---

## Category 1: Core Privacy Features (The Big Three)

These are the primary security mechanisms from the roadmap that the current demo is missing. Without these, the system has known privacy leaks.

### 1. Result Privacy via $\rho$ Blinding (Design A) ❌
**Roadmap: §5.4b, §0.5 (Design A)**

The Cloud currently sees the raw risk score (`190984`). It should see random noise.

**What needs to happen:**
- `hospital.py`: Generate random $\rho$, extend the weight vector to $[y, \rho]$ (dimension $n+1$), generate FeDDH keys for the extended vector
- `clinic.py`: Extend the patient vector to $[x, 1]$ (so the dot product becomes $\langle x, y \rangle + \rho \cdot 1$). Receive $\rho$ from Hospital via a sealed channel. After getting the Cloud's response, subtract $\rho$ locally.
- `cloud.py`: No changes needed — it just computes the blinded result. But the discrete-log search range expands from $S$ to $R = 2^k \cdot S$, so decryption is slower.

**Estimated effort:** 1–2 days

---

### 2. Query Privacy via Bucketing / Padding ❌
**Roadmap: §5.4a, §3 (Choice 3)**

The Cloud can identify the cancer model from the vector dimension alone (139 = ACC, 252 = BRCA, 28 = GBM, etc.).

**What needs to happen:**
- Decide on a padding strategy:
  - **Option A:** Pad all vectors to the global union dimension ($n = 3,555$) — maximum privacy, but very expensive encryption
  - **Option B:** Group the 33 cancers into ~10 clinical families (e.g., Gastrointestinal, Gynecological) and pad to a per-family bucket dimension ($n \approx 300$–$500$) — practical middle ground
- `hospital.py`: Pad weight vector with zeros to the agreed dimension. Generate keys at the bucket dimension, not the model dimension.
- `clinic.py`: Pad patient vector with zeros to match. Encrypt at the bucket dimension.
- Need to define the actual clinical bucket groupings (which cancers go together)

**Estimated effort:** 2–3 days (including deciding the bucket groupings)

---

### 3. Pathway XAI (Explainable AI via Hallmark Aggregation) ❌
**Roadmap: §6**

Clinicians need to understand *why* the model gave a particular score. But per-gene explanations ($w_i \cdot x_i$) leak the model weights in $n$ queries.

**What exists:**
- `check2_pathway_rank.py` — proves the $50 \times 3555$ incidence matrix is rank-deficient (rank 50, 3505 free unknowns). This is the *analysis* script.
- `h.all.v2026.1.Hs.symbols.gmt` — the MSigDB Hallmark gene set file is already in the repo.

**What needs to happen:**
- Build a pathway aggregation module that computes $\text{Pathway}_k = \sum_{i \in \text{pathway}_k} w_i \cdot x_i$ for each of the 50 pathways
- The Hospital needs to generate one functional key *per pathway* (50 keys instead of 1 global key)
- The Cloud evaluates each pathway key against the same ciphertext, returning 50 pathway scores
- The Clinic receives and displays pathway-level explanations

**Estimated effort:** 3–5 days

---

## Category 2: Security Mechanisms

### 4. Perturbation (Additive Noise on Returned Scores) ❌
**Roadmap: §0.1, §7**

**What exists:**
- `patients_until_recovery.py` — the *analysis* script that calculates how much noise you need and what accuracy it costs. This is the "central figure" script.

**What needs to happen:**
- Actually *implement* the perturbation in the live demo. Either:
  - The Hospital adds Gaussian noise to the functional key construction (harder, changes the math)
  - The Cloud adds noise to the returned score before sending it back (simpler, but requires trusting the Cloud to actually add noise — which defeats the purpose)
  - Design A ($\rho$ blinding) with a *random* $\rho$ drawn from $\mathcal{N}(0, \sigma^2)$ instead of uniform — this combines result privacy with perturbation naturally
- Run `patients_until_recovery.py` on all 33 real models (not just synthetic data) and generate the actual paper figure

**Estimated effort:** 1 day (if combined with $\rho$ blinding)

---

### 5. Query Budget / Rate Limiting ❌
**Roadmap: §2.8, §4**

The Doctor can currently make unlimited queries. After $n$ queries, extraction is possible.

**What needs to happen:**
- `hospital.py`: Track how many functional keys have been issued per model
- Enforce a configurable rate limit (e.g., max $n/2$ queries per time window)
- Log every key issuance with timestamp, requester identity, and model ID
- Alert when approaching the extraction threshold

**Estimated effort:** Half a day

---

### 6. Audit Logging / Verifiable Computation ❌
**Roadmap: §5.5**

A malicious Cloud could return fabricated scores.

**What needs to happen:**
- Decoy queries: the Hospital periodically submits known-answer patient vectors and checks if the Cloud returns the correct score
- Hash-chained audit log: every query gets a hash commitment that can be verified later
- Signed computation anchors on the Cloud side

**Estimated effort:** 2–3 days

---

### 7. Transport Security ❌
**Roadmap: §3 (Security Hardening)**

All three Flask endpoints currently use plain `http://127.0.0.1` with zero authentication.

**What needs to happen:**
- **Mutual TLS (mTLS):** Upgrade Flask to HTTPS with client certificates. The Clinic must present a valid certificate to connect.
- **Ed25519 Payload Signing:** Every JSON payload is cryptographically signed so the receiver can verify authenticity and integrity.
- **Certificate Authority:** Create a local CA for the demo (self-signed is fine for the paper).

**Estimated effort:** 2–3 days

---

## Category 3: ML Pipeline Fixes

### 8. Missing-Gene Imputation Bug Fix ❌
**Roadmap: §4.1 (Bug 2)**

**What exists:**
- `quantization_check.py` — script that *demonstrates* the bug and prints the fix. Not applied to actual training.

**What needs to happen:**
- Update `Capstone_Final.ipynb` (or equivalent training script) to replace `reindex(fill_value=0)` with `fillna(pd.Series(scaler.mean_, index=scaler.feature_names_in_))`
- Retrain the 33 models with the corrected imputation
- Regenerate `master_33_cancer_weights.npy`
- Re-run the full demo to verify scores change (they should, slightly)

**Estimated effort:** 1 day (mostly waiting for training)

---

### 9. Truncation Bug Fix ❌
**Roadmap: §4.1 (Bug 1)**

**What exists:**
- `quantization_check.py` — demonstrates the bug. Our *demo code* (`hospital.py`, `clinic.py`) already uses `np.rint().astype(int64)`, but the *training pipeline* may still use the buggy `.astype(int)`.

**What needs to happen:**
- Audit `Capstone_Final.ipynb` to ensure the training pipeline uses `np.rint` everywhere
- Verify no weights are silently deleted during quantisation

**Estimated effort:** 1–2 hours

---

### 10. Separate Quantisation Factors ($Q_w \neq Q_x$) ❌
**Roadmap: §4.1 (Bug 3 from `quantization_check.py`)**

Currently both weights and patient features use $Q = 100$. But weights and features have very different distributions.

**What needs to happen:**
- Choose $Q_w$ and $Q_x$ separately based on each distribution's range
- The returned score is divided by $Q_w \times Q_x$ (not $Q^2$)
- Measure the quantisation error at different $Q_w$, $Q_x$ combinations

**Estimated effort:** Half a day

---

## Category 4: Benchmarks and Experiments Needed for the Paper

### 11. Run Extraction Attacks on Real Weights 🔬
**Roadmap: §5.1, §0.1**

**What exists:**
- `extraction_attack.py` — works on synthetic data by default. Has a `--weights` flag for real data.

**What needs to happen:**
- Run `python3 extraction_attack.py --weights master_33_cancer_weights.npy --models 33` and capture the full output table for the paper
- This produces Table 4 in the paper outline

**Estimated effort:** 10 minutes

---

### 12. Run Perturbation Analysis on Real Weights 🔬
**Roadmap: §0.1**

**What exists:**
- `patients_until_recovery.py` — works on synthetic data by default. Has `--weights` and `--model` flags.

**What needs to happen:**
- Run on all 33 real models (or at least 5–6 representative ones)
- Generate `patients_until_recovery.png` for each — this is THE central figure of the paper

**Estimated effort:** 1 hour

---

### 13. Run Pathway Rank Check on Real Gene List 🔬
**Roadmap: §6.1**

**What exists:**
- `check2_pathway_rank.py` — needs a GMT file and a gene list file as arguments
- `h.all.v2026.1.Hs.symbols.gmt` — already in repo
- `genes_cancer2.txt` — already in repo

**What needs to happen:**
- Run `python3 check2_pathway_rank.py h.all.v2026.1.Hs.symbols.gmt genes_cancer2.txt` and capture the output
- This produces Table 14 in the paper outline

**Estimated effort:** 5 minutes

---

### 14. Backend Benchmark at Multiple Dimensions 🔬
**Roadmap: §6 (Performance Benchmarking)**

**What exists:**
- `benchmark.py` — compares py_ecc vs mclbn256 at $n=20$ only

**What needs to happen:**
- Extend to run at $n = 20, 50, 100, 139, 200, 300, 500$
- Record encrypt time, decrypt time, keygen time at each
- Generate the scalability plot (Figure 5 in the paper outline)

**Estimated effort:** Half a day

---

### 15. Multi-Model End-to-End Demo ❌
**Not in roadmap, but critical for paper**

Currently only ACC ($n=139$) has been demo'd end-to-end.

**What needs to happen:**
- Run the full 3-party demo on at least 5 models (GBM, ACC, BRCA, plus 2–3 mid-range)
- Report latency for each
- Extract multiple patients (not just Patient 1)

**Estimated effort:** 1 day

---

### 16. Run Quantisation Check on Real Weights 🔬
**Roadmap: §4.1**

**What exists:**
- `quantization_check.py` — has `--weights` flag

**What needs to happen:**
- Run `python3 quantization_check.py --weights master_33_cancer_weights.npy --models 33`
- Capture the output showing how many genes truncation kills vs rounding

**Estimated effort:** 5 minutes

---

## Quick Reference: Priority Order

| # | Item | Category | Effort | Priority |
|---|---|---|---|---|
| 1 | $\rho$ Blinding | Core Privacy | 1–2 days | 🔴 Critical |
| 2 | Bucketing / Padding | Core Privacy | 2–3 days | 🔴 Critical |
| 11 | Extraction attacks on real data | Benchmark | 10 min | 🔴 Critical |
| 12 | Perturbation on real data | Benchmark | 1 hour | 🔴 Critical |
| 13 | Pathway rank on real data | Benchmark | 5 min | 🔴 Critical |
| 16 | Quantisation check on real data | Benchmark | 5 min | 🔴 Critical |
| 15 | Multi-model demo | Benchmark | 1 day | 🔴 Critical |
| 8 | Imputation bug fix | ML Pipeline | 1 day | 🟡 Important |
| 9 | Truncation bug fix | ML Pipeline | 1–2 hrs | 🟡 Important |
| 3 | Pathway XAI | Core Privacy | 3–5 days | 🟡 Important |
| 5 | Query budget / rate limit | Security | Half day | 🟡 Important |
| 14 | Multi-dimension benchmark | Benchmark | Half day | 🟡 Important |
| 10 | Separate $Q_w$/$Q_x$ | ML Pipeline | Half day | 🟢 Nice-to-have |
| 4 | Perturbation in live demo | Security | 1 day | 🟢 Nice-to-have |
| 6 | Audit logs | Security | 2–3 days | 🟢 Nice-to-have |
| 7 | Transport security | Infrastructure | 2–3 days | 🟢 Nice-to-have |
