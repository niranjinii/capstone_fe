import mclbn256
import random
from mife.data.pairing import PairingBase
from mife.data.group import GroupElem

MCL_CURVE_ORDER = 16798108731015832284940804142231733909759579603404752749028378864165570215949

def _to_fr(scalar: int):
    """Safely converts a python int to mclbn256.Fr"""
    fr = mclbn256.Fr()
    pos_scalar = scalar % MCL_CURVE_ORDER
    hex_scalar = hex(pos_scalar)[2:]
    hex_bytes = hex_scalar.encode()
    
    methods_to_try = [
        lambda: fr.fromstr(hex_bytes, 16),
        lambda: fr.fromstr(hex_scalar, 16),
        lambda: fr.fromstr(hex_bytes),
        lambda: fr.fromstr(hex_scalar),
    ]
    for m in methods_to_try:
        try:
            m()
            return fr
        except Exception:
            continue
    try:
        return mclbn256.Fr(pos_scalar)
    except Exception:
        return mclbn256.Fr(hex_scalar)


class MclG1Wrapper(GroupElem):
    def __init__(self, val=None):
        self.val = val

    @property
    def inner(self):
        # Safely extracts without triggering the 'None' getattr trap
        if hasattr(self, 'val') and self.val is not None:
            return self.val
        if hasattr(self, 'point') and self.point is not None:
            return self.point
        return None

    def __add__(self, other):
        if isinstance(self.inner, tuple):
            from py_ecc.bn128 import add
            return MclG1Wrapper(add(self.inner, other.inner))
        return MclG1Wrapper(self.inner + other.inner)

    def __neg__(self):
        if isinstance(self.inner, tuple):
            from py_ecc.bn128 import neg
            return MclG1Wrapper(neg(self.inner))
        return MclG1Wrapper(-self.inner)

    def __rmul__(self, scalar: int):
        if isinstance(self.inner, tuple):
            from py_ecc.bn128 import multiply
            return MclG1Wrapper(multiply(self.inner, int(scalar)))
        fr = _to_fr(scalar)
        return MclG1Wrapper(self.inner * fr)

    def __eq__(self, other):
        if isinstance(self.inner, tuple):
            return self.inner == other.inner
        return self.inner.serialize() == other.inner.serialize()

    def __hash__(self):
        if isinstance(self.inner, tuple):
            return hash(str(self.inner))
        return hash(self.inner.serialize())

    def export(self) -> dict:
        pass


class MclG2Wrapper(GroupElem):
    def __init__(self, val=None):
        self.val = val

    @property
    def inner(self):
        if hasattr(self, 'val') and self.val is not None:
            return self.val
        if hasattr(self, 'point') and self.point is not None:
            return self.point
        return None

    def __add__(self, other):
        if isinstance(self.inner, tuple):
            from py_ecc.bn128 import add
            return MclG2Wrapper(add(self.inner, other.inner))
        return MclG2Wrapper(self.inner + other.inner)

    def __neg__(self):
        if isinstance(self.inner, tuple):
            from py_ecc.bn128 import neg
            return MclG2Wrapper(neg(self.inner))
        return MclG2Wrapper(-self.inner)

    def __rmul__(self, scalar: int):
        if isinstance(self.inner, tuple):
            from py_ecc.bn128 import multiply
            return MclG2Wrapper(multiply(self.inner, int(scalar)))
        fr = _to_fr(scalar)
        return MclG2Wrapper(self.inner * fr)

    def __eq__(self, other):
        if isinstance(self.inner, tuple):
            return self.inner == other.inner
        return self.inner.serialize() == other.inner.serialize()

    def __hash__(self):
        if isinstance(self.inner, tuple):
            return hash(str(self.inner))
        return hash(self.inner.serialize())

    def export(self) -> dict:
        pass


