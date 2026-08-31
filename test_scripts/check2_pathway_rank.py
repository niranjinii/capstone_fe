"""Check 2 (roadmap section 6.1) - does pathway aggregation actually hide weights?

The privacy claim for pathway-level explanations depends on the pathway-by-gene
incidence matrix being RANK DEFICIENT over the active gene set. If its rank
reaches the number of active genes, the system of equations is fully determined,
individual weights are recoverable, and section 6 collapses to one paragraph.

Run:  python3 check2_pathway_rank.py h.all.v2023.1.Hs.symbols.gmt genes_cancer2.txt
      (GMT from MSigDB; gene list = one active gene symbol per line)
"""
import sys
import numpy as np

def load_gmt(path):
    sets = {}
    with open(path) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) > 2:
                sets[parts[0]] = set(parts[2:])
    return sets

def main(gmt_path, genes_path):
    pathways = load_gmt(gmt_path)
    genes = [g.strip() for g in open(genes_path) if g.strip()]
    idx = {g: i for i, g in enumerate(genes)}
    n = len(genes)

    rows, kept = [], []
    for name, members in pathways.items():
        hits = [idx[g] for g in members if g in idx]
        if hits:
            row = np.zeros(n)
            row[hits] = 1.0
            rows.append(row)
            kept.append(name)

    if not rows:
        sys.exit("no pathway overlaps the active gene set - check symbol namespace "
                 "(HGNC symbols vs Ensembl IDs is the usual cause)")

    A = np.vstack(rows)
    r = np.linalg.matrix_rank(A)
    print(f"active genes            : {n}")
    print(f"pathways with >=1 hit   : {len(kept)}")
    print(f"incidence matrix        : {A.shape}")
    print(f"rank                    : {r}")
    print(f"unknowns left free      : {n - r}\n")

    if r >= n:
        print("RESULT: FULLY DETERMINED. Pathway aggregation hides nothing -")
        print("        every individual weight is recoverable from the pathway sums.")
        print("        The privacy argument for section 6 is void. Reduce section 6 to")
        print("        one honest paragraph: per-gene FE explanations are an extraction")
        print("        oracle, and aggregation does not fix it at realistic overlap.")
        print("        The clinical-utility argument still stands on its own.")
    else:
        frac = (n - r) / n
        print(f"RESULT: RANK DEFICIENT. {n-r} of {n} dimensions ({frac:.0%}) stay")
        print("        underdetermined. The privacy argument survives - quantify it")
        print("        exactly this way in the paper, and report the residual")
        print("        subspace dimension rather than asserting 'many unknowns'.")
        if frac < 0.1:
            print("\n        CAUTION: under 10% free. Thin enough that side information")
            print("        (weight signs, sparsity priors) may close the gap. Say so.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
