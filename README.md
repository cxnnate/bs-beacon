# BSBeacon

A real-time misinformation detection pipeline that monitors Telegram channels, extracts discrete factual claims using Claude, deduplicates them semantically with an NLI guard, and surfaces high-priority claims to human fact-checkers through a live dashboard.

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
│             │  3. Claude extracts claims via forced tool use (schema-enforced)
│             │  4. Urgency signals detected (rules + LLM)
│             │  5. Multilingual embeddings computed per claim (768-dim)
│             │  6. Vector search finds candidates → NLI guard decides:
│             │     entailment → merge · contradiction → link · neutral → new
└──────┬──────┘
       │
       ▼
  PostgreSQL (claims, claim_relations, sources, raw_messages)
       │
       ├──────────────► FastAPI (REST + WebSocket)
       │                      │
       │                      ▼
       │               React dashboard
       └──────────────► ntfy.sh alerts on urgent claims
```

## Services

Five Docker services (`docker compose up`):

| Service | Purpose |
|---|---|
| `bsbeacon-db` | PostgreSQL 16 + pgvector |
| `bsbeacon-scraper` | Telethon ingestion loop |
| `bsbeacon-processor` | Extraction → dedup → persist pipeline |
| `bsbeacon-api` | FastAPI on port 8000 (proxied by the dashboard's nginx) |
| `bsbeacon-dashboard` | React app served by nginx on port 80 |

## Dashboard

Six views, real-time via WebSocket:

- **Live Feed** — new claims as they arrive, grouped by review status, filterable by channel and topic
- **Trending** — most-seen claims over the trailing window
- **Analysis** — checkworthiness vs. virality scatter (Recharts)
- **Queue** — fact-check queue sorted by urgency + checkworthiness, with verdict buttons (✓ Verified / ✕ Debunked / ? Needs info)
- **Network** — force-directed graph of claim relations: red dashed edges are contradictions, gray edges are paraphrases, node size = times seen, click any node to inspect and apply a verdict
- **Logs** — live scraper/processor container logs

Claims that have been merged from multiple sightings show a **"seen ×N"** badge.

## Claim extraction

Claims are extracted by Claude through a **forced tool call** (`record_extracted_claims`), so the API enforces the output schema — no JSON parsing or markdown-fence stripping. The extraction:

- Returns only discrete, verifiable factual statements (not opinions, calls to action, or vague assertions)
- Splits compound statements into separate claims
- Scores each claim for check-worthiness (0.0–1.0)
- Classifies by **topic**: `health | politics | finance | technology | military | environment | science | crime | other`
- Detects **urgency signals** (panic language, "BREAKING", excessive caps)
- Detects **conspiratorial framing** as an orthogonal boolean — deliberately *not* a topic, so the extractor never pre-judges veracity

Unknown topics returned by the LLM are coerced to `other` rather than failing.

## Deduplication

Two-stage dedup with an NLI guard prevents the same information being counted multiple times as it spreads — without ever merging a claim with its own negation:

1. **Text hash** — SHA-256 of lowercased, whitespace-normalized message text. Exact reposts bypass the LLM entirely and copy claim sources from the original.
2. **Semantic + NLI** — `intfloat/multilingual-e5-base` embeddings (768-dim, cross-lingual: Russian/Spanish/English variants of the same claim land together) retrieve candidates above `0.88` cosine via pgvector. Each candidate then passes through a local NLI cross-encoder (`cross-encoder/nli-deberta-v3-base`, bidirectional):
   - **Entailment** → merge into the existing claim, increment `occurrence_count`
   - **Contradiction** → keep both claims, link them with a `contradicts` edge in `claim_relations` (a debunk circulating alongside its claim is signal, not noise)
   - **Neutral** → insert as a new claim

The embedding-similarity threshold is a *candidate-retrieval* cutoff, not a merge threshold — the NLI model makes the merge decision. Note that e5-family cosine similarity runs high (~0.77 even for unrelated texts).

## Database schema

| Table | Purpose |
|---|---|
| `raw_messages` | Every Telegram message as ingested, with processing state |
| `claims` | Deduplicated factual claims with embeddings and metadata |
| `claim_relations` | Claim ↔ claim edges (`contradicts` / `paraphrase`) |
| `claim_sources` | Many-to-many: which messages contributed to each claim |
| `checkpoints` | Last-seen message ID per channel for incremental fetching |

Each claim carries: `claim_text`, `topic`, `temporal`, `checkworthy_score`, `source_attribution`, `urgency_signals`, `conspiratorial_framing`, `occurrence_count`, `status` (`unreviewed | verified | debunked | needs_info`), `embedding` (768-dim vector), plus reserved columns for upcoming scoring work (`priority_score`, `source_reliability`, `narrative_id`, `scrubbed`).

## API

HTTP Basic auth on all endpoints. WebSocket at `/ws` pushes new claims in real time.

```
GET    /api/claims                 search/filter (status, topic, urgent, search, paging)
GET    /api/claims/network         claim-relation graph (nodes + edges, ?days=N)
GET    /api/claims/{id}            claim detail + sources
PATCH  /api/claims/{id}            apply verdict: verified | debunked | needs_info
GET    /api/stats                  totals, queue depth, today's counts
GET    /api/logs/{service}         container logs (scraper | processor)
WS     /ws                         live claim stream
```

## Setup

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL with pgvector)
- A Telegram account with API credentials — get them at [my.telegram.org](https://my.telegram.org)
- An Anthropic API key

### Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
ANTHROPIC_API_KEY=sk-ant-...
API_USERNAME=admin
API_PASSWORD=change-me
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

The processor downloads two HuggingFace models on first start (~1.5 GB total): the e5 embedding model and the NLI cross-encoder. Both run locally — no API calls.

```bash
# Dashboard dev server (from dashboard/)
npm install && npm run dev
```

### Docker (all services)

```bash
docker compose up
```

Dashboard at `http://localhost`, API proxied under `/api`.

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
| `dedup.similarity_threshold` | `0.88` | Cosine cutoff for NLI-guard candidate retrieval |
| `urgency.caps_ratio_threshold` | `0.4` | Fraction of ALL-CAPS words that triggers urgency |
| `urgency.min_exclamation_marks` | `3` | Exclamation mark count that triggers urgency |

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_API_ID` | Yes | From my.telegram.org |
| `TELEGRAM_API_HASH` | Yes | From my.telegram.org |
| `TELEGRAM_SESSION_NAME` | No | Path for Telethon session file (default: `bsbeacon`) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `ANTHROPIC_MODEL` | No | Model to use (default: `claude-sonnet-4-6`) |
| `API_USERNAME` / `API_PASSWORD` | Yes (API) | HTTP Basic credentials; API returns 503 if unset |
| `DATABASE_URL` | Yes | asyncpg connection string |
| `DATABASE_MIGRATION_URL` | Yes | psycopg2 connection string (for Alembic) |
| `NTFY_TOPIC` | No | ntfy.sh topic for urgent-claim alerts (no-op if unset) |
| `NTFY_SERVER` | No | Self-hosted ntfy server (default: ntfy.sh) |
| `LLM_PROVIDER` | No | `claude` (default, only option currently) |

## Tests

```bash
pytest tests/                        # all tests
pytest tests/test_claim_extractor.py # single file
pytest -k "test_dedup"               # by name
```

96 tests. LLM and DB calls are mocked; the embedding tests load the real e5 model (downloaded on first run).

## Project structure

```
src/
  ingestion/
    scraper.py         — Telethon polling loop, message storage, checkpointing
    checkpoint.py      — Per-channel last-seen message ID (PostgreSQL-backed)
  processing/
    pipeline.py        — Main loop: fetch → extract → embed → NLI dedup → store
    claim_extractor.py — Claude tool-use client, EXTRACTION_TOOL schema, LLMClient protocol
    schemas.py         — Pydantic models + enums (ClaimTopic, ClaimStatus, ClaimRelation, NLILabel)
    dedup.py           — Text-hash dedup, candidate retrieval, NLI guard, claim insert/merge/link
    embeddings.py      — multilingual-e5 singleton and cosine similarity
    language.py        — Language detection (langdetect)
    urgency.py         — Rule-based urgency detection
  api/
    main.py            — FastAPI app + WebSocket endpoint
    auth.py            — HTTP Basic auth
    ws.py              — Claim polling broadcast loop
    routes/            — claims (incl. /network), stats, logs
  alerts/
    dispatcher.py      — ntfy.sh urgent-claim notifications
  db/
    connection.py      — SQLAlchemy async engine and session factory
dashboard/             — React + TypeScript (Vite): LiveFeed, Trending, Analysis,
                         Queue, Network (d3-force graph), Logs
config/
  channels.yaml        — Monitored Telegram channels
  settings.yaml        — Runtime configuration
  system_prompt.txt    — LLM extraction instructions
migrations/
  versions/001_initial_schema.py    — Initial schema (pgvector, core tables)
  versions/002_process_chain_v2.py  — Topic taxonomy, 768-dim embeddings, claim_relations
```

## Roadmap

Tracked in `MYTHOS_PLAN.md`:

- **Event-driven ingestion** — Telethon `events.NewMessage` handlers with polling demoted to a recovery sweep; edit/delete tracking (deletion-after-virality as a signal)
- **Channel discovery** — forward-graph snowball sampling with human approval
- **Evaluation harness** — labeled extraction/dedup sets with precision/recall gates in CI
- **Scoring** — fact-check corpus matching (Google Fact Check Tools), per-channel source reliability, percentile-normalized virality, composite priority score
- **Narratives** — HDBSCAN clustering over claim embeddings, narrative time series, acceleration alerts
- **Media OCR** — Tesseract → vision-LLM escalation for image-borne claims
