import json
import logging
import os
import re
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


_FALLBACK_META = {
    "message_type": "unclear",
    "claim_count": 0,
    "language_detected": "unknown",
    "contains_media_reference": False,
    "urgency_signals": False,
}


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

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()

        try:
            return ExtractionResult.model_validate(json.loads(raw))
        except Exception as e:
            logger.warning("Failed to parse LLM response: %s", e, exc_info=True)
            return ExtractionResult(
                claims=[],
                meta=ExtractionMeta(**_FALLBACK_META),
            )


def make_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "claude")
    if provider == "claude":
        return ClaudeClient()
    raise ValueError(f"Unknown LLM provider: {provider}")
