# BSBeacon — Telegram Misinformation Detection Pipeline

## Project overview

BSBeacon is a real-time data pipeline that ingests messages from Telegram channels, extracts discrete claims using NLP, classifies them by credibility and virality, and surfaces high-priority misinformation for human fact-checkers. The system runs 24/7, polling every 3 minutes, and outputs to a searchable claims database, a live dashboard, a fact-checker routing queue, and webhook alerts.

The architecture follows the same four-stage pattern as proven real-time intelligence pipelines: **Ingest → Process → Classify → Output**.

---

## Phased roadmap

### Phase 1 — Architecture and design (this document)

Deliverable: Complete system design, data models, tech stack decisions, and implementation plan.

### Phase 2 — Working prototype

Deliverable: Telegram ingestion + basic claim extraction running locally. Covers Stage 1 and partial Stage 2.

### Phase 3 — Full pipeline with dashboard

Deliverable: All four stages operational with a React dashboard, fact-checker queue, and webhook alerts.

---

## Stage 1 — Ingest

### Purpose

Poll a curated list of public Telegram channels every 3 minutes. Capture raw messages with full metadata and store them for downstream processing.

### Components

**Telethon client** — Python async client using the Telegram MTProto API. Requires a personal `api_id` and `api_hash` from https://my.telegram.org. Free to use, but subject to rate limits (Telegram may impose a 24-hour soft ban if requests are too aggressive).

**Channel list** — A configuration file or database table of target channels. Start with 10–20 channels known for spreading misinformation in your domain of interest (health, politics, crypto, etc.). Channels can be added or removed without restarting the pipeline.

**Raw message store** — PostgreSQL table storing every message with full metadata.

### Data model: `raw_messages`

```sql
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
    media_type      TEXT,               -- 'photo', 'video', 'document', NULL
    media_file_id   TEXT,
    forward_from    TEXT,               -- original channel if forwarded
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    processed       BOOLEAN DEFAULT FALSE,
    UNIQUE(channel_id, telegram_msg_id)
);

CREATE INDEX idx_raw_messages_date ON raw_messages(message_date DESC);
CREATE INDEX idx_raw_messages_unprocessed ON raw_messages(processed) WHERE processed = FALSE;
```

### Implementation notes

- Use `telethon.TelegramClient` with `client.iter_messages()` to fetch new messages since the last checkpoint.
- Store a `last_message_id` per channel to avoid re-fetching.
- Handle media downloads separately — store `file_id` references, download on demand.
- Run as an async loop with `asyncio.sleep(180)` between cycles.
- Log all errors and rate-limit events. If soft-banned, back off exponentially.

### Key file: `src/ingestion/scraper.py`

```
- TelegramClient setup with api_id, api_hash, session file
- load_channel_list() from config/channels.yaml
- fetch_new_messages(channel, since_id) → list of raw messages
- store_messages(messages) → batch insert to PostgreSQL
- main loop: for each channel, fetch + store, sleep 180s
```

---

## Stage 2 — Process

### Purpose

Transform raw Telegram messages into structured, deduplicated claims with extracted entities and metadata. This is the intelligence layer.

### Components

**Language detection** — `langdetect` detects the source language locally before any LLM call. Fast, free, and deterministic. Result stored as `source_language`. No pre-translation — Claude processes multilingual input natively and confirms language in the extraction response.

**Claim extractor** — The core NLP component. Uses an LLM (Claude API or a local model) with a rich structured output schema (see `docs/superpowers/specs/CLAIM_EXTRACTION_PROMPT.md`). Returns per-claim entities, category, temporality, checkworthy score, and source attribution, plus message-level metadata (message type, language, urgency signals). A single message may yield zero claims (chatter) or several. `checkworthy_score` is advisory — non-deterministic across calls; use combined with virality score (Phase 3) for routing decisions.

**Urgency detection** — Rules-based complement to the LLM's `urgency_signals` flag: caps ratio > 0.4, keywords ("BREAKING", "URGENT", "share before deleted"), countdown language, excessive punctuation. Result is OR'd with the LLM flag. Deterministic, free, catches obvious cases without spending tokens.

**Text-hash dedup** — Before calling the LLM, compute a SHA-256 hash of the normalized message text. If already processed (common with viral forwards), reuse the prior extraction and skip the API call entirely.

