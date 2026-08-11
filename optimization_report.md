# Functional Encryption Performance Optimization Report

## Overview

This project implements a **privacy-preserving cancer risk scoring system** using **Inner Product Functional Encryption (IPFE)**. The system allows a Cloud server to compute a dot product (risk score) on encrypted patient gene data without ever learning the patient's raw values or the model weights.

The mathematical core is:
> Given encrypted patient vector **x** and a functional key for weights **y**, compute **⟨x, y⟩** without decrypting **x**.

---

## Part 1: The Original Baseline (py_ecc)

### What `pymife` is
[`pymife`](https://github.com/Felix-Rm/pymife) is a Python library implementing the **FeDDH (Function-hiding Inner Product Functional Encryption)** scheme. It uses **Bilinear Pairings** on the BN254 elliptic curve — a highly specific structure where `e(G1, G2) → GT` enables the inner product to be computed in the exponent.

### What `py_ecc` is
[`py_ecc`](https://github.com/ethereum/py_ecc) is Ethereum's pure-Python reference implementation of BN254 curve arithmetic. `pymife` uses it by default. Being pure Python, every scalar multiplication on the curve runs as interpreted bytecode — painfully slow for cryptographic workloads.

### Baseline performance (n=300)
| Operation | Time |
|---|---|
| Key Generation | ~7 minutes |
| Encryption (one patient) | ~several minutes |
| Decryption/Evaluation | ~several minutes |

This was completely unusable at any real vector size.

---

## Part 2: The C++ Backend — `mclbn256` + `mcl_backend.py`

### The Plan
Replace `py_ecc` with [`mclbn256`](https://github.com/nthparty/mclbn256) — a Python binding around the [MCL cryptographic library](https://github.com/herumi/mcl) written in highly optimized C++. Same BN254 curve, same math, 100–500x faster.

### How `pymife` accepts a custom backend
`pymife` was designed with a `PairingBase` abstract class. Any class implementing its interface can be passed as `F=...` to `FeDDH.generate()`. This is the injection point we exploited.

### What `mcl_backend.py` does
We wrote `MclPairing` — a wrapper that implements `PairingBase` using `mclbn256` objects:

```python
class MclG1Wrapper(GroupElem):
    def __rmul__(self, scalar: int):
        fr = _to_fr(scalar)
        return MclG1Wrapper(self.val * fr)   # C++ scalar mul

class MclGTWrapper(GroupElem):
    def __add__(self, other):
        return MclGTWrapper(self.val * other.val)  # GT "addition" = field multiplication

    def __rmul__(self, scalar: int):
        fr = _to_fr(scalar)
        return MclGTWrapper(self.val ** fr)  # GT "scaling" = exponentiation
```

The key wrappers (`MclG1Wrapper`, `MclG2Wrapper`, `MclGTWrapper`) intercept every math operator `pymife` calls and redirect them to `mclbn256`'s C++ methods.

### Critical Bug: Wrong Curve Order
The biggest roadblock was a silent mathematical mismatch. `pymife` inverts its key matrices modulo a **prime order**. We initially used the Ethereum BN254 order (`21888...`) but `mclbn256` uses a slightly different BN curve with order `16798108731015832284940804142231733909759579603404752749028378864165570215949`. With the wrong modulus, the matrix never properly cancelled out during decryption, causing `discrete_log_bound_brute` to fail with "not found in bounds."

**Fix:** Override `MclPairing.order()` to return the correct value:
```python
def order(self) -> int:
    return 16798108731015832284940804142231733909759579603404752749028378864165570215949
```

### Critical Bug: `setInt()` truncates 254-bit integers
Python's `ctypes` wrapper for `mclbn256.Fr.setInt()` silently truncates integers larger than 64 bits. Key scalars in FeDDH are ~254-bit numbers. This corrupted all scalar multiplications silently.

**Fix:** Use `fromstr()` with hexadecimal encoding instead:
```python
def _to_fr(scalar: int):
    ORDER = 16798108731015832284940804142231733909759579603404752749028378864165570215949
    pos_scalar = scalar % ORDER
    hex_scalar = hex(pos_scalar)[2:]
    fr = mclbn256.Fr()
    fr.fromstr(hex_scalar.encode(), 16)
    return fr
```

### Result after C++ backend
| Operation | Before (py_ecc) | After (mclbn256) | Speedup |
|---|---|---|---|
| Encryption (n=300) | minutes | **~0.5s** | ~500x |
| Decryption (n=300) | minutes | **~0.15s** | ~500x |

---

## Part 3: Setup Phase Optimization — `fast_feddh_generate`

### The remaining bottleneck
Even with the C++ backend handling curve math, `FeDDH.generate()` still had to invert a 300×300 matrix of **pure Python `ZmodR` objects** — a massive overhead because every arithmetic operation went through Python's object system.

Profiling revealed: `FeDDH.generate(300)` with `mclbn256` backend still took **~7 minutes** because the matrix inversion code in `pymife` is not pluggable — it always runs in Python.

### The fix: raw integer Gaussian elimination
We wrote `fast_feddh_generate()` which bypasses `pymife`'s `Matrix` class entirely and does the inversion using plain Python `int`s, then wraps the result back into `pymife` objects:

```python
# Instead of ZmodR objects, work with raw ints:
factor_inv = pow(factor, -1, order)   # Python's built-in modular inverse (extremely fast)
det = (det * factor) % order
for j in range(n):
    A[pivot][j] = (A[pivot][j] * factor_inv) % order
```

Python's arbitrary-precision `int` arithmetic is vastly faster than routing everything through `ZmodR.__mul__` objects.

| Keygen (n=300) | Time |
|---|---|
| `FeDDH.generate()` default | ~7 minutes |
| `fast_feddh_generate()` | **~20 seconds** |

---

## Part 4: Parallelism — `parallel_eval.py`

### Why parallelism helps here
In the real system, many independent patients are queued for evaluation. Each patient's data can be encrypted and evaluated independently. This is a textbook parallel workload.

### Why it's tricky
- **Python's GIL** blocks CPU-level parallelism for pure-Python code across threads.
- **`multiprocessing`** bypasses the GIL by using separate OS processes.
- **Python 3.14 changed the default start method** from `fork` to `forkserver` on Linux. `forkserver` re-imports the module fresh in each worker, losing all globals (including the master key).
- **Pickling the key** through `pool.map()` is expensive and serial — the 300×300 matrix of Python objects serializes slowly.

### The solution
Force `fork()` so workers inherit the parent's memory snapshot directly:

```python
multiprocessing.set_start_method('fork')

# Key is set BEFORE the Pool is created
GLOBAL_KEY = fast_feddh_generate(n_size, F=backend)

# Workers inherit GLOBAL_KEY via fork — zero pickling cost
with multiprocessing.Pool(processes=n_buckets) as pool:
    results = pool.map(evaluate_bucket, buckets)
```

`fork()` creates child processes by cloning the parent's memory at the OS level — instantaneous, zero serialization. Workers see `GLOBAL_KEY` already populated.

### Final benchmark (n=300, 4 buckets)
| | Time |
|---|---|
| Setup (keygen) | 21.8s (one-time) |
| All 4 buckets, parallel | **0.96s** |
| Equivalent sequential | 3.37s |
| **Parallel speedup** | **3.5x** |

---

## Part 5: The Full System Architecture (3-Party Demo)

The system involves three separate services communicating over HTTP:

```
┌─────────────┐     ek (delegated key)     ┌─────────────┐
│   Hospital  │ ──────────────────────────► │    Clinic   │
│  (hospital.py) │                          │  (clinic.py)│
│             │ ◄── sealed functional key ──│             │
└─────────────┘                             └──────┬──────┘
       │                                           │ encrypted patient data +
       │ functional key (sealed)                   │ sealed functional key
       │                                           ▼
       └─────────────────────────────────► ┌─────────────┐
                                            │    Cloud    │
                                            │  (cloud.py) │
                                            │             │
                                            │  decrypts → │
                                            │  risk score │
                                            └─────────────┘
```

### `hospital.py` (Port 5001)
- Loads real cancer model weights from `master_33_cancer_weights.npy`
- Generates and holds the **FeDDH master key**
- Generates a **delegated encryption key (ek)** from the master key's B* matrix and serves it to the Clinic
- Generates the **functional key (sk)** for the weight vector, seals it with the Cloud's X25519 public key, and serves it

### `fhipe_serializer.py` (your friend's work)
Handles serialization of `pymife` curve objects across the network:
- `serialize_point(pt)` — extracts `(x, y)` coordinates as JSON-safe integers
- `deserialize_point(data, Class)` — reconstructs the wrapper object
- Works for both G1 (FQ coordinates) and G2 (FQ2 coordinates)

### `delegated_crypto.py` (your friend's work)
Implements **delegated encryption** — the Clinic can encrypt patient data without ever touching the master key:
- `generate_ek(master_key)` — precomputes `B*_ij * g2` for all matrix entries
- `delegated_encrypt(ek, x)` — Clinic computes `β * Σ_i x_i * ek[i][j]` for each j
- The resulting ciphertext is mathematically identical to what `FeDDH.encrypt()` would produce

### `clinic.py`
- Fetches dimension `n` from Hospital
- Simulates patient gene expression vector
- Fetches `ek` from Hospital, encrypts locally using `delegated_encrypt`
- Fetches sealed functional key from Hospital
- Sends both to Cloud for evaluation

### `cloud.py` (Port 5002)
- Holds its X25519 private key
- Unseals the functional key using its private key
- Calls `FeDDH.decrypt()` with reconstructed objects
- Returns the risk score

## Part 6: Final Integration & Demo Enhancements

We successfully merged the `mclbn256` speedups into the 3-party distributed architecture, resolving the known integration gaps and creating a fully working, lightning-fast demo.

### 1. Serializer Porting (`fhipe_serializer.py`)
We completely rewrote the serializers to handle the C++ `mclbn256` objects. Instead of extracting raw coordinates via Python attributes (`.point`), we now use `mclbn256`'s native `.serialize()` and `.deserialize()` byte-array methods, encoding them into `base64` strings for JSON transmission. This perfectly bridged the network gap between `clinic.py` and `cloud.py` without losing the C++ speed.

### 2. Kangaroo Bounds Expansion for Negative Scores
When testing with real TCGA data, `clinic.py` simulates quantized normal distributions that easily yield negative vectors. The baseline `discrete_log_bound_brute` decryption algorithm failed because it only searched positive bounds. We expanded the search bounds in `cloud.py` to `(-1000000, 1000000)` to accurately decrypt negative aggregate risk scores without failing.

### 3. Dynamic Model Feature Subsetting (The Biggest Win)
The original approach arbitrarily sliced the first `N` genes from the dataset, feeding the model useless zeroes. 
We updated `hospital.py` to dynamically find the exact active genes for a given model (`np.flatnonzero(selected_model_weights != 0)`). For the ACC model, this is exactly **139** genes.
`hospital.py` now exposes a `/get_active_indices` endpoint. `clinic.py` hits this endpoint, slices the patient's full 20,531-dimension Xena vector down to exactly those 139 active genes, and encrypts *only* what the model needs. 

This not only ensures **mathematical correctness** but drastically improves speed, as the $O(n^2)$ encryption in `clinic.py` now runs on $N=139$ instead of a bloated $N=300$, dropping encryption time to **under 2 seconds**.

---

## Summary of All Improvements

| Step | What Changed | Impact |
|---|---|---|
| C++ backend | `mcl_backend.py` wraps `mclbn256` | ~500x faster enc/eval |
| Curve order fix | Correct prime for `mclbn256` | Fixed decryption |
| `setInt` fix | Use `fromstr()` for large scalars | Fixed scalar mul |
| Keygen optimization | Raw int Gaussian elimination | 7 min → ~20s setup |
| Parallelism | `fork()` + shared global key | 3.5x speedup for batch jobs |
| C++ Serialization | `base64` byte-array encoding | Unlocked 3-party network demo |
| Negative Bounds | Expanded search to `±1,000,000` | Supported real normalized data |
| Dynamic Subsetting | Extracting 139 active features | Guaranteed ML correctness & 2s enc |
