import pytest
from pydantic import ValidationError
from src.processing.schemas import (
    ExtractionResult, ExtractedClaim, ExtractionMeta,
    ClaimEntities, ClaimCategory, Temporality, MessageType,
)


def test_valid_extraction_result():
    data = {
        "claims": [{
            "text": "The FDA approved Drug X",
            "entities": {"people": [], "organizations": ["FDA"], "locations": [], "quantities": []},
            "category": "health",
            "temporal": "past",
            "checkworthy_score": 0.9,
            "source_attribution": None,
        }],
        "meta": {
            "message_type": "news_share",
            "claim_count": 1,
            "language_detected": "en",
            "contains_media_reference": False,
            "urgency_signals": False,
        },
    }
    result = ExtractionResult.model_validate(data)
    assert len(result.claims) == 1
    assert result.claims[0].category == ClaimCategory.health
    assert result.meta.message_type == MessageType.news_share


def test_empty_claims_valid():
    data = {
        "claims": [],
        "meta": {
            "message_type": "conversation",
            "claim_count": 0,
            "language_detected": "en",
            "contains_media_reference": False,
            "urgency_signals": False,
        },
    }
    result = ExtractionResult.model_validate(data)
    assert result.claims == []
    assert result.meta.claim_count == 0


def test_checkworthy_score_above_one_raises():
    with pytest.raises(ValidationError):
        ExtractedClaim(
            text="test claim",
            entities=ClaimEntities(),
            category=ClaimCategory.health,
            temporal=Temporality.past,
            checkworthy_score=1.5,
        )


def test_checkworthy_score_below_zero_raises():
    with pytest.raises(ValidationError):
        ExtractedClaim(
            text="test claim",
            entities=ClaimEntities(),
            category=ClaimCategory.health,
            temporal=Temporality.past,
            checkworthy_score=-0.1,
        )


def test_unknown_category_coerced_to_other():
    claim = ExtractedClaim(
        text="test claim",
        entities=ClaimEntities(),
        category="history",
        temporal=Temporality.past,
        checkworthy_score=0.5,
    )
    assert claim.category == ClaimCategory.other


def test_entities_default_to_empty_lists():
    entities = ClaimEntities()
    assert entities.people == []
    assert entities.organizations == []
    assert entities.locations == []
    assert entities.quantities == []
