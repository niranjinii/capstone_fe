# Research Paper Outline: Privacy-Preserving Cancer Risk Prediction via Function-Hiding Inner Product Encryption

> [!NOTE]
> This is a **structural outline** for your mentor. Each section lists its headings, the general idea of the content, and where diagrams/tables/figures should go. Sections marked with 🔧 are things you've already built and can write from code. Sections marked with 📐 need new experiments or analysis. Sections marked with 📝 are pure writing.

---

## Abstract
📝 **~250 words. One paragraph.**

Content idea: Frame the problem (genomic AI needs privacy for *both* the patient data AND the model weights), state the approach (FHIPE with a 3-party capability-separation architecture), and list 5 concrete contributions:
1. Formalisation of the extraction vulnerability in public-key IPFE (both chosen-input and natural-use attacks)
2. A working FHIPE system with a ~500× C++ backend speedup, processing real TCGA data at sub-3-second latency
3. A delegated encryption protocol ($g^{B^*}$) enforcing capability separation without master key exposure
4. A quantified trade-off space across three result-privacy designs (A/B/C), with honest characterisation of what *cannot* be protected
5. Perturbation-based model lifetime analysis showing quadratic noise–lifetime scaling

End with: real TCGA pan-cancer data (33 types, 20,531 genes), all code released.

---

## 1. Introduction

### 1.1 The Privacy Imperative in Genomic AI
📝 Set the scene. Cloud-based ML inference on genomic data has two simultaneous privacy requirements that traditional encryption can't solve:
- **Patient data privacy** — gene expression vectors are more identifying than SSNs, immutable, and shared with relatives
- **Model weight confidentiality** — weights are derived *from* patient data (training cohort leakage, membership inference)

Explain why traditional approaches (FHE, MPC, TEEs) each fall short for this specific use case. Position Functional Encryption as uniquely suited: non-interactive, single-round evaluation, model owner goes offline.

### 1.2 The Extraction Vulnerability: Why Naïve FE Fails
📝 The intellectual hook of the paper. State the core theorem informally:
> In any public-key IPFE scheme, an adversary holding both $mpk$ and $sk_y$ can recover $y$ in exactly $n$ queries.

Explain why this is devastating: it's not a bug, it's a *theorem*. The Cloud extracts offline, instantly, for free, undetectably. Then introduce the even scarier Attack B: a Doctor collecting $n$ real patient scores can solve a linear system — no chosen inputs, indistinguishable from clinical use.

### 1.3 Our Approach and Contributions
📝 List contributions (mirror the abstract but with section references). Key framing: "FHIPE does not prevent extraction — it changes its *cost and visibility*." Converts a free/invisible/offline attack into an expensive/visible/online one.

### 1.4 Paper Organisation
📝 Brief roadmap of sections.

---

## 2. Background and Theoretical Foundations

### 2.1 Functional Encryption: The Paradigm
📝 Define FE formally (Setup, KeyGen, Encrypt, Decrypt). Contrast with traditional PKE (all-or-nothing) and FHE (produces ciphertexts, not plaintexts). Emphasise *succinctness*: decryption yields $f(x)$, not another ciphertext.

### 2.2 Inner Product Functional Encryption (IPFE)
📝 Specialise to $f_y(x) = \langle x, y \rangle$. Explain why this is exactly what linear classifiers compute (logistic regression, Lasso, linear SVM).

> **Table 1:** Comparison of IPFE constructions (Abdalla et al. 2015, Agrawal et al. 2016, Bishop et al. 2015, Kim et al. 2018) — columns: Assumption, Key Setting, Function Hiding (Yes/No).

### 2.3 Function-Hiding IPE: The FeDDH Construction
📝 Full mathematical walkthrough:
- Setup: random invertible $B$, adjugate $B^* = (\det B)(B^{-1})^\top$
- Encryption using $B^*$ and random $\beta$
- Key generation using $B$ and random $\alpha$
- Decryption via pairings + discrete log recovery
- Why function hiding holds (neither $B$ nor $B^*$ is revealed individually)

### 2.4 The Public-Key / Secret-Key Boundary
📝 This is the *crux*. State precisely why public-key IPFE cannot be function-hiding. Explain that capability separation is what makes secret-key FHIPE operationally meaningful.

> **Key quote to build around:** "Model confidentiality is not a property of the cipher — it is a property of how capabilities are partitioned across nodes."

