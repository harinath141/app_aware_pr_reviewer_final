"""Fernet encryption for stored per-owner GitHub tokens.

Deliberately imports nothing from app.config or app.db so it can be unit-tested with no
environment set up.
"""
import base64
import hashlib
import os
from cryptography.fernet import Fernet, InvalidToken

# Prefixes GitHub uses for its tokens, longest first so "github_pat_" is not shadowed by "ghp_".
TOKEN_PREFIXES = ("github_pat_", "ghp_", "gho_", "ghu_", "ghs_")

class CryptoKeyMissing(RuntimeError):
    """No encryption key is configured, so tokens cannot be stored or read."""

class TokenDecryptionError(RuntimeError):
    """Ciphertext could not be decrypted - almost always a changed or wrong key."""

def generate_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()

def is_valid_key(key: str | None) -> bool:
    if not key:
        return False
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
        return True
    except (ValueError, TypeError):
        return False

def key_fingerprint(key: str) -> str:
    """Short, non-secret identifier for a key.

    Stored alongside each row so a rotated key is reported at startup rather than surfacing
    later as an InvalidToken on some unrelated webhook.
    """
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def encrypt_token(plaintext: str, key: str | None) -> str:
    if not key:
        raise CryptoKeyMissing("GITHUB_CREDENTIAL_KEY is not configured")
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()

def decrypt_token(ciphertext: str, key: str | None) -> str:
    if not key:
        raise CryptoKeyMissing("GITHUB_CREDENTIAL_KEY is not configured")
    try:
        return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise TokenDecryptionError(
            "stored token could not be decrypted - the encryption key has changed") from exc

def mask_token(token: str | None) -> str:
    """Displayable hint. The only token-derived value any API response may contain."""
    if not token:
        return ""
    for prefix in TOKEN_PREFIXES:
        if token.startswith(prefix):
            return f"{prefix}…{token[-4:]}" if len(token) > len(prefix) + 4 else f"{prefix}…"
    return f"…{token[-4:]}" if len(token) > 4 else "…"
