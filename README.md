# BSBeacon

A real-time misinformation detection pipeline that monitors Telegram channels, extracts discrete factual claims using Claude AI, deduplicates them semantically, and surfaces high-priority claims for human fact-checkers.

## How it works

```
Telegram channels
      │
      ▼
┌─────────────┐
│   Scraper   │  Polls channels every 3 minutes via Telethon, stores raw
│             │  messages in PostgreSQL with per-channel checkpointing
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Processor  │  For each unprocessed message:
│             │  1. Detect language, compute text hash
│             │  2. Text-hash dedup — exact/near-exact reposts skip LLM
│             │  3. Claude extracts discrete factual claims as JSON
│             │  4. Urgency signals detected (rules + LLM)
│             │  5. Sentence-transformer embeddings computed per claim
│             │  6. Semantic dedup — cosine similarity > 0.85 → merge
│             │  7. New claims inserted; duplicates increment occurrence count
└─────────────┘
       │
       ▼
  PostgreSQL
  (claims, sources, raw_messages)
```

## Database schema

| Table | Purpose |
|---|---|
| `raw_messages` | Every Telegram message as ingested, with processing state |
| `claims` | Deduplicated factual claims with embeddings and metadata |
| `claim_sources` | Many-to-many: which messages contributed to each claim |
| `checkpoints` | Last-seen message ID per channel for incremental fetching |

Each claim carries: `claim_text`, `category`, `temporal`, `checkworthy_score`, `source_attribution`, `urgency_signals`, `occurrence_count`, `embedding` (384-dim vector).

## Claim extraction

Claims are extracted by Claude using a structured system prompt that instructs the model to:
- Return only discrete, verifiable factual statements (not opinions, calls to action, or vague assertions)
- Split compound statements into separate claims
- Score each claim for check-worthiness (0.0–1.0)
- Classify by category: `health | politics | finance | technology | military | environment | science | crime | conspiracy | other`
- Detect urgency signals (panic language, "BREAKING", excessive caps)

Unknown categories returned by the LLM are coerced to `other` rather than failing.

## Deduplication

Two-stage dedup prevents the same information being counted multiple times as it spreads across channels:

1. **Text hash** — SHA-256 of lowercased, whitespace-normalized message text. Exact reposts bypass the LLM entirely and copy claim sources from the original.
2. **Semantic similarity** — sentence-transformers `all-MiniLM-L6-v2` (384-dim, L2-normalized) with cosine similarity threshold of 0.85 via pgvector. Claims above the threshold merge into the existing record and increment `occurrence_count`.

## Setup

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL with pgvector)
- A Telegram account with API credentials — get them at [my.telegram.org](https://my.telegram.org)
- An Anthropic API key

### Install

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
ANTHROPIC_API_KEY=sk-ant-...
```

### Database

```bash
docker compose up -d db
alembic upgrade head
```

### Channels

Edit `config/channels.yaml` to add the public Telegram channels you want to monitor:

```yaml
channels:
  news:
    - username: bbcnews
      display_name: "BBC News"
  geopolitics:
    - username: somegeopoliticschannel
      display_name: "Geopolitics Watch"
```

`username` is the part after `t.me/` in the channel's public link.

## Running

### Development (individual services)

```bash
# First run — Telegram will prompt for your phone number and a verification code
python -m src.ingestion.scraper

# In a second terminal
python -m src.processing.pipeline
```

After the first successful scraper run, a session file is saved to `.telegram_session/` and subsequent runs connect without prompting.

### Docker (all services)

```bash
docker compose up
```

Services: `bsbeacon-db`, `bsbeacon-scraper`, `bsbeacon-processor`.

Logs:
```bash
docker logs -f bsbeacon-scraper
docker logs -f bsbeacon-processor
```

## Configuration

`config/settings.yaml` controls runtime behaviour:

| Key | Default | Description |
|---|---|---|
| `scraper.poll_interval_seconds` | `180` | How often to check each channel for new messages |
| `scraper.min_message_length` | `20` | Messages shorter than this are skipped |
| `processor.poll_interval_seconds` | `30` | How often to check for unprocessed messages |
| `processor.batch_size` | `20` | Messages processed per cycle |
| `processor.max_failed_attempts` | `3` | Failed attempts before a message is abandoned |
| `urgency.caps_ratio_threshold` | `0.4` | Fraction of ALL-CAPS words that triggers urgency |
| `urgency.min_exclamation_marks` | `3` | Exclamation mark count that triggers urgency |

The semantic dedup threshold (default `0.85`) is set in `src/processing/dedup.py`.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_API_ID` | Yes | From my.telegram.org |
| `TELEGRAM_API_HASH` | Yes | From my.telegram.org |
| `TELEGRAM_SESSION_NAME` | No | Path for Telethon session file (default: `bsbeacon`) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `ANTHROPIC_MODEL` | No | Model to use (default: `claude-sonnet-4-6`) |
| `DATABASE_URL` | Yes | asyncpg connection string |
| `DATABASE_MIGRATION_URL` | Yes | psycopg2 connection string (for Alembic) |
| `LLM_PROVIDER` | No | `claude` (default, only option currently) |

## Tests

```bash
pytest tests/                        # all tests
pytest tests/test_claim_extractor.py # single file
pytest -k "test_dedup"               # by name
```

62 tests, no external dependencies required (LLM and DB calls are mocked).

## Project structure

```
src/
  ingestion/
    scraper.py       — Telethon polling loop, message storage, checkpointing
    checkpoint.py    — Per-channel last-seen message ID (PostgreSQL-backed)
  processing/
    pipeline.py      — Main processing loop: fetch → extract → dedup → store
    claim_extractor.py — Claude API client and LLMClient protocol
    schemas.py       — Pydantic models for claims and extraction results
    dedup.py         — Text-hash and semantic dedup, claim insert/merge
    embeddings.py    — Sentence-transformer singleton and cosine similarity
    language.py      — Language detection (langdetect)
    urgency.py       — Rule-based urgency detection
  db/
    connection.py    — SQLAlchemy async engine and session factory
config/
  channels.yaml      — Monitored Telegram channels
  settings.yaml      — Runtime configuration
  system_prompt.txt  — LLM extraction instructions
migrations/
  versions/001_initial_schema.py — Full schema (pgvector extension, all tables)
```

## Roadmap

- **Phase 3** — FastAPI query layer, React dashboard (claim feed, trending, scatter plot), Slack/Discord webhook alerts
- **Phase 4** — Credibility classifier (DistilBERT fine-tuned on fact-checker verdicts), ClaimBuster/Google Fact Check API cross-reference, virality scoring
