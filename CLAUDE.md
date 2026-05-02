# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**BSBeacon** — a real-time pipeline that ingests Telegram channel messages, extracts discrete claims via NLP/LLM, classifies them by credibility and virality, and routes high-priority misinformation to human fact-checkers. Runs 24/7, polling every 3 minutes.

The canonical design document is `PLAN.md`. Read it for data models, prompt templates, scoring formulas, and implementation rationale.

## Four-stage architecture

```
Ingest (Telethon) → Process (spaCy + Claude API) → Classify (DistilBERT/RoBERTa + virality math) → Output (FastAPI + React dashboard + webhooks)
```

- **Stage 1 — Ingest**: `src/ingestion/` — Telethon async polling, per-channel checkpointing, raw messages → PostgreSQL
- **Stage 2 — Process**: `src/processing/` — language detection, translation, LLM claim extraction, spaCy NER, sentence-transformer dedup (cosine similarity > 0.92 → merge)
- **Stage 3 — Classify**: `src/classification/` — virality scorer (pure math), credibility transformer, ClaimBuster/Google Fact Check API cross-reference
- **Stage 4 — Output**: `src/api/` (FastAPI), `dashboard/` (React + Recharts + WebSocket), `src/alerts/` (webhook dispatcher)

## Tech stack

| Component | Technology |
|---|---|
| Ingestion | Python, Telethon, asyncio |
| DB | PostgreSQL + pgvector (for claim embeddings) |
| Processing | spaCy, sentence-transformers, Claude API |
| Classification | HuggingFace transformers (DistilBERT → RoBERTa) |
| API | FastAPI |
| Dashboard | React, Recharts, WebSocket |
| Orchestration | APScheduler or Dagster |
| Dev environment | Docker Compose |

## Commands

### Setup
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in Telegram API keys, DB URL, Anthropic API key
docker compose up -d  # starts PostgreSQL
alembic upgrade head  # run migrations
python scripts/seed_channels.py  # populate initial channel list
```

### Run
```bash
# Full pipeline
docker compose up

# Individual stages (dev)
python -m src.ingestion.scraper        # ingestion loop
python -m src.processing.pipeline      # process unprocessed messages
uvicorn src.api.main:app --reload      # API server
cd dashboard && npm run dev            # React dashboard
```

### Test
```bash
pytest tests/                          # all tests
pytest tests/test_claim_extractor.py  # single test file
pytest -k "test_dedup"                 # single test by name
```

### Dashboard
```bash
cd dashboard
npm install
npm run dev    # dev server
npm run build  # production build
```

### Model training
```bash
python scripts/train_credibility.py   # fine-tune credibility classifier
```

## Implementation order

The plan prescribes this order — follow it:

1. **Foundation**: DB schema via Alembic, `.env`, `config/channels.yaml`
2. **Ingestion loop**: `src/ingestion/scraper.py` — get messages into PostgreSQL
3. **Claim extraction**: `src/processing/claim_extractor.py` — iterate on the prompt until quality is high (this is the hardest part)
4. **Entity extraction + dedup**: spaCy NER + sentence-transformer similarity
5. **Classification**: virality scorer first (no ML), then credibility model with pre-trained weights before fine-tuning
6. **API**: FastAPI layer + all endpoints
7. **Dashboard**: claim feed and trending view first, then scatter plot and queue
8. **Alerts**: webhook dispatcher → Slack/Discord

## Key design decisions

- **Dedup threshold**: cosine similarity > 0.92 → merge and increment `occurrence_count`. Below this → new claim.
- **pgvector**: claims embeddings use `VECTOR(384)` with an `ivfflat` index. Requires the pgvector PostgreSQL extension.
- **Claim extraction prompt**: the template is in `PLAN.md` Stage 2. It instructs the model to return a JSON array and ignore opinions/chatter. Pre-filter short or media-only messages before sending to the LLM to control costs.
- **Credibility pipeline**: always routes to human fact-checkers for final verdict. Fact-checker verdicts feed back as training data.
- **Virality formula**: weighted sum of spread rate, channel count, view count, and occurrence count — see `PLAN.md` Stage 3 for exact weights.

## Environment variables

See `.env.example`. Required: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `ANTHROPIC_API_KEY`, `DATABASE_URL`. Optional: `CLAIMBUSTER_API_KEY`, `GOOGLE_FACTCHECK_API_KEY`, webhook URLs.
