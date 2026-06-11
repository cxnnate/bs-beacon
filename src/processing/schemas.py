from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum


class ClaimTopic(str, Enum):
    health = "health"
    politics = "politics"
    finance = "finance"
    technology = "technology"
    military = "military"
    environment = "environment"
    science = "science"
    crime = "crime"
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


class ClaimRelation(str, Enum):
    paraphrase = "paraphrase"
    contradicts = "contradicts"


class ClaimStatus(str, Enum):
    unreviewed = "unreviewed"
    verified = "verified"
    debunked = "debunked"
    needs_info = "needs_info"


class NLILabel(str, Enum):
    entailment = "entailment"
    contradiction = "contradiction"
    neutral = "neutral"


class ClaimEntities(BaseModel):
    people: list[str] = []
    organizations: list[str] = []
    locations: list[str] = []
    quantities: list[str] = []


class ExtractedClaim(BaseModel):
    text: str
    entities: ClaimEntities
    topic: ClaimTopic
    temporal: Temporality = Temporality.unspecified
    checkworthy_score: float = Field(ge=0.0, le=1.0)
    source_attribution: Optional[str] = None

    @field_validator('topic', mode='before')
    @classmethod
    def coerce_topic(cls, v: object) -> object:
        if isinstance(v, str) and v not in {e.value for e in ClaimTopic}:
            return ClaimTopic.other.value
        return v


class ExtractionMeta(BaseModel):
    message_type: MessageType
    language_detected: str
    urgency_signals: bool = False
    conspiratorial_framing: bool = False


class ExtractionResult(BaseModel):
    claims: list[ExtractedClaim] = []
    meta: ExtractionMeta
