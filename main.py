from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/")
async def get():
    return HTMLResponse("<h1>Cyberpunk Soccer server active</h1>")

@app.websocket("/ws/test")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection accepted")
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Server received: {data}")