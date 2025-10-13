from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Event(BaseModel):
    timestamp_iso: str
    kind: str
    payload: Dict[str, Any]


RECENT: Deque[Event] = deque(maxlen=500)


@app.post("/api/events")
async def post_event(event: Event):
    RECENT.append(event)
    # broadcast to websockets
    await broadcast(event)
    return {"ok": True}


@app.get("/api/events")
async def get_events():
    return [e.dict() for e in list(RECENT)]


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def send_json(self, message: Dict[str, Any]):
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


async def broadcast(event: Event):
    await manager.send_json(event.dict())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # send recent on connect
        await websocket.send_json({"type": "recent", "events": [e.dict() for e in list(RECENT)]})
        while True:
            await websocket.receive_text()  # keepalive / ignore
    except WebSocketDisconnect:
        manager.disconnect(websocket)
