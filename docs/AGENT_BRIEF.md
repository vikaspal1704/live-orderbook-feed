# Agent Brief — Live Orderbook Feed

**Primary instructions for AI coding agents.**  
Author: Vikas Pal · Repo: https://github.com/vikaspal1704/live-orderbook-feed

Read this file completely before writing code.

---

## 1. Mission

Implement an educational **real-time L2 order-book WebSocket fan-out service** in Python that matches [`API_CONTRACT.md`](API_CONTRACT.md) exactly, passes acceptance tests, ships a demo WS client, and keeps CI green.

**Stack is locked:** **FastAPI + Starlette WebSockets + uvicorn + Pydantic v2** (see [`TRD.md`](TRD.md)). Do not switch to aiohttp for v1.

**This repository may currently be docs-only.** You implement the code; do not change protocol semantics that are already locked in the docs.

**Sibling:** [mini-matching-engine](https://github.com/vikaspal1704/mini-matching-engine) is a separate matching CLOB. **Do not implement a matching engine in this repo.**

---

## 2. Read order (mandatory)

1. [`PRD.md`](PRD.md) — goals, MUST requirements, out of scope  
2. [`TRD.md`](TRD.md) — FastAPI lock, layout, config, concurrency, CI  
3. [`API_CONTRACT.md`](API_CONTRACT.md) — exact JSON field names, REST, close codes  
4. [`ARCHITECTURE.md`](ARCHITECTURE.md) — fan-out, seq rules, worked subscribe example  
5. [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md) — binary done checklist  
6. [`TEST_PLAN.md`](TEST_PLAN.md) — required test names and fixtures

Then implement. If docs conflict, prefer **API_CONTRACT → ARCHITECTURE → PRD**.

---

## 3. Implementation phases

### Phase 1 — Core book + sequencer + tick source

- Create `pyproject.toml` and package `orderbook_feed/`
- Implement `OrderBook`, `Sequencer`, manual/synthetic `TickSource`
- Integer price/qty; qty `0` deletes level
- Single asyncio-owned book (no matching logic)

### Phase 2 — Hub + FastAPI REST + WebSocket

- Per-client `asyncio.Queue` with `CLIENT_QUEUE_MAX`; drop slow consumers (close **1013**)
- `WS /v1/ws`: subscribe → snapshot (`seq=last_seq`) → deltas; heartbeats
- `GET /health`, `GET /v1/book/{symbol}`
- Wire feed task in app lifespan

### Phase 3 — Tests

- Add all **required** pytest function names from ACCEPTANCE_CRITERIA / TEST_PLAN
- Use **manual** tick injection for determinism
- `test_worked_example_subscribe_snapshot_deltas` follows ARCHITECTURE §7
- `pytest -q` green

### Phase 4 — Demo + CI + README polish

- `demo/ws_client.py` with `python -m demo.ws_client`
- `.github/workflows/ci.yml`: install `.[dev]`, run pytest (optional ruff); **no API keys**
- **Replace** any placeholder/default GitHub README with the project README
- Update README status from “docs-first / implementation pending” to implemented when code lands
- Ensure `LICENSE` (MIT, Vikas Pal 2026) and `AGENTS.md` remain correct

---

## 4. Do

- Follow JSON field names and seq rules literally  
- Use Python 3.11+ and FastAPI (locked)  
- Keep fan-out correct under slow consumers  
- Map every F-MUST to a test  
- Prefer clarity over micro-optimizations  
- After implementation on a branch: **open a PR** to `main` (do not only leave commits local)  
- When replacing README: keep links to `docs/*`, sibling matching-engine note, and MIT

## 5. Don’t

- Don’t add a matching engine, order entry, or trade execution
- Don’t require Binance/Polygon/API keys for core path or CI
- Don’t use `float` for price or quantity
- Don’t block the feed loop on a slow WebSocket send — use queues + drop policy
- Don’t invent alternate message field names (`bid` vs `BID`, `sequence` vs `seq`, etc.)
- Don’t skip heartbeats or sequence numbers
- Don’t leave the default GitHub placeholder README
- Don’t skip `test_worked_example_subscribe_snapshot_deltas`
- Don’t change the public protocol without updating API_CONTRACT + tests in the same change
- Don’t switch the web stack away from FastAPI without an explicit TRD change

---

## 6. Definition of done

Copy from ACCEPTANCE_CRITERIA:

```
DONE when:
1. All section A criteria pass via section B tests.
2. Section C demo runs.
3. Section D CI green (no vendor API keys).
4. Section E README is project README (not placeholder).
5. No WS/REST field divergence from API_CONTRACT.md.
6. No matching-engine code in this repository.
```

---

## 7. Quick reference — protocol

```text
Client → {"type":"subscribe","symbol":"DEMO/USD","client_id":"c1"}
Server → {"type":"snapshot","symbol":"DEMO/USD","seq":S,"ts":...,"bids":[...],"asks":[...]}
Server → {"type":"delta","symbol":"DEMO/USD","seq":S+1,"ts":...,"changes":[{"side":"BID","price":99,"quantity":4}]}
Server → {"type":"heartbeat","ts":...}
REST   → GET /health
REST   → GET /v1/book/DEMO%2FUSD
```

Full schemas: [`API_CONTRACT.md`](API_CONTRACT.md).  
Worked example: [`ARCHITECTURE.md`](ARCHITECTURE.md) §7.

---

## 8. Git / PR expectations

- Branch name suggestion: `feat/core-orderbook-feed`
- Commits: focused (book → hub/ws/rest → tests → demo → ci)
- **Open a pull request** if working on a branch; PR description should cite acceptance checklist
- Do not force-push `main`

---

## 9. Out of scope reminder

Synthetic/file-replay only for v1 core path.  
No matching engine. No auth. No DB. No multi-instrument.  
Educational correctness of **fan-out and protocol** > micro-optimization.  
Not a production exchange.