**Semantic deduplication** — Compute sentence embeddings (using `sentence-transformers`) for each extracted claim. Compare against existing claims using cosine similarity. If similarity > 0.92, merge as a duplicate and increment the occurrence counter.

**Deduplication** — Compute sentence embeddings (using `sentence-transformers`) for each claim. Compare against existing claims using cosine similarity. If similarity > 0.92, merge as a duplicate and increment the occurrence counter. This prevents the same claim from being counted hundreds of times across channels.

### Data model: `claims`

```sql
CREATE TABLE claims (
    id                  BIGSERIAL PRIMARY KEY,
    claim_text          TEXT NOT NULL,
    source_language     TEXT,            -- ISO 639-1 code from LLM meta
    first_seen_at       TIMESTAMPTZ NOT NULL,
    last_seen_at        TIMESTAMPTZ NOT NULL,
    occurrence_count    INTEGER DEFAULT 1,
    entities_json       JSONB,           -- {"people": [], "organizations": [], "locations": [], "quantities": []}
    category            TEXT,            -- health | politics | finance | military | environment | science | crime | conspiracy | other
    temporal            TEXT,            -- past | present | future | unspecified
    checkworthy_score   FLOAT,           -- LLM-estimated 0.0–1.0; how important to fact-check
    source_attribution  TEXT,            -- who/what the message attributes this claim to, or NULL
    urgency_signals     BOOLEAN,         -- true if the source message had panic/urgency language
    message_type        TEXT,            -- news_share | opinion_rant | forwarded_alert | propaganda | etc.
    embedding           VECTOR(384),     -- pgvector for semantic dedup
    credibility_score   FLOAT,           -- set in Stage 3 by classifier
    virality_score      FLOAT,           -- set in Stage 3
    status              TEXT DEFAULT 'unreviewed',  -- unreviewed, queued, verified, debunked
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_claims_embedding ON claims USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_claims_virality ON claims(virality_score DESC NULLS LAST);
CREATE INDEX idx_claims_last_seen ON claims(last_seen_at DESC);
CREATE INDEX idx_claims_created ON claims(created_at DESC);
```

### Data model: `claim_sources` (join table)

```sql
CREATE TABLE claim_sources (
    id              BIGSERIAL PRIMARY KEY,
    claim_id        BIGINT REFERENCES claims(id),
    raw_message_id  BIGINT REFERENCES raw_messages(id),
    channel_name    TEXT NOT NULL,
    message_date    TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_claim_sources_claim ON claim_sources(claim_id);
```

### Claim extraction prompt

See `docs/superpowers/specs/CLAIM_EXTRACTION_PROMPT.md` for the full system prompt, output schema, example input/output pairs, Pydantic models, and cost estimates. Key characteristics:

- Returns structured JSON with per-claim `entities`, `category`, `temporal`, `checkworthy_score`, and `source_attribution`
- Returns message-level `meta`: `message_type`, `language_detected`, `urgency_signals`
- Claude handles multilingual input natively — `language_detected` in the response identifies the source language
- If zero verifiable claims exist, returns `{"claims": [], "meta": {...}}`

### Processing pipeline flow

```
raw_message
  → language_detect (langdetect — local, deterministic)
  → text_hash_dedup_check (skip LLM if already processed)
  → rules_urgency_check (regex — fast, deterministic)
  → claim_extract (LLMClient → ExtractionResult)
  → urgency = rules_result OR llm_meta.urgency_signals
  → per claim: compute_embedding → semantic_dedup_check
  → insert_or_merge_claim → link_claim_source → mark_processed
```

### Key files

```
src/processing/
├── pipeline.py          # orchestrates the full processing flow
├── language.py          # langdetect-based language detection (local, deterministic)
├── claim_extractor.py   # LLM-based extraction returning rich ExtractionResult
├── urgency.py           # rules-based urgency detection (OR'd with LLM flag)
├── schemas.py           # Pydantic models for ExtractionResult
├── dedup.py             # text-hash dedup + embedding similarity + merge logic
└── embeddings.py        # sentence-transformers wrapper
```

### Python integration

