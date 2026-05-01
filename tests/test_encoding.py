import pytest

from app.encoding import ALPHABET, BASE, decode, encode


def test_alphabet_is_base62():
    assert BASE == 62
    assert len(ALPHABET) == 62
    assert len(set(ALPHABET)) == 62  # no duplicates


def test_zero_encodes_to_first_char():
    assert encode(0) == ALPHABET[0]


@pytest.mark.parametrize(
    "n,expected",
    [
        (1, "1"),
        (10, "a"),
        (35, "z"),
        (36, "A"),
        (61, "Z"),
        (62, "10"),
        (63, "11"),
    ],
)
def test_known_encodings(n, expected):
    assert encode(n) == expected


@pytest.mark.parametrize("n", [1, 5, 61, 62, 63, 100, 3844, 9999, 10**6, 10**12])
def test_encode_decode_round_trip(n):
    assert decode(encode(n)) == n


def test_one_million_fits_in_four_chars():
    assert len(encode(10**6)) <= 4


def test_negative_raises():
    with pytest.raises(ValueError):
        encode(-1)
