from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ClaimCategory(str, Enum):
    health = "health"
    politics = "politics"
    finance = "finance"
    technology = "technology"
    military = "military"
    environment = "environment"
    science = "science"
    crime = "crime"
    conspiracy = "conspiracy"
    other = "other"


class Temporality(str, Enum):
    past = "past"
    present = "present"
    future = "future"
    unspecified = "unspecified"


class MessageType(str, Enum):
    news_share = "news_share"
    opinion_rant = "opinion_rant"
    forwarded_alert = "forwarded_alert"
    question = "question"
    conversation = "conversation"
    propaganda = "propaganda"
    satire = "satire"
    unclear = "unclear"


class ClaimEntities(BaseModel):
    people: list[str] = []
    organizations: list[str] = []
    locations: list[str] = []
    quantities: list[str] = []


class ExtractedClaim(BaseModel):
    text: str
    entities: ClaimEntities
    category: ClaimCategory
    temporal: Temporality = Temporality.unspecified
    checkworthy_score: float = Field(ge=0.0, le=1.0)
    source_attribution: Optional[str] = None


class ExtractionMeta(BaseModel):
    message_type: MessageType
    claim_count: int = Field(ge=0)
    language_detected: str
    contains_media_reference: bool = False
    urgency_signals: bool = False


class ExtractionResult(BaseModel):
    claims: list[ExtractedClaim] = []
    meta: ExtractionMeta
