# Extension Plan: Non-Linear Models via Random Fourier Features

> [!IMPORTANT]
> **Gate condition:** This extension only proceeds if the FHIPE dimension feasibility experiment (Step 1 below) shows that your system can handle D ≥ 500 dimensions at a usable speed. Run Step 1 first — if it fails, the extension stops there, and that finding is itself a publishable result.

---

## Background: Why This Works Mathematically

Your FH-IPFE scheme is strictly linear — it can only compute dot products. But a linear dot product in a *transformed space* can approximate a non-linear kernel in the *original space*.

This is the **Random Fourier Features (RFF)** trick from Rahimi & Recht (2007):

$$k(x, z) \approx \phi(x)^T \phi(z)$$

where $k$ is a non-linear RBF kernel and $\phi$ is a random feature map:

$$\phi(x) = \sqrt{\frac{2}{D}} \cos(W x + b)$$

- $W$ is a $D \times n$ random matrix drawn from $\mathcal{N}(0, 1/\gamma^2)$ (where $\gamma$ is the RBF bandwidth)
- $b$ is a $D$-vector drawn from $\text{Uniform}(0, 2\pi)$
- $D$ is the number of random features (the new dimension you encrypt)
- $n$ is the original gene dimension (~139 active genes per model)

The brilliant part: **the cosine is applied in plaintext on the Clinic's machine before encryption**. The Cloud still just computes a linear dot product on the encrypted feature-mapped vector. The cryptography does not change at all.

---

## The Architecture Change

```
CURRENT SYSTEM:
  Clinic: encrypt(x)                    → Cloud: <x, w>

NEW SYSTEM:
  Clinic: encrypt(φ(x))                 → Cloud: <φ(x), w_rff>
          ↑ plaintext transform, local
```

