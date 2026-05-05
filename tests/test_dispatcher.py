import pytest
from unittest.mock import AsyncMock, MagicMock


async def test_dispatch_alert_sends_ntfy_payload(mocker, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "bsbeacon-alerts")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.sh")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))
    mocker.patch("src.alerts.dispatcher.httpx.AsyncClient", return_value=mock_client)

    from src.alerts.dispatcher import dispatch_alert
    await dispatch_alert("Iran evacuating military HQ", "Geopolitics Watch", 0.91)

    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == "https://ntfy.sh/bsbeacon-alerts"
    assert kwargs["content"] == "Iran evacuating military HQ"
    assert kwargs["headers"]["Title"] == "BSBeacon Alert — Geopolitics Watch"
    assert kwargs["headers"]["Priority"] == "high"
    assert kwargs["headers"]["Tags"] == "warning,bsbeacon"


async def test_dispatch_alert_noop_without_topic(mocker, monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    mock_http = mocker.patch("src.alerts.dispatcher.httpx.AsyncClient")

    from src.alerts.dispatcher import dispatch_alert
    await dispatch_alert("Test claim", "Test Channel", 0.5)

    mock_http.assert_not_called()


async def test_dispatch_alert_does_not_raise_on_network_error(mocker, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "bsbeacon-alerts")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=Exception("network failure"))
    mocker.patch("src.alerts.dispatcher.httpx.AsyncClient", return_value=mock_client)

    from src.alerts.dispatcher import dispatch_alert
    await dispatch_alert("Test claim", "Test Channel", 0.5)  # must not raise
