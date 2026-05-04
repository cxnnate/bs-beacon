# BSBeacon Phase 3 — API, Dashboard & Alerts Design

**Goal:** Expose the claims database through a FastAPI query layer, surface it in a real-time React dashboard with sidebar navigation, and push urgent claims to ntfy.

**Architecture:** Two new Docker services (`bsbeacon-api`, `bsbeacon-dashboard`) join the existing compose stack. The dashboard is a React SPA served by Nginx; Nginx proxies `/api` and `/ws` to FastAPI. Webhook alerts fire inline from the processor — no new service needed.

**Tech stack:** FastAPI, React + Vite + TypeScript, Recharts, Nginx, ntfy

---

## 1. Docker Services

Two new services added to `docker-compose.yml`:

**`bsbeacon-api`**
- Reuses the existing Python `Dockerfile` (command override: `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`)
- Depends on `bsbeacon-db`
- Exposes port 8000 (internal only — Nginx proxies to it)

**`bsbeacon-dashboard`**
- Built from `dashboard/Dockerfile` — multi-stage: Node build stage, then Nginx serve stage
- Exposes port 80 (public-facing)
- Config from `dashboard/nginx.conf`

**nginx.conf responsibilities:**
- Serve `dashboard/dist` static files
- `location /api/` → proxy to `bsbeacon-api:8000`
- `location /ws` → proxy to `bsbeacon-api:8000/ws` with WebSocket upgrade headers

---

## 2. FastAPI — `src/api/`

### Auth
HTTP Basic Auth on all routes. Single shared credential from env vars `API_USERNAME` and `API_PASSWORD`. Implemented as a FastAPI dependency injected at the router level.

### File structure
```
src/api/
  main.py          — app factory, CORS, mounts routers, WebSocket endpoint
  auth.py          — HTTP Basic Auth dependency
  ws.py            — WebSocketManager: broadcast to all connected clients
  routes/
    claims.py      — claim CRUD endpoints
    stats.py       — aggregate stats endpoint
    logs.py        — docker log tail endpoint
```

### Endpoints

**`GET /api/claims`**
Query params: `status` (unreviewed/reviewed/dismissed), `category`, `urgent` (bool), `search` (text), `page`, `page_size` (default 50).
Returns paginated list of claims ordered by `created_at DESC`.

Response shape per claim:
```json
{
  "id": 1,
  "claim_text": "...",
  "category": "military",
  "temporal": "past",
  "checkworthy_score": 0.91,
  "source_attribution": null,
  "urgency_signals": true,
  "occurrence_count": 3,
  "status": "unreviewed",
  "first_seen_at": "2026-05-04T14:03:00Z",
  "last_seen_at": "2026-05-04T14:09:00Z",
  "channels": ["Geopolitics Watch", "Geopolitics Prime"]
}
```

`channels` is derived from `claim_sources` — distinct `channel_name` values for that claim.

**`GET /api/claims/{id}`**
Returns single claim including full `sources` array (raw_message_id, channel_name, message_date).

**`PATCH /api/claims/{id}`**
Body: `{"status": "reviewed" | "dismissed"}`.
Updates `claims.status`. Returns updated claim.

**`GET /api/stats`**
Returns:
```json
{
  "total_claims": 247,
  "unreviewed": 12,
  "urgent_unreviewed": 3,
  "messages_today": 84,
  "claims_today": 31
}
```

**`GET /api/logs/{service}`**
`service` must be one of: `scraper`, `processor`. Runs `docker logs --tail 30 bsbeacon-{service}` via `subprocess.run`, returns plain text. Returns 400 for unknown service names.

**`WebSocket /ws`**
On connect: authenticates via query param `?token=base64(username:password)`.
On new claim inserted by processor: `ws_manager.broadcast(claim_json)`.
Clients reconnect automatically on disconnect (handled in React).

---

## 3. WebSocket Integration

`ws.py` exports a singleton `ws_manager`. `pipeline.py` imports it and calls `asyncio.create_task(ws_manager.broadcast(claim_data))` after a successful `insert_claim()`. This is fire-and-forget — a WebSocket failure never blocks claim processing.

