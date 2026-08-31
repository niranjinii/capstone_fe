"""Quick validation: does the constant-shift quantisation produce the correct dot product?

Computes the dot product three ways:
  1. Raw float dot product (ground truth)
  2. OLD method: abs(val)+1 quantisation (BROKEN — destroys sign)
  3. NEW method: constant-shift quantisation (CORRECT — preserves sign)

Run:  python verify_sign_fix.py
"""
import numpy as np

# Load real data
weights_all = np.load('master_33_cancer_weights.npy', allow_pickle=True)
patient_full = np.load('patient1_full.npy')

SCALING_FACTOR = 100.0

print("Verifying sign-preserving quantisation across all 33 cancer models...\n")
print(f"{'Model':>5} {'n':>5} {'Float DP':>12} {'OLD (abs+1)':>12} {'NEW (shift)':>12} {'OLD err%':>10} {'NEW err%':>10}")
print("-" * 72)

for model_idx in range(weights_all.shape[0]):
    w = weights_all[model_idx]
    active = np.flatnonzero(w != 0)
    n = len(active)
    if n == 0:
        continue
    
    w_active = w[active]
    x_active = patient_full[active]
    
    # Ground truth: float dot product
    float_dp = np.dot(x_active, w_active)
    
    # Quantize patient
    qx = np.rint(x_active * SCALING_FACTOR).astype(np.int64)
    
    # OLD method: abs(val) + 1 (BROKEN)
    qw_old = [int(abs(val)) + 1 for val in np.rint(w_active * SCALING_FACTOR)]
    dp_old = sum(int(qx[i]) * qw_old[i] for i in range(n))
    
    # NEW method: constant shift (CORRECT)
    raw_q = [int(val) for val in np.rint(w_active * SCALING_FACTOR)]
    C = max(0, -min(raw_q)) + 1
    qw_new = [w + C for w in raw_q]
    dp_shifted = sum(int(qx[i]) * qw_new[i] for i in range(n))
    correction = C * sum(int(v) for v in qx)
    dp_new = dp_shifted - correction
    
    # Expected quantized dot product (no shift, just quantize both sides)
    qw_true = [int(val) for val in np.rint(w_active * SCALING_FACTOR)]
    dp_true_q = sum(int(qx[i]) * qw_true[i] for i in range(n))
    
    # Error relative to float
    err_old = abs(dp_old - dp_true_q) / max(abs(dp_true_q), 1) * 100
    err_new = abs(dp_new - dp_true_q) / max(abs(dp_true_q), 1) * 100
    
    print(f"{model_idx:>5} {n:>5} {float_dp:>12.2f} {dp_old:>12} {dp_new:>12} {err_old:>9.2f}% {err_new:>9.2f}%")

print("\nIf NEW err% is 0.00% for all models, the fix is mathematically exact.")
print("If OLD err% is large, the abs()+1 method was producing wrong results.")
