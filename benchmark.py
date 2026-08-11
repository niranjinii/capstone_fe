import time
from mife.single.fhiding.ddh import FeDDH, Bn128Pairing
from mcl_backend import MclPairing

n = 20
x = [i for i in range(n)]
y = [i+1 for i in range(n)]

print(f'--- Benchmarking vector size n={n} ---')

# 1. py_ecc backend (Default)
print('\n[1] Running default py_ecc backend (Pure Python)...')
start_time = time.time()
backend_slow = Bn128Pairing()
key_slow = FeDDH.generate(n, F=backend_slow)
pub_key_slow = key_slow.get_public_key()
keygen_time_slow = time.time() - start_time
print(f'Key Generation: {keygen_time_slow:.3f}s')

start_time = time.time()
ct_slow = FeDDH.encrypt(x, key_slow)
sk_slow = FeDDH.keygen(y, key_slow)
enc_time_slow = time.time() - start_time
print(f'Encryption & SK Gen: {enc_time_slow:.3f}s')

start_time = time.time()
res_slow = FeDDH.decrypt(ct_slow, pub_key_slow, sk_slow, (0, 100000))
eval_time_slow = time.time() - start_time
print(f'Decryption (Evaluation): {eval_time_slow:.3f}s (Result: {res_slow})')


# 2. mclbn256 backend (C++)
print('\n[2] Running Custom mclbn256 backend (C++)...')
start_time = time.time()
backend_fast = MclPairing()
key_fast = FeDDH.generate(n, F=backend_fast)
pub_key_fast = key_fast.get_public_key()
keygen_time_fast = time.time() - start_time
print(f'Key Generation: {keygen_time_fast:.3f}s')

start_time = time.time()
ct_fast = FeDDH.encrypt(x, key_fast)
sk_fast = FeDDH.keygen(y, key_fast)
enc_time_fast = time.time() - start_time
print(f'Encryption & SK Gen: {enc_time_fast:.3f}s')

start_time = time.time()
res_fast = FeDDH.decrypt(ct_fast, pub_key_fast, sk_fast, (0, 100000))
eval_time_fast = time.time() - start_time
print(f'Decryption (Evaluation): {eval_time_fast:.3f}s (Result: {res_fast})')

print(f'\nSPEEDUP: Decryption is {eval_time_slow / eval_time_fast:.1f}x faster!')