---

## 4. React Dashboard — `dashboard/`

**Stack:** Vite, React 18, TypeScript, Recharts, no UI framework (custom CSS).

**Sidebar navigation — six items:**

| Item | Icon | View |
|---|---|---|
| Live Feed | ● | Real-time claim cards, WebSocket-pushed |
| Trending | 📈 | Bar chart — top 20 claims by occurrence_count |
| Analysis | 🔬 | Scatter plot — checkworthy_score vs occurrence_count, colored by category |
| Queue | ✅ | Unreviewed claims sorted by urgency + checkworthy_score desc |
| Scraper | 🟢/🔴 | Last 30 log lines from bsbeacon-scraper, polled every 10s |
| Processor | 🟢/🔴 | Last 30 log lines from bsbeacon-processor, polled every 10s |

Status indicator (🟢/🔴) on Scraper and Processor reflects whether the last log fetch succeeded.

**Claim card (Live Feed and Queue):**
- Claim text
- Channel name + relative timestamp (e.g. "📡 Geopolitics Watch · 2m ago")
- Category badge + temporal
- Checkworthy score + occurrence count (bottom right)
- URGENT badge (red, left border accent) if `urgency_signals=true`
- ✓ Reviewed and ✕ Dismiss buttons — optimistic update, PATCH to API

**Live Feed behaviour:**
- Connects to `ws://host/ws` on mount with Basic Auth token
- New claims prepended to the top of the list
- Reconnects with exponential backoff on disconnect

**Log view behaviour:**
- `GET /api/logs/{service}` polled every 10s
- Displayed in a dark monospace container
- Auto-scrolls to bottom on new content

**File structure:**
```
dashboard/
  src/
    App.tsx              — sidebar layout, view routing
    api.ts               — typed fetch wrappers for all API endpoints
    ws.ts                — WebSocket hook with reconnect logic
    views/
      LiveFeed.tsx
      Trending.tsx
      Analysis.tsx
      Queue.tsx
      Logs.tsx           — shared log view, takes service prop
    components/
      ClaimCard.tsx
      Sidebar.tsx
  Dockerfile             — multi-stage: node:20 build → nginx:alpine serve
  nginx.conf
  vite.config.ts
```

---

## 5. Webhook Alerts — `src/alerts/dispatcher.py`

Called from `pipeline.py` immediately after `insert_claim()` when `urgency=True`.

```python
async def dispatch_alert(claim_text: str, channel_name: str, score: float) -> None:
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        return
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh")
    # POST to ntfy with priority and tag headers
```

**ntfy message format:**
- Title: `BSBeacon Alert — {channel_name}`
- Body: claim text
- Priority: `high`
- Tags: `warning,bsbeacon`

Errors are logged as warnings — a failed alert never raises or blocks claim processing.

**Option C — Viral spread alerts (documented, not implemented):**
```python
# Future: also alert when occurrence_count crosses NTFY_VIRAL_THRESHOLD (default 3)
# Called from merge_claim() in dedup.py after incrementing occurrence_count.
# async def dispatch_viral_alert(claim_id, claim_text, occurrence_count, channel_name)
```

---

## 6. Environment Variables

New vars added to `.env` and `.env.example`:

| Variable | Required | Description |
|---|---|---|
| `API_USERNAME` | Yes | Dashboard login username |
| `API_PASSWORD` | Yes | Dashboard login password |
| `NTFY_TOPIC` | No | ntfy topic name — alerts disabled if unset |
| `NTFY_SERVER` | No | ntfy server URL (default: `https://ntfy.sh`) |

---

## 7. Testing

- `tests/test_api_claims.py` — GET /claims filtering, PATCH status update (async test client, mocked DB)
- `tests/test_api_stats.py` — GET /stats response shape
- `tests/test_api_logs.py` — GET /logs/scraper with mocked subprocess
- `tests/test_dispatcher.py` — dispatch_alert sends correct ntfy payload; no-op when NTFY_TOPIC unset (mocked httpx)

No browser/E2E tests. Dashboard tested manually.
