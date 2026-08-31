import numpy as np
np.random.seed(42)
n = 50
raw_patient_vector = np.random.randn(n)
SCALING_FACTOR = 100.0
quantized_patient_vector = np.rint(raw_patient_vector * SCALING_FACTOR).astype(np.int64).tolist()

raw_weights_data = np.load('master_33_cancer_weights.npy', allow_pickle=True)
if raw_weights_data.ndim == 0:
    selected_model_weights = list(raw_weights_data.item().values())[0]
else:
    selected_model_weights = list(raw_weights_data.item().values())[0]

trimmed_weights = selected_model_weights[:n]
quantized_weights = [int(abs(val)) + 1 for val in np.rint(trimmed_weights * SCALING_FACTOR)]

dot = sum(quantized_patient_vector[i] * quantized_weights[i] for i in range(n))
print('Dot product:', dot)
