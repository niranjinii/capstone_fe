import json
import mclbn256
from py_ecc.bn128 import FQ, FQ2
from mife.single.fhiding.ddh import FeDDH
from mcl_backend import MclPairing, MclG1Wrapper, MclG2Wrapper, fast_feddh_generate

# -----------------------------------------------------------------------------
# DYNAMIC CLASS RESOLUTION
# Uses MclPairing so _G1Class/_G2Class resolve to mclbn256 wrappers.
# fast_feddh_generate(2) is near-instant for n=2.
# -----------------------------------------------------------------------------
_dummy_master = fast_feddh_generate(2, F=MclPairing())
_dummy_ct = FeDDH.encrypt([0, 0], _dummy_master)
_dummy_sk = FeDDH.keygen([0, 0], _dummy_master)

_CiphertextClass = type(_dummy_ct)
_KeyClass = type(_dummy_sk)
_G2WrapperClass = type(_dummy_ct.c1)   # FeDDH ciphertexts are in G2
_G1WrapperClass = type(_dummy_sk.k1)   # FeDDH functional keys are in G1

# -----------------------------------------------------------------------------
# UNIFIED COORDINATE EXTRACTOR
# Automatically handles both FQ and FQ2 coordinate types.
# -----------------------------------------------------------------------------

def serialize_coord(c):
    """Dynamically serializes FQ or FQ2 coordinates."""
    if hasattr(c, 'coeffs'):
        return [str(coeff.n if hasattr(coeff, 'n') else int(coeff)) for coeff in c.coeffs]
    elif hasattr(c, 'n'):
        return str(c.n)
    else:
        return str(int(c))

def deserialize_coord(data):
    """Dynamically reconstructs FQ or FQ2 coordinates."""
    if isinstance(data, list):
        return FQ2([int(data[0]), int(data[1])])
    else:
        return FQ(int(data))

def serialize_point(pt):
    """Serializes a curve point — auto-detects mclbn256 wrapper or py_ecc wrapper."""
    if pt is None:
        return None
    if hasattr(pt, 'val'):
        # mclbn256 wrapper (MclG1Wrapper or MclG2Wrapper)
        # .serialize() returns compressed bytes; we hex-encode for JSON transport
        return {"mcl": pt.val.serialize().hex()}
    elif hasattr(pt, 'point'):
        # py_ecc wrapper
        raw_tuple = pt.point
        return {"x": serialize_coord(raw_tuple[0]), "y": serialize_coord(raw_tuple[1])}
    else:
        raise ValueError(f"Unknown point type: {type(pt)}")

def deserialize_point(data, TargetClass):
    """Reconstructs a curve point — handles both mclbn256 hex format and py_ecc dict format."""
    if data is None:
        return None
    if isinstance(data, dict) and 'mcl' in data:
        # mclbn256 format — use _deserialize (in-place mutation)
        raw_bytes = bytes.fromhex(data['mcl'])
        if TargetClass == MclG1Wrapper:
            val = mclbn256.G1()
            val._deserialize(raw_bytes)
            return MclG1Wrapper(val)
        else:  # MclG2Wrapper
            val = mclbn256.G2()
            val._deserialize(raw_bytes)
            return MclG2Wrapper(val)
    else:
        # py_ecc format
        obj = TargetClass.__new__(TargetClass)
        obj.point = (deserialize_coord(data["x"]), deserialize_coord(data["y"]))
        return obj

# -----------------------------------------------------------------------------
# CIPHERTEXTS & KEYS
# -----------------------------------------------------------------------------

def serialize_ciphertext(ct):
    """Converts PyMIFE ciphertext object to a JSON string."""
    payload = {
        "c1": serialize_point(ct.c1),
        "c2": [serialize_point(p) for p in ct.c2]
    }
    return json.dumps(payload)

def deserialize_ciphertext(json_str):
    """Reconstructs the PyMIFE ciphertext object from a JSON string."""
    data = json.loads(json_str)
    
    ct_obj = _CiphertextClass.__new__(_CiphertextClass)
    ct_obj.c1 = deserialize_point(data["c1"], _G2WrapperClass)
    ct_obj.c2 = [deserialize_point(p, _G2WrapperClass) for p in data["c2"]]
    
    return ct_obj

def serialize_functional_key(sk):
    """Converts PyMIFE functional key object to a JSON string."""
    payload = {
        "k1": serialize_point(sk.k1),
        "k2": [serialize_point(p) for p in sk.k2]
    }
    return json.dumps(payload)

def deserialize_functional_key(json_str):
    """Reconstructs the PyMIFE functional key object from a JSON string."""
    data = json.loads(json_str)
    
    sk_obj = _KeyClass.__new__(_KeyClass)
    sk_obj.k1 = deserialize_point(data["k1"], _G1WrapperClass)
    sk_obj.k2 = [deserialize_point(p, _G1WrapperClass) for p in data["k2"]]
    
    return sk_obj