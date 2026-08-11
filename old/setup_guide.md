
# Onboarding Guide: Privacy-Preserving Intelligence for Healthcare 5.0
**Project Focus:** Secure Genomic AI Pipeline via Function-Hiding Inner Product Encryption (FHIPE) & Pathway Aggregation  

Welcome to the team! This document covers the core architecture decisions of our capstone, how to configure your WSL environment, what our codebase scripts actually do, and your immediate task: solving our network serialization bottleneck.

---

## 1. Our Architecture Choices & Why We Made Them

Our project executes clinical cancer risk predictions over encrypted high-dimensional genomic data. We are solving a three-part security and systems problem:


```

[Hospital/Client: Input x & Blinder ρ] + [Model Owner: Weights y]
│
▼ (Chunked Parallel FHIPE)
[Cloud Server Computes: <x, y> + ρ across Parallel Buckets]
│
▼ (Blinded Score Transmission)
[Doctor's Laptop: Subtracts ρ Locally]

```

### Choice 1: FHIPE (Function-Hiding Inner Product Encryption) over Standard IPFE
* **The Math:** We compute the inner product $\langle x, y \rangle$ between a patient's gene expression vector $x$ and our L1-regularized Lasso cancer model weights $y$.
* **Why FHIPE:** Standard Functional Encryption only hides the patient's data $x$ while leaving the model weights $y$ exposed to the evaluator. FHIPE encrypts **both** vectors. The Cloud server executes pairings blindly without ever learning the patient's biomarkers or our proprietary weights.

### Choice 2: Design A (Hospital-Blinded Score) over Design B (Split Decryption)
* **The Threat:** Even with FHIPE, if the Cloud learns the final decrypted risk score $\langle x, y \rangle$, it can observe traffic over time and execute an online extraction attack to solve for our weights equation-by-equation (**Roadmap §2.4 / §2.8**).
* **Why Design A:** 
  * The Hospital adds a fresh random blinding number $\rho$ to the setup. The Cloud computes $\langle x, y \rangle + \rho$, which looks like complete mathematical noise to the server.
  * The Doctor receives $\text{score} + \rho$ from the Cloud and subtracts $\rho$ locally.
  * **Why not Design B?** Design B lets the Doctor perform the final discrete-log decryption locally, which strips the Hospital of query logging and usage visibility. Design A keeps computation countable and logged while forcing the Cloud's discrete-log search range to expand from $S$ to $R = 2^k \cdot S$.

### Choice 3: Chunked Parallel FHIPE (Intermediate Buckets)
* **The Bottleneck:** FHIPE key generation and setup matrix inversions scale cubically at $O(n^3)$. Running all 3,555 unique genes across our 33 cancer models in a single monolithic vector freezes execution.
* **The Solution:** We group our 33 cancer models into smaller clinical buckets (e.g., Gastrointestinal, Gynecological, Respiratory), keeping vector sizes around $n = 300\text{--}500$. 
* **The Cubic Win:** Because $(10 \times 300^3)$ is roughly 100 times smaller than $(3000^3)$, Setup becomes feasible. On the current `py_ecc` backend, per-query latency is still ~3.5s × n (i.e., ~17 min at n=300). Gate 1 deliberately sets no latency target — correctness and serialization come first. A native pairing backend (RELIC, MCL, or PBC) is a post-Gate-1 optimization if needed.
* **The Query Privacy Win ($k$-Anonymity):** Evaluating disease models within clinical cohorts ensures the Cloud server cannot determine which specific cancer within a family is being diagnosed.

### Choice 4: Explainable AI via Pathway Aggregation (Roadmap §6)
* **The XAI Threat:** Allowing clinicians to query individual gene contribution scores ($w_i \cdot x_i$) gives an attacker one linear equation per query, leaking the model weights in as few as 28 to 252 queries depending on the cancer model.
* **The Solution:** We group individual genes into **50 Hallmark biological pathways** from the Molecular Signatures Database (MSigDB). The clinician receives functional pathway contributions (e.g., *"Apoptosis Pathway contributed +0.42"*).
* **The Security Proof:** In linear algebra, 50 equations with 3,555 unknown variables leaves **3,505 dimensions (99%) underdetermined**. Even under a white-box attack where the adversary knows the pathway dictionary, the individual weights cannot be mathematically reconstructed.

---

## 2. WSL Environment & Dependency Setup

Since you are running WSL (Ubuntu/Debian Linux), open your terminal and run these exact steps from a clean shell:

### Step 1: Install System Build & Cryptographic Dependencies
We need C-compilers and GNU Multiple Precision Arithmetic (GMP/SSL) headers so our underlying cryptographic engines can build cleanly:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential python3-venv python3-pip python3-dev libssl-dev libgmp-dev git

```

### Step 2: Create and Activate an Isolated Virtual Environment

```bash
mkdir -p ~/healthcare5_capstone && cd ~/healthcare5_capstone
python3 -m venv venv
source venv/bin/activate

