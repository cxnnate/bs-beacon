from fastapi import APIRouter, Depends
from sqlalchemy import text
from src.api.auth import require_auth
from src.api.schemas import StatsResponse
from src.db.connection import AsyncSessionLocal

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def get_stats(_: str = Depends(require_auth)):
    async with AsyncSessionLocal() as session:
        counts_row = await session.execute(text("""
            SELECT
                COUNT(*) AS total_claims,
                COUNT(*) FILTER (WHERE status = 'unreviewed') AS unreviewed,
                COUNT(*) FILTER (WHERE status = 'unreviewed' AND urgency_signals = TRUE)
                  AS urgent_unreviewed
            FROM claims
        """))
        counts = counts_row.fetchone()

        today_row = await session.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM raw_messages
                 WHERE message_date::date = CURRENT_DATE) AS messages_today,
                (SELECT COUNT(*) FROM claims
                 WHERE created_at::date = CURRENT_DATE) AS claims_today
        """))
        today = today_row.fetchone()

    return StatsResponse(
        total_claims=counts[0],
        unreviewed=counts[1],
        urgent_unreviewed=counts[2],
        messages_today=today[0],
        claims_today=today[1],
    )
