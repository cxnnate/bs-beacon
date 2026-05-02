# BSBeacon Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working local prototype that ingests Telegram messages and extracts structured claims into PostgreSQL using a two-process architecture.

**Architecture:** Two decoupled async Python processes (scraper + processor) share a PostgreSQL database. The scraper polls Telegram every 3 minutes and writes raw messages. The processor polls for unprocessed messages every 30 seconds, runs language detection, urgency rules, LLM extraction, and semantic dedup, then writes structured claims.

**Tech Stack:** Python 3.11, Telethon, SQLAlchemy async + asyncpg, Alembic, pgvector, langdetect, sentence-transformers (all-MiniLM-L6-v2), Anthropic SDK, Pydantic v2, Docker Compose, pytest + pytest-asyncio

---

## File Map

```
bs-beacon/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
├── alembic.ini
├── .env.example
├── config/
│   ├── channels.yaml
│   ├── settings.yaml
│   └── system_prompt.txt          # raw system prompt text (no markdown)
├── migrations/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── src/
│   ├── __init__.py
│   ├── db/
│   │   ├── __init__.py
│   │   └── connection.py           # async SQLAlchemy engine + session factory
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── scraper.py              # Telethon polling loop
│   │   └── checkpoint.py           # per-channel last_message_id
│   └── processing/
│       ├── __init__.py
│       ├── schemas.py              # Pydantic models for ExtractionResult
│       ├── language.py             # langdetect wrapper
│       ├── urgency.py              # rules-based urgency detection
│       ├── embeddings.py           # sentence-transformers wrapper
│       ├── claim_extractor.py      # LLMClient protocol + ClaudeClient
│       ├── dedup.py                # text-hash dedup + semantic dedup
│       └── pipeline.py             # processing orchestration loop
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_schemas.py
    ├── test_language.py
    ├── test_urgency.py
    ├── test_embeddings.py
    ├── test_claim_extractor.py
    ├── test_dedup.py
    ├── test_checkpoint.py
    ├── test_scraper.py
    └── test_pipeline.py
```

---

## Task 1: Project scaffold

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.env.example`
- Create: `config/channels.yaml`
- Create: `config/settings.yaml`
- Create: `src/__init__.py`, `src/db/__init__.py`, `src/ingestion/__init__.py`, `src/processing/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p src/db src/ingestion src/processing config migrations/versions tests
touch src/__init__.py src/db/__init__.py src/ingestion/__init__.py src/processing/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write `requirements.txt`**

```
telethon>=1.36
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
psycopg2-binary>=2.9
alembic>=1.13
langdetect>=1.0.9
sentence-transformers>=3.0
anthropic>=0.40
pydantic>=2.0
pgvector>=0.3
python-dotenv>=1.0
pyyaml>=6.0
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.12
```

- [ ] **Step 3: Write `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Write `.env.example`**

```
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION_NAME=bsbeacon

DATABASE_URL=postgresql+asyncpg://bsbeacon:bsbeacon@db:5432/bsbeacon
DATABASE_URL_LOCAL=postgresql+asyncpg://bsbeacon:bsbeacon@localhost:5432/bsbeacon
DATABASE_MIGRATION_URL=postgresql://bsbeacon:bsbeacon@localhost:5432/bsbeacon

POSTGRES_USER=bsbeacon
POSTGRES_PASSWORD=bsbeacon
POSTGRES_DB=bsbeacon

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-6

LLM_PROVIDER=claude
```

- [ ] **Step 5: Write `config/channels.yaml`**

```yaml
channels:
  health:
    - username: "channelname1"
      display_name: "Health Channel Placeholder 1"
  politics:
    - username: "channelname2"
      display_name: "Politics Channel Placeholder 1"
  global_affairs:
    - username: "channelname3"
      display_name: "Global Affairs Channel Placeholder 1"
```

- [ ] **Step 6: Write `config/settings.yaml`**

```yaml
scraper:
  poll_interval_seconds: 180
  min_message_length: 20

processor:
  poll_interval_seconds: 30
  batch_size: 20
  max_failed_attempts: 3

dedup:
  similarity_threshold: 0.92

urgency:
  caps_ratio_threshold: 0.4
  min_exclamation_marks: 3
```

- [ ] **Step 7: Write `docker-compose.yml`**

```yaml
version: '3.9'

services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-bsbeacon}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-bsbeacon}
      POSTGRES_DB: ${POSTGRES_DB:-bsbeacon}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bsbeacon"]
      interval: 5s
      timeout: 5s
      retries: 5

  scraper:
    build: .
    command: python -m src.ingestion.scraper
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./config:/app/config
      - ./.telegram_session:/app/.telegram_session

  processor:
    build: .
    command: python -m src.processing.pipeline
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./config:/app/config

volumes:
  postgres_data:
```

- [ ] **Step 8: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
```

- [ ] **Step 9: Install dependencies locally**

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Expected: All packages install without errors.

- [ ] **Step 10: Commit**

```bash
git init
git add .
git commit -m "feat: project scaffold — config, docker-compose, requirements"
```

---

## Task 2: Database migrations

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/001_initial_schema.py`

- [ ] **Step 1: Initialise Alembic**

```bash
alembic init migrations
```

- [ ] **Step 2: Update `alembic.ini` to use env var**

Replace the `sqlalchemy.url` line in `alembic.ini`:

```ini
sqlalchemy.url = postgresql://bsbeacon:bsbeacon@localhost:5432/bsbeacon
```

Then update `migrations/env.py` to read from `DATABASE_MIGRATION_URL` env var. Replace the `run_migrations_online` function:

```python
import os
from dotenv import load_dotenv

load_dotenv()

