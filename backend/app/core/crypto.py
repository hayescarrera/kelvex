import base64
import hashlib
import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _derive_fernet_key(source: str) -> bytes:
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache()
def _get_fernet() -> Fernet:
    settings = get_settings()
    key_source = settings.CREDENTIAL_ENCRYPTION_KEY or settings.SECRET_KEY
    return Fernet(_derive_fernet_key(key_source))


def encrypt_json(payload: dict) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    token = _get_fernet().encrypt(raw).decode("utf-8")
    return {"v": 1, "ciphertext": token}


def is_encrypted_payload(payload: dict) -> bool:
    return isinstance(payload, dict) and "ciphertext" in payload


def decrypt_json(payload: dict) -> dict:
    # Backward compatibility for existing plain-JSON records.
    if not is_encrypted_payload(payload):
        return payload
    try:
        token = payload["ciphertext"].encode("utf-8")
        raw = _get_fernet().decrypt(token)
        return json.loads(raw.decode("utf-8"))
    except (InvalidToken, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Unable to decrypt credentials payload") from exc
