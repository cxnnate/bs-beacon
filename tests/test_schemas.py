import pytest
from pydantic import ValidationError
from src.processing.schemas import (
    ExtractionResult, ExtractedClaim, ExtractionMeta,
    ClaimEntities, ClaimTopic, Temporality, MessageType,
    ClaimRelation, ClaimStatus, NLILabel,
)


def test_valid_extraction_result():
    data = {
        "claims": [{
            "text": "The FDA approved Drug X",
            "entities": {"people": [], "organizations": ["FDA"], "locations": [], "quantities": []},
            "topic": "health",
            "temporal": "past",
            "checkworthy_score": 0.9,
            "source_attribution": None,
        }],
        "meta": {
            "message_type": "news_share",
            "language_detected": "en",
            "urgency_signals": False,
            "conspiratorial_framing": False,
        },
    }
    result = ExtractionResult.model_validate(data)
    assert len(result.claims) == 1
    assert result.claims[0].topic == ClaimTopic.health
    assert result.meta.message_type == MessageType.news_share


def test_empty_claims_valid():
    data = {
        "claims": [],
        "meta": {
            "message_type": "conversation",
            "language_detected": "en",
            "urgency_signals": False,
            "conspiratorial_framing": False,
        },
    }
    result = ExtractionResult.model_validate(data)
    assert result.claims == []


def test_checkworthy_score_above_one_raises():
    with pytest.raises(ValidationError):
        ExtractedClaim(
            text="test claim",
            entities=ClaimEntities(),
            topic=ClaimTopic.health,
            temporal=Temporality.past,
            checkworthy_score=1.5,
        )


def test_checkworthy_score_below_zero_raises():
    with pytest.raises(ValidationError):
        ExtractedClaim(
            text="test claim",
            entities=ClaimEntities(),
            topic=ClaimTopic.health,
            temporal=Temporality.past,
            checkworthy_score=-0.1,
        )


def test_unknown_topic_coerced_to_other():
    claim = ExtractedClaim(
        text="test claim",
        entities=ClaimEntities(),
        topic="history",
        temporal=Temporality.past,
        checkworthy_score=0.5,
    )
    assert claim.topic == ClaimTopic.other


def test_conspiracy_is_not_a_topic():
    assert "conspiracy" not in {e.value for e in ClaimTopic}
    claim = ExtractedClaim(
        text="test claim",
        entities=ClaimEntities(),
        topic="conspiracy",
        temporal=Temporality.past,
        checkworthy_score=0.5,
    )
    assert claim.topic == ClaimTopic.other


def test_conspiratorial_framing_defaults_false():
    meta = ExtractionMeta(message_type=MessageType.unclear, language_detected="en")
    assert meta.conspiratorial_framing is False
    assert meta.urgency_signals is False


def test_entities_default_to_empty_lists():
    entities = ClaimEntities()
    assert entities.people == []
    assert entities.organizations == []
    assert entities.locations == []
    assert entities.quantities == []


def test_claim_relation_values():
    assert {e.value for e in ClaimRelation} == {"paraphrase", "contradicts"}


def test_claim_status_values():
    assert {e.value for e in ClaimStatus} == {"unreviewed", "verified", "debunked", "needs_info"}


def test_nli_label_values():
    assert {e.value for e in NLILabel} == {"entailment", "contradiction", "neutral"}
