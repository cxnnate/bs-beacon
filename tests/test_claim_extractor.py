import json
import pytest
from unittest.mock import MagicMock, patch
from src.processing.claim_extractor import ClaudeClient, make_llm_client
from src.processing.schemas import (
    ExtractionResult, ExtractedClaim, ExtractionMeta,
    ClaimEntities, ClaimCategory, Temporality, MessageType,
)


VALID_RESPONSE_JSON = json.dumps({
    "claims": [{
        "text": "The FDA approved a new COVID-19 vaccine",
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
})

EMPTY_RESPONSE_JSON = json.dumps({
    "claims": [],
    "meta": {
        "message_type": "conversation",
        "claim_count": 0,
        "language_detected": "en",
        "contains_media_reference": False,
        "urgency_signals": False,
    },
})


def _make_mock_anthropic_response(content: str):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=content)]
    return mock_response


def test_extract_returns_extraction_result():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = _make_mock_anthropic_response(VALID_RESPONSE_JSON)
        client = ClaudeClient()
        result = client.extract("The FDA approved a new vaccine.", "TestChannel", "2026-01-01", 100, 10)
        assert isinstance(result, ExtractionResult)
        assert len(result.claims) == 1
        assert result.claims[0].category == ClaimCategory.health


def test_extract_empty_message_returns_no_claims():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = _make_mock_anthropic_response(EMPTY_RESPONSE_JSON)
        client = ClaudeClient()
        result = client.extract("Good morning everyone!", "TestChannel", "2026-01-01", 10, 0)
        assert result.claims == []
        assert result.meta.claim_count == 0


def test_extract_handles_malformed_json():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = _make_mock_anthropic_response("not valid json {{")
        client = ClaudeClient()
        result = client.extract("Some message", "TestChannel", "2026-01-01", 0, 0)
        assert isinstance(result, ExtractionResult)
        assert result.claims == []
        assert result.meta.message_type == MessageType.unclear


def test_extract_strips_markdown_fences():
    fenced = "```json\n" + VALID_RESPONSE_JSON + "\n```"
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = _make_mock_anthropic_response(fenced)
        client = ClaudeClient()
        result = client.extract("The FDA approved a new vaccine.", "TestChannel", "2026-01-01", 100, 10)
        assert len(result.claims) == 1


def test_extract_empty_content_returns_fallback():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "max_tokens"
        MockAnthropic.return_value.messages.create.return_value = mock_response
        client = ClaudeClient()
        result = client.extract("Some message", "TestChannel", "2026-01-01", 0, 0)
        assert isinstance(result, ExtractionResult)
        assert result.claims == []
        assert result.meta.message_type == MessageType.unclear


def test_make_llm_client_returns_claude_client():
    with patch.dict("os.environ", {"LLM_PROVIDER": "claude"}):
        with patch("src.processing.claim_extractor.Anthropic"):
            client = make_llm_client()
            assert isinstance(client, ClaudeClient)


def test_make_llm_client_unknown_provider_raises():
    with patch.dict("os.environ", {"LLM_PROVIDER": "unknown_provider"}):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            make_llm_client()
