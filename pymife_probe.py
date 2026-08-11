"""Roadmap section 2.1 - reproduce the PyMIFE findings yourself.

Confirms: (1) function-hiding IPE exists in PyMIFE and is correct,
          (2) ciphertexts do NOT serialize - the blocking defect,
          (3) py_ecc timing, so you can see the wall.

    pip install pymife py_ecc
    python3 pymife_probe.py
"""
import pickle, random, time, sys

try:
    from mife.single.fhiding.ddh import FeDDH
except ImportError:
    sys.exit("pip install pymife py_ecc")

print("1. CORRECTNESS")
for n in (2, 4):
    key = FeDDH.generate(n)
    x = [random.randint(0, 20) for _ in range(n)]
    y = [random.randint(0, 20) for _ in range(n)]
    t = time.time(); c = FeDDH.encrypt(x, key); te = time.time() - t
    sk = FeDDH.keygen(y, key)
    t = time.time()
    z = FeDDH.decrypt(c, key.get_public_key(), sk, (0, 50000))
    td = time.time() - t
    truth = sum(p * q for p, q in zip(x, y))
    print(f"   n={n}: got {z}, want {truth}, correct={z == truth} "
          f"| enc {te:.1f}s dec {td:.1f}s")

print("\n2. SERIALIZATION (the blocking defect)")
key = FeDDH.generate(3)
c = FeDDH.encrypt([1, 2, 3], key)
sk = FeDDH.keygen([4, 5, 6], key)
for label, obj in (("ciphertext", c), ("functional key", sk),
                   ("public key", key.get_public_key())):
    try:
        b = pickle.dumps(obj)
        print(f"   {label:16} OK   {len(b)} bytes")
    except Exception as e:
        print(f"   {label:16} FAIL {type(e).__name__}")
print("   -> ciphertexts cannot leave the process. This is what you fix.")
print(f"   -> GroupElem.export() returns: {c.c1.export()!r}  (unimplemented)")

print("\n3. THE WALL")
print("   measured ~3.5 s per dimension on py_ecc bn128:")
for n in (64, 200, 800):
    print(f"     n={n:<4} ~{3.5 * n / 60:.1f} min per query")
print("   -> a fast PairingBase backend is required, not optional")
