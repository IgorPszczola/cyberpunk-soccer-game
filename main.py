from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List, Dict
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/")
async def get():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

class ConnectionManager:
    def __init__(self):
        self.waiting_player: WebSocket = None
        self.active_matches: Dict[WebSocket, WebSocket] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        
        if self.waiting_player is None:
            self.waiting_player = websocket
            await websocket.send_json({"type": "info", "message": "Waiting for opponent..."})
        else:
            opponent = self.waiting_player
            self.waiting_player = None
            
            self.active_matches[websocket] = opponent
            self.active_matches[opponent] = websocket
            
            # Start game with roles
            await opponent.send_json({"type": "match_start", "role": "shooter", "message": "You are the SHOOTER (Hacker)"})
            await websocket.send_json({"type": "match_start", "role": "goalkeeper", "message": "You are the GOALKEEPER (Defender)"})

    def handle_disconnect(self, websocket: WebSocket):
        if self.waiting_player == websocket:
            self.waiting_player = None
        
        if websocket in self.active_matches:
            opponent = self.active_matches[websocket]
            del self.active_matches[websocket]
            if opponent in self.active_matches:
                del self.active_matches[opponent]
            return opponent
        return None

manager = ConnectionManager()

@app.websocket("/ws/game")
async def game_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            opponent = manager.active_matches.get(websocket)
            if opponent:
                await opponent.send_json({"type": "opponent_move", "data": data})
    except WebSocketDisconnect:
        opponent = manager.handle_disconnect(websocket)
        if opponent:
            await opponent.send_json({"type": "info", "message": "Opponent disconnected. Game over."})