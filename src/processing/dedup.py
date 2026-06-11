import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.processing.schemas import ClaimRelation, ExtractedClaim, ExtractionMeta, NLILabel

_NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"


def _embedding_to_pg(embedding: list[float]) -> str:
    """Convert an embedding list to PostgreSQL vector format string."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


class NLIChecker(Protocol):
    def check_relation(self, text_a: str, text_b: str) -> NLILabel: ...


class CrossEncoderNLIChecker:
    """Classifies the relation between two claims via a local cross-encoder.

    Guards dedup against merging a claim with its own negation: embedding
    similarity captures topicality, not stance.
    """

    # Label order per the cross-encoder/nli-deberta-v3-base model card.
    _LABELS = [NLILabel.contradiction, NLILabel.entailment, NLILabel.neutral]

    def __init__(self):
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(_NLI_MODEL_NAME)

    def check_relation(self, text_a: str, text_b: str) -> NLILabel:
        # Bidirectional check: only call it entailment if it holds both ways,
        # so a more specific claim doesn't merge into a broader one.
        forward, backward = self._model.predict([(text_a, text_b), (text_b, text_a)])
        label_fwd = self._LABELS[int(forward.argmax())]
        label_bwd = self._LABELS[int(backward.argmax())]
        if NLILabel.contradiction in (label_fwd, label_bwd):
            return NLILabel.contradiction
        if label_fwd == NLILabel.entailment and label_bwd == NLILabel.entailment:
            return NLILabel.entailment
        return NLILabel.neutral


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
        SELECT id FROM raw_messages
        WHERE text_hash = :hash AND processed = TRUE AND id != :exclude_id
        LIMIT 1
        """),
        {"hash": text_hash, "exclude_id": exclude_id},
    )
    row = result.fetchone()
    return row[0] if row else None


async def find_candidate_claims(
    session: AsyncSession,
    embedding: list[float],
    threshold: float = 0.88,
    limit: int = 5,
) -> list[tuple[int, str]]:
    """Find dedup candidates by embedding similarity.

    Returns (claim_id, claim_text) pairs ordered by similarity. The threshold
    casts a wide net on purpose — the NLI guard decides merge vs. contradiction.
    """
    embedding_str = _embedding_to_pg(embedding)
    result = await session.execute(
        text("""
        SELECT id, claim_text
        FROM claims
        WHERE 1 - (embedding <=> CAST(:embedding AS vector)) > :threshold
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
        """),
        {"embedding": embedding_str, "threshold": threshold, "limit": limit},
    )
    return [(row[0], row[1]) for row in result.fetchall()]


async def resolve_dedup(
    session: AsyncSession,
    nli_checker: NLIChecker,
    new_claim_text: str,
    candidates: list[tuple[int, str]],
) -> tuple[Optional[int], list[int]]:
    """Decide what to do with a new claim given its similarity candidates.

    Returns (merge_target_id, contradiction_ids): the first candidate whose
    relation is entailment becomes the merge target; candidates that contradict
    the new claim are collected for claim_relations edges; neutral candidates
    are ignored.
    """
    merge_target: Optional[int] = None
    contradictions: list[int] = []
    for candidate_id, candidate_text in candidates:
        relation = nli_checker.check_relation(new_claim_text, candidate_text)
        if relation == NLILabel.entailment and merge_target is None:
            merge_target = candidate_id
        elif relation == NLILabel.contradiction:
            contradictions.append(candidate_id)
    return merge_target, contradictions


async def insert_claim_relation(
    session: AsyncSession,
    claim_a: int,
    claim_b: int,
    relation: ClaimRelation,
) -> None:
    """Link two claims (paraphrase or contradiction edge)."""
    await session.execute(
        text("""
        INSERT INTO claim_relations (claim_a, claim_b, relation)
        VALUES (:claim_a, :claim_b, :relation)
        ON CONFLICT DO NOTHING
        """),
        {"claim_a": claim_a, "claim_b": claim_b, "relation": relation.value},
    )


async def merge_claim(
    session: AsyncSession,
    claim_id: int,
    raw_message_id: int,
    channel_name: str,
    message_date: datetime,
    channel_id: Optional[int] = None,
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
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_id, channel_name, message_date)
        VALUES (:claim_id, :raw_message_id, :channel_id, :channel_name, :message_date)
        """),
        {
            "claim_id": claim_id,
            "raw_message_id": raw_message_id,
            "channel_id": channel_id,
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
    and adds a source reference linking it to the raw message. The claim
    starts as its own dedup cluster (cluster_id = its own id).
    Returns the ID of the new claim.
    """
    now = datetime.now(timezone.utc)
    embedding_str = _embedding_to_pg(embedding)
    result = await session.execute(
        text("""
        INSERT INTO claims (
            claim_text, source_language, first_seen_at, last_seen_at,
            occurrence_count, entities_json, topic, temporal,
            checkworthy_score, source_attribution, urgency_signals,
            conspiratorial_framing, embedding, status, created_at
        ) VALUES (
            :claim_text, :source_language, :now, :now,
            1, :entities_json, :topic, :temporal,
            :checkworthy_score, :source_attribution, :urgency_signals,
            :conspiratorial_framing, CAST(:embedding AS vector), 'unreviewed', :now
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
            "topic": claim.topic.value,
            "temporal": claim.temporal.value,
            "checkworthy_score": claim.checkworthy_score,
            "source_attribution": claim.source_attribution,
            "urgency_signals": urgency,
            "conspiratorial_framing": meta.conspiratorial_framing,
            "embedding": embedding_str,
        },
    )
    row = result.fetchone()
    if row is None:
        raise RuntimeError("INSERT INTO claims returned no id — RETURNING clause failed")
    claim_id = row[0]
    await session.execute(
        text("UPDATE claims SET cluster_id = :id WHERE id = :id"),
        {"id": claim_id},
    )
    await session.execute(
        text("""
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_id, channel_name, message_date)
        VALUES (:claim_id, :raw_message_id, :channel_id, :channel_name, :message_date)
        """),
        {
            "claim_id": claim_id,
            "raw_message_id": message["id"],
            "channel_id": message.get("channel_id"),
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
    channel_id: Optional[int] = None,
) -> None:
    """Copy claims from one message to another.

    Used when a message is forwarded/copied: creates new source references
    for all claims extracted from the source message, pointing to the target message.
    Updates occurrence counts accordingly.
    """
    await session.execute(
        text("""
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_id, channel_name, message_date)
        SELECT claim_id, :target_id, :channel_id, :channel_name, :message_date
        FROM claim_sources
        WHERE raw_message_id = :source_id
        """),
        {
            "target_id": target_msg_id,
            "source_id": source_msg_id,
            "channel_id": channel_id,
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
