from datetime import datetime, timezone
from src.api.schemas import ClaimResponse, ClaimDetail, StatsResponse, PatchStatusRequest, ClaimsListResponse
from pydantic import ValidationError
import pytest


def test_claim_response_serializes():
    c = ClaimResponse(
        id=1,
        claim_text="Test claim",
        category="military",
        temporal="past",
        checkworthy_score=0.91,
        source_attribution=None,
        urgency_signals=True,
        occurrence_count=3,
        status="unreviewed",
        first_seen_at=datetime(2026, 5, 4, 14, 0, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 5, 4, 14, 9, tzinfo=timezone.utc),
        channels=["Geopolitics Watch", "Geopolitics Prime"],
    )
    assert c.id == 1
    assert c.channels == ["Geopolitics Watch", "Geopolitics Prime"]


def test_patch_status_rejects_invalid():
    with pytest.raises(ValidationError):
        PatchStatusRequest(status="bogus")


def test_patch_status_accepts_reviewed():
    req = PatchStatusRequest(status="reviewed")
    assert req.status == "reviewed"


def test_stats_response_shape():
    s = StatsResponse(total_claims=247, unreviewed=12, urgent_unreviewed=3, messages_today=84, claims_today=31)
    assert s.total_claims == 247
