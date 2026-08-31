"""Roadmap section 4.1 - the two data bugs, quantified.

Bug 1: (x*100).astype(int) TRUNCATES toward zero. Lasso coefficients in the
       0.001-0.05 range are silently deleted.
Bug 2: reindex(fill_value=0) then StandardScaler maps a missing gene to
       (0-mu)/sigma - an extreme negative z-score, not a neutral value.

Run with your weights to get the real numbers:
    python3 quantization_check.py --weights master_33_cancer_weights.npy
"""
import argparse
import numpy as np


def main(a):
    rng = np.random.default_rng(0)
    if a.weights:
        W = np.load(a.weights)
        print(f"loaded {a.weights}: {W.shape}\n")
    else:
        print("no --weights: synthetic Lasso-like coefficients\n")
        W = np.zeros((5, 2000))
        for i in range(5):
            idx = rng.choice(2000, rng.integers(20, 200), replace=False)
            W[i, idx] = rng.normal(0, 0.03, len(idx))

    print("BUG 1 - truncation vs rounding")
    print(f"{'model':>6} {'active':>7} {'killed by trunc':>16} {'%':>7} {'killed by rint':>15}")
    print("-" * 56)
    tot_a = tot_t = tot_r = 0
    for i in range(min(a.models, W.shape[0])):
        w = W[i][np.flatnonzero(W[i])]
        n = len(w)
        trunc = (w * a.q).astype(np.int64)
        rint = np.rint(w * a.q).astype(np.int64)
        kt, kr = int((trunc == 0).sum()), int((rint == 0).sum())
        tot_a += n; tot_t += kt; tot_r += kr
        print(f"{i:>6} {n:>7} {kt:>16} {100*kt/max(n,1):>6.1f}% {kr:>15}")
    print("-" * 56)
    print(f"{'ALL':>6} {tot_a:>7} {tot_t:>16} {100*tot_t/max(tot_a,1):>6.1f}% {tot_r:>15}")
    print(f"\n  fix: np.rint(w * Q).astype(np.int64)")
    if tot_t > tot_r:
        print(f"  -> truncation is currently deleting {tot_t - tot_r} more genes than rounding")

    print("\nBUG 2 - missing-gene imputation")
    mu, sd = 6.0, 2.0          # typical log-scale RNA-seq
    print(f"  assuming gene mean={mu}, sd={sd} (typical log RNA-seq)")
    print(f"  fill_value=0    -> z = (0-{mu})/{sd} = {(0-mu)/sd:+.2f}   <- extreme, injects fake signal")
    print(f"  fill=scaler.mean_ -> z = ({mu}-{mu})/{sd} = {0.0:+.2f}   <- neutral, correct")
    print("\n  fix: aligned = raw.reindex(columns=scaler.feature_names_in_)")
    print("       aligned = aligned.fillna(pd.Series(scaler.mean_,")
    print("                 index=scaler.feature_names_in_))")
    print("       and log how many genes were imputed per patient")

    print("\nBUG 3 - one factor for two distributions")
    print("  weights and features have different scales; pick Q_w and Q_x")
    print("  separately from their own distributions, then divide the returned")
    print("  score by (Q_w * Q_x) rather than by Q**2.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--weights"); p.add_argument("--models", type=int, default=5)
    p.add_argument("--q", type=float, default=100.0)
    main(p.parse_args())
