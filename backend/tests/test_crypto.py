from app.core.crypto import decrypt_json, encrypt_json, is_encrypted_payload


def test_encrypt_decrypt_roundtrip():
    payload = {"api_key": "abc123", "secret": "value"}
    encrypted = encrypt_json(payload)

    assert is_encrypted_payload(encrypted)
    assert decrypt_json(encrypted) == payload


def test_decrypt_handles_legacy_plaintext():
    legacy_payload = {"username": "ops@coldgrid.io", "password": "legacy"}
    assert decrypt_json(legacy_payload) == legacy_payload
