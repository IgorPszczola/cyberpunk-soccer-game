import hashlib
import hmac
import os

from fastapi import HTTPException


def hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return digest.hex()


def build_password_record(password: str) -> tuple[str, str]:
    salt_hex = os.urandom(16).hex()
    return salt_hex, hash_password(password, salt_hex)


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    computed = hash_password(password, salt_hex)
    return hmac.compare_digest(computed, expected_hash_hex)


def validate_nickname(nickname: str) -> str:
    normalized = nickname.strip()
    if not 3 <= len(normalized) <= 24:
        raise HTTPException(status_code=400, detail="Nickname must be 3-24 characters.")
    if not normalized.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Nickname can contain letters, digits, and underscore.")
    return normalized


def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
