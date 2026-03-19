import hashlib
import hmac
import os
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, Optional
from contextlib import asynccontextmanager
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from database import connect_to_mongodb, close_mongodb_connection, db_instance

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongodb()
    yield
    await close_mongodb_connection()


app = FastAPI(lifespan=lifespan)


class RegisterRequest(BaseModel):
    nickname: str
    password: str
    password_confirm: str


class LoginRequest(BaseModel):
    nickname: str
    password: str


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


def get_users_collection():
    if db_instance.db is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db_instance.db["users"]


@app.post("/api/register")
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
    await users.insert_one({
        "nickname": nickname.lower(),
        "display_nickname": nickname,
        "password_salt": salt_hex,
        "password_hash": password_hash,
        "created_at": datetime.now(timezone.utc),
    })
    return {"status": "ok", "nickname": nickname}


@app.post("/api/login")
async def login(payload: LoginRequest):
    nickname = validate_nickname(payload.nickname)
    users = get_users_collection()
    user = await users.find_one({"nickname": nickname.lower()})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid nickname or password.")

    if not verify_password(payload.password, user.get("password_salt", ""), user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid nickname or password.")

    return {
        "status": "ok",
        "nickname": user.get("display_nickname", nickname),
    }

class GameRoom:
    def __init__(self, player1: WebSocket, shooter: WebSocket, player_names: Dict[WebSocket, str]):
        self.players = [player1]
        self.shooter = shooter
        self.player_names = dict(player_names)
        self.moves: Dict[WebSocket, int] = {}  # Ruchy: {ws: strefa}
        self.score: Dict[WebSocket, int] = {player1: 0}
        self.round_number = 1
        self.target_score = 3
        self.game_over = False
        self.rematch_votes: Dict[WebSocket, Optional[bool]] = {player1: None}

    def add_player(self, websocket: WebSocket, nickname: str):
        self.players.append(websocket)
        self.player_names[websocket] = nickname
        self.score[websocket] = 0
        self.rematch_votes[websocket] = None

    def reset_for_rematch(self):
        self.moves = {}
        self.score = {player: 0 for player in self.players}
        self.round_number = 1
        self.game_over = False
        self.rematch_votes = {player: None for player in self.players}
        # Start rematch with swapped opening shooter for fairness.
        self.shooter = self.get_opponent(self.shooter) or self.shooter

    def get_opponent(self, websocket: WebSocket) -> Optional[WebSocket]:
        for player in self.players:
            if player != websocket:
                return player
        return None

    def get_role(self, websocket: WebSocket) -> str:
        return "shooter" if websocket == self.shooter else "goalkeeper"

    def get_player_name(self, websocket: WebSocket) -> str:
        return self.player_names.get(websocket, "Unknown")

    def build_player_state(self, websocket: WebSocket) -> Dict[str, int]:
        opponent = self.get_opponent(websocket)
        return {
            "round": self.round_number,
            "target_score": self.target_score,
            "your_score": self.score.get(websocket, 0),
            "opponent_score": self.score.get(opponent, 0) if opponent else 0,
            "your_nickname": self.get_player_name(websocket),
            "opponent_nickname": self.get_player_name(opponent) if opponent else "Pending",
        }

    async def send_match_or_round_start(self, event_type: str):
        for player in self.players:
            role = self.get_role(player)
            state = self.build_player_state(player)
            await player.send_json({
                "type": event_type,
                "role": role,
                "message": "ATTACK VECTOR (Hacker)" if role == "shooter" else "ICE PROTOCOL (Defender)",
                **state,
            })

    async def check_result(self):
        if len(self.moves) != 2 or self.game_over:
            return

        p1, p2 = self.players
        shooter_ws = self.shooter
        goalkeeper_ws = p2 if shooter_ws == p1 else p1

        shooter_zone = self.moves[shooter_ws]
        goalkeeper_zone = self.moves[goalkeeper_ws]
        result = "SAVED" if shooter_zone == goalkeeper_zone else "GOAL"

        if result == "GOAL":
            self.score[shooter_ws] += 1

        for p in self.players:
            opponent = p1 if p == p2 else p2
            await p.send_json({
                "type": "round_result",
                "result": result,
                "shooter_zone": shooter_zone,
                "goalkeeper_zone": goalkeeper_zone,
                "your_zone": self.moves[p],
                "opponent_zone": self.moves[opponent],
                **self.build_player_state(p),
            })

        winner = next((player for player, points in self.score.items() if points >= self.target_score), None)
        if winner:
            self.game_over = True
            for player in self.players:
                opponent = p1 if player == p2 else p2
                await player.send_json({
                    "type": "game_over",
                    "result": "WIN" if player == winner else "LOSE",
                    "winner": "you" if player == winner else "opponent",
                    "your_score": self.score[player],
                    "opponent_score": self.score[opponent],
                    "target_score": self.target_score,
                })
        else:
            self.shooter = goalkeeper_ws
            self.round_number += 1
            await self.send_match_or_round_start("round_start")

        self.moves = {}

class ConnectionManager:
    def __init__(self):
        self.waiting_player: Optional[WebSocket] = None
        self.rooms: Dict[WebSocket, GameRoom] = {}
        self.player_nicknames: Dict[WebSocket, str] = {}

    def get_player_nickname(self, websocket: WebSocket) -> str:
        return self.player_nicknames.get(websocket, "Unknown")

    def cleanup_room(self, room: GameRoom):
        # Remove all room references from matchmaking and active room index.
        for player in room.players:
            if self.waiting_player == player:
                self.waiting_player = None
            self.rooms.pop(player, None)

    async def queue_or_match(self, websocket: WebSocket):
        if self.waiting_player is None:
            self.waiting_player = websocket
            await websocket.send_json({"type": "info", "message": "Transmitting handshake... waiting for rival node."})
            return

        if self.waiting_player == websocket:
            return

        waiting_nickname = self.get_player_nickname(self.waiting_player)
        room = GameRoom(
            player1=self.waiting_player,
            shooter=self.waiting_player,
            player_names={self.waiting_player: waiting_nickname},
        )
        room.add_player(websocket, self.get_player_nickname(websocket))

        self.rooms[self.waiting_player] = room
        self.rooms[websocket] = room

        await room.send_match_or_round_start("match_start")
        self.waiting_player = None

    async def connect(self, websocket: WebSocket, nickname: str):
        await websocket.accept()
        self.player_nicknames[websocket] = nickname
        await self.queue_or_match(websocket)

    async def handle_move(self, websocket: WebSocket, zone: int):
        room = self.rooms.get(websocket)
        if room:
            if room.game_over:
                await websocket.send_json({"type": "info", "message": "Session closed. Await rematch handshake."})
                return

            if websocket in room.moves:
                await websocket.send_json({"type": "info", "message": "Packet already deployed this cycle."})
                return

            if not isinstance(zone, int) or not 1 <= zone <= 9:
                await websocket.send_json({"type": "info", "message": "Invalid node. Select firewall node 1-9."})
                return

            room.moves[websocket] = zone
            await websocket.send_json({"type": "info", "message": "Packet injected. Waiting for opponent signal..."})
            await room.check_result()

    async def handle_rematch_vote(self, websocket: WebSocket, accepted: bool):
        room = self.rooms.get(websocket)
        if not room:
            return

        if not room.game_over:
            await websocket.send_json({"type": "info", "message": "Rematch protocol unlocks after session end."})
            return

        opponent = room.get_opponent(websocket)
        room.rematch_votes[websocket] = bool(accepted)

        if not accepted:
            players_to_requeue = list(room.players)
            for player in room.players:
                await player.send_json({
                    "type": "rematch_declined",
                    "message": "Rematch rejected. Reconnect to acquire a new rival node.",
                })
            self.cleanup_room(room)
            for player in players_to_requeue:
                await self.queue_or_match(player)
            return

        if opponent and room.rematch_votes.get(opponent) is True:
            room.reset_for_rematch()
            await room.send_match_or_round_start("match_start")
        else:
            await websocket.send_json({"type": "rematch_waiting", "message": "Rematch vote transmitted. Awaiting opponent confirmation..."})
            if opponent:
                await opponent.send_json({"type": "rematch_waiting", "message": "Incoming rematch request detected. Accept handshake?"})

    def disconnect(self, websocket: WebSocket):
        if self.waiting_player == websocket:
            self.waiting_player = None
        room = self.rooms.pop(websocket, None)
        self.player_nicknames.pop(websocket, None)
        if room:
            for p in room.players:
                if p != websocket:
                    self.cleanup_room(room)
                    return p
        return None

manager = ConnectionManager()

@app.get("/health/db")
async def db_health():
    if db_instance.client is None or db_instance.db is None:
        return {"status": "error", "database": "disconnected"}

    try:
        await db_instance.client.admin.command("ping")
        return {"status": "ok", "database": db_instance.db.name}
    except Exception as exc:
        return {"status": "error", "database": "unreachable", "detail": str(exc)}

@app.get("/")
async def get():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws/game")
async def game_endpoint(websocket: WebSocket):
    raw_nickname = websocket.query_params.get("nickname", "")
    try:
        nickname = validate_nickname(raw_nickname)
    except HTTPException:
        await websocket.accept()
        await websocket.close(code=1008, reason="Invalid nickname")
        return

    await manager.connect(websocket, nickname)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "move":
                await manager.handle_move(websocket, data.get("zone"))
            if data.get("action") == "rematch":
                await manager.handle_rematch_vote(websocket, data.get("accepted") is True)
    except WebSocketDisconnect:
        opponent = manager.disconnect(websocket)
        if opponent:
            try: await opponent.send_json({"type": "info", "message": "Rival node disconnected. Session terminated."})
            except: pass