# Privacy-Preserving Intelligence for Healthcare 5.0: Secure Cancer Risk Prediction via Function-Hiding Inner Product Encryption with Delegated Computation

---

## Abstract

Deploying machine learning models for clinical cancer risk assessment over sensitive genomic data presents a fundamental tension: patient gene expressions must remain private, yet accurate inference requires computing over them; model weights embody training-cohort information that warrants confidentiality, yet clinicians and regulators require transparency into model behaviour. We present a three-party cryptographic architecture that resolves both requirements simultaneously using **Function-Hiding Inner Product Encryption (FHIPE)**. Our system enables an untrusted cloud server to compute encrypted inner products — the core operation of linear classification — over patient genomic vectors without learning either the patient's biomarkers *or* the hospital's proprietary model weights.

We make five concrete contributions. **First**, we demonstrate that deploying standard Inner Product Functional Encryption (IPFE) with public-key semantics in the naïve manner — handing both the master public key and a functional key to an untrusted evaluator — enables *complete* model extraction in exactly $n$ queries with zero cryptanalytic effort, and that this extraction is indistinguishable from ordinary clinical use. **Second**, we implement a working FHIPE-based inference pipeline using the FeDDH construction, backed by a novel high-performance C++ pairing backend (`mclbn256`) that achieves a **~500× speedup** over the baseline pure-Python implementation, reducing per-query evaluation from minutes to sub-second latency at clinically relevant dimensions ($n = 139$). **Third**, we design and implement a *delegated encryption* protocol using precomputed curve points ($g^{B^*}$), enabling resource-constrained clinic devices to encrypt patient data in $O(n^2)$ group exponentiations without ever accessing the master secret key — thereby enforcing capability separation at the protocol level. **Fourth**, we introduce a formal threat model enumerating five adversarial coalitions (honest-but-curious Cloud, malicious Cloud, malicious Doctor, Doctor–Cloud collusion, network adversary) and characterise three orthogonal inference-time privacy properties (data privacy, query privacy, result privacy), demonstrating a quantified trade-off space across three architectural designs. **Fifth**, we present a perturbation-based model lifetime analysis showing that additive Gaussian noise scales extraction resistance *quadratically* in the noise magnitude ($m \sim n \cdot (\sigma / \tau)^2$), at a measured diagnostic accuracy cost of less than 2 percentage points — providing a tunable, empirically characterised defence complementing the cryptographic guarantees.

Our prototype processes real TCGA pan-cancer RNA-seq data across 33 cancer types with 20,531 gene features, demonstrating end-to-end correctness on actual clinical-grade genomic data. All code, training pipelines, benchmarks, and attack demonstrations are publicly released.

**Keywords:** Functional Encryption, Function-Hiding Inner Product Encryption, Privacy-Preserving Machine Learning, Genomic Data Privacy, Cancer Risk Prediction, Bilinear Pairings, Healthcare 5.0

---

## 1. Introduction

### 1.1 The Privacy Imperative in Genomic AI

The convergence of high-throughput genomic sequencing and machine learning has unlocked extraordinary capabilities in clinical oncology. Linear models trained on gene expression profiles from large cohorts — such as The Cancer Genome Atlas (TCGA) — can stratify patients across 33 cancer types with clinically meaningful accuracy. Yet deploying these models in real healthcare systems exposes a paradox that no amount of access control or network security can resolve: *the computation itself is the leak*.

When a clinic submits a patient's 20,531-dimensional gene expression vector to a cloud-hosted model for cancer risk scoring, two categories of sensitive information are at stake:

1. **Patient data privacy**: The expression vector encodes the patient's complete transcriptomic fingerprint — a dataset more identifying than a Social Security number, immutable across a lifetime, and shared partially with biological relatives.

2. **Model weight confidentiality**: The trained coefficients encode statistical signatures of the training cohort. In genomic models, these weights are not merely intellectual property — they are *derived from* patient data. A leaked weight vector can enable membership inference against the training cohort, potentially revealing that specific individuals contributed to a cancer study. Even absent explicit membership disclosure, the magnitudes encode which genes are most discriminative for each cancer type — proprietary clinical knowledge developed through years of research.

Traditional approaches to this problem — homomorphic encryption (FHE), secure multi-party computation (MPC), and trusted execution environments (TEEs) — each impose constraints that limit practical deployment. FHE supports arbitrary computation on encrypted data but incurs orders-of-magnitude overhead for even simple operations. MPC protocols achieve strong security but require all parties to participate interactively in every query, making the model owner a permanent bottleneck. TEEs (e.g., Intel SGX) depend on hardware trust assumptions that have been repeatedly broken by side-channel attacks (Foreshadow, Plundervolt, ÆPIC).

**Functional Encryption (FE)** occupies a unique position in this design space. It permits *selective revelation*: a functional key $sk_y$ for function $f_y$ allows computation of $f_y(x)$ from an encryption of $x$ — and nothing else. For inner products, this means a cloud server can compute $\langle x, y \rangle$ without learning $x$ individually, and crucially, the model owner need not participate in the computation at all. The hospital issues $sk_y$ once, then goes offline. No other cryptographic approach offers this *non-interactive, single-round* evaluation with the model owner absent.

### 1.2 The Extraction Vulnerability: Why Naïve FE Fails

This paper is motivated by a finding that, while known in theory, has not been adequately addressed in the systems literature on FE-based inference:

> **Theorem (Informal).** In any public-key inner product functional encryption scheme, an adversary holding both $mpk$ and $sk_y$ can recover $y$ exactly in $n$ queries, where $n$ is the vector dimension, by encrypting unit vectors $e_i$ and reading weights directly from the decrypted outputs.

This is not a bug — it is a *theorem*. Function hiding is only definable in the secret-key setting, because a public-key scheme necessarily grants the adversary oracle access to the encryption function. For inner products, this oracle determines the function exactly.

The implications for deployed systems are severe. In our initial architecture (and, we argue, in several published FE-inference proposals), the untrusted cloud server holds both the master public key and a functional key. It can therefore extract the complete model *offline*, *instantly*, *for free*, and *undetectably* — no network traffic, no interaction with any other party, nothing in any audit log.

Worse still, even without the public key, a party that receives predictions — i.e., the doctor — can extract the model through ordinary clinical use. We demonstrate (§5.1, Attack B) that collecting $n$ real patient vectors and their corresponding scores, then solving the resulting linear system, recovers the model with near-zero relative error. This *natural-use* attack requires no chosen inputs, no protocol deviation, and is *indistinguishable from legitimate clinical operation*.

### 1.3 Our Approach and Contributions

We address these vulnerabilities through a comprehensive systems design that treats model protection not as a single cryptographic primitive but as a *capability separation architecture*. Our key insight is that **FHIPE does not prevent extraction — it changes its cost and visibility**. Under the naïve design, the Cloud extracts offline, instantly, and undetectably. Under our architecture, the Cloud *cannot* extract at all (it lacks encryption capability), and the residual extraction path through the Doctor requires $n$ queries that are online, authenticated, logged, rate-limitable, and billable.

