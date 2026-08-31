from bucket_config import BUCKETS, CANCER_TYPES

def get_cancer_type_name(model_index: int) -> str:
    if 0 <= model_index < len(CANCER_TYPES):
        return CANCER_TYPES[model_index]
    return f"MODEL_{model_index}"

def get_bucket_info(model_index: int, raw_dim: int):
    cancer_name = get_cancer_type_name(model_index)
    for bucket_name, config in BUCKETS.items():
        if cancer_name in config["cancers"]:
            return bucket_name, config["max_dim"]
    return "large", BUCKETS["large"]["max_dim"]

def pad_weights(quantized_weights: list, target_dim: int) -> list:
    trimmed = quantized_weights[:target_dim]
    pad_len = target_dim - len(trimmed)
    if pad_len <= 0:
        return trimmed
    # Pad with 1 to avoid PyMIFE k2 None bugs on zeros
    return trimmed + [1] * pad_len

def pad_patient_vector(patient_vector: list, target_dim: int) -> list:
    trimmed = patient_vector[:target_dim]
    pad_len = target_dim - len(trimmed)
    if pad_len <= 0:
        return trimmed
    # Pad with 0 so the padding contributes 0 * 1 = 0 to the dot product
    return trimmed + [0] * pad_len

def build_batch_payload(ciphertexts: list, functional_keys: list) -> dict:
    if len(ciphertexts) != len(functional_keys):
        raise ValueError("Ciphertexts and functional keys lists must have identical lengths.")
    evaluations = [
        {"ciphertext": ct, "functional_key": sk}
        for ct, sk in zip(ciphertexts, functional_keys)
    ]
    return {"evaluations": evaluations}