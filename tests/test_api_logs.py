import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from src.api.main import app
from src.api.auth import require_auth


@pytest.fixture(autouse=True)
def override_auth():
    async def mock_auth():
        return "testuser"
    app.dependency_overrides[require_auth] = mock_auth
    yield
    app.dependency_overrides.clear()


async def test_get_logs_scraper(mocker):
    mock_container = MagicMock()
    mock_container.logs.return_value = b"[14:03] DB connection OK\n"

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container
    mocker.patch("src.api.routes.logs.docker_sdk.from_env", return_value=mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/logs/scraper")

    assert resp.status_code == 200
    assert "DB connection OK" in resp.text
    mock_client.containers.get.assert_called_once_with("bsbeacon-scraper")
    mock_container.logs.assert_called_once_with(tail=30, stdout=True, stderr=True)


async def test_get_logs_unknown_service_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/logs/api")
    assert resp.status_code == 400
