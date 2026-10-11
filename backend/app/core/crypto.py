"""AES-256-GCM encryption for secrets stored at rest (OAuth tokens, API keys)."""

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_KEY_BYTES = 32
_NONCE_BYTES = 12


class DecryptionError(Exception):
    pass


def _load_key() -> bytes:
    raw = get_settings().token_encryption_key
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        key = b""
    if len(key) != _KEY_BYTES:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY must be 32 random bytes encoded in base64")
    return key


def validate_encryption_key() -> None:
    _load_key()


def encrypt(plaintext: str) -> str:
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_load_key()).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(token: str) -> str:
    try:
        data = base64.b64decode(token, validate=True)
        nonce, ciphertext = data[:_NONCE_BYTES], data[_NONCE_BYTES:]
        return AESGCM(_load_key()).decrypt(nonce, ciphertext, None).decode()
    except (binascii.Error, ValueError, InvalidTag) as exc:
        raise DecryptionError("Stored secret could not be decrypted") from exc