```python
import json
import anthropic
from src.processing.schemas import ExtractionResult

SYSTEM_PROMPT = """..."""  # full prompt from docs/superpowers/specs/CLAIM_EXTRACTION_PROMPT.md

def extract_claims(message_text: str, channel_name: str, message_date: str,
                   view_count: int = 0, forward_count: int = 0) -> ExtractionResult:
    client = anthropic.Anthropic()

    user_prompt = f"""Analyze this Telegram message and extract all claims:

Channel: {channel_name}
Date: {message_date}
Views: {view_count}
Forwards: {forward_count}

Message:
---
{message_text}
---"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw_text = response.content[0].text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rstrip("```").strip()

    try:
        return ExtractionResult.model_validate(json.loads(raw_text))
    except Exception:
        return ExtractionResult(claims=[], meta={"message_type": "unclear", ...})
```

### Pydantic schemas (`src/processing/schemas.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class ClaimCategory(str, Enum):
    health = "health"; politics = "politics"; finance = "finance"
    technology = "technology"; military = "military"; environment = "environment"
    science = "science"; crime = "crime"; conspiracy = "conspiracy"; other = "other"

class Temporality(str, Enum):
    past = "past"; present = "present"; future = "future"; unspecified = "unspecified"

class MessageType(str, Enum):
    news_share = "news_share"; opinion_rant = "opinion_rant"
    forwarded_alert = "forwarded_alert"; question = "question"
    conversation = "conversation"; propaganda = "propaganda"
    satire = "satire"; unclear = "unclear"

class ClaimEntities(BaseModel):
    people: list[str] = []; organizations: list[str] = []
    locations: list[str] = []; quantities: list[str] = []

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

---

## Stage 3 — Classify

### Purpose

Score each claim on two axes: how fast it is spreading (virality) and how likely it is to be false (credibility). Cross-reference against known fact-check databases.

### Components

**Virality scorer** — Computes a spread velocity metric based on: occurrence count, number of unique channels, forward count, view count, and time since first appearance. Claims appearing in 5+ channels within 1 hour get a high virality score.

```python
def compute_virality(claim):
    channel_count = count_unique_channels(claim.id)
    total_views = sum_views_across_sources(claim.id)
    hours_alive = (now() - claim.first_seen_at).total_hours()
    spread_rate = channel_count / max(hours_alive, 0.1)

    score = (
        0.4 * normalize(spread_rate) +
        0.3 * normalize(channel_count) +
        0.2 * normalize(total_views) +
        0.1 * normalize(claim.occurrence_count)
    )
    return min(score, 1.0)
```

**Credibility classifier** — A fine-tuned transformer model (start with `distilbert-base-uncased` for speed, upgrade to `roberta-base` for accuracy). Training data sources:

- LIAR dataset (12,800 labeled statements from PolitiFact)
- FakeNewsNet dataset
- FEVER (Fact Extraction and Verification) dataset
- Custom labeled data from your own pipeline over time

The classifier outputs a probability between 0 (likely false) and 1 (likely true).

**Fact-check cross-reference** — Query the ClaimBuster API and Google Fact Check Tools API to check if the claim (or a semantically similar one) has already been fact-checked. If a match is found, auto-populate the credibility score and link to the existing fact-check.

### Classification logic

```python
def classify_claim(claim):
    virality = compute_virality(claim)
    credibility = credibility_model.predict(claim.claim_text)
    existing_check = query_factcheck_apis(claim.claim_text)

    if existing_check:
        credibility = existing_check.rating
        claim.status = 'verified' if credibility > 0.7 else 'debunked'

    claim.virality_score = virality
    claim.credibility_score = credibility

    # High virality + low credibility = priority for fact-checkers
    if virality > 0.7 and credibility < 0.3:
        enqueue_for_factcheck(claim, priority='high')
    elif virality > 0.5 and credibility < 0.5:
        enqueue_for_factcheck(claim, priority='medium')
```

### Key files

```
src/classification/
├── virality.py          # spread velocity computation
├── credibility.py       # transformer-based classifier
├── factcheck_api.py     # ClaimBuster + Google Fact Check integration
└── classifier.py        # orchestrates scoring + queue routing
```

---

## Stage 4 — Output

### Purpose

Serve classified claims through multiple output channels: a searchable database, a real-time dashboard, a fact-checker priority queue, and webhook alerts.

### Components

**Claims API (FastAPI)** — RESTful API serving the claims database. Supports full-text search, filtering by topic/status/score, and pagination.

