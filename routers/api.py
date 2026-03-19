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


def get_db_or_503():
    if db_instance.db is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db_instance.db


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


@router.get("/api/profile/{nickname}/stats")
async def profile_stats(nickname: str):
    normalized = validate_nickname(nickname)
    db = get_db_or_503()
    stats = await db["user_stats"].find_one({"nickname": normalized.lower()})

    if not stats:
        return {
            "nickname": normalized,
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "goals_scored": 0,
            "goals_conceded": 0,
            "avg_lives_remaining": 0.0,
            "saves": 0,
            "shots_taken": 0,
            "win_rate": 0.0,
            "save_rate": 0.0,
        }

    games_played = int(stats.get("games_played", 0))
    wins = int(stats.get("wins", 0))
    draws = int(stats.get("draws", 0))
    saves = int(stats.get("saves", 0))
    shots_taken = int(stats.get("shots_taken", 0))
    lives_remaining_total = int(stats.get("lives_remaining_total", 0))

    return {
        "nickname": stats.get("display_nickname", normalized),
        "games_played": games_played,
        "wins": wins,
        "losses": int(stats.get("losses", 0)),
        "draws": draws,
        "goals_scored": int(stats.get("goals_scored", 0)),
        "goals_conceded": int(stats.get("goals_conceded", 0)),
        "avg_lives_remaining": round((lives_remaining_total / games_played), 2) if games_played else 0.0,
        "saves": saves,
        "shots_taken": shots_taken,
        "win_rate": round((wins / games_played) * 100, 1) if games_played else 0.0,
        "save_rate": round((saves / shots_taken) * 100, 1) if shots_taken else 0.0,
    }


@router.get("/api/profile/{nickname}/history")
async def profile_history(nickname: str, limit: int = 8):
    normalized = validate_nickname(nickname)
    db = get_db_or_503()
    effective_limit = min(max(limit, 1), 20)

    cursor = db["matches"].find(
        {"players.nickname": normalized.lower()},
        {"players": 1, "created_at": 1, "target_score": 1, "rounds_played": 1},
    ).sort("created_at", -1).limit(effective_limit)

    history = []
    async for match in cursor:
        players = match.get("players", [])
        me = next((p for p in players if p.get("nickname") == normalized.lower()), None)
        opponent = next((p for p in players if p.get("nickname") != normalized.lower()), None)
        if not me:
            continue

        created_at = match.get("created_at")
        created_iso = created_at.isoformat() if created_at else None

        history.append(
            {
                "created_at": created_iso,
                "result": me.get("result", "UNKNOWN"),
                "your_score": int(me.get("score", 0)),
                "opponent_score": int(me.get("opponent_score", 0)),
                "your_lives": int(me.get("lives", 0)),
                "opponent_nickname": opponent.get("display_nickname", "Unknown") if opponent else "Unknown",
                "rounds_played": int(match.get("rounds_played", 0)),
                "target_score": int(match.get("target_score", 0)),
            }
        )

    return {"nickname": normalized, "history": history}
