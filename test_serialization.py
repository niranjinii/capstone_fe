from mife.single.fhiding.ddh import FeDDH
from fhipe_serializer import (
    serialize_ciphertext, deserialize_ciphertext,
    serialize_functional_key, deserialize_functional_key
)

# 1. Setup and Encryption (Clinic/Hospital)
key = FeDDH.generate(4)
c = FeDDH.encrypt([1, 2, 3, 4], key)
sk = FeDDH.keygen([5, 6, 7, 8], key)

# 2. Convert objects to raw JSON strings (simulating HTTP/Network transmit)
json_ct = serialize_ciphertext(c)
json_sk = serialize_functional_key(sk)

print(f"Serialized Ciphertext length: {len(json_ct)} bytes")
print(f"Serialized Functional Key length: {len(json_sk)} bytes")

# 3. Reconstruct objects at receiver (Cloud)
received_ct = deserialize_ciphertext(json_ct)
received_sk = deserialize_functional_key(json_sk)

# 4. Decrypt
result = FeDDH.decrypt(received_ct, key.get_public_key(), received_sk, (0, 1000))
print(f"Decryption Result after deserialization: {result}")
assert result == 70, "Serialization round-trip failed!"
print("SUCCESS: FHIPE serialization round-trip verified!")