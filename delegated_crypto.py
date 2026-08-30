import json
import random
from py_ecc.bn128 import curve_order as PY_ECC_ORDER
from fhipe_serializer import serialize_point, deserialize_point, _G2WrapperClass

def _prepare_for_serialization(pt):
    """
    Ensures the point is in the exact wrapper class that fhipe_serializer expects.
    If it's a hybrid MclG2Wrapper holding a py_ecc tuple, we repackage it 
    into a PyMIFE _G2WrapperClass so serialize_point() processes it correctly.
    """
    inner_data = getattr(pt, 'inner', getattr(pt, 'val', pt))
    
    if isinstance(inner_data, tuple):
        try:
            # Bypass PyMIFE's strict __init__ constraints using __new__
            obj = _G2WrapperClass.__new__(_G2WrapperClass)
            obj.point = inner_data
            return obj
        except Exception:
            pass
            
    return pt

# -----------------------------------------------------------------------------
# DELEGATED CRYPTO ENGINE
# -----------------------------------------------------------------------------
def generate_ek(master_key):
    """
    Hospital: Converts the secret matrix into public points.
    """
    n = master_key.n
    B_star = master_key.msk.B_star.M  
    g2 = master_key.msk.g2
    
    ek = []
    for i in range(n):
        row = []
        for j in range(n):
            # STRICT FIX: Modulo using py_ecc's true curve order
            val = int(B_star[i][j]) % PY_ECC_ORDER
            row.append(val * g2)
        ek.append(row)
        
    return {"ek": ek, "g2": g2}

def serialize_ek(ek_dict):
    """Hospital: Serializes the entire ek matrix and generator for the network."""
    ek_matrix = [[serialize_point(_prepare_for_serialization(pt)) for pt in row] for row in ek_dict["ek"]]
    g2_pt = serialize_point(_prepare_for_serialization(ek_dict["g2"]))
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
    """
    ek = ek_dict["ek"]
    g2 = ek_dict["g2"]
    n = len(x)
    
    beta = random.randint(1, PY_ECC_ORDER - 1)
    
    c2_points = []
    for j in range(n):
        t_j = None
        for i in range(n):
            val = int(x[i]) % PY_ECC_ORDER
            term = val * ek[i][j]
            
            if t_j is None:
                t_j = term
            else:
                t_j = t_j + term
                
        c2_points.append(beta * t_j)
        
    c1 = beta * g2
    
    payload = {
        "c1": serialize_point(_prepare_for_serialization(c1)),
        "c2": [serialize_point(_prepare_for_serialization(p)) for p in c2_points]
    }
    return json.dumps(payload)