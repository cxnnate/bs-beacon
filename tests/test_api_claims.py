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
        "topic": "military",
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
    assert body["items"][0]["topic"] == "military"
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
            resp = await client.get("/api/claims?status=verified")

    assert resp.status_code == 200
    call_params = session.execute.call_args_list[0][0][1]
    assert call_params.get("status") == "verified"


async def test_patch_claim_updates_status():
    update_result = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = _claim_row(status="verified")
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(side_effect=[update_result, select_result])
    sm = MagicMock(return_value=session)

    with patch("src.api.routes.claims.AsyncSessionLocal", sm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch("/api/claims/1", json={"status": "verified"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"


async def test_patch_claim_rejects_invalid_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch("/api/claims/1", json={"status": "bogus"})
    assert resp.status_code == 422


def _network_node_row(id=1, topic="politics"):
    m = MagicMock()
    m._mapping = {
        "id": id,
        "claim_text": f"Claim number {id}",
        "topic": topic,
        "status": "unreviewed",
        "occurrence_count": 1,
        "urgency_signals": False,
    }
    return m


async def test_network_returns_nodes_and_edges():
    edges_result = MagicMock()
    edges_result.fetchall.return_value = [(1, 2, "contradicts")]
    nodes_result = MagicMock()
    nodes_result.fetchall.return_value = [_network_node_row(1), _network_node_row(2)]

    with patch("src.api.routes.claims.AsyncSessionLocal", _session([edges_result, nodes_result])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/claims/network")

    assert resp.status_code == 200
    body = resp.json()
    assert body["edges"] == [{"source": 1, "target": 2, "relation": "contradicts"}]
    assert len(body["nodes"]) == 2
    assert body["nodes"][0]["topic"] == "politics"


async def test_network_empty_when_no_relations():
    edges_result = MagicMock()
    edges_result.fetchall.return_value = []

    with patch("src.api.routes.claims.AsyncSessionLocal", _session([edges_result])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/claims/network")

    assert resp.status_code == 200
    assert resp.json() == {"nodes": [], "edges": []}


async def test_network_days_filter_passes_param():
    edges_result = MagicMock()
    edges_result.fetchall.return_value = []
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(side_effect=[edges_result])
    sm = MagicMock(return_value=session)

    with patch("src.api.routes.claims.AsyncSessionLocal", sm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/claims/network?days=30")

    assert resp.status_code == 200
    query_sql = str(session.execute.call_args_list[0][0][0])
    assert "make_interval" in query_sql
    assert session.execute.call_args_list[0][0][1] == {"days": 30}
