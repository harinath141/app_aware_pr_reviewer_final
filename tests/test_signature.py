import hashlib, hmac
from app.main import verify_signature

def test_signature():
    secret, body = "secret", b'{"ok":true}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(secret, body, sig)
    assert not verify_signature(secret, body, "sha256=bad")
    assert not verify_signature(secret, body, None)
