"""
High-performance cryptographic functions, CRCs, and hashing routines.
"""
from __future__ import annotations

import binascii
import hashlib
import struct
from typing import BinaryIO, Union
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class Crc16:
    """CRC-16 implementations (CCITT 0x1021 and X.25 0x8408)."""

    # Pre-calculated CCITT lookup table (poly 0x1021, init 0x0000)
    _TABLE_CCITT = []
    # Pre-calculated X.25 lookup table (poly 0x8408, init 0xFFFF)
    _TABLE_X25 = []

    @classmethod
    def _init_tables(cls):
        if not cls._TABLE_CCITT:
            for i in range(256):
                curr = i << 8
                for _ in range(8):
                    if curr & 0x8000:
                        curr = ((curr << 1) ^ 0x1021) & 0xFFFF
                    else:
                        curr = (curr << 1) & 0xFFFF
                cls._TABLE_CCITT.append(curr)

        if not cls._TABLE_X25:
            for i in range(256):
                curr = i
                for _ in range(8):
                    if curr & 1:
                        curr = (curr >> 1) ^ 0x8408
                    else:
                        curr = curr >> 1
                cls._TABLE_X25.append(curr & 0xFFFF)

    @classmethod
    def ccitt(cls, data: bytes, init: int = 0x0000) -> int:
        """Calculate CRC-16 CCITT (used in VCOM / IDT frame protocols)."""
        cls._init_tables()
        crc = init
        for b in data:
            crc = ((crc << 8) ^ cls._TABLE_CCITT[((crc >> 8) ^ b) & 0xFF]) & 0xFFFF
        return crc

    @classmethod
    def x25(cls, data: bytes) -> int:
        """Calculate CRC-16 X.25 / CCITT-inverted (used in Huawei eRecovery/DLOAD)."""
        cls._init_tables()
        crc = 0xFFFF
        for b in data:
            crc = (crc >> 8) ^ cls._TABLE_X25[(crc ^ b) & 0xFF]
        return (~crc) & 0xFFFF

    @classmethod
    def x25_bytes(cls, data: bytes) -> bytes:
        """Return 2-byte little-endian X.25 CRC."""
        crc = cls.x25(data)
        return struct.pack("<H", crc)


# Initialize tables at import time
Crc16._init_tables()


def crc32(data: bytes, init: int = 0) -> int:
    """Standard CRC32 calculation."""
    return binascii.crc32(data, init) & 0xFFFFFFFF


def sha256_hash(data: Union[bytes, BinaryIO]) -> str:
    """Compute SHA256 hex digest for bytes or a file stream."""
    h = hashlib.sha256()
    if isinstance(data, (bytes, bytearray)):
        h.update(data)
    else:
        while chunk := data.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def md5_hash(data: Union[bytes, BinaryIO]) -> str:
    """Compute MD5 hex digest for bytes or a file stream."""
    h = hashlib.md5()
    if isinstance(data, (bytes, bytearray)):
        h.update(data)
    else:
        while chunk := data.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def aes_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes, unpad: bool = True) -> bytes:
    """Decrypt ciphertext using AES-CBC with PKCS7 unpadding."""
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    if unpad and plaintext:
        pad_len = plaintext[-1]
        if 1 <= pad_len <= 16 and plaintext[-pad_len:] == bytes([pad_len]) * pad_len:
            plaintext = plaintext[:-pad_len]
    return plaintext


def aes_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes, pad: bool = True) -> bytes:
    """Encrypt plaintext using AES-CBC with PKCS7 padding."""
    if pad:
        pad_len = 16 - (len(plaintext) % 16)
        plaintext = plaintext + bytes([pad_len]) * pad_len
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()
