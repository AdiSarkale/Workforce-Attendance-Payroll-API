def test_verify_qr_token():
    import hashlib
    from app.api.deps import verify_qr_token

    token = "demo-token"
    digest = hashlib.sha256(token.encode()).hexdigest()

    assert verify_qr_token(token, digest)
    assert not verify_qr_token("wrong-token", digest)
