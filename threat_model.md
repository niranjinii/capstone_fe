# Privacy-Preserving Clinical Decision Support: Formal Threat Model

This document outlines the formal security guarantees, adversary models, and cryptographic mitigations of the privacy-preserving cancer diagnosis system.

## 1. System Architecture & Trust Boundaries

The system involves three distinct parties:

1. **Hospital (Key Authority):** Holds the master secret key (MSK) and cleartext model weights. Trusted to issue keys correctly, but untrusted by the patient for viewing raw genomic data.
2. **Clinic (Client):** Holds raw patient data. Fully trusted by the patient, but untrusted by the Hospital (cannot be allowed to extract model weights).
3. **Cloud (Evaluator):** Performs the heavy lifting (encrypted matrix multiplications). Fully untrusted by both parties. Must learn neither the patient's data nor the model weights.

## 2. Adversary Model & Mitigations

| Adversary | Capability | Goal | Mitigation | Owner |
|---|---|---|---|---|
| **Honest-but-curious Cloud** | Has access to ciphertexts, functional keys, and evaluation results. | Learn patient gene expressions. | **Functional Encryption (FE):** Provably reveals *only* the inner product of the vectors. Patient vectors remain semantically secure. | Base System |
| **Honest-but-curious Cloud** | Has access to pathway-level functional keys and pathway scores. | Infer individual gene weights via linear algebra. | **Differential Privacy (DP):** Calibrated Laplace noise ($\epsilon$-DP) is added to pathway scores to prevent exact weight recovery. | Member D |
| **Malicious Cloud** | Full control over server execution. | Fabricate evaluation results or delete past queries to hide malicious activity. | **Merkle Tree Audit Log:** Cryptographically chains all evaluations. <br> **Decoy Verification:** Hospital periodically tests Cloud integrity with known-answer ciphertexts. | Member D |
| **Malicious Doctor / Clinic** | Ability to query pathway explanations repeatedly. | Extract model weights via repeated querying of different sub-vectors. | **Privacy Budget ($\epsilon$ Tracking):** Hospital enforces a hard limit on the total privacy budget a clinic can consume for XAI. | Member D |
| **Malicious Doctor / Clinic** | Ability to request overall functional keys repeatedly. | Extract model weights via Attack B (extraction attack). | **Key Rate Limiter:** Hard cap on total functional keys issued (max $n/2$). | Member C |
| **Network Attacker** | Intercepts traffic between parties. | MITM, replay attacks, data theft in transit. | **NaCl Sealed Boxes & mTLS:** XSalsa20-Poly1305 sealing + mTLS. Replay prevention via UUID and timestamps. | Member C |

## 3. Formal Security Properties

### 3.1 Explainable AI Privacy ($\epsilon$-Differential Privacy)
The pathway explanation module satisfies $\epsilon$-Differential Privacy. The Laplace mechanism adds noise proportional to the sensitivity of the pathway score:
$\Delta f = \max || f(D) - f(D') ||_1$
This ensures that the Cloud's output distribution does not leak the exact underlying weights of the hospital's model, effectively neutralizing partial weight extraction attacks on the XAI interface.

### 3.2 Audit Log Integrity (Tamper-Evidence)
The `MerkleAuditLog` guarantees cryptographic tamper-evidence. It models the ledger as a balanced binary hash tree where every evaluation $E_i$ is a leaf $H(E_i)$.
If the Cloud attempts to fabricate a past score or delete an entry, the Merkle root $R$ changes, instantly failing the integrity verification check ($R' \neq R$). 
Furthermore, the log supports $O(\log n)$ inclusion proofs for efficient partial auditing.

### 3.3 Zero-Knowledge Evaluation (Functional Encryption)
The core encryption relies on the FeDDH (Functional Encryption based on Decisional Diffie-Hellman) scheme. Under the standard DDH assumption, the ciphertext perfectly hides the patient vector $X$, revealing only $\langle X, W \rangle$ upon decryption with the functional key for $W$.

## 4. Limitations & Future Work

While the system is robust against data extraction and tampering, the current threat model explicitly excludes:
- **Side-Channel Attacks:** Timing or power analysis on the Cloud node during FeDDH decryption.
- **Hardware Compromise:** SGX or TrustZone exploits on the hospital server containing the MSK.
- **Model Poisoning:** The current scope assumes the hospital's trained model is benign and accurate.