The Cloud, Hospital, and FeDDH scheme are unchanged. The only changes are:
1. Hospital trains an SVM/logistic regression on `φ(x_train)` instead of `x_train`
2. Hospital generates the functional key for `w_rff` (the model's weight in feature space)
3. Clinic applies the random map before encrypting

---

## Step-by-Step Implementation Plan

### Phase 0 — Prerequisite Reading (1 hour)
Read your roadmap Section 10 in full. Also read:
- Rahimi, A. & Recht, B. (2007). "Random Features for Large-Scale Kernel Machines." *NeurIPS 2007*. — The foundational RFF paper.
- Your `check1_gene_union.py` results — you need to know the active gene dimension for each cancer model.

---

### Phase 1 — Dimension Feasibility Experiment (Half a day)
**This is the Gate. Run this before writing any new code.**

The core question: at what dimension $D$ does your FHIPE system become too slow or run out of memory?

Create `test_scripts/rff_dimension_wall.py`:

```python
"""
Finds the FHIPE dimension wall for Random Fourier Features.
Tests increasing D values, measuring keygen time and ek size.
Stops when keygen exceeds 60s or ek exceeds available RAM.
"""
import time
import numpy as np
from mcl_backend import MclPairing, fast_feddh_generate
from delegated_crypto import generate_ek, serialize_ek
import json

F = MclPairing()
results = []

# Test D = 50, 100, 200, 300, 500, 750, 1000, 2000, 5000
# Stop early if too slow
for D in [50, 100, 200, 300, 500, 750, 1000, 2000, 5000]:
    print(f"\n--- Testing D={D} ---")
    try:
        t0 = time.time()
        mk = fast_feddh_generate(D, F=F)
        t_keygen = time.time() - t0
        print(f"  Keygen: {t_keygen:.1f}s")
        
        t0 = time.time()
        ek = generate_ek(mk)
        t_ek = time.time() - t0
        
        ek_json = serialize_ek(ek)
        ek_bytes = len(json.dumps(ek_json).encode())
        print(f"  EK gen: {t_ek:.1f}s, EK size: {ek_bytes/1e6:.1f} MB")
        
        results.append({
            "D": D,
            "keygen_s": round(t_keygen, 2),
            "ek_size_mb": round(ek_bytes / 1e6, 2),
            "feasible": t_keygen < 60 and ek_bytes < 500e6
        })
        
        if t_keygen > 60 or ek_bytes > 500e6:
            print(f"  WALL HIT at D={D}. Stopping.")
            break
    except MemoryError:
        print(f"  OOM at D={D}. Stopping.")
        results.append({"D": D, "keygen_s": None, "ek_size_mb": None, "feasible": False})
        break

print("\n=== DIMENSION WALL RESULTS ===")
for r in results:
    status = "✓ FEASIBLE" if r["feasible"] else "✗ TOO SLOW/LARGE"
    print(f"D={r['D']:5d} | Keygen: {str(r['keygen_s'])+'s':>8} | EK: {str(r['ek_size_mb'])+'MB':>10} | {status}")
```

**What the output tells you:**
- If $D = 500$ is feasible → proceed to Phase 2
- If the wall is at $D = 200$ or below → the RFF approach is not viable with current hardware. Stop here and write up the negative result.
- If the wall is at $D = 300$–$400$ → marginal. Run Phase 2 anyway with $D = 200$ to get accuracy numbers, even if they are poor.

> [!NOTE]
> Based on your existing benchmarks (keygen for n≈139 takes ~20s), you can project: keygen scales as O(D²) for the Gaussian elimination in `fast_feddh_generate`. D=500 would be roughly (500/139)² × 20s ≈ 260s. This may already be beyond your threshold. The experiment will confirm it.

---

### Phase 2 — Train the RFF Model (Half a day, only if Phase 1 passes)

Create `rff_model.py`:

```python
"""
Trains an RBF-kernel SVM (via Random Fourier Features) on TCGA RNA-seq data.
Produces a weight vector w_rff in feature space for use with FH-IPFE.
"""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Parameters — tune D based on Phase 1 feasibility
D = 500          # number of random features (MUST be ≤ dimension wall)
gamma = 0.01     # RBF bandwidth (tune via cross-validation)
CANCER_IDX = 0   # which cancer model to train

# Load weights and determine active gene indices
raw_weights = np.load('master_33_cancer_weights.npy', allow_pickle=True)
base_weights = raw_weights[CANCER_IDX]
active_idx = np.flatnonzero(base_weights != 0)
n = len(active_idx)
print(f"Original dimension n={n}, mapping to D={D} random features")

# --- Random Fourier Feature Map ---
# W: shape (D, n), drawn from N(0, gamma^2)
# b: shape (D,), drawn from Uniform(0, 2*pi)
rng = np.random.RandomState(42)
W = rng.randn(D, n) * gamma
b = rng.uniform(0, 2 * np.pi, D)

def rff_map(x_mat):
    """Map matrix of gene vectors (rows) to RFF space. Shape: (N, D)"""
    proj = x_mat @ W.T + b          # (N, D)
    return np.cos(proj) * np.sqrt(2.0 / D)

# Save W and b — Hospital needs these to build w_rff
# Clinic also needs W and b (these are PUBLIC, not secret)
np.save('rff_W.npy', W)
np.save('rff_b.npy', b)

# --- You need to load real training data here ---
# X_train: (N_samples, n_genes) — active gene subset from TCGA
# y_train: binary labels for CANCER_IDX cancer vs other
#
# Placeholder: replace with your real data loading
# X_train = load_tcga_training_data(active_idx)
# y_train = load_labels(CANCER_IDX)
#
# X_train_rff = rff_map(X_train)
# scaler = StandardScaler()
# X_train_rff_scaled = scaler.fit_transform(X_train_rff)
# 
# clf = LogisticRegression(C=1.0, max_iter=1000)
# clf.fit(X_train_rff_scaled, y_train)
# w_rff = clf.coef_[0]   # shape (D,)
# np.save('rff_weights.npy', w_rff)

print("Done. w_rff saved. Use rff_weights.npy as the model weight in hospital.py")
```

**Key design decisions:**
- **$\gamma$ (bandwidth):** Controls how non-linear the kernel is. $\gamma = 1/n$ is a common default. Tune with cross-validation.
- **$D$ (features):** Larger = more accurate kernel approximation but harder for FHIPE. Start with your wall value and decrease until accuracy degrades.
- **Model:** Logistic Regression in RFF space approximates a kernel SVM. Works well because the RFF transform already captures the non-linearity.

---

### Phase 3 — Integrate into the 3-Party System (1 day, only if Phases 1+2 succeed)

#### Changes to `hospital.py`
```python
# Load RFF parameters (public)
W = np.load('rff_W.npy')
b = np.load('rff_b.npy')

# Load RFF model weights instead of Lasso weights
w_rff = np.load('rff_weights.npy')
# ... quantize and shift w_rff as usual

@app.route('/get_rff_params', methods=['GET'])
def get_rff_params():
    """Clinic needs W and b to compute φ(x) before encryption.
    These are PUBLIC — no secrecy required."""
    return jsonify({
        "W": W.tolist(),
        "b": b.tolist(),
        "D": int(W.shape[0]),
        "gamma": float(gamma)
    })
```

#### Changes to `clinic.py`
```python
# 1. Fetch RFF parameters from Hospital
rff_params = requests.get('http://127.0.0.1:5001/get_rff_params').json()
W = np.array(rff_params['W'])
b = np.array(rff_params['b'])
D = rff_params['D']

# 2. Apply the feature map BEFORE encryption (plaintext, local)
raw_patient_vector = patient_full_vector[active_indices]
proj = raw_patient_vector @ W.T + b          # shape (D,)
phi_x = np.cos(proj) * np.sqrt(2.0 / D)     # shape (D,)

# 3. Quantize φ(x) (cosine output is in [-1, 1] so use different scale)
RFF_SCALING_FACTOR = 10000.0
quantized_phi = np.rint(phi_x * RFF_SCALING_FACTOR).astype(np.int64).tolist()

# 4. Encrypt φ(x) instead of x — everything else is identical
json_ct = delegated_encrypt(ek, quantized_phi)
```

> [!WARNING]
> The cosine output is in `[-1.0, 1.0]`, not in the original gene expression range. Use a different scaling factor (e.g., 10,000) and remember that the weight shift $C$ and the score correction formula in `clinic.py` must be updated accordingly.

#### No changes to `cloud.py`
The Cloud still just evaluates a linear dot product. It has no idea you changed the input space.

---

### Phase 4 — Accuracy Benchmark (Half a day)

Run two comparisons:
1. **Plaintext RFF SVM** vs **Plaintext Lasso** — how much accuracy does the non-linear model actually gain?
2. **Encrypted RFF SVM** (your system) vs **Encrypted Lasso** (your existing system) — same question, in the encrypted setting, with the quantization overhead.

Create `test_scripts/rff_accuracy_benchmark.py` to measure:
- Classification accuracy across all 33 cancer types
- Quantization error introduced by the FE integer representation
- End-to-end latency (keygen + ek + encrypt + evaluate)

---

## Decision Tree: What to Write in the Paper

```
Phase 1: D_wall experiment
├── D_wall ≥ 500 → proceed to Phase 2
│   ├── RFF accuracy significantly better → "We demonstrate non-linear extension is 
│   │                                         feasible and improves accuracy by X%"
│   └── RFF accuracy similar to Lasso → "Random features provide no significant gain;
│                                         linear Lasso is sufficient for this domain"
└── D_wall < 300 → STOP. Write:
    "We empirically establish the FHIPE dimension wall at D={wall} for our hardware.
     Random Fourier Features require D≥500 for meaningful kernel approximation,
     which lies beyond this wall. This establishes a concrete open problem
     for future work using optimized pairing hardware (GPUs, FPGAs)."
```

**All three outcomes are publishable.** A well-documented negative result (the wall exists and blocks non-linear models) is arguably the most interesting to a cryptography reviewer, as it gives a concrete target for future optimization work.

---

## Timeline (If You Have Time)

| Day | Task |
|---|---|
| Day 1 AM | Run `rff_dimension_wall.py`. Interpret results. |
| Day 1 PM | If feasible: Write `rff_model.py`, train on real TCGA data |
| Day 2 AM | If feasible: Integrate into `hospital.py` and `clinic.py` |
| Day 2 PM | If feasible: Run accuracy benchmark, write results section |
| Either way | Write the dimension wall analysis into the paper as Section 7 or an appendix |

---

## Key Reference

Rahimi, A. & Recht, B. (2007). "Random Features for Large-Scale Kernel Machines." *Advances in Neural Information Processing Systems (NeurIPS) 2007*, Vol. 20.

This is the paper you must cite as the source of the random feature map construction.
