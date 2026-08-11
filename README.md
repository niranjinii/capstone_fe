# Verification and experiment scripts

Companion to the roadmap. Each maps to a section. All run on synthetic data
with no arguments, so you can see them work before your real data exists.

    pip install numpy matplotlib          # for all of them
    pip install pymife py_ecc             # for pymife_probe.py only

| Script | Roadmap | What it does | Needs |
|---|---|---|---|
| `pymife_probe.py` | 2.1 | Reproduces the PyMIFE finding: FHIPE exists and is correct, ciphertexts do not serialize, py_ecc is too slow | pymife, py_ecc |
| `quantization_check.py` | 4.1 | Quantifies the truncation and imputation bugs. **Run first** — every other number depends on the fix | weights `.npy` (optional) |
| `extraction_attack.py` | 5.1, 0.1 | Both attacks. Attack B is the important one: n ordinary patients, no chosen inputs, no misbehaviour | weights `.npy` (optional) |
| `patients_until_recovery.py` | 0.1 | **The central experiment.** Lifetime vs noise vs accuracy cost, and the figure | weights `.npy` (optional) |
| `check1_gene_union.py` | 1 | The dimension decision — computes the global union and tells you which branch you are in | weights `.npy` **required** |
| `check2_pathway_rank.py` | 6.1 | Whether pathway aggregation actually hides weights. Ten minutes, can delete a workstream | MSigDB `.gmt` + gene list |

## Suggested order, week 1

1. `quantization_check.py` — fix the bugs, retrain, then everything downstream is trustworthy
2. `check1_gene_union.py` — the highest-value single decision in the plan
3. `extraction_attack.py` — the result that motivates the paper
4. `patients_until_recovery.py` — the central figure
5. `check2_pathway_rank.py` — before committing five days to section 6
6. `pymife_probe.py` — after you get home; confirms the crypto already works

## One finding already worth knowing

`patients_until_recovery.py` shows lifetime scaling **quadratically** in the
noise scale, roughly `m ~ n * (sigma/tolerance)^2`, not by a constant factor.
On synthetic data, sigma=100 cost 0.19 percentage points of accuracy and bought
1.3x lifetime; sigma=1000 cost 1.9pp and pushed recovery beyond 12n patients.
Confirm on your real weights — if it holds, perturbation is a stronger control
than the roadmap currently claims, and that is a better result than the one
written down.
