import pytest
from datetime import datetime, timezone
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


def _claim_row(id=1, status="unreviewed"):
    m = MagicMock()
    m._mapping = {
        "id": id,
        "claim_text": "Iran evacuating military HQ",
        "category": "military",
        "temporal": "past",
        "checkworthy_score": 0.91,
        "source_attribution": None,
        "urgency_signals": True,
        "occurrence_count": 1,
        "status": status,
        "first_seen_at": datetime(2026, 5, 4, 14, 0, tzinfo=timezone.utc),
        "last_seen_at": datetime(2026, 5, 4, 14, 5, tzinfo=timezone.utc),
        "channels": ["Geopolitics Watch"],
    }
    return m


def _session(execute_results):
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(side_effect=execute_results)
    return MagicMock(return_value=session)


async def test_get_claims_returns_list():
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    rows_result = MagicMock()
    rows_result.fetchall.return_value = [_claim_row()]

    with patch("src.api.routes.claims.AsyncSessionLocal", _session([count_result, rows_result])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/claims")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["category"] == "military"
    assert body["items"][0]["channels"] == ["Geopolitics Watch"]


async def test_get_claims_status_filter():
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    rows_result = MagicMock()
    rows_result.fetchall.return_value = []
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(side_effect=[count_result, rows_result])
    sm = MagicMock(return_value=session)

    with patch("src.api.routes.claims.AsyncSessionLocal", sm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/claims?status=reviewed")

    assert resp.status_code == 200
    call_params = session.execute.call_args_list[0][0][1]
    assert call_params.get("status") == "reviewed"


async def test_patch_claim_updates_status():
    update_result = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = _claim_row(status="reviewed")
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(side_effect=[update_result, select_result])
    sm = MagicMock(return_value=session)

    with patch("src.api.routes.claims.AsyncSessionLocal", sm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch("/api/claims/1", json={"status": "reviewed"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "reviewed"


async def test_patch_claim_rejects_invalid_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch("/api/claims/1", json={"status": "bogus"})
    assert resp.status_code == 422
