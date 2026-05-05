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
    mock_run = mocker.patch("src.api.routes.logs.subprocess.run")
    mock_run.return_value = MagicMock(stdout="[14:03] DB connection OK\n", stderr="")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/logs/scraper")

    assert resp.status_code == 200
    assert "DB connection OK" in resp.text
    mock_run.assert_called_once_with(
        ["docker", "logs", "--tail", "30", "bsbeacon-scraper"],
        capture_output=True,
        text=True,
        timeout=10,
    )


async def test_get_logs_unknown_service_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/logs/api")
    assert resp.status_code == 400
