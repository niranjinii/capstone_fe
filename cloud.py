import base64
import multiprocessing
import traceback
from concurrent.futures import ProcessPoolExecutor
from flask import Flask, request, jsonify
from mife.single.fhiding.ddh import FeDDH
from nacl.public import PrivateKey, SealedBox

from fhipe_serializer import deserialize_ciphertext, deserialize_functional_key

try:
    multiprocessing.set_start_method("fork")
except RuntimeError:
    pass

app = Flask(__name__)

cloud_private_key = PrivateKey.generate()
cloud_public_key = cloud_private_key.public_key

def decrypt_single_evaluation(eval_item: dict, private_key: PrivateKey) -> int:
    sealed_box = SealedBox(private_key)
    encrypted_sk_bytes = base64.b64decode(eval_item["functional_key"])
    decrypted_sk_json = sealed_box.decrypt(encrypted_sk_bytes).decode("utf-8")
    
    ct = deserialize_ciphertext(eval_item["ciphertext"])
    sk = deserialize_functional_key(decrypted_sk_json)
    
    dim = len(ct.c2)
    dummy_pk = FeDDH.generate(dim).get_public_key()
    return FeDDH.decrypt(ct, dummy_pk, sk, (0, 50000))

def _worker_wrapper(args):
    item, priv_bytes = args
    priv_key = PrivateKey(priv_bytes)
    return decrypt_single_evaluation(item, priv_key)

@app.route("/public_key", methods=["GET"])
def get_public_key():
    encoded_pk = base64.b64encode(cloud_public_key.encode()).decode("utf-8")
    return jsonify({"public_key": encoded_pk})

@app.route("/evaluate", methods=["POST"])
def evaluate():
    try:
        data = request.json
        result = decrypt_single_evaluation(data, cloud_private_key)
        return jsonify({"encrypted_result": result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/evaluate_batch", methods=["POST"])
def evaluate_batch():
    try:
        data = request.json
        items = data.get("evaluations", [])
        if not items:
            return jsonify({"error": "No evaluation items provided"}), 400
            
        priv_bytes = bytes(cloud_private_key)
        worker_args = [(item, priv_bytes) for item in items]
        
        with ProcessPoolExecutor(max_workers=min(len(items), 8)) as executor:
            results = list(executor.map(_worker_wrapper, worker_args))
            
        return jsonify({"results": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5002)