### 2.5 Subclasses and Alternatives
📝 Brief comparison table of privacy-preserving computation approaches.

> **Table 2:** Comparison matrix — IPFE/FHIPE vs FHE vs MPC vs TEE vs DP vs MIFE. Columns: Model Owner Online?, Arbitrary Functions?, Practical Overhead, Trust Assumptions.

---

## 3. Related Work

### 3.1 Functional Encryption Theory
📝 Boneh/Sahai/Waters (2011), Abdalla et al. (2015, 2018), Bishop/Jain/Kowalczyk (2015), Kim et al. (2018), Agrawal/Libert/Stehlé (2016).

### 3.2 FE-Based Machine Learning Inference
📝 Dufour-Sans/Gay/Pointcheval (2019) "Reading in the Dark", Ligier et al. (2017), Marc/Stopar/Hartman (2019). **Identify the gap:** no published system addresses extraction attack characterisation + function-hiding mitigation + delegated encryption + empirical trade-off analysis for a genomic application.

### 3.3 Privacy-Preserving Genomics
📝 Bogos/Gassend/Hubaux (2017), broader genomic privacy literature. TCGA Pan-Cancer reference (Weinstein et al. 2013).

### 3.4 Model Extraction Attacks
📝 Tramèr et al. (2016) — formalised prediction API extraction. Our Attack B instantiates their result in the IPFE context.

### 3.5 Software Artefacts
📝 PyMIFE (unimplemented `export()` methods, pure-Python bottleneck), MCL/mclbn256 (C++ pairing engine). Frame *our* contribution as the bridge.

---

## 4. Threat Model and Security Analysis

> [!IMPORTANT]
> This section is separated from System Design (unlike the current draft which mixes them). The roadmap emphasises that the threat model should be its own first-class section because the paper's positioning is "exploratory, not advocacy."

### 4.1 Parties and Trust Assumptions
📝 Define the three parties (Hospital/KGC, Clinic/Doctor, Cloud/Evaluator) and their trust levels. Hospital = fully trusted. Cloud = honest-but-curious (primary) or malicious (secondary). Doctor = semi-trusted (may attempt extraction through legitimate use).

### 4.2 Adversarial Coalitions
📝 Enumerate five adversaries and their capabilities.

> **Table 3: Adversarial Coalition Matrix**
> Rows: Honest-but-curious Cloud, Malicious Cloud, Malicious Doctor, Doctor–Cloud collusion, Network adversary
> Columns: What they hold, Data privacy, Model confidentiality, Query privacy, Result privacy

### 4.3 Three Orthogonal Privacy Properties
📝 Define precisely:
1. **Data privacy** — Cloud cannot learn individual gene expression values
2. **Query privacy** — Cloud cannot determine which cancer model is being evaluated
3. **Result privacy** — Cloud cannot learn the risk score

Explain that these are *orthogonal*: FHIPE gives you (1) for free, but (2) and (3) require additional architectural mechanisms.

### 4.4 Extraction Attack Formalisation
📝 + 🔧 Formalise both attacks:
- **Attack A (Chosen Input):** Encrypt unit vectors $e_i$, read $y_i$ directly. Requires encryption capability. $n$ queries, exact recovery. Reference `extraction_attack.py`.
- **Attack B (Natural Use):** Collect $n$ patient vectors and scores, solve $y = X^{-1}s$ via least squares. No chosen inputs, indistinguishable from legitimate use.

> **Table 4: Extraction Attack Results Across All 33 TCGA Models**
> Columns: Cancer type, Active genes ($n$), Attack A exact?, Attack B relative error, Attack B time

### 4.5 The Capability Separation Argument
📝 This is the paper's core intellectual contribution. FHIPE doesn't *prevent* extraction — it *changes who can do it and at what cost*. The Cloud goes from "free offline extraction" to "structurally impossible." The Doctor goes from "free offline extraction" to "$n$ online, authenticated, logged queries."

---

## 5. System Design and Architecture

### 5.1 Design Goals
📝 Five requirements: data privacy, model weight confidentiality, non-interactive evaluation, clinical latency (<5s), honest threat reporting.

### 5.2 Three-Party Architecture

> **Figure 1: System Architecture Diagram** 📐
> Full architecture diagram showing Hospital, Clinic, Cloud with all data flows:
> - Hospital → Clinic: active indices, delegated encryption key ($ek$), sealed functional key
> - Clinic → Cloud: encrypted ciphertext ($ct$) + sealed functional key ($sk_y$)
> - Cloud → Clinic: blinded risk score
> Show capability separation: who holds what (msk, $B^*$, $g^{B^*}$, $sk_y$)

