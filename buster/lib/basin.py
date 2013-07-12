"""
Basin is a Python module for generating string representations of integers
and bytestrings with arbitrary base and alphabet.

"""

__all__ = ['encode', 'decode', 'bytestring_to_integer',
    'integer_to_bytestring']

def encode(alphabet, n):
    """
    Encode integer value `n` using `alphabet`. The resulting string will be a
    base-N representation of `n`, where N is the length of `alphabet`.
    
    """
    
    if not (isinstance(n, int) or isinstance(n, long)):
        raise TypeError('value to encode must be an int or long')
    r = []
    base  = len(alphabet)
    while n >= base:
        r.append(alphabet[n % base])
        n = n / base
    r.append(str(alphabet[n % base]))
    r.reverse()
    return ''.join(r)
    

def decode(alphabet, string):
    """
    Determine the integer value encoded by `string` with alphabet `alphabet`.
    
    """
    if not isinstance(string, basestring):
        raise TypeError('value to decode must be a string')
    r = 0
    base = len(alphabet)
    for i, digit in enumerate(string):
        if digit not in alphabet:
            raise ValueError("'%s' is not a valid digit" % digit)
        r += alphabet.index(digit) * (base ** (len(string) - i - 1))
    return int(r)
    

def bytestring_to_integer(bytes):
    """Return the integral representation of a bytestring."""
    
    n = 0
    for (i, byte) in enumerate(bytes):
        n += ord(byte) << (8 * i)
    return n
    

def integer_to_bytestring(n):
    """Return the bytestring represented by an integer."""
    
    bytes = []
    while n > 0:
        bytes.append(chr(n - ((n >> 8) << 8)))
        n = n >> 8
    return ''.join(bytes)
    
