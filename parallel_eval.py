import multiprocessing
import time
from mife.single.fhiding.ddh import FeDDH

# Try to load MclPairing if mclbn256 is installed, otherwise fallback to default
try:
    from mcl_backend import MclPairing, fast_feddh_generate
    HAS_MCL = True
except ImportError:
    HAS_MCL = False
    print('Warning: mclbn256 not found. Falling back to slow py_ecc backend.')

# Single shared master key — set in parent before fork() so all workers
# inherit it from memory. Zero pickling cost, 20s setup instead of 80s.
GLOBAL_KEY = None




def evaluate_bucket(bucket_data):
    bucket_id = bucket_data['id']
    n = bucket_data['n']

    # All workers share the same master key inherited via fork() — no pickling.
    key = GLOBAL_KEY
    pub_key = key.get_public_key()

    print(f'Bucket {bucket_id}: Encrypting vector of size {n}...')
    start = time.time()
    ct = FeDDH.encrypt(bucket_data['x'], key)
    sk = FeDDH.keygen(bucket_data['y'], key)
    enc_time = time.time() - start

    print(f'Bucket {bucket_id}: Evaluating (Decrypting)...')
    start = time.time()
    result = FeDDH.decrypt(ct, pub_key, sk, (0, 10000))
    eval_time = time.time() - start

    return {'id': bucket_id, 'result': result, 'enc_time': enc_time, 'eval_time': eval_time}


if __name__ == '__main__':
    # fork() is required: workers must inherit BUCKET_KEYS from parent memory.
    # Python 3.14 defaults to forkserver which re-imports and loses all globals.
    multiprocessing.set_start_method('fork')

    n_size = 300
    n_buckets = 4

    print('Initializing parallel evaluation...')
    print(f'\n--- SETUP PHASE ---')
    print(f'Generating Master Key for n={n_size} (one-time, shared across all buckets)...')
    print('This takes ~20s...')
    setup_start = time.time()
    if HAS_MCL:
        backend = MclPairing()
        GLOBAL_KEY = fast_feddh_generate(n_size, F=backend)
    else:
        GLOBAL_KEY = FeDDH.generate(n_size)
    print(f'Key ready in {time.time()-setup_start:.1f}s!\n')

    # Buckets only carry data — key is inherited from parent via fork()
    buckets = [
        {'id': i, 'n': n_size, 'x': [i + 1] * n_size, 'y': [2] * n_size}
        for i in range(n_buckets)
    ]

    print('--- PARALLEL EVALUATION PHASE ---')
    total_start = time.time()

    # Pool is created AFTER GLOBAL_KEY is populated — fork() clones the full
    # parent memory into each worker, so they all see GLOBAL_KEY immediately.
    with multiprocessing.Pool(processes=n_buckets) as pool:
        results = pool.map(evaluate_bucket, buckets)

    total_time = time.time() - total_start

    print('\n--- Results ---')
    for r in results:
        bid = r['id']
        score = r['result']
        enc = r['enc_time']
        ev = r['eval_time']
        print(f'Bucket {bid}: Score = {score} (Enc: {enc:.3f}s, Eval: {ev:.3f}s)')

    seq_time = sum(r['enc_time'] + r['eval_time'] for r in results)
    print(f'\nTotal Wall-Clock Time (parallel): {total_time:.3f}s')
    print(f'Equivalent sequential time:       {seq_time:.3f}s')
    print(f'Parallel speedup:                 {seq_time / total_time:.1f}x')
