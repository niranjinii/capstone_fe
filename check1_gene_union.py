"""Check 1 (roadmap section 1) - the dimension decision.

Computes the global union of Lasso-active genes across all 33 cancers and
tells you which branch of the section 1 decision tree you land in.

Run:  python3 check1_gene_union.py master_33_cancer_weights.npy
"""
import sys
import numpy as np

def main(path):
    W = np.load(path)                      # expected shape: (33, n_genes)
    if W.ndim != 2:
        sys.exit(f"expected a 2-D weight matrix, got shape {W.shape}")
    n_models, n_genes = W.shape
    print(f"weight matrix: {n_models} models x {n_genes} genes\n")

    active = [set(np.flatnonzero(W[i])) for i in range(n_models)]
    counts = np.array([len(a) for a in active])
    union = set().union(*active)

    print("per-cancer active gene counts")
    print(f"  min {counts.min()}   median {int(np.median(counts))}   "
          f"max {counts.max()}   sum {counts.sum()}")
    print(f"\nGLOBAL UNION: {len(union)} genes")
    print(f"  overlap factor: {counts.sum() / max(len(union), 1):.2f}x "
          f"(1.0 = fully disjoint, higher = more sharing)\n")

    # extraction lifetime, both metrics (roadmap section 1 table)
    worst, u = int(counts.min()), len(union)
    print("extraction lifetime, in patients")
    print(f"  per-cancer dim, single key : targeted {worst:6d} | suite {int(counts.sum()):7d}")
    print(f"  union dim,      single key : targeted {u:6d} | suite {u * n_models:7d}")
    print(f"  union dim,      all keys   : targeted {u:6d} | suite {u:7d}")
    print(f"  -> targeted gain from adopting the union: {u / max(worst,1):.1f}x\n")

    # FHIPE feasibility (BN254: 32-byte compressed G1)
    ek_mb = u * u * 32 / 1e6
    print("FHIPE cost at the union dimension")
    print(f"  ek size      ~ {ek_mb:,.1f} MB   ({u}^2 G1 points, BN254)")
    print(f"  Setup        ~ {u**3:.2e} field ops  (O(n^3) matrix inverse)")
    print(f"  encryption   ~ {u*u:.2e} exponentiations\n")

    if u <= 500:
        print("BRANCH: union <= 500 -> ADOPT. All four consequences available,")
        print("        and all-keys evaluation becomes possible.")
    elif u <= 1500:
        print("BRANCH: union 500-1500 -> INTERMEDIATE BUCKETS.")
        print("        Group cancers into buckets of similar dimension. Partial")
        print("        dimension privacy, proportional lifetime gain, /model_metadata")
        print("        still leaks within a bucket, all-keys works only within a bucket.")
    else:
        print("BRANCH: union > 1500 -> UNAVAILABLE UNDER FHIPE.")
        print("        Run the dimension experiment on Damgard only (Setup and")
        print("        encryption are linear there) and report the FHIPE wall as")
        print("        the boundary. Note: all-keys is then unavailable too, so")
        print("        query privacy has no mitigation under FHIPE. Say so explicitly.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
