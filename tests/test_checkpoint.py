import pytest
from unittest.mock import AsyncMock, MagicMock
from src.ingestion.checkpoint import get_last_id, update_last_id


@pytest.mark.asyncio
async def test_get_last_id_no_existing_checkpoint(mock_session):
    mock_session.execute.return_value.fetchone.return_value = None
    result = await get_last_id(mock_session, channel_id=12345)
    assert result == 0


@pytest.mark.asyncio
async def test_get_last_id_returns_stored_value(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (99,)
    result = await get_last_id(mock_session, channel_id=12345)
    assert result == 99


@pytest.mark.asyncio
async def test_update_last_id_calls_upsert(mock_session):
    await update_last_id(mock_session, channel_id=12345, channel_name="TestChannel", last_msg_id=500)
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    call_kwargs = call_args[0][1]
    assert call_kwargs["channel_id"] == 12345
    assert call_kwargs["last_msg_id"] == 500
    assert call_kwargs["channel_name"] == "TestChannel"
