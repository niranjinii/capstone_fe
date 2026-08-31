import requests
import base64
from nacl.public import PublicKey, SealedBox

# Fetch key from 5004
cloud_resp = requests.get("http://127.0.0.1:5004/public_key").json()
print("Cloud Public Key:", cloud_resp['public_key'])
cloud_pk_bytes = base64.b64decode(cloud_resp['public_key'])
cloud_pk = PublicKey(cloud_pk_bytes)

sealed_box = SealedBox(cloud_pk)
enc = sealed_box.encrypt(b'test data')
payload = {
    "ciphertext": "dummy",
    "functional_key": base64.b64encode(enc).decode('utf-8')
}

res = requests.post("http://127.0.0.1:5004/evaluate", json=payload)
print(res.status_code, res.text)
