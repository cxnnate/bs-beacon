import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from src.processing.dedup import (
    compute_text_hash,
    find_by_text_hash,
    find_similar_claim,
    merge_claim,
    insert_claim,
    copy_claims_from_message,
)
from src.processing.schemas import (
    ExtractedClaim, ClaimEntities, ClaimCategory,
    Temporality, ExtractionMeta, MessageType,
)


def test_same_text_produces_same_hash():
    h1 = compute_text_hash("The FDA approved a new vaccine today.")
    h2 = compute_text_hash("The FDA approved a new vaccine today.")
    assert h1 == h2


def test_different_texts_produce_different_hashes():
    h1 = compute_text_hash("The FDA approved a new vaccine today.")
    h2 = compute_text_hash("The WHO met in Geneva to discuss boosters.")
    assert h1 != h2


def test_hash_normalizes_whitespace_and_case():
    h1 = compute_text_hash("  The FDA approved a vaccine  ")
    h2 = compute_text_hash("the fda approved a vaccine")
    assert h1 == h2


@pytest.mark.asyncio
async def test_find_by_text_hash_returns_none_when_not_found(mock_session):
    mock_session.execute.return_value.fetchone.return_value = None
    result = await find_by_text_hash(mock_session, "abc123", exclude_id=1)
    assert result is None


@pytest.mark.asyncio
async def test_find_by_text_hash_returns_id_when_found(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (42,)
    result = await find_by_text_hash(mock_session, "abc123", exclude_id=1)
    assert result == 42


@pytest.mark.asyncio
async def test_find_similar_claim_returns_none_when_no_match(mock_session):
    mock_session.execute.return_value.fetchone.return_value = None
    result = await find_similar_claim(mock_session, [0.1] * 384)
    assert result is None


@pytest.mark.asyncio
async def test_find_similar_claim_returns_id_when_match(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (7,)
    result = await find_similar_claim(mock_session, [0.1] * 384)
    assert result == 7


@pytest.mark.asyncio
async def test_merge_claim_updates_occurrence_count(mock_session):
    await merge_claim(mock_session, claim_id=5, raw_message_id=10,
                      channel_name="TestChannel", message_date=datetime.now(timezone.utc))
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_insert_claim_returns_id(mock_session, sample_extraction_result):
    first_result = MagicMock()
    first_result.fetchone.return_value = (99,)
    second_result = MagicMock()
    mock_session.execute.side_effect = [first_result, second_result]

    claim = sample_extraction_result.claims[0]
    meta = sample_extraction_result.meta
    message = {"id": 1, "channel_name": "TestChannel", "message_date": datetime.now(timezone.utc)}

    claim_id = await insert_claim(
        mock_session, claim=claim, embedding=[0.1] * 384,
        source_language="en", urgency=False, meta=meta, message=message,
    )
    assert claim_id == 99


@pytest.mark.asyncio
async def test_copy_claims_executes_insert_and_update(mock_session):
    await copy_claims_from_message(
        mock_session, source_msg_id=1, target_msg_id=2,
        channel_name="TestChannel", message_date=datetime.now(timezone.utc),
    )
    assert mock_session.execute.call_count == 2