> **Table 5: Capability Separation Matrix**
> Rows: Master secret key, Encryption matrix $B^*$, Delegated enc. key, Functional key, Encryption capability, Decryption capability, Can extract model?
> Columns: Hospital, Clinic, Cloud

### 5.3 Delegated Encryption Protocol
📝 + 🔧 The $g^{B^*}$ precomputation. Explain mathematically why the Clinic can encrypt but cannot derive functional keys (needs $B$, not $B^*$). Reference `delegated_crypto.py`.

Cost analysis: $O(n^2)$ scalar muls in $G_2$, ~3× slower than direct encryption for BN254 — acceptable trade-off for capability separation.

### 5.4 Sealed Key Delivery
📝 + 🔧 NaCl SealedBox (X25519 + XSalsa20-Poly1305). The Clinic is a courier but cannot peek inside the sealed functional key. Reference `cloud.py` and `hospital.py`.

### 5.5 Result Privacy: Design A (Hospital-Blinded Score)
📝 Extend vector by one slot: Clinic encrypts $[x, 1]$, Hospital issues key for $[y, \rho]$. Cloud computes $\langle x, y \rangle + \rho$ — uninformative. Clinic subtracts $\rho$.

> **Table 6: Result Privacy Design Comparison**
> Rows: Design A (Blinded), Design B (Split Decryption), Design C (Hospital-in-Loop)
> Columns: Result privacy, Decryption cost, Hospital online?, Doctor extraction control

### 5.6 Query Privacy: Bucketing and Padding
📝 Dimension leaks cancer type (139 = ACC, 252 = BRCA, etc.). Mitigation: pad to a shared dimension. Trade-off: union dimension ($n=3555$) gives maximum privacy but 651× more encryption work. Intermediate clinical buckets ($n=300-500$) are the practical middle ground.

> **Figure 2: Query Privacy vs Encryption Cost Trade-off Curve** 📐
> X-axis: bucket dimension. Y-axis (left): encryption time. Y-axis (right): number of indistinguishable cancer models.

---

## 6. Implementation

### 6.1 Machine Learning Pipeline
📝 + 🔧 L1-regularised logistic regression (Lasso), One-vs-Rest, TCGA/Xena pan-cancer data (33 types, 20,531 genes). Per-cancer active gene counts: 28–252, median ~100, global union 3,555.

Discuss the two bugs fixed:
1. **Truncation bug:** `astype(int)` vs `np.rint().astype(int64)` — silently deletes features with small coefficients
2. **Imputation bug:** `fill_value=0` after `StandardScaler` injects fake suppression signal; correct approach: impute with `scaler.mean_`

### 6.2 High-Performance Pairing Backend (`mcl_backend.py`)
🔧 The critical engineering contribution.

Describe the three bugs solved:
1. **Curve order mismatch** — mclbn256 uses a different BN254 parameterisation than py_ecc
2. **64-bit integer truncation** — `Fr.setInt()` silently truncates 254-bit scalars; fixed with `Fr.fromstr(hex, 16)`
3. **GT group algebra mapping** — "addition" = field multiplication, "scalar mul" = exponentiation

> **Table 7: Backend Performance Comparison**
> Rows: Single pairing, Scalar mul (G1), Encrypt ($n=20$), Decrypt ($n=20$), Keygen ($n=300$), Full query ($n=139$)
> Columns: py_ecc (Pure Python), mclbn256 (C++), Speedup

Include code snippet of `_to_fr()` showing the hex-encoding workaround.

### 6.3 Optimised Key Generation (`fast_feddh_generate`)
🔧 Raw Python `int` Gaussian elimination bypassing PyMIFE's `ZmodR` object system. 7 min → 20s for $n=300$.

Include code snippet showing `pow(factor, -1, order)` vs the `ZmodR.__mul__` overhead.

### 6.4 Network Serialisation (`fhipe_serializer.py`)
🔧 Fixing PyMIFE's unimplemented `export()` methods. Dual-mode serialiser (mclbn256 `.serialize()` hex-encoding + py_ecc `FQ`/`FQ2` integer extraction).

> **Table 8: Serialisation Overhead**
> Rows: Ciphertext, Functional key, Delegated enc. key
> Columns: Dimension, Serialised size, Serialise time, Deserialise time

