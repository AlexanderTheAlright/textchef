"""Group duplicate texts so each is embedded, clustered and shown once.

Exact: same text after lowercasing and dropping punctuation.
Near: word 4-shingle Jaccard of at least NEAR, found with MinHash banding
and then checked exactly.
"""
from __future__ import annotations

import re
import zlib

import numpy as np

NEAR = 0.9
SHINGLE = 4
BANDS, ROWS = 8, 4          # a pair at Jaccard 0.9 shares a band with probability 0.9998
_NORM = re.compile(r"[^a-z0-9]+")
_PRIME = (1 << 61) - 1


def normalize(text: str) -> str:
    return _NORM.sub(" ", text.lower()).strip()


def _shingles(norm: str) -> np.ndarray:
    words = norm.split()
    if len(words) <= SHINGLE:
        return np.array([zlib.crc32(norm.encode())], np.int64)
    grams = {" ".join(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}
    return np.array([zlib.crc32(g.encode()) for g in grams], np.int64)


def group_duplicates(texts: list[str]) -> tuple[np.ndarray, int, int]:
    """Return (group index per text, texts merged as exact, texts merged as near)."""
    norms = [normalize(t) for t in texts]
    first: dict[str, int] = {}
    exact_of = np.array([first.setdefault(n, len(first)) for n in norms])
    keys = list(first)                      # one entry per exact group
    n_exact = len(texts) - len(keys)

    rng = np.random.default_rng(42)
    a = rng.integers(1, _PRIME, BANDS * ROWS, dtype=np.int64)
    b = rng.integers(0, _PRIME, BANDS * ROWS, dtype=np.int64)
    sets = [_shingles(k) for k in keys]
    parent = list(range(len(keys)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    buckets: dict[tuple, int] = {}
    for i, s in enumerate(sets):
        sig = ((s[:, None] * a + b) % _PRIME).min(0)
        for band in range(BANDS):
            key = (band, *sig[band * ROWS:(band + 1) * ROWS].tolist())
            j = buckets.setdefault(key, i)
            if j == i or find(i) == find(j):
                continue
            inter = len(np.intersect1d(s, sets[j], assume_unique=True))
            if inter / (len(s) + len(sets[j]) - inter) >= NEAR:
                parent[find(i)] = find(j)

    roots = np.array([find(i) for i in range(len(keys))])
    _, group_of_key = np.unique(roots, return_inverse=True)
    n_near = len(keys) - int(group_of_key.max() + 1 if len(keys) else 0)
    return group_of_key[exact_of].astype(np.int32), n_exact, n_near
