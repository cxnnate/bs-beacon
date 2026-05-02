import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from src.processing.schemas import (
    ExtractionResult, ExtractedClaim, ExtractionMeta,
    ClaimEntities, ClaimCategory, Temporality, MessageType,
)


@pytest.fixture
def mock_session():
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = None
    result.fetchall.return_value = []
    session.execute.return_value = result
    return session


@pytest.fixture
def sample_extraction_result():
    return ExtractionResult(
        claims=[
            ExtractedClaim(
                text="The FDA approved a new COVID-19 vaccine",
                entities=ClaimEntities(organizations=["FDA"]),
                category=ClaimCategory.health,
                temporal=Temporality.past,
                checkworthy_score=0.9,
                source_attribution=None,
            )
        ],
        meta=ExtractionMeta(
            message_type=MessageType.news_share,
            claim_count=1,
            language_detected="en",
            contains_media_reference=False,
            urgency_signals=False,
        ),
    )


@pytest.fixture
def sample_raw_message():
    return {
        "id": 1,
        "telegram_msg_id": 1000,
        "channel_id": 100,
        "channel_name": "TestChannel",
        "message_text": "The FDA approved a new COVID-19 vaccine for emergency use.",
        "message_date": datetime.now(timezone.utc),
        "views": 1000,
        "forwards": 50,
    }
