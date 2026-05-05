from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


class ClaimResponse(BaseModel):
    id: int
    claim_text: str
    category: str
    temporal: str
    checkworthy_score: float
    source_attribution: Optional[str]
    urgency_signals: bool
    occurrence_count: int
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    channels: list[str]


class ClaimSource(BaseModel):
    raw_message_id: int
    channel_name: str
    message_date: datetime


class ClaimDetail(ClaimResponse):
    sources: list[ClaimSource]


class PatchStatusRequest(BaseModel):
    status: Literal["reviewed", "dismissed"]


class ClaimsListResponse(BaseModel):
    items: list[ClaimResponse]
    total: int
    page: int
    page_size: int


class StatsResponse(BaseModel):
    total_claims: int
    unreviewed: int
    urgent_unreviewed: int
    messages_today: int
    claims_today: int
