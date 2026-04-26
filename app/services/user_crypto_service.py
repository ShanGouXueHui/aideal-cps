from __future__ import annotations

import base64
import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, hmac
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def normalize_identity(value: str | None) -> str:
    return str(value or "").strip()


@lru_cache(maxsize=1)
def _fernet_key() -> bytes:
    key = (
        os.getenv("USER_DATA_ENCRYPTION_KEY")
        or os.getenv("AIDEAL_USER_DATA_ENCRYPTION_KEY")
        or ""
    ).strip()
    if not key:
        raise RuntimeError("USER_DATA_ENCRYPTION_KEY is required for user data encryption")
    return key.encode("utf-8")


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(_fernet_key())


@lru_cache(maxsize=1)
def _hmac_key() -> bytes:
    try:
        return base64.urlsafe_b64decode(_fernet_key())
    except Exception:
        return _fernet_key()


def hash_identity(value: str | None) -> str | None:
    text = normalize_identity(value)
    if not text:
        return None
    signer = hmac.HMAC(_hmac_key(), hashes.SHA256())
    signer.update(text.encode("utf-8"))
    return signer.finalize().hex()


def encrypt_text(value: str | None) -> str | None:
    text = normalize_identity(value)
    if not text:
        return None
    return _fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str | None) -> str | None:
    token = normalize_identity(value)
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
