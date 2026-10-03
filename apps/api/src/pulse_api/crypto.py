"""AES-256-GCM for integration credentials. Plaintext never leaves this module's return value."""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTION_KEY_VERSION = 1
_NONCE_BYTES = 12


class TokenCipherError(Exception):
    """Ciphertext cannot be decrypted. The message stays generic."""


def encrypt_token(key_b64: str, plaintext: str) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    encrypted = AESGCM(_decode_key(key_b64)).encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + encrypted


def decrypt_token(key_b64: str, payload: bytes) -> str:
    if len(payload) <= _NONCE_BYTES:
        raise TokenCipherError
    nonce, encrypted = payload[:_NONCE_BYTES], payload[_NONCE_BYTES:]
    try:
        clear = AESGCM(_decode_key(key_b64)).decrypt(nonce, encrypted, None)
    except (InvalidTag, ValueError):
        raise TokenCipherError from None
    return clear.decode("utf-8")


def validate_encryption_key(key_b64: str) -> None:
    _decode_key(key_b64)


def _decode_key(key_b64: str) -> bytes:
    try:
        key = base64.b64decode(key_b64, validate=True)
    except ValueError:
        raise TokenCipherError from None
    if len(key) != 32:
        raise TokenCipherError
    return key
