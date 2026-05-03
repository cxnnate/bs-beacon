import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from src.processing.pipeline import process_message, fetch_batch, mark_processed, mark_failed, should_abandon


async def test_fetch_batch_returns_list(mock_session):
    mock_row = MagicMock()
    mock_row._mapping = {
        "id": 1, "message_text": "Test message about health policy.",
        "channel_name": "TestChannel", "channel_id": 100,
        "message_date": datetime.now(timezone.utc), "views": 100, "forwards": 5
    }
    mock_session.execute.return_value.fetchall.return_value = [mock_row]
    batch = await fetch_batch(mock_session, batch_size=20)
    assert len(batch) == 1
    assert batch[0]["channel_name"] == "TestChannel"


async def test_mark_processed_updates_db(mock_session):
    await mark_processed(mock_session, msg_id=1)
    mock_session.execute.assert_called_once()
    call_kwargs = mock_session.execute.call_args[0][1]
    assert call_kwargs["id"] == 1


async def test_mark_failed_increments_counter(mock_session):
    await mark_failed(mock_session, msg_id=1)
    mock_session.execute.assert_called_once()


async def test_should_abandon_returns_true_at_max(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (3,)
    result = await should_abandon(mock_session, msg_id=1, max_attempts=3)
    assert result is True


async def test_should_abandon_returns_false_below_max(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (1,)
    result = await should_abandon(mock_session, msg_id=1, max_attempts=3)
    assert result is False


async def test_process_message_calls_llm_and_stores_claim(
    mock_session, sample_extraction_result, sample_raw_message
):
    mock_llm = MagicMock()
    mock_llm.extract.return_value = sample_extraction_result
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [0.1] * 384

    # 6 execute calls:
    # 1. UPDATE text_hash on raw_messages
    # 2. find_by_text_hash → no hit
    # 3. find_similar_claim → no hit
    # 4. INSERT claims RETURNING id
    # 5. INSERT claim_sources
    # 6. mark_processed UPDATE
    responses = [
        MagicMock(fetchone=MagicMock(return_value=None)),   # UPDATE text_hash
        MagicMock(fetchone=MagicMock(return_value=None)),   # find_by_text_hash → no hit
        MagicMock(fetchone=MagicMock(return_value=None)),   # find_similar_claim → no hit
        MagicMock(fetchone=MagicMock(return_value=(1,))),   # INSERT claims RETURNING id
        MagicMock(fetchone=MagicMock(return_value=None)),   # INSERT claim_sources
        MagicMock(fetchone=MagicMock(return_value=None)),   # mark_processed UPDATE
    ]
    mock_session.execute.side_effect = responses

    await process_message(mock_session, sample_raw_message, mock_llm, mock_embedder)

    mock_llm.extract.assert_called_once()
    mock_embedder.embed.assert_called_once_with("The FDA approved a new COVID-19 vaccine")


async def test_process_message_skips_llm_on_text_hash_hit(
    mock_session, sample_extraction_result, sample_raw_message
):
    mock_llm = MagicMock()
    mock_embedder = MagicMock()

    # 5 execute calls:
    # 1. UPDATE text_hash
    # 2. find_by_text_hash → hit (returns existing msg id 42)
    # 3. copy_claims INSERT into claim_sources (SELECT)
    # 4. copy_claims UPDATE claims occurrence_count
    # 5. mark_processed
    responses = [
        MagicMock(fetchone=MagicMock(return_value=None)),   # update text_hash
        MagicMock(fetchone=MagicMock(return_value=(42,))),  # find_by_text_hash → hit
        MagicMock(fetchone=MagicMock(return_value=None)),   # copy_claims insert
        MagicMock(fetchone=MagicMock(return_value=None)),   # copy_claims update
        MagicMock(fetchone=MagicMock(return_value=None)),   # mark_processed
    ]
    mock_session.execute.side_effect = responses

    await process_message(mock_session, sample_raw_message, mock_llm, mock_embedder)

    mock_llm.extract.assert_not_called()
