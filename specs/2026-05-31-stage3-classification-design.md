# Stage 3 Classification — Design Spec

**Date:** 2026-05-31
**Status:** Approved

## Overview

Implement Stage 3 of the BSBeacon pipeline: virality scoring, LLM-based credibility scoring, and Google Fact Check API cross-reference. All scoring runs inline in the existing processing pipeline — no new services.

The `virality_score` and `credibility_score` columns already exist in the `claims` table but are never populated. This spec closes that gap.

---

## Component 1 — Credibility Scoring (LLM)

**Approach:** Add `credibility_score: float` to `ExtractedClaim` in `src/processing/schemas.py`. Update `config/system_prompt.txt` to instruct Claude to score each claim's credibility alongside extraction.

**Rubric added to system prompt:**
- `0.0` = demonstrably false or highly misleading
- `0.5` = unverifiable, ambiguous, or lacks context
- `1.0` = appears factually accurate based on available context

**Rationale:** Claude already reads the full message context at extraction time (channel name, views, forwards, surrounding language). Adding one field costs zero extra API calls. Score flows through `ExtractionResult` → `insert_claim` → DB automatically after the schema change.

**Files changed:**
- `src/processing/schemas.py` — add `credibility_score: float = Field(ge=0.0, le=1.0)` to `ExtractedClaim`
- `config/system_prompt.txt` — add credibility scoring rubric and field to output schema

---

## Component 2 — Virality Scorer

**New file:** `src/classification/virality.py`

Single public function:

```python
def compute_virality(
    occurrence_count: int,
    channel_count: int,
    total_views: int,
    hours_alive: float,
) -> float
```

**Formula:**
```
spread_rate = channel_count / max(hours_alive, 0.1)

score = (
    0.4 * norm(spread_rate, 10.0)    +  # 10 channels/hr = ceiling
    0.3 * norm(channel_count, 20.0)  +  # 20 unique channels = ceiling
    0.2 * norm(total_views, 100_000) +  # 100k views = ceiling
    0.1 * norm(occurrence_count, 50)    # 50 occurrences = ceiling
)

return min(score, 1.0)
```

Where `norm(x, scale) = min(x / scale, 1.0)` (linear clamp).

**At insert:** `channel_count=1`, `occurrence_count=1`, `total_views` from source message, `hours_alive=0.1` (floor for brand-new claims).

**At merge:** query current claim row for `occurrence_count` and `first_seen_at`, query `SUM(views)` across `claim_sources`, recompute virality, update row.

**Normalization ceilings** are tunable once real data flows through.

---

## Component 3 — Google Fact Check API

**New file:** `src/classification/factcheck.py`

Fires as `asyncio.create_task` after a new claim is inserted — same pattern as `dispatch_alert`. No-ops silently if `GOOGLE_FACTCHECK_API_KEY` is unset.

**API call:**
```
GET https://factchecktools.googleapis.com/v1alpha1/claims:search
  ?query=<claim_text>
  &key=<GOOGLE_FACTCHECK_API_KEY>
```

**Rating → credibility score mapping:**

| Publisher rating | Score |
|---|---|
| False / Pants on Fire | 0.05 |
| Mostly False | 0.2 |
| Half True / Mixed | 0.5 |
| Mostly True | 0.75 |
| True | 0.95 |

**On match:** Update `credibility_score` with the mapped score. Also update `status`:
- Score ≤ 0.2 → `'debunked'`
- Score ≥ 0.75 → `'verified'`
- Score 0.5 (Half True / Mixed) → no status change, only credibility score updated

**On no match / error:** log and swallow. Never block the pipeline.

**HTTP client:** `httpx` async (already in `requirements.txt`).

**New env var:** `GOOGLE_FACTCHECK_API_KEY` — add to `.env.example` and `docker-compose.yml`.

---

## Pipeline Integration

### `src/processing/dedup.py`

- `insert_claim`: write `credibility_score` from `claim.credibility_score`; call `compute_virality` with initial values; write both scores. Return `claim_id` for downstream use.
- `merge_claim`: query current state, recompute virality, update `virality_score`.

### `src/processing/pipeline.py`

- After `insert_claim` succeeds: fire `asyncio.create_task(check_and_update_factcheck(claim_id, claim_text))` if API key is set.
- No new arguments at `process_message` level — key read from env at startup.

### `src/api/schemas.py`

Add to `ClaimResponse`:
```python
virality_score: Optional[float] = None
credibility_score: Optional[float] = None
```

### `src/api/routes/claims.py`

Add `c.virality_score` and `c.credibility_score` to `_CLAIM_COLS`. Dashboard scatter plot populates immediately.

---

## New Files

```
src/classification/
├── __init__.py
├── virality.py       # compute_virality()
└── factcheck.py      # check_and_update_factcheck()
```

---

## Environment Variables

| Var | Required | Purpose |
|---|---|---|
| `GOOGLE_FACTCHECK_API_KEY` | No | Enables fact-check cross-reference; silently skipped if unset |

---

## Testing

- `tests/test_virality.py` — unit tests for `compute_virality` with boundary values (new claim, high-virality claim, ceiling clamp)
- `tests/test_factcheck.py` — mock `httpx` responses; test rating→score mapping, no-match path, error swallowing
- Existing `tests/test_claim_extractor.py` — update mock `ExtractedClaim` fixtures to include `credibility_score`

No real API or DB needed — consistent with existing test strategy.

---

## Out of Scope

- Fine-tuned credibility classifier (DistilBERT/RoBERTa) — future phase
- Periodic virality refresh job — scores update naturally on each merge
- ClaimBuster API — defunct
