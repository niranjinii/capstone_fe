"""
One-shot script. Run once to generate the admin Ed25519 keypair.
  - admin_signing.key → KEEP OFFLINE, never on the hospital server
  - admin_verify.pub  → copy to the hospital server directory
"""
from nacl.signing import SigningKey

sk = SigningKey.generate()
with open("admin_signing.key", "wb") as f:
    f.write(sk.encode())
with open("admin_verify.pub", "wb") as f:
    f.write(sk.verify_key.encode())
print("Generated admin keypair.")
print("  admin_signing.key  →  keep this OFFLINE (air-gapped)")
print("  admin_verify.pub   →  deploy this to the hospital server")
