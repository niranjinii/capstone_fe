# Beyond the Roadmap: What Would Make This Publish-Worthy

> [!NOTE]
> These are recommendations for work **not already covered** by your roadmap or current plan. They're organised by how much a reviewer would care about them, with effort estimates.

---

## 1. Comparative Baselines (Reviewers Will Ask "Why Not X?")

Right now, the paper says "FHIPE is better than FHE/MPC/TEE" in a qualitative table. A reviewer will immediately ask: **"Did you actually benchmark any of those?"** You don't need to build full systems, but you need *something* empirical.

### 1a. Paillier (Additively Homomorphic) Baseline
**Effort: 1–2 days** | **Impact: High**

Paillier encryption is the most common "simple HE" baseline for linear inference. Implement a toy Paillier inner-product evaluation at $n=139$ and measure:
- Encryption time
- Ciphertext size
- Evaluation time
- Whether the model owner must be online

This gives you a concrete row in your performance table showing FHIPE is faster/smaller/non-interactive. Python has `phe` (python-paillier) which makes this trivial.

### 1b. Plaintext Baseline (Unencrypted Inference)
**Effort: 30 minutes** | **Impact: Medium**

Run the same dot product *without* any encryption. Report the raw NumPy time. This gives you the "overhead factor" — e.g., "our system adds 3 seconds of overhead to a 0.001s plaintext computation, a 3000× factor, but sub-clinical-latency."

Reviewers love seeing the honest overhead number. Hiding it looks evasive.

### 1c. TenSEAL / SEAL (FHE) Comparison
**Effort: 2–3 days** | **Impact: High**

