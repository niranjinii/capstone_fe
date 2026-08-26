"""Roadmap section 0.1 - THE central experiment and the paper's main figure.

Plots, for one model:
  * patients-until-recovery, against noise scale sigma
  * diagnostic accuracy loss, against the same sigma

The point of the figure: noise buys a measurable constant, not a barrier, and
the two curves cross somewhere. That crossing is your result.

    python3 patients_until_recovery.py
    python3 patients_until_recovery.py --weights master_33_cancer_weights.npy --model 2
"""
import argparse
import numpy as np


def recover(X, s):
    sol, *_ = np.linalg.lstsq(X.astype(float), s, rcond=None)
    return sol


def patients_needed(y_q, sigma, rng, tol=0.05, cap_mult=12, trials=3):
    """Smallest m with median relative error <= tol. None if never within cap."""
    n = len(y_q)
    cap = int(cap_mult * n)
    lo, hi = n, cap
    def err_at(m):
        es = []
        for _ in range(trials):
            X = np.rint(rng.normal(0, 1, (m, n)) * 100).astype(np.int64)
            s = X.astype(float) @ y_q.astype(float)
            if sigma > 0:
                s = s + rng.normal(0, sigma, m)
            yh = recover(X, s)
            es.append(np.linalg.norm(yh - y_q) / max(np.linalg.norm(y_q), 1e-12))
        return float(np.median(es))
    if err_at(cap) > tol:
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if err_at(mid) <= tol: hi = mid
        else: lo = mid + 1
    return lo


def accuracy_loss(y_q, sigma, rng, trials=400):
    """Mean absolute error in the sigmoid probability caused by noise."""
    n = len(y_q)
    X = np.rint(rng.normal(0, 1, (trials, n)) * 100).astype(np.int64)
    true = X.astype(float) @ y_q.astype(float) / 1e4
    noisy = true + rng.normal(0, sigma, trials) / 1e4
    p = lambda z: 1.0 / (1.0 + np.exp(-np.clip(z, -50, 50)))
    return float(np.mean(np.abs(p(true) - p(noisy))) * 100)


def main(a):
    rng = np.random.default_rng(a.seed)
    if a.weights:
        W = np.load(a.weights); w = W[a.model][np.flatnonzero(W[a.model])]
        print(f"model {a.model} from {a.weights}: n = {len(w)}")
    else:
        w = rng.normal(0, 0.05, 60); print(f"synthetic model: n = {len(w)}")
    y_q = np.rint(w * 100).astype(np.int64)
    n = len(y_q)

    sigmas = [0, 1e2, 1e3, 1e4, 3e4, 1e5]
    print(f"\n{'sigma':>10} {'patients to recover':>21} {'vs baseline':>13} "
          f"{'accuracy cost':>15}")
    print("-" * 63)
    base = None
    rows = []
    for sg in sigmas:
        m = patients_needed(y_q, sg, rng, tol=a.tol)
        acc = accuracy_loss(y_q, sg, rng)
        if base is None and m: base = m
        mult = f"{m/base:.1f}x" if (m and base) else "-"
        shown = str(m) if m else f">{12*n}"
        rows.append((sg, m, acc))
        print(f"{sg:>10.0f} {shown:>21} {mult:>13} {acc:>14.2f}pp")

    print(f"\n(recovery = relative weight error <= {a.tol:.0%}; "
          f"accuracy cost = mean abs. change in predicted probability)")
    print("Interpretation: each row is a point on the paper's central figure.")
    print("Find the sigma where accuracy cost is still clinically acceptable and")
    print("report the lifetime multiplier you bought. That number is the result.")

    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        f, ax1 = plt.subplots(figsize=(7, 4.2))
        xs = [r[0] for r in rows]
        ys = [r[1] if r[1] else np.nan for r in rows]
        ax1.plot(xs, ys, "o-", color="#1a1a1a", label="patients to recover")
        ax1.set_xlabel("noise scale sigma"); ax1.set_ylabel("patients until recovery")
        ax1.set_xscale("symlog")
        ax2 = ax1.twinx()
        ax2.plot(xs, [r[2] for r in rows], "s--", color="#a02020",
                 label="accuracy cost (pp)")
        ax2.set_ylabel("mean abs. probability error (pp)", color="#a02020")
        ax1.set_title(f"Model lifetime vs perturbation (n={n})")
        f.tight_layout(); f.savefig("patients_until_recovery.png", dpi=150)
        print("\nwrote patients_until_recovery.png")
    except ImportError:
        print("\n(matplotlib not installed - table only)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--weights"); p.add_argument("--model", type=int, default=0)
    p.add_argument("--tol", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=0)
    main(p.parse_args())
