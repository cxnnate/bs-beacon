import pytest
from unittest.mock import MagicMock, patch
from src.processing.claim_extractor import ClaudeClient, make_llm_client, EXTRACTION_TOOL
from src.processing.schemas import ExtractionResult, ClaimTopic, MessageType


VALID_TOOL_INPUT = {
    "claims": [{
        "text": "The FDA approved a new COVID-19 vaccine",
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

EMPTY_TOOL_INPUT = {
    "claims": [],
    "meta": {
        "message_type": "conversation",
        "language_detected": "en",
        "urgency_signals": False,
        "conspiratorial_framing": False,
    },
}


def _make_mock_tool_response(tool_input: dict):
    mock_response = MagicMock()
    block = MagicMock()
    block.input = tool_input
    mock_response.content = [block]
    return mock_response


def test_extract_returns_extraction_result():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = _make_mock_tool_response(VALID_TOOL_INPUT)
        client = ClaudeClient()
        result = client.extract("The FDA approved a new vaccine.", "TestChannel", "2026-01-01", 100, 10)
        assert isinstance(result, ExtractionResult)
        assert len(result.claims) == 1
        assert result.claims[0].topic == ClaimTopic.health


def test_extract_forces_tool_choice():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        mock_create = MockAnthropic.return_value.messages.create
        mock_create.return_value = _make_mock_tool_response(VALID_TOOL_INPUT)
        client = ClaudeClient()
        client.extract("The FDA approved a new vaccine.", "TestChannel", "2026-01-01", 100, 10)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] == [EXTRACTION_TOOL]
        assert kwargs["tool_choice"] == {"type": "tool", "name": "record_extracted_claims"}


def test_extract_empty_message_returns_no_claims():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = _make_mock_tool_response(EMPTY_TOOL_INPUT)
        client = ClaudeClient()
        result = client.extract("Good morning everyone!", "TestChannel", "2026-01-01", 10, 0)
        assert result.claims == []


def test_extract_api_error_returns_fallback():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.side_effect = RuntimeError("API down")
        client = ClaudeClient()
        result = client.extract("Some message", "TestChannel", "2026-01-01", 0, 0)
        assert isinstance(result, ExtractionResult)
        assert result.claims == []
        assert result.meta.message_type == MessageType.unclear


def test_extract_invalid_tool_input_returns_fallback():
    with patch("src.processing.claim_extractor.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = _make_mock_tool_response(
            {"claims": "not a list", "meta": {}}
        )
        client = ClaudeClient()
        result = client.extract("Some message", "TestChannel", "2026-01-01", 0, 0)
        assert result.claims == []
        assert result.meta.message_type == MessageType.unclear


def test_extraction_tool_schema_matches_pydantic_models():
    claim_props = EXTRACTION_TOOL["input_schema"]["properties"]["claims"]["items"]["properties"]
    assert set(claim_props["topic"]["enum"]) == {e.value for e in ClaimTopic}
    meta_props = EXTRACTION_TOOL["input_schema"]["properties"]["meta"]["properties"]
    assert set(meta_props["message_type"]["enum"]) == {e.value for e in MessageType}
    assert "conspiratorial_framing" in meta_props
    assert "claim_count" not in meta_props


def test_make_llm_client_returns_claude_client():
    with patch.dict("os.environ", {"LLM_PROVIDER": "claude"}):
        with patch("src.processing.claim_extractor.Anthropic"):
            client = make_llm_client()
            assert isinstance(client, ClaudeClient)


def test_make_llm_client_unknown_provider_raises():
    with patch.dict("os.environ", {"LLM_PROVIDER": "unknown_provider"}):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            make_llm_client()