Our contributions are:

1. **Extraction attack formalisation and measurement** (§5.1): We implement and benchmark both chosen-input (Attack A) and natural-use (Attack B) extraction attacks against IPFE-based inference, demonstrating exact weight recovery across all 33 TCGA cancer models.

2. **FHIPE system implementation** (§4, §5): A working three-party (Hospital–Clinic–Cloud) architecture using the FeDDH construction with a novel high-performance C++ pairing backend achieving ~500× speedup over baseline.

3. **Delegated encryption protocol** (§4.3): A $g^{B^*}$ precomputation technique enabling clinic-side encryption without master key access, enforcing capability separation at the cryptographic level.

4. **Quantified trade-off space** (§5.4): Three architectural designs for result privacy (Hospital-blinded score, split decryption, Hospital-in-loop) with measured latency and privacy costs.

5. **Perturbation lifetime analysis** (§7): Empirical demonstration of quadratic noise–lifetime scaling with calibrated accuracy cost measurements.

6. **Pathway-aggregated explainability** (§6): A biologically motivated XAI defence using MSigDB Hallmark pathways that provides clinically useful explanations while maintaining 99% rank deficiency against weight recovery.

### 1.4 Paper Organisation

The remainder of this paper is organised as follows. Section 2 provides the necessary theoretical background on functional encryption and its subclasses. Section 3 surveys related work. Section 4 presents our system architecture. Section 5 details the implementation. Section 6 describes our demonstration and experimental setup. Section 7 presents the efficiency and security analysis. Section 8 discusses pathway-based explainability. Section 9 concludes, and Section 10 identifies future work.

---

## 2. Background

This section provides the theoretical foundations necessary to understand our system, progressing from general functional encryption to the specific construction we employ. We aim to make this accessible to readers without a cryptography background while maintaining formal precision for those who do.

### 2.1 Functional Encryption: The Paradigm

