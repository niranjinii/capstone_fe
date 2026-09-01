"""
Admin runs once per doctor to register them.
Usage:
    python register_doctor.py --doctor-id dr_alice --budget 10.0
    python register_doctor.py --doctor-id dr_bob --budget 15.0
"""
import argparse
import json
import os
from nacl.signing import SigningKey
import nacl.encoding

p = argparse.ArgumentParser(description="Register a new doctor in the hospital registry")
p.add_argument("--doctor-id", required=True, help="Unique doctor identifier")
p.add_argument("--budget", type=float, default=10.0,
               help="XAI privacy budget (epsilon) for this doctor")
p.add_argument("--hospital-signing-key", default="hospital_signing.key",
               help="Path to hospital signing key (to re-sign the registry)")
a = p.parse_args()

# Generate doctor keypair
doctor_sk = SigningKey.generate()
doctor_vk_hex = doctor_sk.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()

# Save doctor's private key
key_file = f"{a.doctor_id}.key"
with open(key_file, "wb") as f:
    f.write(doctor_sk.encode())

# Load existing registry (unsigned raw dict at this point)
REGISTRY_FILE = "doctor_registry.json"
registry = {}
if os.path.exists(REGISTRY_FILE):
    with open(REGISTRY_FILE) as f:
        wrapper = json.load(f)
    if "data_hex" in wrapper:
        # Already signed — extract inner data
        registry = json.loads(bytes.fromhex(wrapper["data_hex"]))
    else:
        registry = wrapper

# Add/update doctor
registry[a.doctor_id] = {
    "verify_key": doctor_vk_hex,
    "budget": a.budget,
    "enabled": True,
}

# 🛡️ Gap #2: ALWAYS write signed wrapper — never write unsigned JSON
with open(a.hospital_signing_key, "rb") as f:
    hospital_sk = SigningKey(f.read())

data_bytes = json.dumps(registry, separators=(",", ":")).encode()
signature = hospital_sk.sign(data_bytes).signature.hex()
wrapper = {"signature": signature, "data_hex": data_bytes.hex()}

with open(REGISTRY_FILE, "w") as f:
    json.dump(wrapper, f)

print(f"Doctor '{a.doctor_id}' registered with budget={a.budget} epsilon.")
print(f"  Private key: {key_file}  — give this to the doctor, keep it secret.")
print(f"  Registry updated: {REGISTRY_FILE}")
