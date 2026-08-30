import math
import logging
from mcl_backend import MclPairing

logger = logging.getLogger("BSGS")

def bsgs_discrete_log(target_GT, generator_GT, bounds, backend=None):
    """
    Finds r such that generator_GT^r == target_GT within the given bounds [lower, upper].
    Uses the Baby-Step Giant-Step algorithm to run in O(sqrt(N)) time.
    """
    if backend is None:
        backend = MclPairing()
        
    lower, upper = bounds
    N = upper - lower + 1
    m = int(math.ceil(math.sqrt(N)))
    
    # We want to solve for r in: target_GT == generator_GT^r
    # Let r = r' + lower, so r' is in [0, N-1]
    # target_GT == generator_GT^(r' + lower)
    # target_GT * generator_GT^(-lower) == generator_GT^r'
    
    # T_shifted = target_GT * generator_GT^(-lower)
    # Note: in MclGTWrapper, + is multiplication, and scalar * obj is exponentiation
    T_shifted = target_GT + (-lower * generator_GT)

    # 1. Baby steps: compute generator_GT^j for j in [0, m)
    logger.debug(f"Precomputing {m} baby steps...")
    baby_steps = {}
    current = backend.identityT()
    for j in range(m):
        baby_steps[current.inner.serialize()] = j
        current = current + generator_GT
        
    # 2. Giant steps: search for i in [0, m)
    # We want to check if T_shifted * generator_GT^(-i*m) is in baby_steps
    # g_inv_m = generator_GT^(-m)
    g_inv_m = (-m) * generator_GT
    
    logger.debug("Searching giant steps...")
    current = T_shifted
    for i in range(m):
        key = current.inner.serialize()
        if key in baby_steps:
            r_prime = i * m + baby_steps[key]
            return r_prime + lower
        current = current + g_inv_m
        
    raise ValueError(f"Discrete logarithm not found in bounds {bounds}")

def feddh_decrypt_bsgs(ct, sk, bounds, backend=None):
    """
    Decrypts a FeDDH ciphertext using the fast BSGS algorithm.
    This replaces PyMIFE's FeDDH.decrypt() which uses linear search.
    """
    if backend is None:
        backend = MclPairing()
        
    # D1 = e(c1, k1)
    D1 = backend.pairing(ct.c1, sk.k1)
    
    # D2 = product_i e(c2[i], k2[i])
    D2 = backend.identityT()
    for c_i, k_i in zip(ct.c2, sk.k2):
        D2 = D2 + backend.pairing(c_i, k_i)
        
    return bsgs_discrete_log(target_GT=D2, generator_GT=D1, bounds=bounds, backend=backend)
