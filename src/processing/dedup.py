import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.processing.schemas import ExtractedClaim, ExtractionMeta


def _embedding_to_pg(embedding: list[float]) -> str:
    """Convert an embedding list to PostgreSQL vector format string."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


def compute_text_hash(text_content: str) -> str:
    """Compute a normalized SHA256 hash of claim text.

    Normalizes whitespace and case to ensure equivalent texts produce the same hash.
    """
    normalized = " ".join(text_content.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


async def find_by_text_hash(
    session: AsyncSession, text_hash: str, exclude_id: int
) -> Optional[int]:
    """Find a claim ID by text hash, excluding a specific message.

    Returns the ID of a previously processed message with the same text hash,
    or None if not found.
    """
    result = await session.execute(
        text("""
        SELECT rm.id FROM raw_messages rm
        JOIN claim_sources cs ON cs.raw_message_id = rm.id
        WHERE rm.text_hash = :hash AND rm.processed = TRUE AND rm.id != :exclude_id
        LIMIT 1
        """),
        {"hash": text_hash, "exclude_id": exclude_id},
    )
    row = result.fetchone()
    return row[0] if row else None


async def find_similar_claim(
    session: AsyncSession,
    embedding: list[float],
    threshold: float = 0.92,
) -> Optional[int]:
    """Find a semantically similar claim using pgvector.

    Uses cosine similarity to find claims with embeddings similar to the given one.
    Returns the ID of the most similar claim above the threshold, or None.
    """
    embedding_str = _embedding_to_pg(embedding)
    result = await session.execute(
        text("""
        SELECT id
        FROM claims
        WHERE 1 - (embedding <=> CAST(:embedding AS vector)) > :threshold
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT 1
        """),
        {"embedding": embedding_str, "threshold": threshold},
    )
    row = result.fetchone()
    return row[0] if row else None


async def merge_claim(
    session: AsyncSession,
    claim_id: int,
    raw_message_id: int,
    channel_name: str,
    message_date: datetime,
) -> None:
    """Merge a duplicate claim into an existing one.

    Increments the occurrence count and adds a new source reference.
    """
    await session.execute(
        text("""
        UPDATE claims
        SET occurrence_count = occurrence_count + 1, last_seen_at = NOW()
        WHERE id = :id
        """),
        {"id": claim_id},
    )
    await session.execute(
        text("""
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_name, message_date)
        VALUES (:claim_id, :raw_message_id, :channel_name, :message_date)
        """),
        {
            "claim_id": claim_id,
            "raw_message_id": raw_message_id,
            "channel_name": channel_name,
            "message_date": message_date,
        },
    )


async def insert_claim(
    session: AsyncSession,
    claim: ExtractedClaim,
    embedding: list[float],
    source_language: str,
    urgency: bool,
    meta: ExtractionMeta,
    message: dict,
) -> int:
    """Insert a new claim into the database.

    Creates a new claim record with the given embedding and metadata,
    and adds a source reference linking it to the raw message.
    Returns the ID of the new claim.
    """
    now = datetime.now(timezone.utc)
    embedding_str = _embedding_to_pg(embedding)
    result = await session.execute(
        text("""
        INSERT INTO claims (
            claim_text, source_language, first_seen_at, last_seen_at,
            occurrence_count, entities_json, category, temporal,
            checkworthy_score, source_attribution, urgency_signals,
            message_type, embedding, status, created_at
        ) VALUES (
            :claim_text, :source_language, :now, :now,
            1, :entities_json, :category, :temporal,
            :checkworthy_score, :source_attribution, :urgency_signals,
            :message_type, CAST(:embedding AS vector), 'unreviewed', :now
        )
        RETURNING id
        """),
        {
            "claim_text": claim.text,
            "source_language": source_language,
            "now": now,
            "entities_json": json.dumps({
                "people": claim.entities.people,
                "organizations": claim.entities.organizations,
                "locations": claim.entities.locations,
                "quantities": claim.entities.quantities,
            }),
            "category": claim.category.value,
            "temporal": claim.temporal.value,
            "checkworthy_score": claim.checkworthy_score,
            "source_attribution": claim.source_attribution,
            "urgency_signals": urgency,
            "message_type": meta.message_type.value,
            "embedding": embedding_str,
        },
    )
    row = result.fetchone()
    if row is None:
        raise RuntimeError("INSERT INTO claims returned no id — RETURNING clause failed")
    claim_id = row[0]
    await session.execute(
        text("""
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_name, message_date)
        VALUES (:claim_id, :raw_message_id, :channel_name, :message_date)
        """),
        {
            "claim_id": claim_id,
            "raw_message_id": message["id"],
            "channel_name": message["channel_name"],
            "message_date": message["message_date"],
        },
    )
    return claim_id


async def copy_claims_from_message(
    session: AsyncSession,
    source_msg_id: int,
    target_msg_id: int,
    channel_name: str,
    message_date: datetime,
) -> None:
    """Copy claims from one message to another.

    Used when a message is forwarded/copied: creates new source references
    for all claims extracted from the source message, pointing to the target message.
    Updates occurrence counts accordingly.
    """
    await session.execute(
        text("""
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_name, message_date)
        SELECT claim_id, :target_id, :channel_name, :message_date
        FROM claim_sources
        WHERE raw_message_id = :source_id
        """),
        {
            "target_id": target_msg_id,
            "source_id": source_msg_id,
            "channel_name": channel_name,
            "message_date": message_date,
        },
    )
    await session.execute(
        text("""
        UPDATE claims
        SET occurrence_count = occurrence_count + 1, last_seen_at = NOW()
        WHERE id IN (
            SELECT claim_id FROM claim_sources WHERE raw_message_id = :source_id
        )
        """),
        {"source_id": source_msg_id},
    )