```
GET  /api/claims                    # list with filters
GET  /api/claims/{id}               # single claim with sources
GET  /api/claims/trending           # top virality last 24h
GET  /api/claims/queue              # fact-check queue sorted by priority
POST /api/claims/{id}/review        # mark as verified/debunked
GET  /api/stats                     # pipeline health metrics
GET  /api/narratives                # clustered claim groups
```

**Dashboard (React)** — Real-time web dashboard showing:

- Live feed of new claims as they arrive
- Trending narratives (clusters of related claims)
- Virality vs. credibility scatter plot
- Channel activity heatmap
- Fact-check queue with claim cards
- Pipeline health metrics (ingestion rate, processing lag, queue depth)

**Fact-check queue** — Priority-sorted queue where high-virality, low-credibility claims surface first. Fact-checkers can mark claims as verified, debunked, or needs-more-info. Verdicts feed back into the credibility model as training data.

**Webhook alerts** — Configurable alerts triggered when a claim exceeds thresholds. Example triggers:

- Any claim with virality > 0.8 and credibility < 0.2
- A known debunked narrative resurfaces
- A new claim appears in 10+ channels within 30 minutes

Alert destinations: Slack, Discord, email, or any webhook URL.

### Key files

```
src/api/
├── main.py              # FastAPI app
├── routes/
│   ├── claims.py        # claim CRUD + search
│   ├── queue.py         # fact-check queue endpoints
│   └── stats.py         # pipeline metrics
└── models.py            # Pydantic response schemas

dashboard/
├── src/
│   ├── App.jsx
│   ├── components/
│   │   ├── ClaimFeed.jsx
│   │   ├── TrendingNarratives.jsx
│   │   ├── ScatterPlot.jsx
│   │   ├── ChannelHeatmap.jsx
│   │   └── FactCheckQueue.jsx
│   └── hooks/
│       └── useWebSocket.js    # real-time updates
└── package.json

src/alerts/
├── webhook.py           # generic webhook dispatcher
├── slack.py             # Slack-specific formatting
└── triggers.py          # threshold-based alert rules
```

---

## Tech stack summary

| Layer | Technology | Why |
|---|---|---|
| Ingestion | Python, Telethon, asyncio | Free Telegram API, async for performance |
| Message queue | Redis (optional) | Decouple ingestion from processing |
| Processing | spaCy, sentence-transformers, Claude API | Best-in-class NLP, flexible claim extraction |
| Classification | HuggingFace transformers (DistilBERT/RoBERTa) | Fine-tunable, fast inference |
| Database | PostgreSQL + pgvector | Relational + vector similarity search |
| API | FastAPI | Async, auto-docs, Pydantic validation |
| Dashboard | React, Recharts, WebSocket | Real-time, component-based |
| Alerts | Webhook dispatcher | Flexible, works with Slack/Discord/email |
| Orchestration | APScheduler or Dagster | Job scheduling and monitoring |
| Deployment | Docker Compose | Single-command local dev, easy to deploy |

---

## Project structure

```
bsbeacon/
├── PLAN.md
├── README.md
├── docker-compose.yml
├── .env.example                  # API keys, DB credentials
├── config/
│   ├── channels.yaml             # target Telegram channels
│   └── alerts.yaml               # webhook URLs + thresholds
├── src/
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── scraper.py            # Telethon polling loop
│   │   └── checkpoint.py         # track last_message_id per channel
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── pipeline.py           # orchestrate full processing flow
│   │   ├── language.py           # langdetect + translation
│   │   ├── claim_extractor.py    # LLM claim extraction
│   │   ├── entity_extractor.py   # spaCy NER + topics
│   │   ├── dedup.py              # embedding similarity
│   │   └── embeddings.py         # sentence-transformers
│   ├── classification/
│   │   ├── __init__.py
│   │   ├── virality.py           # spread velocity
│   │   ├── credibility.py        # transformer classifier
│   │   ├── factcheck_api.py      # external API integration
│   │   └── classifier.py         # orchestrate scoring
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app
│   │   ├── routes/
│   │   │   ├── claims.py
│   │   │   ├── queue.py
│   │   │   └── stats.py
│   │   └── models.py             # Pydantic schemas
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── webhook.py
│   │   ├── slack.py
│   │   └── triggers.py
│   └── db/
│       ├── __init__.py
│       ├── connection.py         # SQLAlchemy engine
│       └── migrations/           # Alembic migrations
├── dashboard/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx
│   │   └── components/
├── models/
│   ├── credibility/              # fine-tuned model weights
│   └── training/                 # training scripts + data
├── tests/
│   ├── test_scraper.py
│   ├── test_claim_extractor.py
│   ├── test_dedup.py
│   └── test_classifier.py
├── scripts/
│   ├── seed_channels.py          # populate initial channel list
│   ├── backfill.py               # process historical messages
│   └── train_credibility.py      # fine-tune credibility model
└── requirements.txt
```

