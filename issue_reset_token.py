"""
Admin runs this when a budget reset is needed.
Usage:
    python issue_reset_token.py --admin-key admin_signing.key --target-epoch 4 --scope global
    python issue_reset_token.py --admin-key admin_signing.key --target-epoch 4 --scope doctor:dr_alice
"""
import argparse
import base64
import json
import time
from nacl.signing import SigningKey

p = argparse.ArgumentParser(description="Issue a signed budget reset token")
p.add_argument("--admin-key", required=True, help="Path to admin_signing.key")
p.add_argument("--target-epoch", required=True, type=int,
               help="Must be current hospital epoch + 1")
p.add_argument("--scope", default="global",
               help="'global' or 'doctor:<doctor_id>'")
a = p.parse_args()

with open(a.admin_key, "rb") as f:
    sk = SigningKey(f.read())

payload = json.dumps({
    "action": "reset_budget",
    "target_epoch": a.target_epoch,
    "issued_at": int(time.time()),
    "scope": a.scope,
}, separators=(",", ":")).encode()

signed = sk.sign(payload)  # 64-byte sig + payload
token_b64 = base64.b64encode(signed).decode()

print(f"\nReset token (valid for 5 minutes):\n{token_b64}")
print(f"\nPOST to: https://localhost:5001/reset_budget")
print(f'Body:    {{"token": "{token_b64}"}}')
