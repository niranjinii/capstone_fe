import numpy as np
from bucketing import get_cancer_type_name

weights = np.load("master_33_cancer_weights.npy", allow_pickle=True)
if isinstance(weights, np.ndarray) and weights.ndim == 2:
    pass
else:
    weights = list(weights.item().values())

patient = np.load("patient1_full.npy")

print("Raw Z-Scores (Dot Product) for patient1_full.npy:")
for i, w in enumerate(weights):
    if isinstance(weights, list):
        w = np.array(w)
    score = np.dot(patient, w)
    cancer_name = get_cancer_type_name(i)
    print(f"Model {i:2d} ({cancer_name:5s}): Z-score = {score:.4f}")
