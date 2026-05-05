import asyncio
import base64
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="BSBeacon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.ws import ws_manager
from src.api.routes import claims as claims_router
from src.api.routes import stats as stats_router
from src.api.routes import logs as logs_router


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(ws_manager.poll_loop())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        decoded = base64.b64decode(token).decode()
        username, password = decoded.split(":", 1)
        if username != os.getenv("API_USERNAME") or password != os.getenv("API_PASSWORD"):
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

app.include_router(claims_router.router, prefix="/api")
app.include_router(stats_router.router, prefix="/api")
app.include_router(logs_router.router, prefix="/api")
