"""Fernet-based encryption for API keys stored in the database."""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import SECRET_KEY


def _derive_fernet_key() -> bytes:
    """Derive a 32-byte Fernet key from SECRET_KEY via SHA-256."""
    digest = hashlib.sha256(SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_fernet_key())


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key string, return base64-encoded ciphertext."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext back to the original API key."""
    return _fernet.decrypt(ciphertext.encode()).decode()