class MclGTWrapper(GroupElem):
    def __init__(self, val=None):
        self.val = val

    @property
    def inner(self):
        if hasattr(self, 'val') and self.val is not None:
            return self.val
        if hasattr(self, 'point') and self.point is not None:
            return self.point
        return None

    def __add__(self, other):
        return MclGTWrapper(self.inner * other.inner)

    def __neg__(self):
        inv = mclbn256.GT()
        mclbn256.mclbn256.GT_inv(inv, self.inner)
        return MclGTWrapper(inv)

    def __rmul__(self, scalar: int):
        fr = _to_fr(scalar)
        return MclGTWrapper(self.inner ** fr)

    def __eq__(self, other):
        return self.inner.serialize() == other.inner.serialize()

    def __hash__(self):
        return hash(self.inner.serialize())

    def export(self) -> dict:
        pass


class MclPairing(PairingBase):
    def __init__(self):
        self._g1 = mclbn256.G1()
        self._g1.hash(b"1")

        self._g2 = mclbn256.G2()
        self._g2.hash(b"1")
        
        self._identity_t = None

    def order(self) -> int:
        return MCL_CURVE_ORDER

    def generator1(self) -> MclG1Wrapper:
        return MclG1Wrapper(self._g1)

    def generator2(self) -> MclG2Wrapper:
        return MclG2Wrapper(self._g2)

    def generatorT(self) -> MclGTWrapper:
        return self.pairing(self.generator1(), self.generator2())

    def identity1(self) -> MclG1Wrapper:
        g = mclbn256.G1()
        g.clear()
        return MclG1Wrapper(g)

    def identity2(self) -> MclG2Wrapper:
        g = mclbn256.G2()
        g.clear()
        return MclG2Wrapper(g)

    def identityT(self) -> MclGTWrapper:
        if self._identity_t is None:
            g = mclbn256.GT()
            g.clear()
            self._identity_t = MclGTWrapper(g)
        return self._identity_t

    def pairing(self, g1: MclG1Wrapper, g2: MclG2Wrapper) -> MclGTWrapper:
        gt = g1.inner.pairing(g2.inner)
        return MclGTWrapper(gt)


def fast_feddh_generate(n: int, F=None):
    from mife.single.fhiding.ddh import _FeDDH_MK, _FeDDH_MSK
    from mife.data.zmod_r import ZmodR
    from mife.data.matrix import Matrix

    if F is None:
        F = MclPairing()

    g1 = F.generator1()
    g2 = F.generator2()
    order = F.order()
    G = ZmodR(order)

    while True:
        B_raw = [[random.randint(0, order - 1) for _ in range(n)] for _ in range(n)]
        A = [row[:] for row in B_raw]
        I = [[1 if i == j else 0 for j in range(n)] for i in range(n)]
        det = 1
        valid = True

        for i in range(n):
            pivot = i
            while pivot < n and A[pivot][i] == 0:
                pivot += 1
            if pivot == n:
                valid = False
                break

            A[i], A[pivot] = A[pivot], A[i]
            I[i], I[pivot] = I[pivot], I[i]
            if pivot != i:
                det = -det

            pivot = i
            factor = A[pivot][i]
            try:
                factor_inv = pow(factor, -1, order)
            except ValueError:
                valid = False
                break

            det = (det * factor) % order
            for j in range(n):
                A[pivot][j] = (A[pivot][j] * factor_inv) % order
                I[pivot][j] = (I[pivot][j] * factor_inv) % order
            for j in range(n):
                if j == pivot:
                    continue
                t = A[j][pivot]
                for k in range(n):
                    I[j][k] = (I[j][k] - t * I[pivot][k]) % order
                    A[j][k] = (A[j][k] - t * A[pivot][k]) % order

        if valid:
            break

    B_star_raw = [[(det * I[j][i]) % order for j in range(n)] for i in range(n)]
    B_matrix = Matrix([[G(val) for val in row] for row in B_raw])
    B_star_matrix = Matrix([[G(val) for val in row] for row in B_star_raw])

    msk = _FeDDH_MSK(g1, g2, B_matrix, B_star_matrix, G(det))
    return _FeDDH_MK(n, F, G, msk=msk)