```

*(Tip: Always ensure `(venv)` appears in your terminal prompt before installing packages or running scripts.)*

### Step 3: Install Core ML and Cryptography Libraries

```bash
pip install --upgrade pip
pip install --no-cache-dir numpy pandas scipy scikit-learn py_ecc matplotlib
pip install --no-cache-dir pymife

```

*(Note: `pymife` is available directly via PyPI and relies on `py_ecc` for elliptic curve pairings.)*

---

## 3. Roadmap & Codebase Reference Directory

Below is the directory of scripts and files you will be working with, mapped directly to our architectural document (`FE_Genomic_AI_Roadmap.pdf`):

| File Name | Roadmap Section | Purpose & What It Tests |
| --- | --- | --- |
| `Capstone_Final.ipynb` | **§1 (ML Baseline)** | Trains L1-regularized OneVsRest Lasso models across TCGA/Xena data; outputs sparse cancer feature weights. |
| `master_33_cancer_weights.npy` | **§1 (ML Baseline)** | The pre-computed matrix containing all 33 sparse cancer weight vectors (3,555 total active genes). |
| `extraction_attack.py` | **§2.4 (Attack B)** | Simulates a malicious Cloud observing unblinded scores; proves weights can be solved equation-by-equation. |
| `patients_until_recovery.py` | **§2.8 / §4 (Query Budget)** | Calculates the exact mathematical query threshold required for an attacker to reconstruct each cancer model. |
| `h.all.v2026.1.Hs.symbols.gmt` | **§6 (XAI Defense)** | The biological dictionary of 50 Hallmark gene sets from MSigDB used to group genes into functional pathways. |
| `check2_pathway_rank.py` | **§6 (XAI Defense)** | Builds the $(50 \times 3555)$ incidence matrix and proves rank-deficiency (rank 50, leaving 3,505 free unknowns). |
| `pymife_probe.py` | **§3 / Systems Gap** | Diagnostics script that confirms library bottlenecks: verifies `py_ecc` latency and tests ciphertext pickling. |

---

## 4. Your Primary Focus: The Network Serialization Mission

Our Cloud architecture requires sending encrypted patient vectors ($x$) and encrypted model weights ($y$) over network sockets between client machines and the backend server.

### The Problem (`pymife` Serialization Bug)

When you run `pymife_probe.py`, you will see that Python's `pickle` module throws an exception when attempting to serialize a `pymife` ciphertext object.

* **Root Cause:** The three `export()` methods in `mife/data/pyecc_bn128_wrapper.py` (lines 61, 85, 109) are all `pass` — they return `None`. The abstract base class in `mife/data/group.py` declares them, but they were never implemented for the `py_ecc` backend.
* **The Impact:** Without serialization, ciphertexts cannot be converted into byte-streams for network transmission or caching.

### What You Are Actually Serializing

From `mife/single/fhiding/ddh.py`, FeDDH produces three object types:

| Object | Class | Contains |
| --- | --- | --- |
| **Ciphertext** | `_FeDDH_C` | `c1`: one G2 point, `c2`: list of *n* G2 points |
| **Functional Key** | `_FeDDH_SK` | `k1`: one G1 point, `k2`: list of *n* G1 points |
| **Public Key** | `_FeDDH_MK` | `n`, `F` (pairing type), `G` (ZmodR) — no group elements to serialize |

The wrapper classes in `mife/data/pyecc_bn128_wrapper.py` store the raw `py_ecc` objects:

| Wrapper Class | Inner Attribute | py_ecc Type | How to Extract Integers |
| --- | --- | --- | --- |
| `Bn128PairingPoint1` (G1) | `.point` | `(FQ, FQ)` or `None` | Each `FQ` has `.n` → 1 int each, 2 total |
| `Bn128PairingPoint2` (G2) | `.point` | `(FQ2, FQ2)` or `None` | Each `FQ2` has `.coeffs` → tuple of 2 `FQ` objects → 4 ints total |
| `Bn128PairingPointT` (GT) | `.val` | `FQ12` | **Not needed** — GT only appears during `decrypt()`, never stored |

### Your Engineering Task (Corrected Order)

#### Step 1: Write serialization helpers (external module, do not patch `pymife`)
Create a `fhipe_serialize.py` module. For each group element type, extract the underlying integers from `py_ecc` objects:

* **G1 points:** Access `wrapper.point` → get `(FQ, FQ)` tuple → read `.n` on each → two Python integers.
* **G2 points:** Access `wrapper.point` → get `(FQ2, FQ2)` tuple → read `.coeffs` on each `FQ2` → each `.coeffs` is a tuple of two `FQ` objects → four Python integers.
* **Identity (point at infinity):** `.point` is `None` → serialize as a flag `{"inf": true}`.
* **Output format:** JSON dict with integer values as strings (each is ~77 digits for BN128's 254-bit field).

#### Step 2: Write deserialization helpers
Reconstruct `py_ecc` objects from the JSON dict:

* **G1:** Call `FQ(int_value)` for x and y → tuple `(FQ(x), FQ(y))` → wrap in `Bn128PairingPoint1(...)`.
* **G2:** Call `FQ2([int1, int2])` for x and y → tuple `(FQ2(x_coeffs), FQ2(y_coeffs))` → wrap in `Bn128PairingPoint2(...)`.
* Import the wrapper classes from `mife.data.pyecc_bn128_wrapper` and the internal `_FeDDH_C` / `_FeDDH_SK` classes from `mife.single.fhiding.ddh`.

#### Step 3: Round-trip correctness test (Gate 1 criteria)
This is the **go/no-go test** from Roadmap §8:

1. Generate key, encrypt a vector, generate a functional key.
2. Serialize ciphertext and functional key to JSON strings.
3. Deserialize back from JSON strings.
4. Decrypt using the deserialized objects.
5. Assert the result matches plaintext inner product.

Run at $n = 4$ first (seconds), then at $n = 64$ (Gate 1 target). Both must produce correct results.

#### Step 4: Network socket test (post-Gate-1)
Only after Step 3 passes at $n = 64$: build a lightweight client-server test using Python's `socket` or `fastapi` module. Client encrypts → serializes → sends over localhost → server deserializes → evaluates → returns blinded score.

---

## 5. Reducing Query Latency (the ~17 min problem)

On the current `py_ecc` backend, each dimension costs ~3.5 seconds (scalar multiplications in pure Python). At $n = 300$, that is ~17 minutes per query — unusable for any deployment scenario. Three approaches, ordered by effort:

### Option A: Swap to `py_ecc`'s optimized backend (free, ~2–3× speedup)

`py_ecc` ships two implementations side by side. `pymife` imports from `py_ecc.bn128` (affine coordinates, non-optimized field arithmetic). But `py_ecc.optimized_bn128` exists and uses **Jacobian projective coordinates** (`(x, y, z)` 3-tuples instead of `(x, y)` 2-tuples), which avoids expensive modular inversions during point addition.

**What to do:** Write a new `OptimizedBn128Pairing` class in `pyecc_bn128_wrapper.py` that imports from `py_ecc.optimized_bn128` instead of `py_ecc.bn128`. The key differences to handle:

* Points become 3-tuples `(FQ, FQ, FQ)` instead of 2-tuples `(FQ, FQ)`.
* Point-at-infinity is `(FQ.one(), FQ.one(), FQ.zero())` instead of `None`.
* The `normalize()` function converts Jacobian → affine when needed.
* Serialization extracts 3 ints per G1 point, 6 ints per G2 point.

**Expected speedup:** ~2–3× (fewer field divisions). Still pure Python, but a quick win.

### Option B: `mclbn256` native backend (~10,000× speedup)

The `mclbn256` package (`pip install mclbn256`) provides Python bindings to the **MCL** C library — a highly optimized BN254 pairing engine. MCL performs a single pairing in ~0.3 ms vs `py_ecc`'s ~3,500 ms.

**What to do:** Write a new `MclPairing` class implementing `pymife`'s `PairingBase` interface:
```python
from mife.data.pairing import PairingBase
from mclbn256 import G1, G2, GT, Fr

