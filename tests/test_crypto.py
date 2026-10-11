"""Crypto tests import only app.crypto, so they need no environment or database."""
import pytest

from app.crypto import (CryptoKeyMissing, TokenDecryptionError, decrypt_token, encrypt_token,
                        generate_key, is_valid_key, key_fingerprint, mask_token)

KEY = generate_key()

def test_roundtrip():
    assert decrypt_token(encrypt_token("github_pat_secret", KEY), KEY) == "github_pat_secret"

def test_same_plaintext_encrypts_differently():
    # Fernet uses a random IV, so the same token must not produce identical ciphertext.
    assert encrypt_token("same-value", KEY) != encrypt_token("same-value", KEY)

def test_wrong_key_raises_a_clear_error():
    ciphertext = encrypt_token("secret", KEY)
    with pytest.raises(TokenDecryptionError):
        decrypt_token(ciphertext, generate_key())

def test_key_is_required():
    with pytest.raises(CryptoKeyMissing):
        encrypt_token("secret", None)
    with pytest.raises(CryptoKeyMissing):
        decrypt_token("whatever", "")

def test_is_valid_key():
    assert is_valid_key(KEY)
    assert not is_valid_key(None)
    assert not is_valid_key("")
    assert not is_valid_key("not-a-fernet-key")

def test_key_fingerprint_is_stable_and_key_specific():
    assert key_fingerprint(KEY) == key_fingerprint(KEY)
    assert key_fingerprint(KEY) != key_fingerprint(generate_key())
    assert len(key_fingerprint(KEY)) == 16

def test_mask_never_reveals_the_secret():
    token = ("github_pat_11AEJGCII0aBU95bfbvnK6_vqe5PRVroK03wWJhobpjshyPld9w8l5rA1XhQWMBZjjH4"
             "HVWDPEuJ5lpIsh")
    masked = mask_token(token)
    assert token not in masked
    assert masked.startswith("github_pat_")
    assert masked.endswith(token[-4:])
    assert len(masked) < len(token) / 2

def test_mask_handles_unknown_prefixes_and_short_values():
    assert mask_token("") == ""
    assert mask_token(None) == ""
    assert mask_token("abc") == "…"          # too short to reveal anything
    assert mask_token("zzzzzzzzzz") == "…zzzz"
