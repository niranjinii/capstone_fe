import requests
import json
import base64
from nacl.public import PublicKey, SealedBox
from fhipe_serializer import serialize_ciphertext, serialize_functional_key
from mcl_backend import MclPairing, fast_feddh_generate
from mife.single.fhiding.ddh import FeDDH

cloud_url = "http://127.0.0.1:5004"
DIMENSION = 139
master_key = fast_feddh_generate(DIMENSION, F=MclPairing())

dummy_x = [2] * DIMENSION
quantized_weights = [5] * DIMENSION

ciphertext = FeDDH.encrypt(dummy_x, master_key)
serialized_ct = serialize_ciphertext(ciphertext)

functional_key = FeDDH.keygen(quantized_weights, master_key)
json_sk = serialize_functional_key(functional_key)

cloud_resp = requests.get(f"{cloud_url}/public_key").json()
cloud_pk_bytes = base64.b64decode(cloud_resp['public_key'])
cloud_pk = PublicKey(cloud_pk_bytes)

sealed_box = SealedBox(cloud_pk)
encrypted_sk = sealed_box.encrypt(json_sk.encode('utf-8'))
sealed_functional_key = base64.b64encode(encrypted_sk).decode('utf-8')

payload = {
    "ciphertext": serialized_ct,
    "functional_key": sealed_functional_key
}

res = requests.post(f"{cloud_url}/evaluate", json=payload)
print(res.status_code, res.text)
