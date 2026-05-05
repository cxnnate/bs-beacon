import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


async def test_get_stats_response_shape():
    counts_result = MagicMock()
    counts_result.fetchone.return_value = (247, 12, 3)
    today_result = MagicMock()
    today_result.fetchone.return_value = (84, 31)

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(side_effect=[counts_result, today_result])
    sm = MagicMock(return_value=session)

    with patch("src.api.routes.stats.AsyncSessionLocal", sm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_claims"] == 247
    assert body["unreviewed"] == 12
    assert body["urgent_unreviewed"] == 3
    assert body["messages_today"] == 84
    assert body["claims_today"] == 31