---

## Implementation order (for Claude Code)

### Step 1 — Foundation (do this first)

```bash
mkdir bsbeacon && cd bsbeacon
python -m venv venv && source venv/bin/activate
pip install telethon asyncpg sqlalchemy alembic python-dotenv pyyaml
```

Set up `.env` with Telegram credentials, PostgreSQL connection string. Create the database schema with Alembic migrations. Write `config/channels.yaml` with 5–10 starter channels.

### Step 2 — Ingestion loop

Build `src/ingestion/scraper.py`. Get messages flowing into PostgreSQL. Verify with a simple query: `SELECT COUNT(*) FROM raw_messages`.

### Step 3 — Claim extraction

Build `src/processing/claim_extractor.py` using the Claude API. Process unprocessed messages, extract claims, store in the `claims` table. This is the hardest part — iterate on the prompt until extraction quality is high.

### Step 4 — Deduplication

Add text-hash dedup (pre-LLM) and sentence-transformer semantic dedup (post-extraction). Entities come from the LLM extraction result — no spaCy needed in Phase 2. Expect 60–80% of raw claims to be duplicates.

### Step 5 — Classification

Build the virality scorer (pure math, no ML needed). Start the credibility classifier with a pre-trained model before fine-tuning.

### Step 6 — API

Build the FastAPI layer. Test all endpoints. This unlocks the dashboard.

### Step 7 — Dashboard

Build the React dashboard. Start with the claim feed and trending view, then add the scatter plot and queue.

### Step 8 — Alerts

Add webhook alerts. Connect to Slack or Discord.

---

## External APIs and credentials needed

| Service | What for | Cost |
|---|---|---|
| Telegram API | Message ingestion | Free (api_id + api_hash) |
| Anthropic Claude API | Claim extraction | Pay per token |
| ClaimBuster API | Fact-check cross-reference | Free tier available |
| Google Fact Check API | Additional fact-check matching | Free |
| HuggingFace | Pre-trained models | Free (local inference) |

---

## Key metrics to track

- **Ingestion rate**: messages per minute across all channels
- **Processing lag**: time between message arrival and claim extraction
- **Claim yield**: percentage of messages that produce at least one claim
- **Dedup ratio**: percentage of claims merged as duplicates
- **Queue depth**: number of claims awaiting fact-checker review
- **Alert frequency**: alerts triggered per hour
- **Classifier accuracy**: precision/recall on held-out test set (track over time)

---

## Risks and mitigations

**Telegram rate limits** — The API soft-bans aggressive scraping. Mitigation: respect rate limits, use exponential backoff, keep polling interval at 3+ minutes.

**LLM cost for claim extraction** — Processing thousands of messages per day through Claude adds up. Estimated cost using Claude Sonnet (~$3/M input, ~$15/M output tokens, ~500 input / ~400 output per message):

| Volume | Daily cost |
|---|---|
| 1,000 msgs/day | ~$7.50 |
| 5,000 msgs/day | ~$37.50 |
| 10,000 msgs/day | ~$75.00 |

Mitigations: (1) pre-filter short, media-only, and known bot messages before calling the API; (2) text-hash dedup — skip the LLM entirely for forwarded messages with identical text already processed; (3) swap to a local model (Mistral, Llama) once ready.

**Classification accuracy** — The credibility model will have false positives and negatives. Mitigation: always route to human fact-checkers for final verdict. Use fact-checker feedback as training data to improve the model over time.

**Multilingual content** — Telegram channels operate in many languages. Claude handles multilingual input natively and returns `language_detected` in the extraction response — no pre-translation step needed. The source language is stored for reference.

**Legal and ethical considerations** — Only monitor public channels. Do not scrape private groups or personal messages. Comply with GDPR if operating in the EU. Be transparent about methodology if publishing findings.
