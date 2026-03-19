from typing import Dict, Optional

from fastapi import WebSocket


class GameRoom:
    def __init__(self, player1: WebSocket, shooter: WebSocket, player_names: Dict[WebSocket, str]):
        self.players = [player1]
        self.shooter = shooter
        self.player_names = dict(player_names)
        self.moves: Dict[WebSocket, int] = {}
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
        self.shooter = self.get_opponent(self.shooter) or self.shooter

    def get_opponent(self, websocket: WebSocket) -> Optional[WebSocket]:
        for player in self.players:
            if player != websocket:
                return player
        return None

    def get_role(self, websocket: WebSocket) -> str:
        return "shooter" if websocket == self.shooter else "goalkeeper"

    def get_player_name(self, websocket: Optional[WebSocket]) -> str:
        if websocket is None:
            return "Pending"
        return self.player_names.get(websocket, "Unknown")

    def build_player_state(self, websocket: WebSocket) -> Dict[str, object]:
        opponent = self.get_opponent(websocket)
        return {
            "round": self.round_number,
            "target_score": self.target_score,
            "your_score": self.score.get(websocket, 0),
            "opponent_score": self.score.get(opponent, 0) if opponent else 0,
            "your_nickname": self.get_player_name(websocket),
            "opponent_nickname": self.get_player_name(opponent),
        }

    async def send_match_or_round_start(self, event_type: str):
        for player in self.players:
            role = self.get_role(player)
            state = self.build_player_state(player)
            await player.send_json(
                {
                    "type": event_type,
                    "role": role,
                    "message": "ATTACK VECTOR (Hacker)" if role == "shooter" else "ICE PROTOCOL (Defender)",
                    **state,
                }
            )

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
            await p.send_json(
                {
                    "type": "round_result",
                    "result": result,
                    "shooter_zone": shooter_zone,
                    "goalkeeper_zone": goalkeeper_zone,
                    "your_zone": self.moves[p],
                    "opponent_zone": self.moves[opponent],
                    **self.build_player_state(p),
                }
            )

        winner = next((player for player, points in self.score.items() if points >= self.target_score), None)
        if winner:
            self.game_over = True
            for player in self.players:
                opponent = p1 if player == p2 else p2
                await player.send_json(
                    {
                        "type": "game_over",
                        "result": "WIN" if player == winner else "LOSE",
                        "winner": "you" if player == winner else "opponent",
                        "your_score": self.score[player],
                        "opponent_score": self.score[opponent],
                        "target_score": self.target_score,
                    }
                )
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
                await player.send_json(
                    {
                        "type": "rematch_declined",
                        "message": "Rematch rejected. Reconnect to acquire a new rival node.",
                    }
                )
            self.cleanup_room(room)
            for player in players_to_requeue:
                await self.queue_or_match(player)
            return

        if opponent and room.rematch_votes.get(opponent) is True:
            room.reset_for_rematch()
            await room.send_match_or_round_start("match_start")
        else:
            await websocket.send_json(
                {
                    "type": "rematch_waiting",
                    "message": "Rematch vote transmitted. Awaiting opponent confirmation...",
                }
            )
            if opponent:
                await opponent.send_json(
                    {
                        "type": "rematch_waiting",
                        "message": "Incoming rematch request detected. Accept handshake?",
                    }
                )

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
