from __future__ import annotations

from cryptography.fernet import Fernet
import base64
import hashlib


def _get_fernet(key: str) -> Fernet:
    key_bytes = key.encode("utf-8")
    digest = hashlib.sha256(key_bytes).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_api_key(plain_text: str, key: str) -> str:
    f = _get_fernet(key)
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_text: str, key: str) -> str:
    f = _get_fernet(key)
    return f.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")


def mask_api_key(encrypted_text: str, key: str) -> str:
    plain = decrypt_api_key(encrypted_text, key)
    if len(plain) <= 8:
        return plain[:2] + "****" + plain[-2:]
    return plain[:4] + "****" + plain[-4:]
