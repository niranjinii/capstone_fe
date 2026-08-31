import numpy as np
import logging

logger = logging.getLogger("RhoBlinding")

def generate_rho(sigma: float = 1000.0) -> int:
    """
    Generate a Gaussian random noise parameter rho for result blinding
    and extraction resistance.
    """
    # Fix the seed temporarily so we get consistent outputs during demo/dev
    # In production, remove this!
    # np.random.seed()
    rho = int(np.round(np.random.normal(0, sigma)))
    logger.debug(f"Generated rho: {rho}")
    return rho

def extend_weight_vector(weights: list, rho: int) -> list:
    """
    Extend the hospital's weight vector with rho: [w1, ..., wn, rho]
    """
    return list(weights) + [rho]

def extend_patient_vector(patient: list) -> list:
    """
    Extend the clinic's patient vector with 1: [x1, ..., xn, 1]
    The dot product becomes <x, w> + rho * 1 = <x, w> + rho
    """
    return list(patient) + [1]

def correct_blinded_result(blinded_score: int, rho: int) -> int:
    """
    Remove rho from the blinded result to recover the true score.
    """
    return blinded_score - rho