Microsoft SEAL (via TenSEAL Python wrapper) is the gold standard FHE library. Encrypt the same 139-gene vector, compute the same inner product homomorphically, and compare:
- Encryption time, ciphertext size, evaluation time
- Whether you can do it non-interactively (you can, but it's slow)

This is the strongest possible "why not FHE?" answer. If you show FHIPE is 100× faster at linear inference, that's a result.

---

## 2. Missing Experiments the Paper Needs

### 2a. Multi-Model Benchmark (Not Just ACC)
**Effort: 1 day** | **Impact: Critical**

You've only demo'd on ACC ($n=139$). You need to run the full pipeline on at least 5–6 models spanning the range:
- GBM ($n=28$, smallest)
- ACC ($n=139$, your current demo)
- BRCA ($n=252$, largest)
- Plus 2–3 mid-range ones

Report encryption time, decryption time, serialised ciphertext size, and total query latency for each. This proves the system *generalises*, not just works for one cherry-picked model.

### 2b. Multiple Patients
**Effort: 1 day** | **Impact: High**

You've only extracted Patient 1. Extract 5–10 patients and run them all through the pipeline. Report:
- Do all scores look reasonable?
- Is there variance in encryption time? (There shouldn't be, but prove it)
- Does the system handle edge cases (patients with many zero-expression genes)?

A reviewer will absolutely ask "you tested on one patient?" if you don't address this.

### 2c. Quantisation Error Analysis
**Effort: Half a day** | **Impact: Medium**

You quantise with $Q=100$. How much error does this introduce? Compute:
- The *plaintext* dot product (using floats)
- The *quantised* dot product (using ints)
- The relative error between them
- How the error changes with $Q = 10, 100, 1000, 10000$

This is a one-script experiment that produces a clean table showing your $Q=100$ choice is justified. Include a brief discussion of why you didn't use $Q=1000$ (larger discrete-log search range).

### 2d. Discrete-Log Search Range Sensitivity
**Effort: Half a day** | **Impact: Medium**

Your current bounds are `(-1000000, 1000000)`. What happens when you:
- Tighten to `(-100000, 100000)`? (Faster, but might miss extreme scores)
- Widen to `(-10000000, 10000000)`? (Slower, but more robust)

Plot decryption time vs search range. This directly feeds into the Design A ($\rho$ blinding) discussion because $\rho$ expands the range by $2^k$.

---

## 3. Security Hardening (Things Reviewers Will Probe)

### 3a. Side-Channel: Timing Leakage
**Effort: 1 day** | **Impact: Medium-High**

The Cloud's `FeDDH.decrypt()` performs a brute-force search whose runtime depends on the *magnitude* of $\langle x, y \rangle$. A patient with a high risk score takes longer to decrypt than one with a low score. This is a **timing side-channel** that leaks information about the result even if you implement $\rho$ blinding.

Measure this empirically: plot decryption time vs score magnitude. Then discuss mitigation:
- Constant-time decryption (always search the full range)
- Adding random padding to force worst-case search
- Using BSGS instead of linear search (BSGS has more uniform timing)

Even just *acknowledging* this in the paper is better than a reviewer discovering it.

### 3b. The Delegated Encryption Key is a One-Time Pad Problem
**Effort: Pure writing** | **Impact: Medium**

The delegated encryption key $ek = g_2^{B^*}$ is sent once and reused for every query. If the Clinic is compromised *after* receiving $ek$, the attacker has permanent encryption capability. Discuss:
- Should $ek$ be rotated? (Requires re-running Setup)
- Should $ek$ be encrypted at rest on the Clinic's device?
- What's the key lifetime policy?

This is a pure discussion point but shows maturity.

### 3c. Replay Attack on Ciphertexts
**Effort: Pure writing + small code change** | **Impact: Medium**

Nothing currently prevents the Cloud from replaying an old ciphertext against a new functional key, or vice versa. Discuss:
- Adding a nonce/timestamp to the ciphertext metadata
- Binding the ciphertext to a specific functional key via a commitment scheme

Even a simple `query_id` field in the JSON payload would demonstrate awareness.

---

## 4. Presentation Quality (What Separates "Good Project" from "Published Paper")

### 4a. Professional Architecture Diagram
**Effort: 2 hours** | **Impact: Very High**

Your current architecture is ASCII art. For a paper, you need a proper vector diagram (use draw.io, Figma, or even LaTeX TikZ). Show:
- The three parties as distinct boxes with icons
- All data flows with labeled arrows
- A color-coded legend for trust levels (green = trusted, red = untrusted)
- The capability separation clearly visible

This is the single highest-ROI visual investment.

### 4b. Formal Algorithm Boxes
**Effort: 1 day** | **Impact: High**

Write your three core algorithms as formal pseudocode boxes (LaTeX `algorithm2e` style):
1. `DelegatedSetup(msk)` → $ek$
2. `DelegatedEncrypt(ek, x)` → $ct$
3. `SecureEvaluate(ct, sk_y)` → blinded score

This is standard for crypto/systems papers and makes your contribution look rigorous.

### 4c. Reproducibility Package
**Effort: 1 day** | **Impact: High**

Create a single `run_all_experiments.sh` script that:
1. Installs dependencies
2. Runs all benchmarks
3. Generates all tables and figures as CSV/PNG files
4. Runs the extraction attack demo
5. Runs the perturbation analysis

Many venues now require or strongly prefer a reproducibility artifact. This also makes your GitHub repo look professional.

---

## 5. Stretch Goals (If You Have Time)

### 5a. Web Dashboard Demo
**Effort: 3–5 days** | **Impact: Medium (for paper), High (for presentation)**

Build a simple web UI where a "doctor" can:
- Select a cancer model from a dropdown
- Upload or select a patient
- See the encrypted query go out and the risk score come back
- View pathway-level explanations

This doesn't affect the paper content but is *incredible* for conference presentations, demos, and capstone defences. You could record a screencast and include a link in the paper.

### 5b. Formal Security Proof Sketch
**Effort: 2–3 days (if you have the crypto background)** | **Impact: Very High (for crypto venues)**

Write a formal simulation-based security argument for your delegated encryption protocol. Show that the Clinic's view (given $ek = g^{B^*}$) is computationally indistinguishable from a simulator that doesn't know $B^*$, under the DDH assumption.

This elevates the paper from "systems contribution" to "crypto contribution" and opens up venues like PETS or ESORICS.

### 5c. Cross-Institutional Scenario (MIFE)
**Effort: 1–2 weeks** | **Impact: Very High**

PyMIFE already has Multi-Input FE primitives. Implement a scenario where two hospitals each encrypt their own patient data under independent keys, and the Cloud computes a *cross-institutional* aggregate without either hospital seeing the other's data. This is a genuine research contribution that goes beyond the roadmap.

---

## Priority Ranking (My Recommendation)

| Priority | Item | Why |
|---|---|---|
| **Must-do** | 2a. Multi-model benchmark | "You only tested one model" is a fatal reviewer comment |
| **Must-do** | 2b. Multiple patients | "You only tested one patient" is equally fatal |
| **Must-do** | 1b. Plaintext baseline | Takes 30 minutes, gives you the overhead factor |
| **Must-do** | 4a. Professional diagram | First thing a reviewer sees |
| **Should-do** | 1a. Paillier baseline | Strongest "why not HE?" answer with minimal effort |
| **Should-do** | 2c. Quantisation error | Justifies your $Q=100$ choice empirically |
| **Should-do** | 3a. Timing leakage | Shows security maturity |
| **Should-do** | 4b. Algorithm boxes | Standard for the genre |
| **Should-do** | 4c. Reproducibility script | Many venues require this |
| **Nice-to-have** | 1c. TenSEAL comparison | The ultimate "why not FHE?" data point |
| **Nice-to-have** | 2d. DLog range sensitivity | Feeds into Design A discussion |
| **Nice-to-have** | 5a. Web dashboard | Killer for presentations |
| **Stretch** | 5b. Security proof sketch | Opens crypto venues |
| **Stretch** | 5c. MIFE demo | Genuine research contribution |
