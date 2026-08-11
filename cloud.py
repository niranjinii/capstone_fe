import base64
import traceback
from flask import Flask, request, jsonify
from mife.single.fhiding.ddh import FeDDH, _FeDDH_MK
from mife.data.zmod_r import ZmodR
from nacl.public import PrivateKey, SealedBox
from fhipe_serializer import deserialize_ciphertext, deserialize_functional_key
from mcl_backend import MclPairing

app = Flask(__name__)

# 1. Cloud generates its long-term X25519 keypair on boot
cloud_private_key = PrivateKey.generate()
cloud_public_key = cloud_private_key.public_key

@app.route('/public_key', methods=['GET'])
def get_public_key():
    """Expose the Cloud's public key so the Hospital can seal payloads for it."""
    encoded_pk = base64.b64encode(cloud_public_key.encode()).decode('utf-8')
    return jsonify({"public_key": encoded_pk})

@app.route('/evaluate', methods=['POST'])
def evaluate():
    try:
        data = request.json
        
        # 2. Unseal the functional key using the Cloud's private key
        sealed_box = SealedBox(cloud_private_key)
        encrypted_sk_bytes = base64.b64decode(data['functional_key'])
        decrypted_sk_json = sealed_box.decrypt(encrypted_sk_bytes).decode('utf-8')
        
        # 3. Reconstruct the PyMIFE objects
        ct = deserialize_ciphertext(data['ciphertext'])
        sk = deserialize_functional_key(decrypted_sk_json)
        
        # Build a minimal public key with MclPairing backend — no keygen needed,
        # decrypt() only uses pub.F (backend) and pub.n (dimension)
        _backend = MclPairing()
        pub = _FeDDH_MK.__new__(_FeDDH_MK)
        pub.n = len(sk.k2)
        pub.F = _backend
        pub.G = ZmodR(_backend.order())
        pub.msk = None
        
        # Decrypt using expanded bounds to accommodate real clinical score magnitudes,
        # including negative values since the patient gene vector is not strictly positive.
        result = FeDDH.decrypt(ct, pub, sk, (-1000000, 1000000))
        
        return jsonify({"encrypted_result": result})
    except Exception as e:
        print("\n--- ERROR IN /evaluate ---")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5002)