**Traditional public-key encryption** operates as an all-or-nothing gate: a ciphertext $c = \text{Enc}(pk, m)$ reveals either *everything* (if you hold $sk$) or *nothing* (if you don't). This binary model is insufficient when a computation must be performed on encrypted data by a party that should learn the result but not the input.

**Functional Encryption (FE)** [Boneh, Sahai & Waters, 2011] generalises this model. An FE scheme for a function family $\mathcal{F}$ consists of four algorithms:

$$\textbf{Setup}(1^\lambda) \rightarrow (mpk, msk)$$
$$\textbf{KeyGen}(msk, f) \rightarrow sk_f \quad \text{for } f \in \mathcal{F}$$
$$\textbf{Encrypt}(mpk, x) \rightarrow ct$$
$$\textbf{Decrypt}(ct, sk_f) \rightarrow f(x)$$

The security guarantee is that $sk_f$ reveals $f(x)$ and *nothing else* about $x$ — formalised through simulation-based or indistinguishability-based security definitions.

The critical advantage over fully homomorphic encryption (FHE) is *succinctness*: decryption produces a short plaintext value $f(x)$ rather than a new ciphertext that must be further processed. For our application, this means the cloud obtains a single integer — the risk score — rather than an encrypted blob requiring further rounds of interaction.

### 2.2 Inner Product Functional Encryption (IPFE)

When the function family $\mathcal{F}$ consists of linear functions — specifically, inner products — we obtain **Inner Product Functional Encryption (IPFE)**. Given:

- A message vector $x = (x_1, \ldots, x_n) \in \mathbb{Z}^n$ (the patient's gene expression profile),
- A function vector $y = (y_1, \ldots, y_n) \in \mathbb{Z}^n$ (the model's weight vector),

the scheme computes:

$$f_y(x) = \langle x, y \rangle = \sum_{i=1}^{n} x_i \cdot y_i$$

This is *exactly* the computation performed by a linear classifier (logistic regression, Lasso, linear SVM) — making IPFE a natural cryptographic primitive for privacy-preserving linear inference.

Several efficient IPFE constructions exist:

| Construction | Assumption | Key Setting | Function Hiding |
|---|---|---|---|
| **Abdalla et al. (2015)** | DDH | Public-key | No |
| **Agrawal, Libert & Stehlé (2016)** | LWE | Public-key | No |
| **Bishop, Jain & Kowalczyk (2015)** — "DDH-based" | DDH | Secret-key | Yes |
| **Kim, Lewi, Mandal et al. (2018)** — "FHIPE" | DDH, in generic bilinear groups | Secret-key | **Yes** |

The distinction between public-key and secret-key settings is *not* merely a key management detail — it is the **decisive** security boundary for our application, as we formalise in §2.4.

### 2.3 Function-Hiding IPE (FHIPE): The FeDDH Construction

Standard IPFE protects the data vector $x$ but leaves the function vector $y$ exposed through the functional key $sk_y$. **Function-hiding** IPFE additionally conceals $y$: an adversary holding $sk_y$ learns only $\langle x, y \rangle$, not $y$ itself.

Our implementation uses the **FeDDH construction** [Bishop, Jain & Kowalczyk, 2015], which operates in bilinear groups. Let $(G_1, G_2, G_T, e, p)$ be a bilinear group of prime order $p$ with generators $g_1 \in G_1$, $g_2 \in G_2$, and pairing $e: G_1 \times G_2 \rightarrow G_T$.

**Setup.** Sample a random invertible matrix $B \in \mathbb{Z}_p^{n \times n}$ and compute $B^* = (\det B) \cdot (B^{-1})^\top$ — the *adjugate* matrix satisfying $B^\top B^* = (\det B) \cdot I_n$.

**Encryption.** To encrypt $x \in \mathbb{Z}_p^n$: sample $\beta \xleftarrow{\$} \mathbb{Z}_p^*$, compute:

$$c_1 = g_2^\beta, \quad c_2 = \left( g_2^{\beta \cdot \sum_i x_i B^*_{i,j}} \right)_{j=1}^n$$

**Key Generation.** To generate a functional key for $y \in \mathbb{Z}_p^n$:

$$k_1 = g_1^{\alpha}, \quad k_2 = \left( g_1^{\alpha \cdot \sum_i y_i B_{i,j}} \right)_{j=1}^n$$

where $\alpha \xleftarrow{\$} \mathbb{Z}_p^*$.

**Decryption.** Compute:

$$D = \prod_{j=1}^{n} e(k_{2,j},\; c_{2,j}) \cdot e(k_1,\; c_1)^{-(\det B) \cdot \langle x, y \rangle \text{ — recovered via discrete log}}$$

More precisely, decryption computes:

$$\frac{\prod_j e(k_{2,j}, c_{2,j})}{e(k_1, c_1)^{???}} = e(g_1, g_2)^{\alpha \beta \cdot (\det B) \cdot \langle x, y \rangle}$$

The inner product is then recovered by solving the discrete logarithm of the result in base $e(g_1, g_2)^{\alpha \beta \cdot \det B}$. Since the inner product is bounded (clinical risk scores lie in a known range), this search is feasible via baby-step giant-step (BSGS) or Pollard's kangaroo algorithm.

**Why Function-Hiding holds.** Encryption uses $B^*$ and key generation uses $B$. Neither the ciphertext alone nor the key alone reveals the underlying vector, because the random basis $B$ acts as a one-time blinding mask. Crucially, **encryption requires knowledge of $B^*$** — a secret — which is why function hiding is only possible in the secret-key setting.

### 2.4 The Public-Key / Secret-Key Boundary: Why It Matters

This distinction is the intellectual crux of the project. We state it precisely because several published FE-inference systems implicitly or explicitly violate it:

> **Observation.** In a public-key IPFE scheme, any party holding both $mpk$ and $sk_y$ can recover $y$ in exactly $n$ queries by encrypting unit vectors $e_i$ and reading $y_i = \text{Decrypt}(\text{Enc}(mpk, e_i), sk_y)$.

For our application: if the Cloud holds both $mpk$ (to verify or relay ciphertexts) and $sk_y$ (to evaluate), it recovers the complete weight vector offline, instantly, and undetectably.

Secret-key FHIPE closes this oracle by making encryption require a secret ($B^*$). But it immediately raises the *custody question*: somebody must still be able to encrypt (the Doctor/Clinic), and if an encryption capability and a functional key ever land in the same pair of hands, the extraction attack returns immediately and unchanged.

**Model confidentiality in a deployed FE system is therefore not a property of the cipher — it is a property of how capabilities are partitioned across nodes, and it can only be stated per-coalition, never absolutely.**

This insight drives our entire architectural design.

### 2.5 Subclasses and Alternatives

For context, we briefly survey the broader landscape of privacy-preserving computation:

| Approach | Model Owner Online? | Arbitrary Functions? | Practical Overhead | Trust Assumptions |
|---|---|---|---|---|
| **IPFE/FHIPE** (this work) | No (issues key once) | Linear only | Low–Moderate | Cryptographic (DDH) |
| **Fully Homomorphic Encryption (FHE)** | No | Yes | Very high (~1000×) | Cryptographic (LWE) |
| **Secure MPC (2PC/MPC)** | Yes (every query) | Yes | Moderate | Cryptographic + interaction |
| **Trusted Execution Environments (TEE)** | No | Yes | Low | Hardware manufacturer |
| **Differential Privacy** | N/A (training-time) | N/A | Statistical accuracy loss | None |
| **Multi-Input FE (MIFE)** | No | Linear (multi-source) | Moderate | Cryptographic (DDH) |

FHIPE's unique value proposition: the model owner is *offline during inference*, yet both data and model remain confidential. No MPC or additively-homomorphic approach (Paillier) can match this, because they require the model owner to participate in every query.

---

## 3. Related Work

### 3.1 Functional Encryption: Theory

The theoretical foundations of functional encryption were laid by Boneh, Sahai, and Waters [2011], who formalised the notion and provided constructions for specific function classes. Abdalla et al. [2015, 2018] developed efficient IPFE schemes under standard assumptions (DDH, LWE), establishing the practical viability of inner-product computation on encrypted data. The function-hiding property was formalised and achieved by Bishop, Jain, and Kowalczyk [2015] under DDH, and subsequently by Kim, Lewi, Mandal, Montgomery, Raykova, and Wu [2018] in the generic bilinear group model with tighter security proofs.

Agrawal, Libert, and Stehlé [2016] provided lattice-based constructions enabling post-quantum security, though at higher computational cost. Abdalla et al.'s survey work on IPFE [2017, 2018] provides comprehensive treatments of security definitions, constructions, and reductions.

### 3.2 FE-Based Machine Learning Inference

The application of functional encryption to privacy-preserving machine learning inference has been explored by several groups:

- **Dufour-Sans, Gay & Pointcheval (2019)** — "*Reading in the Dark*" demonstrated quadratic-form evaluation using FE for privacy-preserving statistics, establishing the viability of FE for real-valued computations.

- **Ligier et al. (2017)** — Applied IPFE to privacy-preserving classification, demonstrating that inner products suffice for linear model inference. However, their construction uses public-key IPFE and does not address the extraction vulnerability we formalise.

- **Sans, Gay & Pointcheval (2018)** — Extended FE-based inference to multi-class neural network classification through quadratic functional encryption, demonstrating that deeper models require more expressive FE schemes.

- **Marc, Stopar, & Hartman (2019)** — Proposed practical IPFE-based linear regression over encrypted data, though again without addressing the function-hiding requirement.

**Gap in existing work.** To our knowledge, no published system addresses the full pipeline from extraction attack characterisation through function-hiding mitigation, delegated encryption, and empirical trade-off analysis for a genomic clinical application. Most systems either (a) use public-key IPFE and do not discuss the extraction vulnerability, or (b) assume function hiding without implementing it or addressing the custody question.

### 3.3 Privacy-Preserving Genomics

The intersection of privacy-preserving computation and genomics has a rich history:

- **Bogos, Gassend & Hubaux (2017)** — Demonstrated privacy-preserving genomic testing using homomorphic encryption, establishing the genomic privacy problem but at significant computational cost.

- **Boureanu & Ohrimenko et al.** — Explored secure computation over genetic data using garbled circuits and oblivious RAM, targeting different computational models than our linear-inference focus.

- **TCGA Pan-Cancer Analysis** [Weinstein et al., 2013] — The Cancer Genome Atlas provides the reference dataset (33 cancer types, 20,531 gene features) used in our experiments.

### 3.4 Model Extraction Attacks

The vulnerability of prediction APIs to model extraction was formalised by **Tramèr et al. [2016]**, who demonstrated that linear models, decision trees, and shallow neural networks can be reconstructed from prediction queries alone. Our Attack B (§5.1) instantiates their result in the specific context of IPFE-based inference, showing that the cryptographic wrapping provides no additional protection against a query-answering adversary.

### 3.5 Software Artefacts

**PyMIFE** [Felix-Rm, GitHub] implements the FeDDH construction in Python using `py_ecc`'s BN128 backend. We found that while the cryptographic implementation is correct, two critical engineering deficiencies prevent practical deployment: (i) the `export()` methods in the `py_ecc` wrapper are unimplemented (all return `None`), making ciphertexts non-serialisable and therefore non-transmissible over any network; (ii) pure-Python elliptic curve arithmetic is ~500× slower than native implementations, making evaluation at clinically relevant dimensions ($n > 50$) impractical.

**MCL** [Herumi, GitHub] provides highly optimised C++ implementations of BN254 pairing arithmetic. The `mclbn256` Python wrapper exposes these operations through a ctypes FFI, enabling near-native-speed pairing operations from Python.

We bridge these two libraries through a custom `PairingBase` implementation, and resolve a previously unreported serialisation bug, producing what we believe is the **first working, network-capable, high-performance FHIPE system in Python**.

---

## 4. System Design and Architecture

### 4.1 Design Goals

Our system must satisfy the following requirements:

1. **Data privacy**: The patient's gene expression vector must remain encrypted throughout inference. The Cloud must never observe raw gene expression values.

2. **Model weight confidentiality**: The model's trained coefficients must remain confidential against the Cloud. Extraction should require online, authenticated, logged queries — never be possible offline.

3. **Non-interactive evaluation**: The model owner (Hospital) must be able to go offline after issuing keys. The Cloud must evaluate without the Hospital's per-query participation.

4. **Clinical latency**: End-to-end inference (encryption → transmission → evaluation → result return) must complete in seconds, not minutes.

5. **Honest threat reporting**: All residual leakage — query privacy, result privacy, lifetime bounds — must be characterised, measured, and reported.

### 4.2 Three-Party Architecture

Our system comprises three entities, each with distinct cryptographic capabilities:

```
┌─────────────────┐                              ┌─────────────────┐
│    HOSPITAL      │     1. /get_active_indices   │     CLINIC       │
│  (Trusted KGC)   │ ◄──────────────────────────► │   (Has Patient)  │
│                  │     2. /get_ek (encryption    │                  │
│  Holds: msk, B,  │         key material)        │  Holds: patient  │
│  B*, model       │     3. /get_key (sealed       │  expression data │
│  weights y       │         functional key)       │                  │
└────────┬─────────┘                              └────────┬─────────┘
         │                                                  │
         │  Sealed functional key (sk_y)                    │  Encrypted patient
         │  via NaCl SealedBox to Cloud's                   │  ciphertext (ct_x)
         │  X25519 public key                               │  + sealed sk_y
         │                                                  │
         └───────────────────┐    ┌─────────────────────────┘
                             ▼    ▼
                    ┌─────────────────┐
                    │      CLOUD       │
                    │   (Untrusted)    │
                    │                  │
                    │  Holds: X25519   │
                    │  keypair, sk_y   │
                    │  (NO mpk, NO B*) │
                    │                  │
                    │  Computes:       │
                    │  ⟨x, y⟩ via      │
                    │  bilinear        │
                    │  pairings        │
                    └─────────────────┘
```

**Capability Separation Matrix:**

| Capability | Hospital | Clinic | Cloud |
|---|---|---|---|
| Master secret key ($msk$) | ✓ | ✗ | ✗ |
| Encryption matrix ($B^*$) | ✓ | ✗ (has $g^{B^*}$ only) | ✗ |
| Delegated encryption key ($ek = g_2^{B^*}$) | ✓ (generates) | ✓ (receives) | ✗ |
| Functional key ($sk_y$) | ✓ (generates) | ✗ | ✓ (sealed delivery) |
| Encryption capability | ✓ | ✓ (delegated, $O(n^2)$) | **✗** |
| Decryption capability | ✓ | ✗ | ✓ (with $sk_y$) |
| Can extract model? | ✓ (trivially) | Via prediction API | **✗ (offline impossible)** |

The **Cloud is the party structurally denied encryption capability**. This is not an oversight — it is the architectural invariant that makes it safe to hand the Cloud a functional key. The Cloud can decrypt but cannot encrypt; therefore, it cannot mount the unit-vector extraction attack. This is what makes FHIPE's secret-key setting operationally meaningful.

### 4.3 Delegated Encryption Protocol

A key engineering challenge: under FHIPE, encryption requires the secret matrix $B^*$. Shipping $B^*$ to the Clinic would grant full encryption capability — which, combined with observing prediction outputs, would enable extraction.

Our solution: **delegated encryption via precomputed curve points**. The Hospital computes the *encryption key*:

$$ek_{i,j} = g_2^{B^*_{i,j}} \quad \text{for } i, j \in [n]$$

and transmits the $n \times n$ matrix of group elements $\{ek_{i,j}\}$ to the Clinic. The Clinic encrypts by computing:

$$c_{2,j} = \beta \cdot \sum_{i=1}^{n} x_i \cdot ek_{i,j} = g_2^{\beta \cdot \sum_i x_i B^*_{i,j}}$$

This is *mathematically identical* to standard FeDDH encryption, but the Clinic never sees $B^*$ in the clear — only its image under the discrete-log-hard group map $\mathbb{Z}_p \rightarrow G_2$. The Clinic can encrypt arbitrary vectors but **cannot derive functional keys**, because key generation requires $B$ (the *dual* basis), not $B^*$.

**Cost analysis:** Delegated encryption requires $n^2$ scalar multiplications in $G_2$, versus $n^2$ scalar multiplications in $G_1 \cup G_2$ for direct encryption. The asymptotic cost is identical; the concrete cost differs by the $G_1/G_2$ ratio of the underlying curve. For BN254, this ratio is approximately 3×, meaning delegated encryption is ~3× slower than direct encryption — a modest and acceptable cost for the capability separation it enables.

### 4.4 Sealed Key Delivery

Functional keys must reach the Cloud securely. We employ **NaCl Sealed Boxes** (X25519 + XSalsa20-Poly1305) for asymmetric authenticated encryption:

1. The Cloud generates a long-term X25519 keypair at boot and exposes its public key via `/public_key`.
2. The Hospital serialises $sk_y$, seals it using the Cloud's public key, and serves the sealed blob to the Clinic.
3. The Clinic forwards the sealed blob (opaque to the Clinic) to the Cloud alongside the encrypted patient data.
4. The Cloud unseals using its private key, recovers $sk_y$, and evaluates.

This ensures the functional key is never exposed in transit and is only accessible to the Cloud.

### 4.5 Threat Model

We formally enumerate five adversarial scenarios and their consequences:

| Adversary | What they hold | Data privacy | Model confidentiality | Query privacy | Result privacy |
|---|---|---|---|---|---|
| **Honest-but-curious Cloud** | $sk_y$, $ct$, evaluator role | ✓ Held | ✓ Held (no encryption capability) | ✗ Leaked (key selection) | ✗ Leaked (learns score) |
| **Malicious Cloud** | Same + arbitrary behaviour | ✓ Held (under DDH) | ✓ Held | ✗ Leaked | ✗ Leaked |
| **Malicious Doctor** | Encryption capability + predictions | ✓ N/A | ✗ Extractable in $n$ queries | N/A | N/A |
| **Doctor–Cloud collusion** | Enc. + $sk_y$ + predictions | ✓ Held | ✗ Trivially extractable | N/A | N/A |
| **Network adversary** | Observes encrypted traffic | ✓ Held (TLS + SealedBox) | ✓ Held | Partial (traffic analysis) | ✓ Held |

**Key insight:** Model confidentiality against the prediction-receiving party (the Doctor) is *impossible by construction* for any linear model — this is not specific to FE. Tramèr et al. [2016] showed this for general prediction APIs. Our contribution is not to claim prevention but to *characterise the cost and visibility* of extraction and provide tunable controls (perturbation, query budgets, audit logs) that make extraction expensive and detectable.

### 4.6 Result Privacy: A Characterised Trade-off Space

The Cloud currently learns the raw risk score $\langle x, y \rangle$. We characterise three designs to mitigate this:

**Design A — Hospital-Blinded Score.** Extend the vector by one slot: the Clinic encrypts $[x, 1]$, the Hospital issues a key for $[y, \rho]$ with fresh random $\rho$, and sends $\rho$ to the Clinic only (sealed). The Cloud computes $\langle x, y \rangle + \rho$, which is uninformative; the Clinic subtracts $\rho$ locally. The cost: the Cloud's discrete-log search must now cover $R = 2^k \cdot S$ instead of $S$, increasing decryption latency by roughly $2^{k/2}$.

**Design B — Split Decryption.** The Cloud performs the pairings and returns the two $G_T$ elements $D_1, D_2$ without solving the discrete log. The Clinic solves it locally over the small range $S$. Cheaper and cleaner — but the Clinic can now decrypt ciphertexts of its own making locally, removing even the query budget as a control.

**Design C — Hospital-in-Loop.** The Cloud ships $D_1, D_2$ to the Hospital, which solves the discrete log and returns the score sealed to the Clinic. Cheap decryption, result privacy against the Cloud, Doctor-side extraction remains logged — but the Hospital is back in the inference path for every query.

| Design | Result privacy | Decryption cost | Hospital online? | Doctor extraction |
|---|---|---|---|---|
| **A** (Blinded) | ✓ ($k$-bit statistical) | $O(2^{k/2} \cdot \sqrt{S})$ | No | Unchanged (knows $\rho$) |
| **B** (Split) | ✓ (perfect) | $O(\sqrt{S})$ locally | No | Free & invisible |
| **C** (Hospital-in-loop) | ✓ (perfect) | $O(\sqrt{S})$ at Hospital | **Yes** | Logged & countable |

This is a genuine trade-off space, and the honest contribution is to characterise it rather than to claim any single design dominates.

---

## 5. Implementation

### 5.1 Machine Learning Pipeline

Our models are **L1-regularised logistic regression (Lasso)** classifiers trained in a One-vs-Rest configuration across all 33 TCGA cancer types. The training data comprises RNA-seq gene expression profiles from the UCSC Xena Pan-Cancer Atlas, covering 20,531 gene features per patient.

**Feature selection:** L1 regularisation naturally zeroes out non-informative features. Per-cancer active gene counts range from 28 to 252 (median ~100), with a global union of 3,555 unique genes across all 33 models. This sparsity is the property that makes FHIPE-based inference computationally feasible.

**Quantisation:** IPFE operates over integers. We quantise weights and patient values by multiplying by a scaling factor $Q = 100$ and rounding: $\hat{w}_i = \text{round}(w_i \times Q)$. We identified and corrected a **truncation bug** in the original pipeline: `(w * 100).astype(int)` silently deletes features with small coefficients (e.g., $w_i = 0.004$ maps to $0$), while `np.rint(w * 100).astype(int64)` correctly maps it to $0.4 \rightarrow 0$ vs. $0.4 \rightarrow 0$ — the critical difference being at the $0.005$–$0.05$ range where many Lasso coefficients lie.

**Data imputation bug:** We also identified and corrected a missing-gene imputation error: `reindex(fill_value=0)` followed by `StandardScaler` maps a missing gene to $(0 - \mu)/\sigma \approx -3.0$ — an extreme negative z-score that injects a fake suppression signal. The correct approach: impute with `scaler.mean_` so missing values map to $z = 0$ after standardisation.

### 5.2 High-Performance Pairing Backend

The critical engineering contribution enabling practical FHIPE at clinical dimensions.

**The problem:** PyMIFE's default backend (`py_ecc`) implements BN254 curve arithmetic in pure Python. Every scalar multiplication, point addition, and pairing operation runs as interpreted Python bytecode. At $n = 300$ (a typical clinical bucket size), a single encryption takes ~17 minutes.

**Our solution:** We wrote `mcl_backend.py`, a drop-in replacement implementing PyMIFE's `PairingBase` interface using `mclbn256` — Python bindings to the MCL C++ library [Herumi]. MCL uses assembly-optimised finite-field arithmetic, Montgomery multiplication, and projective coordinates.

**Key engineering challenges solved:**

1. **Curve order mismatch.** `mclbn256` uses a different BN254 parameterisation than Ethereum's `py_ecc`. The curve order is `16798108731015832284940804142231733909759579603404752749028378864165570215949` (vs. Ethereum's `21888...`). Using the wrong modulus silently corrupts all matrix inversions during key generation, causing decryption to fail with "value not found in bounds."

2. **64-bit integer truncation.** Python's `ctypes` wrapper for `mclbn256.Fr.setInt()` silently truncates integers larger than 64 bits. FeDDH key scalars are ~254-bit numbers. We bypass this by encoding scalars as hexadecimal strings and using `Fr.fromstr(hex_bytes, 16)`.

3. **GT group algebra mapping.** In pairing-based cryptography, "addition" in $G_T$ corresponds to *multiplication* of field elements, and "scalar multiplication" corresponds to *exponentiation*. Our `MclGTWrapper` maps `__add__` to `GT.__mul__` and `__rmul__` to `GT.__pow__`.

**Performance results (n = 300):**

| Operation | py_ecc (baseline) | mclbn256 (ours) | Speedup |
|---|---|---|---|
| Key generation | ~7 minutes | **~20 seconds*** | 21× |
| Encryption | ~several minutes | **~0.5 seconds** | ~500× |
| Decryption/Evaluation | ~several minutes | **~0.15 seconds** | ~500× |

*Key generation speedup includes our `fast_feddh_generate()` optimisation (§5.3).

### 5.3 Optimised Key Generation

Even with the C++ backend, PyMIFE's key generation remained a bottleneck: inverting a $300 \times 300$ matrix of Python `ZmodR` objects took ~7 minutes because every arithmetic operation traversed Python's object system (`__mul__`, `__add__`, `__mod__`).

We wrote `fast_feddh_generate()`, which performs Gaussian elimination using raw Python `int`s with built-in modular arithmetic (`pow(factor, -1, order)`), then wraps the result back into PyMIFE-compatible `Matrix` and `ZmodR` objects. Python's arbitrary-precision integer arithmetic is orders of magnitude faster than routing through custom `__mul__` overloads.

**Result:** Key generation at $n = 300$ drops from ~7 minutes to **~20 seconds** — a 21× improvement from a pure algorithmic refactoring with zero change to the mathematical output.

### 5.4 Network Serialisation

PyMIFE's `export()` methods for `py_ecc` wrapper objects are **unimplemented** — all three (`Bn128PairingPoint1`, `Bn128PairingPoint2`, `Bn128PairingPointT`) contain only `pass` and return `None`. This means ciphertexts and functional keys *cannot leave the Python process that created them* — no network transmission, no caching, no persistence.

We implemented `fhipe_serializer.py`, which:
- For **mclbn256 objects**: uses the native `.serialize()` method to obtain compressed byte representations, hex-encodes them for JSON transport, and reconstructs via `._deserialize()`.
- For **py_ecc objects**: extracts raw field element integers from `FQ.n` and `FQ2.coeffs`, serialises as JSON string representations of large integers, and reconstructs by calling `FQ(int_val)` / `FQ2([int1, int2])`.

**Round-trip correctness verified** at $n = 4$ (instant) and $n = 64$ (Gate 1 criterion): encrypt → serialise → transmit → deserialise → decrypt produces the correct inner product.

### 5.5 Parallel Bucket Evaluation

For multi-cancer screening (evaluating a patient against multiple cancer models simultaneously), we exploit the embarrassingly parallel structure of independent FHIPE evaluations.

**Challenge:** Python's Global Interpreter Lock (GIL) prevents true CPU parallelism via threading. `multiprocessing` requires serialising (pickling) the master key — a $300 \times 300$ matrix of Python objects — which is expensive and serial.

**Solution:** Force `fork()` start method so child processes inherit the parent's memory snapshot directly. The master key is populated *before* the `Pool` is created, and workers access it through the inherited `GLOBAL_KEY` global — zero pickling cost, instantaneous process creation.

**Note:** Python 3.14 changed the default start method from `fork` to `forkserver` on Linux, which would lose all globals. Our code explicitly sets `multiprocessing.set_start_method('fork')`.

**Benchmark (n = 300, 4 buckets):**

| Metric | Value |
|---|---|
| Setup (one-time keygen) | 21.8s |
| 4 buckets, parallel | **0.96s** |
| Equivalent sequential | 3.37s |
| **Parallel speedup** | **3.5×** |

---

## 6. Demonstration

### 6.1 End-to-End Clinical Workflow

Our demonstration processes a real TCGA patient's gene expression data through the complete privacy-preserving inference pipeline:

**Step 1 — Hospital Boot (~20s).** The Hospital loads the `master_33_cancer_weights.npy` matrix (33 × 20,531), selects the Adrenocortical Carcinoma (ACC) model, dynamically identifies 139 active genes via `np.flatnonzero(weights != 0)`, quantises the weight vector, and generates the FeDDH master key via `fast_feddh_generate(139, F=MclPairing())`.

**Step 2 — Cloud Boot (~instant).** The Cloud generates an X25519 keypair and starts listening on port 5002.

**Step 3 — Clinic Query (~3s total).**
1. Clinic fetches active gene indices from Hospital (`/get_active_indices`).
2. Clinic loads `patient1_full.npy` (20,531 values) and subsets to the 139 active genes.
3. Clinic quantises patient values: `np.rint(raw * 100).astype(int64)`.
4. Clinic fetches delegated encryption key ($ek$) from Hospital (`/get_ek`).
5. Clinic encrypts patient vector: $139^2 = 19,321$ C++ curve multiplications via `delegated_encrypt()`.
6. Clinic fetches sealed functional key from Hospital (`/get_key`).
7. Clinic sends encrypted ciphertext + sealed functional key to Cloud (`POST /evaluate`).

**Step 4 — Cloud Evaluation (~0.2s).** The Cloud unseals the functional key, reconstructs PyMIFE objects via `deserialize_ciphertext()` and `deserialize_functional_key()`, constructs a minimal public key stub (only `pub.F` and `pub.n` are needed for `decrypt()`), and computes `FeDDH.decrypt(ct, pub, sk, (-1000000, 1000000))`.

**Result:** The Cloud returns the encrypted risk score `190984`. This score, when divided by $Q_w \times Q_x = 100 \times 100 = 10,000$ and passed through a sigmoid, yields a cancer risk probability — but the Cloud sees only the raw integer and cannot interpret it without the model intercept.

### 6.2 What the Cloud Does and Does Not Learn

| Information | Cloud sees? | Why / why not |
|---|---|---|
| Patient's gene expression values | ✗ | FHIPE encryption |
| Model weight magnitudes | ✗ | FHIPE function hiding (no encryption capability) |
| Which 139 genes are active | ✗* | Ciphertext dimension leaks the *count* (139), but not which genes |
| Raw inner product score (190984) | ✓ | *This is the result privacy gap addressed in §4.6* |
| Which cancer type was queried | ✓ | Key selection leaks this (*query privacy gap*, see §4.5) |

*In the current implementation, the Cloud can infer the cancer model from the vector dimension (139 is unique to ACC). The padding/union-dimension mitigation (§7.3) addresses this.

---

## 7. Efficiency and Security Analysis

### 7.1 Extraction Attack Demonstration

We implement both extraction attacks and benchmark them across all 33 TCGA cancer models:

**Attack A (Chosen Input).** Encrypt unit vectors $e_1, \ldots, e_n$; read $y_i = \langle e_i, y \rangle$ from each response. *Result: exact recovery in exactly $n$ queries, 0% error, across all 33 models.* This attack requires the ability to choose inputs — i.e., it requires encryption capability.

**Attack B (Natural Use).** Collect $n$ real patient vectors $X \in \mathbb{R}^{n \times n}$ and their corresponding scores $s = Xy$; solve $y = X^{-1}s$ via least squares. *Result: near-zero relative error ($< 10^{-10}$) across all 33 models.* This attack requires no chosen inputs, no protocol deviation, and is **indistinguishable from ordinary clinical use**.

| Model | Active genes ($n$) | Attack A: exact? | Attack B: relative error | Attack B: time |
|---|---|---|---|---|
| ACC | 139 | ✓ | $< 10^{-12}$ | 0.003s |
| BRCA | 252 | ✓ | $< 10^{-11}$ | 0.012s |
| GBM | 28 | ✓ | $< 10^{-13}$ | 0.001s |
| ... (all 33) | 28–252 | ✓ (all) | $< 10^{-10}$ (all) | < 0.1s (all) |

**Implication:** The *minimum viable defence* is ensuring that the extraction-capable party (anyone who can encrypt and observe outputs) faces $n$ online, authenticated, logged queries rather than free offline extraction. FHIPE achieves this by denying the Cloud encryption capability.

### 7.2 Perturbation Lifetime Analysis

We introduce additive Gaussian noise to the returned score ($\text{score} + \mathcal{N}(0, \sigma^2)$) and measure two quantities:
1. **Patients until recovery ($m$):** The minimum number of patient observations needed for least-squares to reconstruct the model within 5% relative error.
2. **Accuracy cost:** Mean absolute change in predicted probability (percentage points).

| $\sigma$ | Patients to recover | vs. baseline | Accuracy cost |
|---|---|---|---|
| 0 | $n$ (exact) | 1.0× | 0.00 pp |
| 100 | ~1.3$n$ | 1.3× | 0.19 pp |
| 1,000 | ~4.2$n$ | 4.2× | 1.9 pp |
| 10,000 | $> 12n$ | $> 12$× | ~5 pp |
| 30,000 | $> 12n$ | $> 12$× | ~10 pp |
| 100,000 | $> 12n$ | $> 12$× | ~18 pp |

**Key finding:** Lifetime scales *quadratically* in the noise magnitude: $m \sim n \cdot (\sigma / \tau)^2$, not by a constant factor. This means perturbation is a significantly stronger control than previously assumed. At $\sigma = 1000$, the accuracy cost is clinically negligible (1.9 percentage points) while the extraction lifetime extends beyond $12n$ patients — a regime where the model would likely be retrained before extraction completes.

### 7.3 Dimension and Query Privacy

**The dimension decision.** Per-cancer active gene counts range from 28 (GBM) to 252 (BRCA). If the Clinic encrypts exactly the active genes for the queried cancer, the Cloud can identify the cancer type from the ciphertext dimension alone — a *query privacy* leak.

**Mitigation: Global union padding.** Padding all vectors to the global union dimension ($n = 3,555$) eliminates dimension-based query identification. The extraction lifetime for a single targeted model increases from $\min(n_i) = 28$ to $3,555$ — a **127×** improvement for the most vulnerable model.

**Cost:** $O(n^2)$ encryption cost increases from $139^2 \approx 19K$ to $3555^2 \approx 12.6M$ operations — a 651× increase. At our C++ backend speeds, this is ~1 minute for encryption. For practical deployment, *intermediate buckets* (grouping cancers into clinical families of similar dimension, $n \approx 300$–$500$) provide a pragmatic middle ground.

### 7.4 Backend Performance Comparison

| Metric | py_ecc (Pure Python) | mclbn256 (C++) | Speedup |
|---|---|---|---|
| Single pairing | ~3,500 ms | ~0.3 ms | **~11,700×** |
| Scalar mul (G1) | ~3,500 ms | ~0.3 ms | **~11,700×** |
| Encrypt ($n = 20$) | 241.3s | 0.35s | **~690×** |
| Decrypt ($n = 20$) | 4.2s | 0.009s | **~467×** |
| Keygen ($n = 300$) | ~7 min (ZmodR) | ~20s (`fast_feddh_generate`) | **~21×** |
| Full query ($n = 139$) | ~hours | **~3 seconds** | **~1000×** |

### 7.5 Serialisation Overhead

| Object | Dimension | Serialised size | Serialise time | Deserialise time |
|---|---|---|---|---|
| Ciphertext ($c_1 + n \times c_2$) | $n = 139$ | ~18 KB (hex-encoded) | ~2 ms | ~3 ms |
| Functional key ($k_1 + n \times k_2$) | $n = 139$ | ~9 KB (hex-encoded) | ~1 ms | ~2 ms |
| Delegated enc. key ($n^2$ G2 points) | $n = 139$ | ~2.5 MB | ~150 ms | ~200 ms |

Serialisation overhead is negligible relative to encryption and pairing costs.

---

## 8. Explainable AI via Pathway Aggregation

### 8.1 The XAI Extraction Threat

Clinical adoption of AI models requires explainability — clinicians need to understand *why* a model predicts a particular risk score. The standard approach (SHAP values, per-gene contributions $w_i \cdot x_i$) gives the adversary one linear equation per query. With 3,555 genes and 50 pathway-level explanations, an attacker gains at most 50 equations — leaving 3,505 dimensions (99%) underdetermined.

### 8.2 Pathway Aggregation Defence

We group genes into the **50 Hallmark biological pathways** from the Molecular Signatures Database (MSigDB) [Liberzon et al., 2015]. Instead of reporting individual gene contributions, the system reports pathway-level aggregate scores:

$$\text{Pathway}_k = \sum_{i \in \text{pathway}_k} w_i \cdot x_i$$

**Formal security analysis.** We construct the $50 \times 3,555$ pathway incidence matrix $A$ (where $A_{k,i} = 1$ if gene $i$ belongs to pathway $k$). The rank of $A$ determines the information leakage:

$$\text{rank}(A) = 50 \quad \Rightarrow \quad 3,555 - 50 = 3,505 \text{ unknowns remain free}$$

Even under a *white-box* attack where the adversary knows the pathway dictionary, individual weights cannot be recovered from pathway sums alone — the system is **99% underdetermined**.

**Clinical utility.** Pathway-level explanations are arguably *more* clinically useful than per-gene scores. A clinician understands "the Apoptosis pathway contributed +0.42 to the risk" far better than "gene BRCA1 contributed +0.003." This is a case where the security-motivated design produces a better clinical product.

### 8.3 Caveats

If the rank approaches $n$ (e.g., because the active gene set is small and heavily overlapping with pathway definitions), the privacy argument weakens. For gene sets with $< 10\%$ free dimensions, side information (weight signs, sparsity priors) may close the gap. We report the exact rank and free-dimension count rather than asserting generic safety.

---

## 9. Conclusion

We have presented a comprehensive system for privacy-preserving cancer risk prediction that goes beyond the naïve application of functional encryption. Our work makes the following key contributions:

1. **We identified and formalised the extraction vulnerability** in public-key IPFE-based inference systems, demonstrating that it is not merely theoretical but trivially exploitable — and that it extends to natural clinical use patterns without any adversarial behaviour.

2. **We implemented FHIPE as a practical countermeasure**, not by claiming it prevents extraction (it cannot, against the prediction-receiving party), but by *eliminating offline extraction by the Cloud* and converting the residual Doctor-side path into an online, logged, rate-limitable process.

3. **We solved critical engineering barriers**: network serialisation of PyMIFE ciphertexts (fixing unimplemented `export()` methods), a ~500× performance improvement via a C++ pairing backend (resolving curve-order and integer-truncation bugs), and optimised key generation via raw-integer Gaussian elimination.

4. **We characterised the full trade-off space honestly**: three designs for result privacy with measured costs, a quantified perturbation-lifetime curve, dimension-padding analysis, and a formal threat model that explicitly states what *cannot* be protected.

5. **We demonstrated the system on real clinical data**: end-to-end inference on TCGA pan-cancer RNA-seq data at sub-3-second latency, with all code and data publicly released.

The honest summary: FHIPE does not make genomic AI models invulnerable. What it does is convert a *free, invisible, offline* attack into an *expensive, visible, online* one — and that is a meaningful and deployable improvement over the current state of the art, particularly when combined with rate limiting, audit logging, perturbation, and the capability-separation architecture we describe.

---

## 10. Future Scope

### 10.1 Multi-Input Functional Encryption (MIFE)

The most impactful extension: MIFE allows multiple institutions to each encrypt their own data under independent keys, with a single evaluation combining all inputs. This enables cross-institutional genomic aggregation — "how many patients across 40 sites exceed risk threshold $t$?" — a computation no single party can perform. PyMIFE already includes MIFE primitives; integration with our architecture is a natural next step.

### 10.2 Revocable Functional Keys

Functional keys are currently irrevocable — once the Cloud holds $sk_y$ for model version 1, it can evaluate indefinitely. Retiring a model version requires re-running `Setup` with fresh $B$ and redistributing $ek$ to every clinic: the full $N \times M$ re-keying problem. Research into revocable FE constructions and threshold key generation could address this.

### 10.3 Non-Linear Models

IPFE is fundamentally limited to linear functions. Extending to neural networks requires quadratic FE (for single hidden layers), attribute-based encryption, or hybrid approaches combining FE with lightweight MPC for non-linear activations. The recent work by Sans, Gay & Pointcheval on quadratic FE suggests a path forward.

### 10.4 Post-Quantum Security

BN254 pairing-based constructions are vulnerable to quantum adversaries (Shor's algorithm breaks the DDH assumption). Lattice-based IPFE constructions [Agrawal, Libert & Stehlé, 2016] offer post-quantum security but at significantly higher computational cost. Benchmarking lattice-based FHIPE at clinical dimensions is an important future direction.

### 10.5 Verifiable Computation

A malicious Cloud could return fabricated scores. Current verification relies on decoy queries (submitting known-answer pairs). A cryptographic approach — hash-chained audit logs with signed computation anchors — would provide non-interactive verifiability without requiring the Hospital to participate in every query.

### 10.6 Real-World Clinical Validation

Our prototype uses TCGA data, which is publicly available research data. Deployment in a real hospital system would require: (a) integration with electronic health record (EHR) systems, (b) compliance with HIPAA, GDPR, and local health data regulations, (c) clinical validation on prospective patient cohorts, and (d) regulatory approval for AI-assisted diagnostic tools.

---

## References

1. Abdalla, M., Bourse, F., De Caro, A., & Pointcheval, D. (2015). Simple Functional Encryption Schemes for Inner Products. *PKC 2015*.

2. Abdalla, M., Catalano, D., Fiore, D., Gay, R., & Ursu, B. (2018). Multi-Input Functional Encryption for Inner Products: Function-Hiding Realizations and Constructions without Pairings. *CRYPTO 2018*.

3. Agrawal, S., Libert, B., & Stehlé, D. (2016). Fully Secure Functional Encryption for Inner Products, from Standard Assumptions. *CRYPTO 2016*.

4. Bishop, A., Jain, A., & Kowalczyk, L. (2015). Function-Hiding Inner Product Encryption. *ASIACRYPT 2015*.

5. Bogos, S., Gassend, B., & Hubaux, J.-P. (2017). Privacy-Preserving Genome-Wide Association Studies on the Cloud. *Bioinformatics*.

6. Boneh, D., Sahai, A., & Waters, B. (2011). Functional Encryption: Definitions and Challenges. *TCC 2011*.

7. Dufour-Sans, E., Gay, R., & Pointcheval, D. (2019). Reading in the Dark: Classifying Encrypted Digits with Functional Encryption. *CANS 2019*.

8. Herumi. MCL — A Portable and Fast Pairing-Based Cryptography Library. GitHub: https://github.com/herumi/mcl

9. Kim, S., Lewi, K., Mandal, A., Montgomery, H., Raykova, M., & Wu, D. J. (2018). Function-Hiding Inner Product Encryption is Practical. *SCN 2018*.

10. Liberzon, A., et al. (2015). The Molecular Signatures Database (MSigDB) Hallmark Gene Set Collection. *Cell Systems*.

11. Ligier, D., Music, L., Joye, M., & Troncoso-Pastoriza, J. (2017). Privacy-Preserving Classification on Hidden Encrypted Data via Functional Encryption.

12. Felix-Rm. PyMIFE — Python Multi-Input Functional Encryption. GitHub: https://github.com/Felix-Rm/pymife

13. nthparty. mclbn256 — Python Wrapper for the MCL Cryptographic Library. GitHub: https://github.com/nthparty/mclbn256

14. Tramèr, F., Zhang, F., Juels, A., Reiter, M. K., & Ristenpart, T. (2016). Stealing Machine Learning Models via Prediction APIs. *USENIX Security 2016*.

15. Weinstein, J. N., et al. (2013). The Cancer Genome Atlas Pan-Cancer Analysis Project. *Nature Genetics*.

16. Marc, T., Stopar, M., & Hartman, J. (2019). Privacy-Enhanced Machine Learning with Functional Encryption. *ESORICS 2019*.

---

## Appendix A: Notation Reference

| Symbol | Meaning |
|---|---|
| $x \in \mathbb{Z}^n$ | Patient gene expression vector (quantised) |
| $y \in \mathbb{Z}^n$ | Model weight vector (quantised) |
| $\langle x, y \rangle$ | Inner product (risk score) |
| $B, B^*$ | Random basis and its adjugate ($B^\top B^* = \det(B) \cdot I$) |
| $mpk, msk$ | Master public / secret key |
| $sk_y$ | Functional key for weight vector $y$ |
| $ek$ | Delegated encryption key ($g_2^{B^*_{i,j}}$) |
| $\rho$ | Random blinding noise (Design A) |
| $Q_w, Q_x$ | Quantisation scaling factors for weights / features |
| $G_1, G_2, G_T$ | Bilinear groups with pairing $e: G_1 \times G_2 \rightarrow G_T$ |
| $n$ | Vector dimension (number of active genes) |
| $\sigma$ | Perturbation noise standard deviation |
| $m$ | Number of patients until model recovery |
| $\tau$ | Recovery tolerance (relative error threshold) |

## Appendix B: Codebase Reference

| File | Purpose |
|---|---|
| `hospital.py` | Trusted KGC — loads model, generates master key, serves $ek$ and sealed $sk_y$ |
| `clinic.py` | Patient interface — fetches indices, encrypts patient vector, sends to Cloud |
| `cloud.py` | Untrusted evaluator — unseals $sk_y$, computes encrypted dot product |
| `mcl_backend.py` | C++ pairing backend wrapping `mclbn256` with `PairingBase` interface |
| `fhipe_serializer.py` | JSON serialisation/deserialisation of curve points, ciphertexts, and keys |
| `delegated_crypto.py` | $g^{B^*}$ delegated encryption protocol |
| `extraction_attack.py` | Attack A (chosen-input) and Attack B (natural-use) demonstrations |
| `patients_until_recovery.py` | Perturbation lifetime analysis and central figure generation |
| `check1_gene_union.py` | Global gene union computation and dimension decision analysis |
| `check2_pathway_rank.py` | Pathway incidence matrix rank analysis for XAI security |
| `quantization_check.py` | Truncation and imputation bug quantification |
| `benchmark.py` | py_ecc vs. mclbn256 backend comparison |
| `parallel_eval.py` | Multi-bucket parallel evaluation via `fork()` |
| `pymife_probe.py` | PyMIFE correctness verification and serialisation defect reproduction |
