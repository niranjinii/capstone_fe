"""Roadmap section 5.1 + 0.1 - the two extraction attacks, measured.

Attack A (chosen input): encrypt unit vectors, read weights off the replies.
                         Needs the ability to choose inputs. n queries.
Attack B (natural use):  collect n real patient vectors and their scores,
                         solve the linear system. NO chosen inputs, no protocol
                         deviation - this is the section 0.1 result and it is the
                         one that matters, because it is indistinguishable from
                         ordinary clinical use.

Runs on synthetic data out of the box so you can see it work, then point it at
your real weights with --weights.

    python3 extraction_attack.py
    python3 extraction_attack.py --weights master_33_cancer_weights.npy
"""
import argparse, time
import numpy as np


def quantize(w, factor):
    return np.rint(np.asarray(w) * factor).astype(np.int64)


def attack_A_chosen_input(y_q, oracle):
    """Encrypt e_i, read y_i. Exact, n queries."""
    n = len(y_q)
    rec = np.zeros(n, dtype=np.int64)
    for i in range(n):
        e = np.zeros(n, dtype=np.int64); e[i] = 1
        rec[i] = round(oracle(e))
    return rec, n


def attack_B_natural(y_q, oracle, X):
    """Use m real patient vectors and their returned scores. Least squares."""
    m = X.shape[0]
    s = np.array([oracle(X[j]) for j in range(m)], dtype=float)
    sol, *_ = np.linalg.lstsq(X.astype(float), s, rcond=None)
    return sol, m


def rel_err(a, b):
    d = np.linalg.norm(np.asarray(a, float) - np.asarray(b, float))
    return d / max(np.linalg.norm(np.asarray(b, float)), 1e-12)


def main(a):
    rng = np.random.default_rng(a.seed)
    if a.weights:
        W = np.load(a.weights)
        print(f"loaded {a.weights}: {W.shape}")
        rows = range(min(a.models, W.shape[0]))
        get = lambda i: W[i][np.flatnonzero(W[i])]
    else:
        print("no --weights given: using synthetic Lasso-like models")
        rows = range(a.models)
        get = lambda i: rng.normal(0, 0.05, rng.integers(20, 200))

    print(f"\n{'model':>5} {'n':>5} {'A: queries':>11} {'A: exact':>9} "
          f"{'B: patients':>12} {'B: rel.err':>11} {'B: sec':>7}")
    print("-" * 68)
    for i in rows:
        w = get(i)
        n = len(w)
        y_q = quantize(w, a.qw)
        oracle = lambda x: float(np.dot(np.asarray(x, float), y_q))

        recA, qA = attack_A_chosen_input(y_q, oracle)
        exact = bool(np.array_equal(recA, y_q))

        # natural-use attack: n independent "patient" vectors
        X = rng.normal(0, 1, (n, n)) * a.qx
        X = np.rint(X).astype(np.int64)
        t0 = time.time()
        recB, m = attack_B_natural(y_q, oracle, X)
        tB = time.time() - t0

        print(f"{i:>5} {n:>5} {qA:>11} {str(exact):>9} {m:>12} "
              f"{rel_err(recB, y_q):>11.2e} {tB:>7.3f}")

    print("\nRead this as: attack B needs no chosen inputs and no misbehaviour.")
    print("It is what n ordinary patients give you for free (section 0.1).")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--weights"); p.add_argument("--models", type=int, default=5)
    p.add_argument("--qw", type=float, default=100.0)
    p.add_argument("--qx", type=float, default=100.0)
    p.add_argument("--seed", type=int, default=0)
    main(p.parse_args())
