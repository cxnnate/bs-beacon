import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from src.ingestion.scraper import should_skip, store_messages, load_channels


def test_should_skip_none_text():
    msg = MagicMock()
    msg.text = None
    assert should_skip(msg) is True


def test_should_skip_short_text():
    msg = MagicMock()
    msg.text = "ok"
    assert should_skip(msg) is True


def test_should_not_skip_valid_text():
    msg = MagicMock()
    msg.text = "The FDA approved a new COVID-19 vaccine for emergency use."
    assert should_skip(msg) is False


def test_load_channels_returns_flat_list(tmp_path):
    yaml_content = """
channels:
  health:
    - username: "healthchan"
      display_name: "Health Chan"
  politics:
    - username: "polchan"
      display_name: "Pol Chan"
"""
    config_file = tmp_path / "channels.yaml"
    config_file.write_text(yaml_content)
    channels = load_channels(str(config_file))
    assert len(channels) == 2
    usernames = [c["username"] for c in channels]
    assert "healthchan" in usernames
    assert "polchan" in usernames


@pytest.mark.asyncio
async def test_store_messages_executes_insert(mock_session):
    messages = [{
        "telegram_msg_id": 1,
        "channel_id": 100,
        "channel_name": "TestChannel",
        "message_text": "Test message about vaccines and health policy.",
        "message_date": datetime.now(timezone.utc),
        "views": 100,
        "forwards": 10,
        "replies": 5,
        "media_type": None,
        "media_file_id": None,
        "forward_from": None,
    }]
    await store_messages(mock_session, messages)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_channel_handles_flood_wait(mocker):
    from telethon.errors import FloodWaitError
    mock_client = AsyncMock()
    flood_error = FloodWaitError(request=MagicMock())
    flood_error.seconds = 0
    mock_client.get_entity.side_effect = flood_error
    mock_sleep = mocker.patch("src.ingestion.scraper.asyncio.sleep", new_callable=AsyncMock)

    mock_session = AsyncMock()
    mock_session.execute.return_value.fetchone.return_value = None

    from src.ingestion.scraper import fetch_channel
    count = await fetch_channel(
        mock_client, mock_session,
        {"username": "testchan", "display_name": "Test", "domain": "health"},
        set(),
    )
    assert count == 0
    mock_sleep.assert_called_once()