### 6.5 Parallel Bucket Evaluation (`parallel_eval.py`)
🔧 `fork()` start method to bypass GIL and avoid pickling the master key. Python 3.14 `forkserver` gotcha.

> **Table 9: Parallel Evaluation Benchmark ($n=300$, 4 buckets)**
> Setup time, parallel time, sequential time, speedup

---

## 7. Demonstration and End-to-End Workflow

### 7.1 Clinical Workflow Walkthrough
🔧 Step-by-step walkthrough of the live demo:
1. Hospital boots (~20s keygen for $n=139$)
2. Cloud boots (X25519 keypair, instant)
3. Clinic queries (~3s total: fetch indices → subset patient → encrypt → send → receive score)

> **Figure 3: Sequence Diagram of a Single Clinical Query** 📐
> Swim-lane diagram: Hospital ↔ Clinic ↔ Cloud, showing each HTTP request/response with timing annotations.

### 7.2 Real Data Processing
🔧 Patient 1 from TCGA Xena (20,531 genes). Dynamic subsetting to 139 active ACC genes. Quantisation with $Q = 100$. Final risk score: `190984`.

### 7.3 What the Cloud Learns and Does Not Learn

> **Table 10: Information Leakage Summary**
> Rows: Patient gene values, Model weight magnitudes, Which genes are active, Raw inner product score, Which cancer type
> Columns: Cloud sees?, Reason

---

## 8. Efficiency and Security Analysis

### 8.1 Perturbation Lifetime Analysis
📐 + 🔧 The paper's "central figure" (per the roadmap). Reference `patients_until_recovery.py`.

Key finding: lifetime scales *quadratically* in noise magnitude: $m \sim n \cdot (\sigma / \tau)^2$. At $\sigma = 1000$, accuracy cost is 1.9pp while extraction lifetime exceeds $12n$.

> **Figure 4: Model Lifetime vs Perturbation (THE key figure)** 📐
> Dual-axis plot. X-axis: noise scale $\sigma$ (symlog). Left Y-axis: patients until recovery. Right Y-axis: accuracy cost (pp). The crossing point is the result.

> **Table 11: Perturbation Lifetime Data**
> Rows: $\sigma$ = 0, 100, 1000, 10000, 30000, 100000
> Columns: Patients to recover, vs baseline multiplier, Accuracy cost (pp)

### 8.2 Dimension and Query Privacy Analysis
📐 Per-cancer active gene counts (28–252). Padding to union ($n=3555$) gives 127× lifetime improvement for GBM but 651× encryption cost increase.

> **Table 12: Active Gene Counts Per Cancer Model (Selected)**
> Show the range and why dimension leaks the cancer type.

### 8.3 End-to-End Latency Breakdown
📐 Decompose the ~3s query into: index fetch, patient loading, encryption, network transmission, Cloud decryption.

> **Table 13: Latency Breakdown for a Single Query ($n=139$)**
> Rows: Fetch indices, Load/subset patient data, Delegated encryption, Network (serialise + transmit), Cloud unseal + decrypt
> Columns: Time, % of total

### 8.4 Scalability Analysis
📐 How does total query time scale with $n$? Plot encryption time vs dimension for $n = 50, 100, 139, 200, 300, 500$.

> **Figure 5: Encryption and Decryption Time vs Dimension** 📐
> Line plot. X-axis: dimension $n$. Y-axis: time (s). Two lines: encryption ($O(n^2)$), decryption ($O(n)$ pairings + BSGS).

---

## 9. Explainable AI via Pathway Aggregation

### 9.1 The XAI Extraction Threat
📝 Per-gene SHAP values give one linear equation per query → $n$ queries = full extraction. This is the same Attack B applied to explanations.

### 9.2 Pathway Aggregation Defence
📝 + 🔧 Group genes into 50 MSigDB Hallmark pathways. Report pathway-level aggregate scores instead of per-gene contributions. Reference `check2_pathway_rank.py`.

Formal security: $50 \times 3555$ incidence matrix has rank 50 → 3,505 free unknowns (99% underdetermined).

> **Table 14: Pathway Rank Analysis**
> Total genes, Number of pathways, Matrix rank, Free unknowns, % underdetermined

### 9.3 Clinical Utility Argument
📝 Pathway explanations are arguably *more useful* than per-gene scores. "Apoptosis pathway contributed +0.42" > "BRCA1 contributed +0.003".

