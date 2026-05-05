import asyncio
import logging
from fastapi import WebSocket
from sqlalchemy import text
from src.db.connection import AsyncSessionLocal

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._last_id: int = 0

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def _broadcast(self, data: dict) -> None:
        dead: set[WebSocket] = set()
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def poll_loop(self) -> None:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("SELECT COALESCE(MAX(id), 0) FROM claims"))
                self._last_id = result.scalar() or 0
        except Exception:
            logger.warning("WebSocket poll_loop: could not init last_id", exc_info=True)

        while True:
            await asyncio.sleep(3)
            try:
                async with AsyncSessionLocal() as session:
                    rows = await session.execute(
                        text("""
                            SELECT c.id, c.claim_text, c.category, c.temporal,
                                   c.checkworthy_score, c.source_attribution,
                                   c.urgency_signals, c.occurrence_count, c.status,
                                   c.first_seen_at::text AS first_seen_at,
                                   c.last_seen_at::text AS last_seen_at,
                                   ARRAY_AGG(DISTINCT cs.channel_name)
                                     FILTER (WHERE cs.channel_name IS NOT NULL) AS channels
                            FROM claims c
                            LEFT JOIN claim_sources cs ON cs.claim_id = c.id
                            WHERE c.id > :last_id
                            GROUP BY c.id
                            ORDER BY c.id ASC
                        """),
                        {"last_id": self._last_id},
                    )
                    for row in rows.fetchall():
                        d = dict(row._mapping)
                        d["channels"] = d["channels"] or []
                        self._last_id = max(self._last_id, d["id"])
                        await self._broadcast(d)
            except Exception:
                logger.exception("WebSocket poll error")


ws_manager = WebSocketManager()
