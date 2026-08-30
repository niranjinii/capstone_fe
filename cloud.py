import base64
import multiprocessing
import traceback
import logging
from concurrent.futures import ProcessPoolExecutor
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("Cloud")
from mife.single.fhiding.ddh import FeDDH
from nacl.public import PrivateKey, SealedBox

from fhipe_serializer import deserialize_ciphertext, deserialize_functional_key
from bsgs import feddh_decrypt_bsgs

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
    
    logger.info("Decrypting single evaluation...")
    ct = deserialize_ciphertext(eval_item["ciphertext"])
    sk = deserialize_functional_key(decrypted_sk_json)
    
    # Decrypt using O(sqrt(N)) BSGS over a massive range (-1M, 1M)
    logger.info("Executing BSGS discrete log solver over (-1,000,000 to 1,000,000)...")
    result = feddh_decrypt_bsgs(ct, sk, (-1000000, 1000000))
    logger.info(f"BSGS decryption successful. Encrypted inner product result: {result}")
    return result

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
    logger.info("Received POST /evaluate request.")
    try:
        data = request.json
        result = decrypt_single_evaluation(data, cloud_private_key)
        logger.info("Single evaluation complete.")
        return jsonify({"encrypted_result": result})
    except Exception as e:
        logger.error(f"Evaluation error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/evaluate_batch", methods=["POST"])
def evaluate_batch():
    logger.info("Received POST /evaluate_batch request.")
    try:
        data = request.json
        items = data.get("evaluations", [])
        if not items:
            logger.warning("No evaluation items provided in batch request.")
            return jsonify({"error": "No evaluation items provided"}), 400
            
        logger.info(f"Processing batch of {len(items)} evaluations...")
        priv_bytes = bytes(cloud_private_key)
        worker_args = [(item, priv_bytes) for item in items]
        
        with ProcessPoolExecutor(max_workers=min(len(items), 8)) as executor:
            results = list(executor.map(_worker_wrapper, worker_args))
            
        logger.info("Batch evaluation complete.")
        return jsonify({"results": results})
    except Exception as e:
        logger.error(f"Batch evaluation error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5002)