"""
Admin runs once per doctor to register them.
Usage:
    python register_doctor.py
    (then type doctor name and budget when prompted)
"""
import json
import os
import sys
from nacl.signing import SigningKey
import nacl.encoding

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_FILE = os.path.join(_SCRIPT_DIR, "doctor_registry.json")
SIGNING_KEY_FILE = os.path.join(_SCRIPT_DIR, "hospital_signing.key")

# --- Auto-locate hospital signing key ---
if not os.path.exists(SIGNING_KEY_FILE):
    print(f"ERROR: hospital_signing.key not found at {SIGNING_KEY_FILE}")
    print("       Start hospital.py first so it can generate the key, then run this script.")
    sys.exit(1)

with open(SIGNING_KEY_FILE, "rb") as f:
    hospital_sk = SigningKey(f.read())

# --- Interactive prompts ---
print("=" * 50)
print("  DOCTOR REGISTRATION")
print("=" * 50)

while True:
    raw = input("  Doctor name (e.g. 'alice' or 'dr_alice'): ").strip()
    if not raw:
        continue
    normalised = raw.lower().replace(" ", "_")
    if not normalised.startswith("dr_"):
        normalised = "dr_" + normalised
    doctor_id = normalised
    break

while True:
    raw_budget = input(f"  XAI privacy budget for {doctor_id} (default 10.0): ").strip()
    if not raw_budget:
        budget = 10.0
        break
    try:
        budget = float(raw_budget)
        break
    except ValueError:
        print("  Please enter a number, e.g. 10.0")

# --- Generate doctor keypair ---
doctor_sk = SigningKey.generate()
doctor_vk_hex = doctor_sk.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()

# --- Save doctor's private key ---
key_file = os.path.join(_SCRIPT_DIR, f"{doctor_id}.key")
with open(key_file, "wb") as f:
    f.write(doctor_sk.encode())

# --- Load existing registry ---
registry = {}
if os.path.exists(REGISTRY_FILE):
    with open(REGISTRY_FILE) as f:
        wrapper = json.load(f)
    if "data_hex" in wrapper:
        registry = json.loads(bytes.fromhex(wrapper["data_hex"]))
    else:
        registry = wrapper

# --- Add/update doctor ---
registry[doctor_id] = {
    "verify_key": doctor_vk_hex,
    "budget": budget,
    "enabled": True,
}

# --- Write signed registry ---
data_bytes = json.dumps(registry, separators=(",", ":")).encode()
signature = hospital_sk.sign(data_bytes).signature.hex()
wrapper = {"signature": signature, "data_hex": data_bytes.hex()}

with open(REGISTRY_FILE, "w") as f:
    json.dump(wrapper, f)

print()
print(f"  ✓ Doctor '{doctor_id}' registered with budget={budget} epsilon.")
print(f"  ✓ Private key saved: {os.path.basename(key_file)}")
print(f"  ✓ Registry updated: {os.path.basename(REGISTRY_FILE)}")
print()
print("  Keep the .key file safe — give it to the doctor, don't share it.")
