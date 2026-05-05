import asyncio
import base64
import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from src.api.ws import ws_manager
from src.api.routes import claims as claims_router
from src.api.routes import stats as stats_router
from src.api.routes import logs as logs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(ws_manager.poll_loop())
    yield

app = FastAPI(title="BSBeacon API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        decoded = base64.b64decode(token).decode()
        username, password = decoded.split(":", 1)
        expected_user = os.getenv("API_USERNAME", "")
        expected_pass = os.getenv("API_PASSWORD", "")
        ok = secrets.compare_digest(username.encode(), expected_user.encode()) and \
             secrets.compare_digest(password.encode(), expected_pass.encode())
        if not ok:
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