### 9.4 Caveats
📝 If active gene set is small and overlaps heavily with pathway definitions, privacy argument weakens. Report exact rank rather than asserting generic safety.

---

## 10. Discussion

### 10.1 Honest Limitations
📝 Frame as the roadmap instructs: "exploratory, not advocacy."
- FHIPE does not prevent extraction by the prediction-receiving party — it changes the cost
- Linear models only (no neural networks)
- BN254 is not post-quantum secure
- Current demo has no transport-layer security (plain HTTP)
- No real clinical validation (TCGA is research data)

### 10.2 The Capability Separation Argument, Revisited
📝 Summarise the paper's core thesis: security is a property of capability *partition*, not of any single primitive.

---

## 11. Conclusion
📝 Restate contributions. Emphasise the honest framing: "converts a free, invisible, offline attack into an expensive, visible, online one."

---

## 12. Future Scope

### 12.1 Multi-Input FE (MIFE)
📝 Cross-institutional genomic aggregation. PyMIFE already has MIFE primitives.

### 12.2 Result Privacy Implementation
📝 Implement Design A ($\rho$ blinding) end-to-end and benchmark the discrete-log search expansion.

### 12.3 Query Privacy via Clinical Buckets
📝 Group 33 cancers into ~10 clinical families, benchmark encryption at bucket dimensions.

### 12.4 Transport Security
📝 mTLS, Ed25519 payload signing, proper certificate-based authentication.

### 12.5 Non-Linear Models
📝 Quadratic FE for single hidden layers (Sans/Gay/Pointcheval). Hybrid FE + lightweight MPC for activations.

### 12.6 Post-Quantum Security
📝 Lattice-based FHIPE (Agrawal/Libert/Stehlé 2016). Benchmark at clinical dimensions.

### 12.7 Verifiable Computation
📝 Hash-chained audit logs with signed computation anchors. Decoy query verification.

### 12.8 Real-World Clinical Validation
📝 EHR integration, HIPAA/GDPR compliance, prospective cohort validation.

---

## References
📝 ~16 references (already well-established in the current draft). Add any new ones from the discussion.

---

## Appendices

### Appendix A: Notation Reference
📝 Symbol table ($x$, $y$, $B$, $B^*$, $\rho$, $Q_w$, $Q_x$, etc.)

### Appendix B: Codebase Reference
📝 File-by-file table mapping each script to its paper section.

---

## Summary of Figures, Tables, and Diagrams

| ID | Type | Section | Content |
|---|---|---|---|
| **Fig. 1** | Architecture Diagram | §5.2 | Three-party system with data flows and capability separation |
| **Fig. 2** | Trade-off Curve | §5.6 | Query privacy vs encryption cost at different bucket dimensions |
| **Fig. 3** | Sequence Diagram | §7.1 | Swim-lane diagram of a single clinical query with timings |
| **Fig. 4** | Dual-axis Plot | §8.1 | **THE key figure** — model lifetime vs perturbation noise vs accuracy cost |
| **Fig. 5** | Line Plot | §8.4 | Encryption/decryption time scaling with dimension $n$ |
| **Table 1** | Comparison | §2.2 | IPFE constructions (assumption, key setting, function hiding) |
| **Table 2** | Comparison | §2.5 | FHIPE vs FHE vs MPC vs TEE vs DP |
| **Table 3** | Security | §4.2 | Adversarial coalition matrix (5 adversaries × 4 privacy properties) |
| **Table 4** | Attack Results | §4.4 | Extraction attacks across all 33 TCGA models |
| **Table 5** | Capabilities | §5.2 | Capability separation matrix (Hospital / Clinic / Cloud) |
| **Table 6** | Design Comparison | §5.5 | Result privacy designs A/B/C trade-offs |
| **Table 7** | Benchmark | §6.2 | py_ecc vs mclbn256 backend performance |
| **Table 8** | Overhead | §6.4 | Serialisation sizes and timings |
| **Table 9** | Benchmark | §6.5 | Parallel evaluation results |
| **Table 10** | Leakage | §7.3 | What the Cloud learns/doesn't learn |
| **Table 11** | Data | §8.1 | Perturbation lifetime data |
| **Table 12** | Data | §8.2 | Active gene counts per cancer model |
| **Table 13** | Breakdown | §8.3 | End-to-end latency decomposition |
| **Table 14** | Security | §9.2 | Pathway rank analysis |
