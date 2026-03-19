from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from services.game import manager
from services.security import validate_nickname

router = APIRouter()


@router.websocket("/ws/game")
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
            try:
                await opponent.send_json({"type": "info", "message": "Rival node disconnected. Session terminated."})
            except Exception:
                pass
