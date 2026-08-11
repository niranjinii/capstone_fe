import json
import random
from mcl_backend import MCL_CURVE_ORDER
from fhipe_serializer import serialize_point, deserialize_point, _G2WrapperClass

# -----------------------------------------------------------------------------
# DELEGATED CRYPTO ENGINE
# -----------------------------------------------------------------------------
def generate_ek(master_key):
    """
    Hospital: Converts the secret matrix into public points.
    PyMIFE mathematically inverted the theoretical scheme by using B_star 
    for encryption instead of B. We adapt to their implementation.
    """
    n = master_key.n
    
    # .M extracts the raw 2D list from PyMIFE's custom Matrix object
    B_star = master_key.msk.B_star.M  
    g2 = master_key.msk.g2
    
    ek = []
    for i in range(n):
        row = []
        for j in range(n):
            val = int(B_star[i][j]) % MCL_CURVE_ORDER
            # PyMIFE overloads the '*' operator for curve scalar multiplication
            row.append(val * g2)
        ek.append(row)
        
    return {"ek": ek, "g2": g2}

def serialize_ek(ek_dict):
    """Hospital: Serializes the entire ek matrix and generator for the network."""
    ek_matrix = [[serialize_point(pt) for pt in row] for row in ek_dict["ek"]]
    g2_pt = serialize_point(ek_dict["g2"])
    return json.dumps({"ek": ek_matrix, "g2": g2_pt})

def deserialize_ek(json_str):
    """Clinic: Reconstructs the ek matrix from the network payload."""
    data = json.loads(json_str)
    ek_matrix = [[deserialize_point(pt, _G2WrapperClass) for pt in row] for row in data["ek"]]
    g2_pt = deserialize_point(data["g2"], _G2WrapperClass)
    return {"ek": ek_matrix, "g2": g2_pt}

def delegated_encrypt(ek_dict, x):
    """
    Clinic: Encrypts patient vector x using only ek.
    Takes O(n^2) operations and prevents the Clinic from minting functional keys.
    """
    ek = ek_dict["ek"]
    g2 = ek_dict["g2"]
    n = len(x)
    
    beta = random.randint(1, MCL_CURVE_ORDER - 1)
    
    c2_points = []
    for j in range(n):
        t_j = None
        for i in range(n):
            val = int(x[i]) % MCL_CURVE_ORDER
            # PyMIFE overloads '*' for (scalar * point)
            term = val * ek[i][j]
            
            if t_j is None:
                t_j = term
            else:
                # PyMIFE overloads '+' for (point + point)
                t_j = t_j + term
                
        # Multiply the summation by beta, exactly as PyMIFE does
        c2_points.append(beta * t_j)
        
    c1 = beta * g2
    
    # We format this exactly like fhipe_serializer.py so the Cloud needs zero changes
    payload = {
        "c1": serialize_point(c1),
        "c2": [serialize_point(p) for p in c2_points]
    }
    return json.dumps(payload)