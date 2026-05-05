from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from src.api.auth import require_auth
from src.api.schemas import (
    ClaimsListResponse, ClaimResponse, ClaimDetail, ClaimSource, PatchStatusRequest,
)
from src.db.connection import AsyncSessionLocal

router = APIRouter()


@router.get("/claims", response_model=ClaimsListResponse)
async def list_claims(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    urgent: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: str = Depends(require_auth),
):
    filters: list[str] = []
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}
    if status:
        filters.append("c.status = :status")
        params["status"] = status
    if category:
        filters.append("c.category = :category")
        params["category"] = category
    if urgent is not None:
        filters.append("c.urgency_signals = :urgent")
        params["urgent"] = urgent
    if search:
        filters.append("c.claim_text ILIKE '%' || :search || '%'")
        params["search"] = search
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    data_query = f"""
        SELECT c.id, c.claim_text, c.category, c.temporal, c.checkworthy_score,
               c.source_attribution, c.urgency_signals, c.occurrence_count, c.status,
               c.first_seen_at, c.last_seen_at,
               ARRAY_AGG(DISTINCT cs.channel_name)
                 FILTER (WHERE cs.channel_name IS NOT NULL) AS channels
        FROM claims c
        LEFT JOIN claim_sources cs ON cs.claim_id = c.id
        {where}
        GROUP BY c.id
        ORDER BY c.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    count_query = f"SELECT COUNT(*) FROM claims c {where}"

    async with AsyncSessionLocal() as session:
        total_result = await session.execute(text(count_query), params)
        total = total_result.scalar() or 0
        rows = await session.execute(text(data_query), params)
        items = []
        for row in rows.fetchall():
            d = dict(row._mapping)
            d["channels"] = d["channels"] or []
            items.append(ClaimResponse(**d))

    return ClaimsListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
async def get_claim(claim_id: int, _: str = Depends(require_auth)):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            text("""
                SELECT c.id, c.claim_text, c.category, c.temporal, c.checkworthy_score,
                       c.source_attribution, c.urgency_signals, c.occurrence_count, c.status,
                       c.first_seen_at, c.last_seen_at,
                       ARRAY_AGG(DISTINCT cs.channel_name)
                         FILTER (WHERE cs.channel_name IS NOT NULL) AS channels
                FROM claims c
                LEFT JOIN claim_sources cs ON cs.claim_id = c.id
                WHERE c.id = :id
                GROUP BY c.id
            """),
            {"id": claim_id},
        )
        claim_row = row.fetchone()
        if not claim_row:
            raise HTTPException(status_code=404, detail="Claim not found")
        d = dict(claim_row._mapping)
        d["channels"] = d["channels"] or []

        sources_result = await session.execute(
            text("""
                SELECT raw_message_id, channel_name, message_date
                FROM claim_sources WHERE claim_id = :id
            """),
            {"id": claim_id},
        )
        sources = [ClaimSource(**dict(r._mapping)) for r in sources_result.fetchall()]

    return ClaimDetail(**d, sources=sources)


@router.patch("/claims/{claim_id}", response_model=ClaimResponse)
async def patch_claim(claim_id: int, body: PatchStatusRequest, _: str = Depends(require_auth)):
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE claims SET status = :status WHERE id = :id"),
            {"status": body.status, "id": claim_id},
        )
        await session.commit()
        row = await session.execute(
            text("""
                SELECT c.id, c.claim_text, c.category, c.temporal, c.checkworthy_score,
                       c.source_attribution, c.urgency_signals, c.occurrence_count, c.status,
                       c.first_seen_at, c.last_seen_at,
                       ARRAY_AGG(DISTINCT cs.channel_name)
                         FILTER (WHERE cs.channel_name IS NOT NULL) AS channels
                FROM claims c
                LEFT JOIN claim_sources cs ON cs.claim_id = c.id
                WHERE c.id = :id
                GROUP BY c.id
            """),
            {"id": claim_id},
        )
        claim_row = row.fetchone()
        if not claim_row:
            raise HTTPException(status_code=404, detail="Claim not found")
        d = dict(claim_row._mapping)
        d["channels"] = d["channels"] or []
    return ClaimResponse(**d)
