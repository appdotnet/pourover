"""
The ``agar.keygen`` module contains functions for generating unique keys of various lengths.
"""

from uuid import uuid4
import basin


def _encode(bytes):
    return basin.encode('23456789abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ', basin.bytestring_to_integer(bytes))

def _gen_key(size=2):
    return ''.join(''.join(it) for it in zip(uuid4().bytes for _ in range(size)))


def gen_short_key():
    """
    Generates a short key (22 chars +/- 1) with a high probability of uniqueness
    """
    return _encode(_gen_key(size=1))

def gen_medium_key():
    """
    Generates a medium key (44 chars +/- 1) with a higher probability of uniqueness
    """
    return _encode(_gen_key(size=2))

def gen_long_key():
    """
    Generates a long key (66 chars +/- 1) with the highest probability of uniqueness
    """
    return _encode(_gen_key(size=3))

generate_key = gen_medium_key
