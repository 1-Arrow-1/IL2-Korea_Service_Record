"""
AES-192-ECB and the gtpack key schedule.

Lifted verbatim from ``il2k_extract.py`` (the standalone extractor written for
this game's archives) so the two cannot drift apart. Decryption only; no
third-party modules, so every line is auditable.

The key for a file is derived from its own virtual path — lowercase, forward
slashes, leading '/'. See ``archive.py`` for the container layout.
"""

import struct  # noqa: F401  (kept so the lifted region needs no edits)

# --------------------------------------------------------------- AES-192 ---
# Decryption only. Tables are computed, not pasted, so they can be checked.

def _build_tables():
    sbox = [0] * 256
    p = q = 1
    while True:                                  # walk the generator 3
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1; q ^= q << 2; q ^= q << 4; q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) \
              ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    inv = [0] * 256
    for i, v in enumerate(sbox):
        inv[v] = i
    return sbox, inv


SBOX, INV_SBOX = _build_tables()
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _xt(a):                                       # multiply by 2 in GF(2^8)
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        b >>= 1
        a = _xt(a)
    return r


def _expand_key(key):
    """AES-192: Nk=6, Nr=12 -> 52 words."""
    nk, nr = 6, 12
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]                                   # RotWord
            t = [SBOX[b] for b in t]                            # SubWord
            t[0] ^= RCON[i // nk - 1]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w


def _add_round_key(s, w, rnd):
    for c in range(4):
        for r in range(4):
            s[r + 4 * c] ^= w[4 * rnd + c][r]


def decrypt_block(block, w):
    s = list(block)
    _add_round_key(s, w, 12)
    for rnd in range(11, -1, -1):
        # InvShiftRows
        for r in range(1, 4):
            row = [s[r + 4 * c] for c in range(4)]
            row = row[-r:] + row[:-r]
            for c in range(4):
                s[r + 4 * c] = row[c]
        # InvSubBytes
        s = [INV_SBOX[b] for b in s]
        _add_round_key(s, w, rnd)
        if rnd:                                                 # InvMixColumns
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                s[4 * c + 0] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
                s[4 * c + 1] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
                s[4 * c + 2] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
                s[4 * c + 3] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)
    return bytes(s)


# Three backends, fastest first:
#   1. Windows CNG (bcrypt.dll) via ctypes - native speed, stdlib only
#   2. pycryptodome, if the user happens to have it
#   3. the pure-Python code above - correct but ~34 KB/s, fine for a few files
class _CNG:
    """AES-192-ECB through Windows' own crypto library. No install needed."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes
        self.b = ctypes.WinDLL("bcrypt.dll")
        self.h = ctypes.c_void_p()
        if self.b.BCryptOpenAlgorithmProvider(ctypes.byref(self.h), "AES", None, 0):
            raise OSError("BCryptOpenAlgorithmProvider failed")
        mode = "ChainingModeECB".encode("utf-16-le") + b"\0\0"
        if self.b.BCryptSetProperty(self.h, "ChainingMode", mode, len(mode), 0):
            raise OSError("BCryptSetProperty(ECB) failed")

    def decrypt(self, data, key):
        ct = self.ct
        hkey = ct.c_void_p()
        kb = ct.create_string_buffer(key, len(key))
        if self.b.BCryptGenerateSymmetricKey(self.h, ct.byref(hkey), None, 0,
                                             kb, len(key), 0):
            raise OSError("BCryptGenerateSymmetricKey failed")
        try:
            n = len(data) // 16 * 16
            out = ct.create_string_buffer(n)
            done = ct.c_ulong(0)
            if self.b.BCryptDecrypt(hkey, data, n, None, None, 0,
                                    out, n, ct.byref(done), 0):
                raise OSError("BCryptDecrypt failed")
            return out.raw[:done.value]
        finally:
            self.b.BCryptDestroyKey(hkey)


_BACKEND = None


def _backend():
    global _BACKEND
    if _BACKEND is None:
        try:
            _BACKEND = ("cng", _CNG())
        except Exception:
            try:
                from Crypto.Cipher import AES
                _BACKEND = ("pycryptodome", AES)
            except ImportError:
                _BACKEND = ("pure-python", None)
    return _BACKEND


def decrypt_ecb(data, key):
    n = len(data) // 16 * 16
    if n == 0:
        return b""
    kind, impl = _backend()
    if kind == "cng":
        return impl.decrypt(data, key)
    if kind == "pycryptodome":
        return impl.new(key, impl.MODE_ECB).decrypt(data[:n])
    w = _expand_key(key)
    return b"".join(decrypt_block(data[i:i + 16], w) for i in range(0, n, 16))


# ------------------------------------------------------------ key schedule --
M = 0xFFFFFFFF


def path_hash(vpath):
    b = vpath.encode("utf-8")
    h = b[0]
    for c in b[1:]:
        h = (h * 0x25 + c) & M
    return h


def derive_key(h):
    x = (h ^ 0xDEADBEEF) & M
    x = ((x ^ (x >> 16)) * 0x49A312C0) & M
    x = ((x ^ (x >> 15)) * 0x10D0143A) & M
    y = (x ^ (x >> 16)) & M
    z = (y ^ 0xA5A5A5A5) & M
    a = ((x >> 24) ^ y) & 0xFF
    b = ((y >> 8) ^ (x >> 16)) & 0xFF
    c = ((z >> 8) ^ (z >> 16)) & 0xFF
    d = (z ^ (z >> 24)) & 0xFF
    return bytes([a, b, b, a, a, b, b, a, a, b, b, a,
                  c, d, d, c, c, d, d, c, c, d, d, c])
