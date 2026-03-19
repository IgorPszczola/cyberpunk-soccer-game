from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from database import db_instance
from schemas.auth import LoginRequest, RegisterRequest
from services.security import (
    build_password_record,
    validate_nickname,
    validate_password,
    verify_password,
)

router = APIRouter()


def get_users_collection():
    if db_instance.db is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db_instance.db["users"]


@router.get("/health/db")
async def db_health():
    if db_instance.client is None or db_instance.db is None:
        return {"status": "error", "database": "disconnected"}

    try:
        await db_instance.client.admin.command("ping")
        return {"status": "ok", "database": db_instance.db.name}
    except Exception as exc:
        return {"status": "error", "database": "unreachable", "detail": str(exc)}


@router.post("/api/register")
async def register(payload: RegisterRequest):
    nickname = validate_nickname(payload.nickname)
    validate_password(payload.password)
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    users = get_users_collection()
    existing = await users.find_one({"nickname": nickname.lower()}, {"_id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="Nickname is already taken.")

    salt_hex, password_hash = build_password_record(payload.password)
    await users.insert_one(
        {
            "nickname": nickname.lower(),
            "display_nickname": nickname,
            "password_salt": salt_hex,
            "password_hash": password_hash,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return {"status": "ok", "nickname": nickname}


@router.post("/api/login")
async def login(payload: LoginRequest):
    nickname = validate_nickname(payload.nickname)
    users = get_users_collection()
    user = await users.find_one({"nickname": nickname.lower()})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid nickname or password.")

    if not verify_password(payload.password, user.get("password_salt", ""), user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid nickname or password.")

    return {"status": "ok", "nickname": user.get("display_nickname", nickname)}
