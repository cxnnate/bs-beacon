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

from src.api.routes import claims as claims_router
from src.api.routes import stats as stats_router
from src.api.routes import logs as logs_router

app.include_router(claims_router.router, prefix="/api")
app.include_router(stats_router.router, prefix="/api")
app.include_router(logs_router.router, prefix="/api")
