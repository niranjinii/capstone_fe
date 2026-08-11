from mcl_backend import MclPairing, fast_feddh_generate, MCL_CURVE_ORDER
import random
import time

F = MclPairing()
g2 = F.generator2()

N = 300
print('Generating fake ek...')
ek = [[g2 for _ in range(N)] for _ in range(N)]
x = [random.randint(0, 100) for _ in range(N)]

print('Encrypting...')
start = time.time()
beta = random.randint(1, MCL_CURVE_ORDER - 1)
c2_points = []
for j in range(N):
    t_j = None
    for i in range(N):
        term = int(x[i]) * ek[i][j]
        if t_j is None:
            t_j = term
        else:
            t_j = t_j + term
    c2_points.append(beta * t_j)
print('Time taken for N=300:', time.time() - start)