class MclPairing(PairingBase):
    def order(self) -> int: ...
    def generator1(self) -> MclG1Wrapper: ...
    def generator2(self) -> MclG2Wrapper: ...
    def pairing(self, g1, g2) -> MclGTWrapper: ...
```

Each wrapper class (`MclG1Wrapper`, `MclG2Wrapper`, `MclGTWrapper`) implements `pymife`'s `GroupElem` interface (`__add__`, `__neg__`, `__rmul__`, `__eq__`, `__hash__`, `export`). Then pass this backend to `FeDDH.generate(n, F=MclPairing())`.

**Expected speedup:** ~10,000×. At $n = 300$: from ~17 minutes to **~0.1 seconds**. This makes the "milliseconds" latency claim real.

**Install:** `pip install mclbn256`

### Option C: Multiprocessing across buckets

Independent of the backend choice, the 10 clinical buckets are embarrassingly parallel. Use Python's `multiprocessing.Pool` to run bucket evaluations across CPU cores. At 10 buckets on 8 cores, wall-clock time drops by ~5–8×.

### Recommended path
1. Get serialization working first (§4 above) on the existing `py_ecc` backend.
2. Try Option A (optimized swap) — it is a single-file change with no new dependencies.
3. If that is not fast enough, implement Option B (`mclbn256`). This is the production-grade solution and the one worth benchmarking in the paper.

---

## 6. Performance Benchmarking

Once serialization is patched and a faster backend is in place, we need empirical charts for our Systems Engineering report chapter:

* **Benchmark Latency Curve:** Measure and plot the Cloud server's discrete-log search execution time as the blinding range expands ($R = 2^k \cdot S$ in **Design A**).
* **Chunked Bucket Benchmarks:** Measure the setup and encryption runtime for a single clinical bucket ($n = 300$) versus a monolithic vector ($n = 1000+$) to empirically demonstrate our $O(n^3)$ parallelization savings.
* **Backend Comparison:** Time a full encrypt → serialize → transmit → deserialize → decrypt cycle on `py_ecc`, `optimized_bn128`, and `mclbn256` at increasing $n$ values. This produces the paper's key systems figure.

```