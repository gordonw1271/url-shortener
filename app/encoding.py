"""Base62 encoding for short codes.

Why base62? It's the smallest URL-safe alphabet that uses only alphanumerics
(0-9, a-z, A-Z) — no escaping needed, no ambiguity from punctuation. With 62
symbols, 6 characters give us 62^6 ≈ 56 billion unique codes, which is far
more than we'll ever need at hobby scale.

Why encode a counter instead of hashing? A counter is collision-free by
construction: every new row gets a unique integer id, and base62(id) is
therefore a unique string. Hashing (e.g. md5 of the long URL) would need
collision handling and would also make the same long URL always map to the
same short code, which can be a feature OR a privacy leak depending on use.
"""

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)


def encode(n: int) -> str:
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return ALPHABET[0]
    chars: list[str] = []
    while n:
        n, rem = divmod(n, BASE)
        chars.append(ALPHABET[rem])
    return "".join(reversed(chars))


def decode(s: str) -> int:
    n = 0
    for ch in s:
        n = n * BASE + ALPHABET.index(ch)
    return n
