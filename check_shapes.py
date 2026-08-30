import numpy as np
weights = np.load("master_33_cancer_weights.npy", allow_pickle=True)
if isinstance(weights, np.ndarray) and weights.ndim == 2:
    w = weights[0]
else:
    w = list(weights.item().values())[0]
p = np.load("patient1_full.npy")
print("W shape:", w.shape, "P shape:", p.shape)
