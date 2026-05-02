# BSBeacon — Phase 2 Design Spec

**Date:** 2026-05-02
**Scope:** Phase 2 working prototype — Telegram ingestion + claim extraction running locally
**Out of scope:** Classification (Stage 3), API, dashboard, alerts (Phase 3)

---

## Overview

Two decoupled Python processes share a PostgreSQL database. The scraper ingests raw Telegram messages; the processor extracts claims from unprocessed messages using the Claude API. Each process runs and restarts independently. The `processed` flag on `raw_messages` is the handoff mechanism between them.

---

## Architecture

```
┌─────────────────┐        ┌─────────────────────────────────────┐
│  scraper.py     │──────▶ │  PostgreSQL                         │
│  (polls every   │        │  raw_messages (processed=FALSE/TRUE) │
│   3 minutes)    │        │  claims                             │
└─────────────────┘        │  claim_sources                      │
                           │  checkpoints                        │
                           └──────────────┬──────────────────────┘
┌─────────────────┐                       │
│  pipeline.py    │◀──────────────────────┘
│  (polls every   │
│   30 seconds)   │
└─────────────────┘
```

### Docker Compose services

| Service | Description |
|---|---|
| `db` | PostgreSQL 16 with pgvector extension |
| `scraper` | runs `src/ingestion/scraper.py` |
| `processor` | runs `src/processing/pipeline.py` |

---

## Configuration

- **`.env`** — credentials: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `ANTHROPIC_API_KEY`, `DATABASE_URL`
- **`config/channels.yaml`** — channel list organized by domain (health/vaccine, politics, global affairs). Editable without restarting services.
- **`config/settings.yaml`** — tunable parameters: poll interval (default 180s), processor batch size (default 20), dedup similarity threshold (default 0.92)

---

## Database schema

Four tables managed by Alembic migrations.

**`raw_messages`** — as defined in PLAN.md, with `processed BOOLEAN DEFAULT FALSE` and `failed_attempts INTEGER DEFAULT 0` added for retry tracking.

**`claims`** — as defined in PLAN.md. `credibility_score` and `virality_score` are NULL in Phase 2 (set in Phase 3). Includes `idx_claims_last_seen` and `idx_claims_created` indexes for time-range queries. A composite `(last_seen_at, virality_score)` index is deferred to Phase 3 when the trending API query shape is known.

**`claim_sources`** — join table linking claims to the raw messages they were extracted from.

**`checkpoints`** — tracks `last_message_id` per channel so the scraper resumes correctly after restart.

```sql
CREATE TABLE checkpoints (
    channel_id   BIGINT PRIMARY KEY,
    channel_name TEXT NOT NULL,
    last_msg_id  BIGINT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Stage 1 — Ingestion (`src/ingestion/`)

### Files

- **`scraper.py`** — async main loop. Loads channel list from `config/channels.yaml`, iterates each channel, calls `fetch_new_messages()`, batch-inserts to `raw_messages`, updates checkpoint, sleeps 180s.
- **`checkpoint.py`** — reads/writes the `checkpoints` table. `get_last_id(channel_id)` and `update_last_id(channel_id, msg_id)`.

### Message filtering at ingest

Skip messages that are:
- Text is NULL or under 20 characters
- Media-only (no text content)
- Forwarded from a channel already in our monitored list (dedup at source)

### Rate limiting

On `FloodWaitError`: back off for the duration Telegram specifies, log the event, continue with other channels. On other errors: log and skip that channel for the current cycle.

---

## Stage 2 — Processing (`src/processing/`)

### Files

- **`pipeline.py`** — polling loop every 30s. Fetches batches of 20 unprocessed `raw_messages`, runs each through the pipeline, commits. Each failure increments `failed_attempts`. After 3 failures, marks `processed=TRUE` to stop retrying — these rows are identifiable by `WHERE processed=TRUE AND failed_attempts >= 3`.
- **`language.py`** — detects language using `langdetect` (local, free, deterministic). Stores the ISO 639-1 code as `source_language`. No translation — Claude processes multilingual input natively and confirms language in the extraction response `meta.language_detected`.
- **`claim_extractor.py`** — sends message text to the LLM via `LLMClient`, returns a validated `ExtractionResult`. On malformed/empty response: logs and raises so the pipeline marks the attempt. `checkworthy_score` is treated as an advisory signal, not a routing gate — it is non-deterministic and should be combined with virality score (Phase 3) for prioritization decisions.
- **`urgency.py`** — rules-based urgency detection as a fast, deterministic complement to the LLM's `urgency_signals` flag. Checks: caps ratio > 0.4, keywords ("BREAKING", "URGENT", "share before deleted", "they don't want you to know"), countdown language, excessive punctuation. Result is OR'd with the LLM flag — either source can set `urgency_signals=TRUE`.
- **`schemas.py`** — Pydantic models for `ExtractionResult`, `ExtractedClaim`, `ExtractionMeta` (as defined in PLAN.md Stage 2).
- **`dedup.py`** — two-layer deduplication: (1) text-hash check (pre-LLM) — SHA-256 of normalized message text, reuses prior extraction if already processed; (2) semantic dedup (post-extraction) — `sentence-transformers` all-MiniLM-L6-v2 (384-dim) embeddings, pgvector `<=>` cosine distance, threshold 0.92.

### LLM abstraction

```python
class LLMClient(Protocol):
    def extract(self, text: str, channel_name: str,
                message_date: str, view_count: int,
                forward_count: int) -> ExtractionResult: ...
```

`ClaudeClient` implements this now. A future `OllamaClient` will implement the same interface. `pipeline.py` receives an `LLMClient` instance — it never imports the Anthropic SDK directly. The active client is selected by `LLM_PROVIDER` in `.env` (default: `claude`).

### Claim extraction prompt

As specified in `docs/superpowers/specs/CLAIM_EXTRACTION_PROMPT.md`. Pre-filters before calling the LLM: skip pure-URL messages and emoji-heavy messages with no prose content.

---

## Processing pipeline flow

```
raw_message
  → language_detect (langdetect — fast, local)
  → text_hash_dedup_check (skip LLM if already processed)
  → rules_urgency_check (regex — fast, deterministic)
  → claim_extract (LLMClient → ExtractionResult)
  → urgency = rules_result OR llm_meta.urgency_signals
  → for each claim:
      → compute_embedding (sentence-transformers)
      → semantic_dedup_check (pgvector cosine similarity)
      → insert_new_claim OR merge_with_existing
      → insert_claim_source
  → mark raw_message processed=TRUE
```

---

## Testing

| File | Coverage |
|---|---|
| `tests/test_claim_extractor.py` | Valid message → `ExtractionResult` with claims; opinion-only → empty claims list; multiple claims extracted and validated via Pydantic; malformed LLM response handled gracefully |
| `tests/test_dedup.py` | Text-hash hit skips LLM call; identical claim merges; paraphrase above 0.92 merges; different claim inserts new |
| `tests/test_urgency.py` | ALL CAPS message flagged; "BREAKING" keyword flagged; calm message not flagged; LLM flag OR'd with rules result |
| `tests/test_scraper.py` | New messages fetched and stored; checkpoint advances; `FloodWaitError` triggers backoff without crash |

`LLMClient` is mocked in all tests — no live Claude API calls in the test suite. Integration smoke tests (live Telegram + Claude API) are manual.

---

## Deliverable

Phase 2 is complete when:
- `docker compose up` starts all three services cleanly
- Scraper populates `raw_messages` from at least one live Telegram channel
- Processor extracts claims and populates the `claims` table
- Duplicate claims are merged (not inserted as new rows)
- All unit tests pass
