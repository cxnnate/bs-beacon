import logging
import os
from pathlib import Path
from typing import Protocol
from anthropic import Anthropic

from src.processing.schemas import ExtractionResult, ExtractionMeta, MessageType

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent.parent / "config" / "system_prompt.txt"


def _load_system_prompt() -> str:
    try:
        return _SYSTEM_PROMPT_PATH.read_text()
    except FileNotFoundError:
        raise FileNotFoundError(f"System prompt not found at {_SYSTEM_PROMPT_PATH}")


EXTRACTION_TOOL = {
    "name": "record_extracted_claims",
    "description": "Record all discrete verifiable claims found in a Telegram message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "entities": {
                            "type": "object",
                            "properties": {
                                "people": {"type": "array", "items": {"type": "string"}},
                                "organizations": {"type": "array", "items": {"type": "string"}},
                                "locations": {"type": "array", "items": {"type": "string"}},
                                "quantities": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                        "topic": {
                            "type": "string",
                            "enum": ["health", "politics", "finance", "technology",
                                     "military", "environment", "science", "crime", "other"],
                        },
                        "temporal": {
                            "type": "string",
                            "enum": ["past", "present", "future", "unspecified"],
                        },
                        "checkworthy_score": {"type": "number", "minimum": 0, "maximum": 1},
                        "source_attribution": {"type": ["string", "null"]},
                    },
                    "required": ["text", "entities", "topic", "checkworthy_score"],
                },
            },
            "meta": {
                "type": "object",
                "properties": {
                    "message_type": {
                        "type": "string",
                        "enum": ["news_share", "opinion_rant", "forwarded_alert",
                                 "question", "conversation", "propaganda", "satire", "unclear"],
                    },
                    "language_detected": {"type": "string"},
                    "urgency_signals": {"type": "boolean"},
                    "conspiratorial_framing": {"type": "boolean"},
                },
                "required": ["message_type", "language_detected",
                             "urgency_signals", "conspiratorial_framing"],
            },
        },
        "required": ["claims", "meta"],
    },
}


def _fallback_result() -> ExtractionResult:
    return ExtractionResult(
        claims=[],
        meta=ExtractionMeta(
            message_type=MessageType.unclear,
            language_detected="unknown",
            urgency_signals=False,
            conspiratorial_framing=False,
        ),
    )


class LLMClient(Protocol):
    def extract(
        self,
        text: str,
        channel_name: str,
        message_date: str,
        view_count: int = 0,
        forward_count: int = 0,
    ) -> ExtractionResult: ...


class ClaudeClient:
    def __init__(self, model: str | None = None):
        self._client = Anthropic()
        self._model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self._system_prompt = _load_system_prompt()

    def extract(
        self,
        text: str,
        channel_name: str,
        message_date: str,
        view_count: int = 0,
        forward_count: int = 0,
    ) -> ExtractionResult:
        user_prompt = (
            f"Analyze this Telegram message and extract all claims:\n\n"
            f"Channel: {channel_name}\n"
            f"Date: {message_date}\n"
            f"Views: {view_count}\n"
            f"Forwards: {forward_count}\n\n"
            f"Message:\n---\n{text}\n---"
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                system=self._system_prompt,
                tools=[EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "record_extracted_claims"},
                messages=[{"role": "user", "content": user_prompt}],
            )
            return ExtractionResult.model_validate(response.content[0].input)
        except Exception:
            logger.exception("Claim extraction failed")
            return _fallback_result()


def make_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "claude")
    if provider == "claude":
        return ClaudeClient()
    raise ValueError(f"Unknown LLM provider: {provider}")