def run_migrations_online() -> None:
    url = os.getenv("DATABASE_MIGRATION_URL", config.get_main_option("sqlalchemy.url"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=url,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
```

- [ ] **Step 3: Write migration `migrations/versions/001_initial_schema.py`**

```python
"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-02
"""
from alembic import op

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
    CREATE TABLE raw_messages (
        id              BIGSERIAL PRIMARY KEY,
        telegram_msg_id BIGINT NOT NULL,
        channel_id      BIGINT NOT NULL,
        channel_name    TEXT NOT NULL,
        message_text    TEXT,
        message_date    TIMESTAMPTZ NOT NULL,
        views           INTEGER,
        forwards        INTEGER,
        replies         INTEGER,
        reactions_json  JSONB,
        media_type      TEXT,
        media_file_id   TEXT,
        forward_from    TEXT,
        ingested_at     TIMESTAMPTZ DEFAULT NOW(),
        processed       BOOLEAN DEFAULT FALSE,
        failed_attempts INTEGER DEFAULT 0,
        text_hash       TEXT,
        UNIQUE(channel_id, telegram_msg_id)
    )
    """)
    op.execute("CREATE INDEX idx_raw_messages_date ON raw_messages(message_date DESC)")
    op.execute("CREATE INDEX idx_raw_messages_unprocessed ON raw_messages(processed) WHERE processed = FALSE")
    op.execute("CREATE INDEX idx_raw_messages_hash ON raw_messages(text_hash)")

    op.execute("""
    CREATE TABLE claims (
        id                  BIGSERIAL PRIMARY KEY,
        claim_text          TEXT NOT NULL,
        source_language     TEXT,
        first_seen_at       TIMESTAMPTZ NOT NULL,
        last_seen_at        TIMESTAMPTZ NOT NULL,
        occurrence_count    INTEGER DEFAULT 1,
        entities_json       JSONB,
        category            TEXT,
        temporal            TEXT,
        checkworthy_score   FLOAT,
        source_attribution  TEXT,
        urgency_signals     BOOLEAN DEFAULT FALSE,
        message_type        TEXT,
        embedding           VECTOR(384),
        credibility_score   FLOAT,
        virality_score      FLOAT,
        status              TEXT DEFAULT 'unreviewed',
        created_at          TIMESTAMPTZ DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_claims_status ON claims(status)")
    op.execute("CREATE INDEX idx_claims_virality ON claims(virality_score DESC NULLS LAST)")
    op.execute("CREATE INDEX idx_claims_last_seen ON claims(last_seen_at DESC)")
    op.execute("CREATE INDEX idx_claims_created ON claims(created_at DESC)")

    op.execute("""
    CREATE TABLE claim_sources (
        id              BIGSERIAL PRIMARY KEY,
        claim_id        BIGINT REFERENCES claims(id),
        raw_message_id  BIGINT REFERENCES raw_messages(id),
        channel_name    TEXT NOT NULL,
        message_date    TIMESTAMPTZ NOT NULL
    )
    """)
    op.execute("CREATE INDEX idx_claim_sources_claim ON claim_sources(claim_id)")

    op.execute("""
    CREATE TABLE checkpoints (
        channel_id   BIGINT PRIMARY KEY,
        channel_name TEXT NOT NULL,
        last_msg_id  BIGINT NOT NULL DEFAULT 0,
        updated_at   TIMESTAMPTZ DEFAULT NOW()
    )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claim_sources")
    op.execute("DROP TABLE IF EXISTS claims")
    op.execute("DROP TABLE IF EXISTS raw_messages")
    op.execute("DROP TABLE IF EXISTS checkpoints")
    op.execute("DROP EXTENSION IF EXISTS vector")
```

Note: The `ivfflat` index on `claims.embedding` is omitted here — it requires at least one row to build effectively. Add it in Phase 3 once data exists:
```sql
CREATE INDEX idx_claims_embedding ON claims USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

- [ ] **Step 4: Start the database and run migrations**

```bash
docker compose up -d db
# Wait for healthy status
docker compose ps

DATABASE_MIGRATION_URL=postgresql://bsbeacon:bsbeacon@localhost:5432/bsbeacon alembic upgrade head
```

Expected output: `Running upgrade  -> 001, initial schema`

- [ ] **Step 5: Verify tables exist**

```bash
docker exec -it $(docker compose ps -q db) psql -U bsbeacon -d bsbeacon -c "\dt"
```

Expected: `raw_messages`, `claims`, `claim_sources`, `checkpoints` listed.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini migrations/
git commit -m "feat: alembic migrations — raw_messages, claims, claim_sources, checkpoints"
```

---

## Task 3: DB connection + test fixtures

**Files:**
- Create: `src/db/connection.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `src/db/connection.py`**

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv

load_dotenv()

_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://bsbeacon:bsbeacon@localhost:5432/bsbeacon")

engine = create_async_engine(_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
```

- [ ] **Step 2: Write `tests/conftest.py`**

```python
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
```

- [ ] **Step 3: Verify import works**

```bash
python -c "from src.db.connection import AsyncSessionLocal; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/db/connection.py tests/conftest.py
git commit -m "feat: async db connection + test fixtures"
```

---

## Task 4: Pydantic schemas

**Files:**
- Create: `src/processing/schemas.py`
- Create: `tests/test_schemas.py`

- [ ] **Step 1: Write failing tests in `tests/test_schemas.py`**

```python
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


def test_invalid_category_raises():
    with pytest.raises(ValidationError):
        ExtractedClaim(
            text="test claim",
            entities=ClaimEntities(),
            category="not_a_category",
            temporal=Temporality.past,
            checkworthy_score=0.5,
        )


def test_entities_default_to_empty_lists():
    entities = ClaimEntities()
    assert entities.people == []
    assert entities.organizations == []
    assert entities.locations == []
    assert entities.quantities == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_schemas.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `schemas` not yet defined.

- [ ] **Step 3: Write `src/processing/schemas.py`**

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ClaimCategory(str, Enum):
    health = "health"
    politics = "politics"
    finance = "finance"
    technology = "technology"
    military = "military"
    environment = "environment"
    science = "science"
    crime = "crime"
    conspiracy = "conspiracy"
    other = "other"


class Temporality(str, Enum):
    past = "past"
    present = "present"
    future = "future"
    unspecified = "unspecified"


class MessageType(str, Enum):
    news_share = "news_share"
    opinion_rant = "opinion_rant"
    forwarded_alert = "forwarded_alert"
    question = "question"
    conversation = "conversation"
    propaganda = "propaganda"
    satire = "satire"
    unclear = "unclear"


class ClaimEntities(BaseModel):
    people: list[str] = []
    organizations: list[str] = []
    locations: list[str] = []
    quantities: list[str] = []


class ExtractedClaim(BaseModel):
    text: str
    entities: ClaimEntities
    category: ClaimCategory
    temporal: Temporality = Temporality.unspecified
    checkworthy_score: float = Field(ge=0.0, le=1.0)
    source_attribution: Optional[str] = None


class ExtractionMeta(BaseModel):
    message_type: MessageType
    claim_count: int = Field(ge=0)
    language_detected: str
    contains_media_reference: bool = False
    urgency_signals: bool = False


class ExtractionResult(BaseModel):
    claims: list[ExtractedClaim] = []
    meta: ExtractionMeta
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_schemas.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/processing/schemas.py tests/test_schemas.py
git commit -m "feat: pydantic schemas for ExtractionResult"
```

---

## Task 5: Language detection

**Files:**
- Create: `src/processing/language.py`
- Create: `tests/test_language.py`

- [ ] **Step 1: Write failing tests in `tests/test_language.py`**

```python
from src.processing.language import detect_language


def test_detects_english():
    assert detect_language("Scientists published a new study on vaccine safety today.") == "en"


def test_detects_spanish():
    assert detect_language("El gobierno aprobó una nueva ley sobre vacunas obligatorias.") == "es"


def test_detects_russian():
    assert detect_language("Правительство одобрило новый закон об обязательной вакцинации.") == "ru"


def test_short_text_returns_unknown():
    assert detect_language("hi") == "unknown"


def test_empty_string_returns_unknown():
    assert detect_language("") == "unknown"


def test_none_returns_unknown():
    assert detect_language(None) == "unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_language.py -v
```

Expected: `ImportError` — module not yet defined.

- [ ] **Step 3: Write `src/processing/language.py`**

```python
from langdetect import detect, LangDetectException


def detect_language(text: str | None) -> str:
    if not text or len(text.strip()) < 20:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_language.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/processing/language.py tests/test_language.py
git commit -m "feat: language detection with langdetect"
```

---

## Task 6: Urgency detection

**Files:**
- Create: `src/processing/urgency.py`
- Create: `tests/test_urgency.py`

- [ ] **Step 1: Write failing tests in `tests/test_urgency.py`**

```python
from src.processing.urgency import check_urgency, combine_urgency


def test_breaking_keyword_flagged():
    assert check_urgency("BREAKING: New vaccine linked to deaths, share now!") is True


def test_urgent_keyword_flagged():
    assert check_urgency("URGENT: They are hiding this from you.") is True


def test_share_before_deleted_flagged():
    assert check_urgency("Share before they delete this. They don't want you to know.") is True


def test_high_caps_ratio_flagged():
    assert check_urgency("THIS VACCINE IS DEADLY AND THEY ARE LYING TO US ALL") is True


def test_excessive_exclamation_flagged():
    assert check_urgency("Wake up people!!! Share this now!!! They are hiding it!!!") is True


def test_calm_message_not_flagged():
    assert check_urgency("Scientists published a new study on mRNA vaccine efficacy.") is False


def test_empty_message_not_flagged():
    assert check_urgency("") is False


def test_combine_urgency_rules_true():
    assert combine_urgency(rules_result=True, llm_result=False) is True


def test_combine_urgency_llm_true():
    assert combine_urgency(rules_result=False, llm_result=True) is True


def test_combine_urgency_both_false():
    assert combine_urgency(rules_result=False, llm_result=False) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_urgency.py -v
```

Expected: `ImportError` — module not yet defined.

- [ ] **Step 3: Write `src/processing/urgency.py`**

```python
URGENCY_KEYWORDS = [
    "breaking", "urgent", "share before deleted", "they don't want you to know",
    "wake up", "share now", "delete soon", "they're hiding", "cover up",
    "before it's too late", "they are hiding", "wake up people",
]


def check_urgency(text: str) -> bool:
    if not text:
        return False

    lower = text.lower()
    if any(kw in lower for kw in URGENCY_KEYWORDS):
        return True

    words = text.split()
    if len(words) >= 5:
        caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)
        if caps_words / len(words) > 0.4:
            return True

    if text.count("!") >= 3:
        return True

    return False


def combine_urgency(rules_result: bool, llm_result: bool) -> bool:
    return rules_result or llm_result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_urgency.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/processing/urgency.py tests/test_urgency.py
git commit -m "feat: rules-based urgency detection"
```

---

## Task 7: Embeddings

**Files:**
- Create: `src/processing/embeddings.py`
- Create: `tests/test_embeddings.py`

- [ ] **Step 1: Write failing tests in `tests/test_embeddings.py`**

```python
from src.processing.embeddings import Embedder


def test_embedding_has_correct_dimensions():
    embedder = Embedder()
    vec = embedder.embed("The FDA approved a new vaccine for COVID-19.")
    assert len(vec) == 384


def test_embedding_is_list_of_floats():
    embedder = Embedder()
    vec = embedder.embed("The FDA approved a new vaccine for COVID-19.")
    assert isinstance(vec, list)
    assert all(isinstance(x, float) for x in vec)


def test_similar_texts_high_cosine_similarity():
    embedder = Embedder()
    v1 = embedder.embed("The FDA approved a new COVID-19 vaccine.")
    v2 = embedder.embed("FDA has given approval to a COVID-19 vaccine.")
    assert embedder.cosine_similarity(v1, v2) > 0.85


def test_different_texts_low_cosine_similarity():
    embedder = Embedder()
    v1 = embedder.embed("The FDA approved a new COVID-19 vaccine.")
    v2 = embedder.embed("Stock markets fell sharply on Friday amid recession fears.")
    assert embedder.cosine_similarity(v1, v2) < 0.5


def test_same_text_similarity_is_one():
    embedder = Embedder()
    text = "The FDA approved a new COVID-19 vaccine."
    v1 = embedder.embed(text)
    v2 = embedder.embed(text)
    assert abs(embedder.cosine_similarity(v1, v2) - 1.0) < 0.001
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_embeddings.py -v
```

Expected: `ImportError` — module not yet defined.

- [ ] **Step 3: Write `src/processing/embeddings.py`**

```python
import numpy as np
from functools import lru_cache
from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(_MODEL_NAME)


class Embedder:
    def __init__(self):
        self._model = _get_model()

    def embed(self, text: str) -> list[float]:
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        a = np.array(v1)
        b = np.array(v2)
        return float(np.dot(a, b))  # Vectors are already L2-normalized
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_embeddings.py -v
```

Expected: All 5 tests PASS. Note: first run downloads the model (~90MB).

- [ ] **Step 5: Commit**

```bash
git add src/processing/embeddings.py tests/test_embeddings.py
git commit -m "feat: sentence-transformers embeddings wrapper"
```

---

## Task 8: Claim extractor + system prompt

**Files:**
- Create: `config/system_prompt.txt`
- Create: `src/processing/claim_extractor.py`
- Create: `tests/test_claim_extractor.py`

- [ ] **Step 1: Write `config/system_prompt.txt`**

This file contains the raw system prompt text (no markdown, no code fences). Copy the prompt body from `docs/superpowers/specs/CLAIM_EXTRACTION_PROMPT.md` — the text inside the first triple-backtick block under `## System prompt`. It starts with "You are BSBeacon, a precision claim extraction system..." and ends with "...return {"claims": [], "meta": {...}} with claim_count: 0."

- [ ] **Step 2: Write failing tests in `tests/test_claim_extractor.py`**

```python
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


def test_make_llm_client_returns_claude_client():
    with patch.dict("os.environ", {"LLM_PROVIDER": "claude"}):
        with patch("src.processing.claim_extractor.Anthropic"):
            client = make_llm_client()
            assert isinstance(client, ClaudeClient)


def test_make_llm_client_unknown_provider_raises():
    with patch.dict("os.environ", {"LLM_PROVIDER": "unknown_provider"}):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            make_llm_client()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_claim_extractor.py -v
```

Expected: `ImportError` — module not yet defined.

- [ ] **Step 4: Write `src/processing/claim_extractor.py`**

```python
import json
import os
from pathlib import Path
from typing import Protocol
from anthropic import Anthropic

from src.processing.schemas import ExtractionResult, ExtractionMeta, MessageType

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent.parent / "config" / "system_prompt.txt"


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text()


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
        view_count: int,
        forward_count: int,
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
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0].strip()

        try:
            return ExtractionResult.model_validate(json.loads(raw))
        except Exception:
            return ExtractionResult(
                claims=[],
                meta=ExtractionMeta(**_FALLBACK_META),
            )


def make_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "claude")
    if provider == "claude":
        return ClaudeClient()
    raise ValueError(f"Unknown LLM provider: {provider}")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_claim_extractor.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add config/system_prompt.txt src/processing/claim_extractor.py tests/test_claim_extractor.py
git commit -m "feat: LLMClient protocol + ClaudeClient implementation"
```

---

## Task 9: Deduplication

**Files:**
- Create: `src/processing/dedup.py`
- Create: `tests/test_dedup.py`

- [ ] **Step 1: Write failing tests in `tests/test_dedup.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from src.processing.dedup import (
    compute_text_hash,
    find_by_text_hash,
    find_similar_claim,
    merge_claim,
    insert_claim,
    copy_claims_from_message,
)
from src.processing.schemas import (
    ExtractedClaim, ClaimEntities, ClaimCategory,
    Temporality, ExtractionMeta, MessageType,
)


def test_same_text_produces_same_hash():
    h1 = compute_text_hash("The FDA approved a new vaccine today.")
    h2 = compute_text_hash("The FDA approved a new vaccine today.")
    assert h1 == h2


def test_different_texts_produce_different_hashes():
    h1 = compute_text_hash("The FDA approved a new vaccine today.")
    h2 = compute_text_hash("The WHO met in Geneva to discuss boosters.")
    assert h1 != h2


def test_hash_normalizes_whitespace_and_case():
    h1 = compute_text_hash("  The FDA approved a vaccine  ")
    h2 = compute_text_hash("the fda approved a vaccine")
    assert h1 == h2


async def test_find_by_text_hash_returns_none_when_not_found(mock_session):
    mock_session.execute.return_value.fetchone.return_value = None
    result = await find_by_text_hash(mock_session, "abc123", exclude_id=1)
    assert result is None


async def test_find_by_text_hash_returns_id_when_found(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (42,)
    result = await find_by_text_hash(mock_session, "abc123", exclude_id=1)
    assert result == 42


async def test_find_similar_claim_returns_none_when_no_match(mock_session):
    mock_session.execute.return_value.fetchone.return_value = None
    result = await find_similar_claim(mock_session, [0.1] * 384)
    assert result is None


async def test_find_similar_claim_returns_id_when_match(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (7,)
    result = await find_similar_claim(mock_session, [0.1] * 384)
    assert result == 7


async def test_merge_claim_updates_occurrence_count(mock_session):
    await merge_claim(mock_session, claim_id=5, raw_message_id=10,
                      channel_name="TestChannel", message_date=datetime.now(timezone.utc))
    assert mock_session.execute.call_count == 2


async def test_insert_claim_returns_id(mock_session, sample_extraction_result):
    mock_session.execute.return_value.fetchone.return_value = (99,)
    claim = sample_extraction_result.claims[0]
    meta = sample_extraction_result.meta
    message = {"id": 1, "channel_name": "TestChannel", "message_date": datetime.now(timezone.utc)}

    claim_id = await insert_claim(
        mock_session, claim=claim, embedding=[0.1] * 384,
        source_language="en", urgency=False, meta=meta, message=message,
    )
    assert claim_id == 99


async def test_copy_claims_executes_insert_and_update(mock_session):
    await copy_claims_from_message(
        mock_session, source_msg_id=1, target_msg_id=2,
        channel_name="TestChannel", message_date=datetime.now(timezone.utc),
    )
    assert mock_session.execute.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dedup.py -v
```

Expected: `ImportError` — module not yet defined.

- [ ] **Step 3: Write `src/processing/dedup.py`**

```python
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.processing.schemas import ExtractedClaim, ExtractionMeta


def compute_text_hash(text_content: str) -> str:
    normalized = " ".join(text_content.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


async def find_by_text_hash(
    session: AsyncSession, text_hash: str, exclude_id: int
) -> Optional[int]:
    result = await session.execute(
        text("""
        SELECT rm.id FROM raw_messages rm
        JOIN claim_sources cs ON cs.raw_message_id = rm.id
        WHERE rm.text_hash = :hash AND rm.processed = TRUE AND rm.id != :exclude_id
        LIMIT 1
        """),
        {"hash": text_hash, "exclude_id": exclude_id},
    )
    row = result.fetchone()
    return row[0] if row else None


async def find_similar_claim(
    session: AsyncSession,
    embedding: list[float],
    threshold: float = 0.92,
) -> Optional[int]:
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    result = await session.execute(
        text("""
        SELECT id
        FROM claims
        WHERE 1 - (embedding <=> CAST(:embedding AS vector)) > :threshold
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT 1
        """),
        {"embedding": embedding_str, "threshold": threshold},
    )
    row = result.fetchone()
    return row[0] if row else None


async def merge_claim(
    session: AsyncSession,
    claim_id: int,
    raw_message_id: int,
    channel_name: str,
    message_date: datetime,
) -> None:
    await session.execute(
        text("""
        UPDATE claims
        SET occurrence_count = occurrence_count + 1, last_seen_at = NOW()
        WHERE id = :id
        """),
        {"id": claim_id},
    )
    await session.execute(
        text("""
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_name, message_date)
        VALUES (:claim_id, :raw_message_id, :channel_name, :message_date)
        """),
        {
            "claim_id": claim_id,
            "raw_message_id": raw_message_id,
            "channel_name": channel_name,
            "message_date": message_date,
        },
    )


async def insert_claim(
    session: AsyncSession,
    claim: ExtractedClaim,
    embedding: list[float],
    source_language: str,
    urgency: bool,
    meta: ExtractionMeta,
    message: dict,
) -> int:
    now = datetime.now(timezone.utc)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    result = await session.execute(
        text("""
        INSERT INTO claims (
            claim_text, source_language, first_seen_at, last_seen_at,
            occurrence_count, entities_json, category, temporal,
            checkworthy_score, source_attribution, urgency_signals,
            message_type, embedding, status, created_at
        ) VALUES (
            :claim_text, :source_language, :now, :now,
            1, :entities_json, :category, :temporal,
            :checkworthy_score, :source_attribution, :urgency_signals,
            :message_type, CAST(:embedding AS vector), 'unreviewed', :now
        )
        RETURNING id
        """),
        {
            "claim_text": claim.text,
            "source_language": source_language,
            "now": now,
            "entities_json": json.dumps({
                "people": claim.entities.people,
                "organizations": claim.entities.organizations,
                "locations": claim.entities.locations,
                "quantities": claim.entities.quantities,
            }),
            "category": claim.category.value,
            "temporal": claim.temporal.value,
            "checkworthy_score": claim.checkworthy_score,
            "source_attribution": claim.source_attribution,
            "urgency_signals": urgency,
            "message_type": meta.message_type.value,
            "embedding": embedding_str,
        },
    )
    claim_id = result.fetchone()[0]
    await session.execute(
        text("""
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_name, message_date)
        VALUES (:claim_id, :raw_message_id, :channel_name, :message_date)
        """),
        {
            "claim_id": claim_id,
            "raw_message_id": message["id"],
            "channel_name": message["channel_name"],
            "message_date": message["message_date"],
        },
    )
    return claim_id


async def copy_claims_from_message(
    session: AsyncSession,
    source_msg_id: int,
    target_msg_id: int,
    channel_name: str,
    message_date: datetime,
) -> None:
    await session.execute(
        text("""
        INSERT INTO claim_sources (claim_id, raw_message_id, channel_name, message_date)
        SELECT claim_id, :target_id, :channel_name, :message_date
        FROM claim_sources
        WHERE raw_message_id = :source_id
        """),
        {
            "target_id": target_msg_id,
            "source_id": source_msg_id,
            "channel_name": channel_name,
            "message_date": message_date,
        },
    )
    await session.execute(
        text("""
        UPDATE claims
        SET occurrence_count = occurrence_count + 1, last_seen_at = NOW()
        WHERE id IN (
            SELECT claim_id FROM claim_sources WHERE raw_message_id = :source_id
        )
        """),
        {"source_id": source_msg_id},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_dedup.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/processing/dedup.py tests/test_dedup.py
git commit -m "feat: text-hash dedup + semantic dedup with pgvector"
```

---

## Task 10: Checkpoint

**Files:**
- Create: `src/ingestion/checkpoint.py`
- Create: `tests/test_checkpoint.py`

- [ ] **Step 1: Write failing tests in `tests/test_checkpoint.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.ingestion.checkpoint import get_last_id, update_last_id


async def test_get_last_id_no_existing_checkpoint(mock_session):
    mock_session.execute.return_value.fetchone.return_value = None
    result = await get_last_id(mock_session, channel_id=12345)
    assert result == 0


async def test_get_last_id_returns_stored_value(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (99,)
    result = await get_last_id(mock_session, channel_id=12345)
    assert result == 99


async def test_update_last_id_calls_upsert(mock_session):
    await update_last_id(mock_session, channel_id=12345, channel_name="TestChannel", last_msg_id=500)
    mock_session.execute.assert_called_once()
    call_kwargs = mock_session.execute.call_args[0][1]
    assert call_kwargs["channel_id"] == 12345
    assert call_kwargs["last_msg_id"] == 500
    assert call_kwargs["channel_name"] == "TestChannel"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_checkpoint.py -v
```

Expected: `ImportError` — module not yet defined.

- [ ] **Step 3: Write `src/ingestion/checkpoint.py`**

```python
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_last_id(session: AsyncSession, channel_id: int) -> int:
    result = await session.execute(
        text("SELECT last_msg_id FROM checkpoints WHERE channel_id = :channel_id"),
        {"channel_id": channel_id},
    )
    row = result.fetchone()
    return row[0] if row else 0


async def update_last_id(
    session: AsyncSession, channel_id: int, channel_name: str, last_msg_id: int
) -> None:
    await session.execute(
        text("""
        INSERT INTO checkpoints (channel_id, channel_name, last_msg_id, updated_at)
        VALUES (:channel_id, :channel_name, :last_msg_id, NOW())
        ON CONFLICT (channel_id) DO UPDATE SET
            last_msg_id = GREATEST(checkpoints.last_msg_id, EXCLUDED.last_msg_id),
            updated_at = NOW()
        """),
        {"channel_id": channel_id, "channel_name": channel_name, "last_msg_id": last_msg_id},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_checkpoint.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/checkpoint.py tests/test_checkpoint.py
git commit -m "feat: per-channel checkpoint tracking"
```

---

## Task 11: Scraper

**Files:**
- Create: `src/ingestion/scraper.py`
- Create: `tests/test_scraper.py`

- [ ] **Step 1: Write failing tests in `tests/test_scraper.py`**

```python
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from src.ingestion.scraper import should_skip, store_messages, load_channels


def test_should_skip_none_text():
    msg = MagicMock()
    msg.text = None
    assert should_skip(msg) is True


def test_should_skip_short_text():
    msg = MagicMock()
    msg.text = "ok"
    assert should_skip(msg) is True


def test_should_not_skip_valid_text():
    msg = MagicMock()
    msg.text = "The FDA approved a new COVID-19 vaccine for emergency use."
    assert should_skip(msg) is False


def test_load_channels_returns_flat_list(tmp_path):
    yaml_content = """
channels:
  health:
    - username: "healthchan"
      display_name: "Health Chan"
  politics:
    - username: "polchan"
      display_name: "Pol Chan"
"""
    config_file = tmp_path / "channels.yaml"
    config_file.write_text(yaml_content)
    channels = load_channels(str(config_file))
    assert len(channels) == 2
    usernames = [c["username"] for c in channels]
    assert "healthchan" in usernames
    assert "polchan" in usernames


async def test_store_messages_executes_insert(mock_session):
    messages = [{
        "telegram_msg_id": 1,
        "channel_id": 100,
        "channel_name": "TestChannel",
        "message_text": "Test message about vaccines and health policy.",
        "message_date": datetime.now(timezone.utc),
        "views": 100,
        "forwards": 10,
        "replies": 5,
        "media_type": None,
        "media_file_id": None,
        "forward_from": None,
    }]
    await store_messages(mock_session, messages)
    mock_session.execute.assert_called_once()


async def test_fetch_channel_handles_flood_wait(mocker):
    from telethon.errors import FloodWaitError
    mock_client = AsyncMock()
    flood_error = FloodWaitError(request=MagicMock())
    flood_error.seconds = 0
    mock_client.get_entity.side_effect = flood_error
    mock_sleep = mocker.patch("src.ingestion.scraper.asyncio.sleep", new_callable=AsyncMock)

    mock_session = AsyncMock()
    mock_session.execute.return_value.fetchone.return_value = None

    from src.ingestion.scraper import fetch_channel
    count = await fetch_channel(
        mock_client, mock_session,
        {"username": "testchan", "display_name": "Test", "domain": "health"},
        set(),
    )
    assert count == 0
    mock_sleep.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scraper.py -v
```

Expected: `ImportError` — module not yet defined.

- [ ] **Step 3: Write `src/ingestion/scraper.py`**

```python
import asyncio
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from sqlalchemy import text

from src.db.connection import AsyncSessionLocal
from src.ingestion.checkpoint import get_last_id, update_last_id

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
_CHANNELS_PATH = Path(__file__).parent.parent.parent / "config" / "channels.yaml"


def load_channels(path: str | None = None) -> list[dict]:
    p = path or str(_CHANNELS_PATH)
    with open(p) as f:
        data = yaml.safe_load(f)
    channels = []
    for domain, channel_list in data["channels"].items():
        for ch in channel_list:
            channels.append({
                "username": ch["username"],
                "domain": domain,
                "display_name": ch["display_name"],
            })
    return channels


def should_skip(message) -> bool:
    if not message.text:
        return True
    if len(message.text.strip()) < 20:
        return True
    return False


async def store_messages(session, messages: list[dict]) -> None:
    for msg in messages:
        await session.execute(
            text("""
            INSERT INTO raw_messages (
                telegram_msg_id, channel_id, channel_name, message_text,
                message_date, views, forwards, replies, media_type,
                media_file_id, forward_from
            ) VALUES (
                :telegram_msg_id, :channel_id, :channel_name, :message_text,
                :message_date, :views, :forwards, :replies, :media_type,
                :media_file_id, :forward_from
            )
            ON CONFLICT (channel_id, telegram_msg_id) DO NOTHING
            """),
            msg,
        )


async def fetch_channel(
    client, session, channel: dict, monitored_channel_ids: set
) -> int:
    username = channel["username"]
    channel_name = channel["display_name"]

    try:
        entity = await client.get_entity(username)
        channel_id = entity.id
        last_id = await get_last_id(session, channel_id)

        messages = []
        async for msg in client.iter_messages(entity, min_id=last_id, limit=100):
            if should_skip(msg):
                continue

            forward_from = None
            if msg.forward and hasattr(msg.forward, "chat_id") and msg.forward.chat_id:
                if msg.forward.chat_id in monitored_channel_ids:
                    continue
                forward_from = str(msg.forward.chat_id)

            media_type = None
            if msg.media:
                media_type = type(msg.media).__name__.lower().replace("messagemedia", "")

            messages.append({
                "telegram_msg_id": msg.id,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "message_text": msg.text,
                "message_date": msg.date,
                "views": msg.views,
                "forwards": msg.forwards,
                "replies": msg.replies.replies if msg.replies else None,
                "media_type": media_type,
                "media_file_id": None,
                "forward_from": forward_from,
            })

        if messages:
            await store_messages(session, messages)
            new_last_id = max(m["telegram_msg_id"] for m in messages)
            await update_last_id(session, channel_id, channel_name, new_last_id)

        return len(messages)

    except FloodWaitError as e:
        logger.warning(f"Rate limited on {username}, sleeping {e.seconds}s")
        await asyncio.sleep(e.seconds)
        return 0
    except Exception as e:
        logger.error(f"Error fetching {username}: {e}")
        return 0


async def run_scraper() -> None:
    load_dotenv()
    settings = yaml.safe_load(_SETTINGS_PATH.read_text())
    poll_interval = settings["scraper"]["poll_interval_seconds"]

    channels = load_channels()
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session_name = os.getenv("TELEGRAM_SESSION_NAME", "bsbeacon")

    async with TelegramClient(session_name, api_id, api_hash) as client:
        logger.info(f"Scraper started — monitoring {len(channels)} channels")
        while True:
            async with AsyncSessionLocal() as session:
                for channel in channels:
                    count = await fetch_channel(client, session, channel, set())
                    if count:
                        logger.info(f"Stored {count} messages from {channel['display_name']}")
                await session.commit()
            await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scraper())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scraper.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/scraper.py tests/test_scraper.py
git commit -m "feat: Telethon scraper with checkpoint and flood-wait handling"
```

---

## Task 12: Processing pipeline

**Files:**
- Create: `src/processing/pipeline.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests in `tests/test_pipeline.py`**

```python
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from src.processing.pipeline import process_message, fetch_batch, mark_processed, mark_failed, should_abandon


async def test_fetch_batch_returns_list(mock_session):
    mock_row = MagicMock()
    mock_row._mapping = {
        "id": 1, "message_text": "Test message about health policy.", 
        "channel_name": "TestChannel", "channel_id": 100,
        "message_date": datetime.now(timezone.utc), "views": 100, "forwards": 5
    }
    mock_session.execute.return_value.fetchall.return_value = [mock_row]
    batch = await fetch_batch(mock_session, batch_size=20)
    assert len(batch) == 1
    assert batch[0]["channel_name"] == "TestChannel"


async def test_mark_processed_updates_db(mock_session):
    await mark_processed(mock_session, msg_id=1)
    mock_session.execute.assert_called_once()
    call_kwargs = mock_session.execute.call_args[0][1]
    assert call_kwargs["id"] == 1


async def test_mark_failed_increments_counter(mock_session):
    await mark_failed(mock_session, msg_id=1)
    mock_session.execute.assert_called_once()


async def test_should_abandon_returns_true_at_max(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (3,)
    result = await should_abandon(mock_session, msg_id=1, max_attempts=3)
    assert result is True


async def test_should_abandon_returns_false_below_max(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (1,)
    result = await should_abandon(mock_session, msg_id=1, max_attempts=3)
    assert result is False


async def test_process_message_calls_llm_and_stores_claim(
    mock_session, sample_extraction_result, sample_raw_message
):
    mock_llm = MagicMock()
    mock_llm.extract.return_value = sample_extraction_result
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [0.1] * 384

    # 6 execute calls: UPDATE text_hash, find_by_text_hash, find_similar_claim,
    # INSERT claims RETURNING id, INSERT claim_sources, mark_processed UPDATE
    responses = [
        MagicMock(fetchone=MagicMock(return_value=None)),   # UPDATE text_hash
        MagicMock(fetchone=MagicMock(return_value=None)),   # find_by_text_hash → no hit
        MagicMock(fetchone=MagicMock(return_value=None)),   # find_similar_claim → no hit
        MagicMock(fetchone=MagicMock(return_value=(1,))),   # INSERT claims RETURNING id
        MagicMock(fetchone=MagicMock(return_value=None)),   # INSERT claim_sources
        MagicMock(fetchone=MagicMock(return_value=None)),   # mark_processed UPDATE
    ]
    mock_session.execute.side_effect = responses

    await process_message(mock_session, sample_raw_message, mock_llm, mock_embedder)

    mock_llm.extract.assert_called_once()
    mock_embedder.embed.assert_called_once_with("The FDA approved a new COVID-19 vaccine")


async def test_process_message_skips_llm_on_text_hash_hit(
    mock_session, sample_extraction_result, sample_raw_message
):
    mock_llm = MagicMock()
    mock_embedder = MagicMock()

    responses = [
        MagicMock(fetchone=MagicMock(return_value=None)),   # update text_hash
        MagicMock(fetchone=MagicMock(return_value=(42,))),  # find_by_text_hash → hit
        MagicMock(fetchone=MagicMock(return_value=None)),   # copy_claims insert
        MagicMock(fetchone=MagicMock(return_value=None)),   # copy_claims update
        MagicMock(fetchone=MagicMock(return_value=None)),   # mark_processed
    ]
    mock_session.execute.side_effect = responses

    await process_message(mock_session, sample_raw_message, mock_llm, mock_embedder)

    mock_llm.extract.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pipeline.py -v
```

Expected: `ImportError` — module not yet defined.

- [ ] **Step 3: Write `src/processing/pipeline.py`**

```python
import asyncio
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import text

from src.db.connection import AsyncSessionLocal
from src.processing.claim_extractor import LLMClient, make_llm_client
from src.processing.dedup import (
    compute_text_hash, find_by_text_hash, find_similar_claim,
    merge_claim, insert_claim, copy_claims_from_message,
)
from src.processing.embeddings import Embedder
from src.processing.language import detect_language
from src.processing.urgency import check_urgency, combine_urgency

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yaml"


async def fetch_batch(session, batch_size: int = 20) -> list[dict]:
    result = await session.execute(
        text("""
        SELECT id, message_text, channel_name, channel_id, message_date, views, forwards
        FROM raw_messages
        WHERE processed = FALSE
          AND message_text IS NOT NULL
          AND length(message_text) >= 20
        ORDER BY message_date ASC
        LIMIT :limit
        """),
        {"limit": batch_size},
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def mark_processed(session, msg_id: int) -> None:
    await session.execute(
        text("UPDATE raw_messages SET processed = TRUE WHERE id = :id"),
        {"id": msg_id},
    )


async def mark_failed(session, msg_id: int) -> None:
    await session.execute(
        text("UPDATE raw_messages SET failed_attempts = failed_attempts + 1 WHERE id = :id"),
        {"id": msg_id},
    )


async def should_abandon(session, msg_id: int, max_attempts: int = 3) -> bool:
    result = await session.execute(
        text("SELECT failed_attempts FROM raw_messages WHERE id = :id"),
        {"id": msg_id},
    )
    row = result.fetchone()
    return bool(row and row[0] >= max_attempts)


async def process_message(session, message: dict, llm_client: LLMClient, embedder: Embedder) -> None:
    msg_id = message["id"]
    msg_text = message["message_text"]

    source_language = detect_language(msg_text)

    text_hash = compute_text_hash(msg_text)
    await session.execute(
        text("UPDATE raw_messages SET text_hash = :hash WHERE id = :id"),
        {"hash": text_hash, "id": msg_id},
    )

    existing_msg_id = await find_by_text_hash(session, text_hash, exclude_id=msg_id)
    if existing_msg_id:
        await copy_claims_from_message(
            session, existing_msg_id, msg_id,
            message["channel_name"], message["message_date"],
        )
        await mark_processed(session, msg_id)
        return

    rules_urgent = check_urgency(msg_text)

    extraction = llm_client.extract(
        text=msg_text,
        channel_name=message["channel_name"],
        message_date=str(message["message_date"]),
        view_count=message.get("views") or 0,
        forward_count=message.get("forwards") or 0,
    )

    urgency = combine_urgency(rules_urgent, extraction.meta.urgency_signals)

    for claim in extraction.claims:
        embedding = embedder.embed(claim.text)
        similar_id = await find_similar_claim(session, embedding)
        if similar_id:
            await merge_claim(session, similar_id, msg_id, message["channel_name"], message["message_date"])
        else:
            await insert_claim(session, claim, embedding, source_language, urgency, extraction.meta, message)

    await mark_processed(session, msg_id)


async def run_pipeline() -> None:
    load_dotenv()
    settings = yaml.safe_load(_SETTINGS_PATH.read_text())
    batch_size = settings["processor"]["batch_size"]
    poll_interval = settings["processor"]["poll_interval_seconds"]
    max_attempts = settings["processor"]["max_failed_attempts"]

    llm_client = make_llm_client()
    embedder = Embedder()

    logger.info("Processor started")

    while True:
        async with AsyncSessionLocal() as session:
            batch = await fetch_batch(session, batch_size)
            for message in batch:
                msg_id = message["id"]
                if await should_abandon(session, msg_id, max_attempts):
                    await mark_processed(session, msg_id)
                    await session.commit()
                    continue
                try:
                    await process_message(session, message, llm_client, embedder)
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    await mark_failed(session, msg_id)
                    await session.commit()
                    logger.error(f"Failed to process message {msg_id}: {e}")

        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_pipeline())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pipeline.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS. No failures.

- [ ] **Step 6: Commit**

```bash
git add src/processing/pipeline.py tests/test_pipeline.py
git commit -m "feat: processing pipeline — language, urgency, extraction, dedup orchestration"
```

---

## Task 13: End-to-end smoke test

This task is manual — it requires live Telegram credentials and a running database.

- [ ] **Step 1: Copy `.env.example` to `.env` and fill in credentials**

```bash
cp .env.example .env
```

Fill in: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `ANTHROPIC_API_KEY`.

For local development, set `DATABASE_URL` to use `localhost` instead of `db`:
```
DATABASE_URL=postgresql+asyncpg://bsbeacon:bsbeacon@localhost:5432/bsbeacon
```

- [ ] **Step 2: Update `config/channels.yaml` with at least one real public channel**

Replace the placeholder usernames with real public Telegram channel usernames (without `@`).

- [ ] **Step 3: Start the database**

```bash
docker compose up -d db
DATABASE_MIGRATION_URL=postgresql://bsbeacon:bsbeacon@localhost:5432/bsbeacon alembic upgrade head
```

- [ ] **Step 4: Run the scraper manually for one cycle**

```bash
python -m src.ingestion.scraper
```

On first run, Telethon will prompt for your phone number and a code sent via Telegram. This creates a `.telegram_session` file for future runs. Let it run for one full poll cycle (3 minutes), then stop with `Ctrl+C`.

- [ ] **Step 5: Verify messages were ingested**

```bash
docker exec -it $(docker compose ps -q db) psql -U bsbeacon -d bsbeacon \
  -c "SELECT channel_name, COUNT(*) FROM raw_messages GROUP BY channel_name;"
```

Expected: At least one row with a count > 0.

- [ ] **Step 6: Run the processor manually**

```bash
python -m src.processing.pipeline
```

Let it run through one batch (30 seconds), then stop.

- [ ] **Step 7: Verify claims were extracted**

```bash
docker exec -it $(docker compose ps -q db) psql -U bsbeacon -d bsbeacon \
  -c "SELECT category, COUNT(*), AVG(checkworthy_score) FROM claims GROUP BY category ORDER BY COUNT(*) DESC;"
```

Expected: Rows grouped by category with claim counts and average checkworthy scores.

- [ ] **Step 8: Verify dedup is working**

```bash
docker exec -it $(docker compose ps -q db) psql -U bsbeacon -d bsbeacon \
  -c "SELECT MAX(occurrence_count), AVG(occurrence_count) FROM claims;"
```

If any `occurrence_count > 1`, semantic dedup is merging repeated claims correctly.

- [ ] **Step 9: Run both services together**

```bash
docker compose up
```

Expected: All three services (`db`, `scraper`, `processor`) start and log activity without crashing.

- [ ] **Step 10: Final commit**

```bash
git add .env.example config/channels.yaml
git commit -m "feat: phase 2 complete — scraper + processor pipeline end-to-end"
```
