import hashlib
import json
import time
import random
import requests
import numpy as np

import os

class MerkleAuditLog:
    def __init__(self, persistence_path='audit_chain.json'):
        self.entries = []          # List of evaluation records (the leaves)
        self.leaf_hashes = []      # SHA-256 hash of each entry
        self.merkle_root = '0' * 64
        self.persistence_path = persistence_path
        self._load_from_disk()

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    def _compute_merkle_root(self) -> str:
        if not self.leaf_hashes:
            return '0' * 64
        nodes = list(self.leaf_hashes)
        while len(nodes) > 1:
            if len(nodes) % 2 == 1:
                nodes.append(nodes[-1])
            next_level = []
            for i in range(0, len(nodes), 2):
                combined = nodes[i] + nodes[i + 1]
                next_level.append(self._hash(combined))
            nodes = next_level
        return nodes[0]

    def log_evaluation(self, query_id, ciphertext_hash, result):
        entry = {
            'index': len(self.entries),
            'query_id': query_id,
            'timestamp': time.time(),
            'ciphertext_hash': ciphertext_hash,
            'result': result,
        }
        entry_hash = self._hash(json.dumps(entry, sort_keys=True))
        entry['entry_hash'] = entry_hash
        self.entries.append(entry)
        self.leaf_hashes.append(entry_hash)
        self.merkle_root = self._compute_merkle_root()
        self._persist_to_disk()

    def verify_chain(self):
        for i, entry in enumerate(self.entries):
            entry_copy = {k: v for k, v in entry.items() if k != 'entry_hash'}
            recomputed = self._hash(json.dumps(entry_copy, sort_keys=True))
            if recomputed != entry.get('entry_hash'):
                return {'valid': False, 'entries_checked': i, 
                        'merkle_root': self.merkle_root, 'first_broken_index': i}
        recomputed_root = self._compute_merkle_root()
        valid = (recomputed_root == self.merkle_root)
        return {'valid': valid, 'entries_checked': len(self.entries),
                'merkle_root': self.merkle_root, 'first_broken_index': None}

    def _persist_to_disk(self):
        with open(self.persistence_path, 'w') as f:
            json.dump({'entries': self.entries, 'merkle_root': self.merkle_root}, f, indent=2)

    def _load_from_disk(self):
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, 'r') as f:
                    data = json.load(f)
                    self.entries = data.get('entries', [])
                    self.leaf_hashes = [e.get('entry_hash', '') for e in self.entries]
                    self.merkle_root = data.get('merkle_root', '0' * 64)
            except json.JSONDecodeError:
                pass

    def get_log(self):
        return {'entries': self.entries, 'merkle_root': self.merkle_root,
                'total_evaluations': len(self.entries)}

def run_decoy_verification(
    cloud_url,
    master_key,
    quantized_weights,
    weight_shift,
    cert=None,
    verify=True,
    signing_key=None
):
    from mife.single.fhiding.ddh import FeDDH
    from fhipe_serializer import serialize_ciphertext, serialize_functional_key
    from nacl.public import PublicKey, SealedBox
    from nacl.signing import VerifyKey
    import nacl.encoding
    import base64
    import uuid

    n = len(quantized_weights)

    # 1. Create a random dummy patient vector
    dummy_x = [random.randint(0, 5) for _ in range(n)]

    # 2. Compute expected cleartext dot product
    expected_result = sum(
        x * w for x, w in zip(dummy_x, quantized_weights)
    )

    # 3. Encrypt dummy vector using Hospital's master key
    ciphertext = FeDDH.encrypt(dummy_x, master_key)
    serialized_ct = serialize_ciphertext(ciphertext)

    # 4. Generate functional key
    functional_key = FeDDH.keygen(quantized_weights, master_key)
    json_sk = serialize_functional_key(functional_key)

    # 5. Fetch Cloud public encryption key using mTLS
    cloud_resp = requests.get(
        f"{cloud_url}/public_key",
        cert=cert,
        verify=verify
    )
    cloud_resp.raise_for_status()
    cloud_pk_bytes = base64.b64decode(cloud_resp.json()["public_key"])

    cloud_pk = PublicKey(cloud_pk_bytes)
    sealed_box = SealedBox(cloud_pk)

    # Seal the functional key for Cloud
    encrypted_sk = sealed_box.encrypt(json_sk.encode("utf-8"))
    sealed_functional_key = base64.b64encode(encrypted_sk).decode("utf-8")

    # 6. Build a normal Cloud evaluation payload
    payload = {
        "ciphertext": serialized_ct,
        "functional_key": sealed_functional_key,
        "query_id": str(uuid.uuid4()),
        "timestamp": int(time.time())
    }

    # Cloud requires Ed25519 signature on POST payloads
    if signing_key is None:
        return {
            "verified": False,
            "error": "Hospital signing key was not provided"
        }

    payload_bytes = json.dumps(
        payload,
        separators=(",", ":")
    ).encode("utf-8")

    signature = signing_key.sign(payload_bytes).signature.hex()

    headers = {
        "X-Signature": signature,
        "X-Verify-Key": signing_key.verify_key.encode(
            encoder=nacl.encoding.HexEncoder
        ).decode("utf-8"),
        "Content-Type": "application/json"
    }

    # 7. Send signed + mTLS-protected request to Cloud
    try:
        response = requests.post(
            f"{cloud_url}/evaluate",
            data=payload_bytes,
            headers=headers,
            cert=cert,
            verify=verify
        )
        response.raise_for_status()

        # 8. Verify Cloud's Ed25519 response signature
        response_sig = response.headers.get("X-Signature")
        if not response_sig:
            return {
                "verified": False,
                "error": "Cloud response was not signed"
            }

        cloud_signing_resp = requests.get(
            f"{cloud_url}/signing_key",
            cert=cert,
            verify=verify
        )
        cloud_signing_resp.raise_for_status()

        cloud_vk_hex = cloud_signing_resp.json()["verify_key"]
        cloud_vk = VerifyKey(
            cloud_vk_hex.encode("utf-8"),
            encoder=nacl.encoding.HexEncoder
        )

        cloud_vk.verify(
            response.content,
            bytes.fromhex(response_sig)
        )

        # 9. Compare Cloud's result with independently calculated result
        cloud_result = response.json().get("encrypted_result")
        verified = (cloud_result == expected_result)

        return {
            "verified": verified,
            "expected": expected_result,
            "received": cloud_result
        }

    except Exception as e:
        return {
            "verified": False,
            "error": str(e)
        }
