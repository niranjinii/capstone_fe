import numpy as np
from bucket_config import CANCER_TYPES

weights = np.load("master_33_cancer_weights.npy", allow_pickle=True)
if isinstance(weights, np.ndarray) and weights.ndim == 2:
    pass
else:
    weights = list(weights.item().values())

for i, w in enumerate(weights):
    if isinstance(w, list):
        w = np.array(w)
    active_count = np.count_nonzero(w)
    print(f"{CANCER_TYPES[i]}: {active_count}")
