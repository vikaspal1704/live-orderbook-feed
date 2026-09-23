# Live Orderbook Feed

An educational **real-time L2 order-book WebSocket fan-out service** in Python — synthetic market data, in-memory book, multi-client broadcast.

Built as a portfolio project by **Vikas Pal** (Software Engineer, Fintech) to demonstrate real-time trading infrastructure: WebSocket fan-out, snapshot + incremental protocol, sequence numbers, heartbeats, reconnect, and slow-consumer / backpressure handling.

| | |
|---|---|
| **Status** | Implemented — see [`tests/`](tests/) and [CI](.github/workflows/ci.yml) |
| **Language** | Python 3.11+ |
| **Framework** | FastAPI (Starlette WebSockets) |
| **License** | [MIT](LICENSE) |
| **Repo** | https://github.com/vikaspal1704/live-orderbook-feed |

**Sibling (matching, not market data):** [mini-matching-engine](https://github.com/vikaspal1704/mini-matching-engine) — limit-order CLOB. This repo does **not** include a matching engine.

---

## What it is

- An in-memory **L2 order book** for a single instrument (`DEMO/USD`)
- A **synthetic (or file-replay) tick generator** that mutates the book — **no paid market-data vendor**, no API keys required for the core path
- A **WebSocket server** that fans out full **snapshots** and **incremental deltas** to many clients
- Protocol focus: **sequence numbers**, snapshot+diff, **heartbeats**, **reconnect** recovery, **backpressure** / slow-consumer handling
- Optional thin **REST**: health + current snapshot
- Fully specified by docs so humans and AI coding agents can implement without guessing

## What it is not

- Not connected to Binance, Polygon, or any live exchange feed in v1
- Not a matching engine, OMS, or trading venue (see sibling repo for matching)
- Not a production exchange market-data plant
- Not multi-instrument or multi-process clustered fan-out in v1

---

## Documentation (start here)

| Doc | Audience | Purpose |
|-----|----------|---------|
| [`docs/AGENT_BRIEF.md`](docs/AGENT_BRIEF.md) | **AI coding agents** | Primary build instructions — read this first |
| [`docs/PRD.md`](docs/PRD.md) | Recruiters / PMs | Goals, personas, functional requirements |
| [`docs/TRD.md`](docs/TRD.md) | Implementers | Stack lock (FastAPI), layout, concurrency, packaging |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | Implementers | Exact WS/REST JSON schemas and field names |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Implementers / interviewers | Fan-out design, protocol, worked subscribe example |
| [`docs/ACCEPTANCE_CRITERIA.md`](docs/ACCEPTANCE_CRITERIA.md) | QA / agents | Binary checklist for “done” |
| [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) | Implementers | Required pytest scenarios and edge cases |
| [`AGENTS.md`](AGENTS.md) | Agents | Short pointer to the brief |

---

## Stack

- **Python** 3.11+
- **HTTP / WebSocket**: **FastAPI** + Starlette WebSockets (locked in [`docs/TRD.md`](docs/TRD.md))
- **ASGI server**: `uvicorn`
- **Packaging**: `pyproject.toml` (hatchling or setuptools)
- **Tests**: `pytest`, `pytest-asyncio`, `httpx` (ASGI transport)
- **Lint** (optional): `ruff`
- **CI**: GitHub Actions (lint + test on push/PR)

---

## How to run

```bash
# Clone
git clone https://github.com/vikaspal1704/live-orderbook-feed.git
cd live-orderbook-feed

# Create venv and install (editable + test deps)
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest -q

# Run server
uvicorn orderbook_feed.app:app --host 0.0.0.0 --port 8000

# Demo client, in a second terminal (prints snapshot then 5 deltas, exits 0)
python -m demo.ws_client

# Or: replay a scripted NDJSON file instead of synthetic ticks
TICK_MODE=replay REPLAY_PATH=samples/demo_ticks.ndjson uvicorn orderbook_feed.app:app
```

Expected behavior: synthetic ticks update the in-memory book; connected WebSocket clients receive a snapshot on subscribe, then sequenced deltas; `/health` returns OK; `/v1/book/DEMO%2FUSD` returns the current snapshot JSON. OpenAPI docs for the REST routes are at `/docs`.

### Deploy (Render)

[`render.yaml`](render.yaml) is a Render Blueprint for a free web service that tracks `main`:

1. Render dashboard → **New** → **Blueprint** → pick this repository → **Apply**.
2. Once live: `https://<service>.onrender.com/health`, and stream with
   `FEED_WS_URL=wss://<service>.onrender.com/v1/ws python -m demo.ws_client`.

Free instances sleep when idle; the first request after a sleep takes a few seconds, and the book restarts from `seq=0`.

### Configuration (environment variables)

| Variable | Default | Meaning |
|----------|---------|---------|
| `SYMBOL` | `DEMO/USD` | Sole instrument |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address (used by `python -m orderbook_feed`) |
| `HEARTBEAT_INTERVAL_SEC` | `5.0` | Server → client heartbeat period |
| `CLIENT_QUEUE_MAX` | `64` | Per-client queue depth before slow-consumer disconnect (close `1013`) |
| `TICK_INTERVAL_MS` | `100` | Synthetic / replay tick cadence |
| `TICK_MODE` | `synthetic` | `synthetic` \| `replay` \| `manual` (tests inject ticks) |
| `REPLAY_PATH` | unset | NDJSON file for `TICK_MODE=replay` |
| `BOOK_DEPTH_LEVELS` | `10` | Top-N levels per side in snapshots |
| `SYNTHETIC_SEED` | unset | Seed for a reproducible synthetic feed |

### Project layout

```
orderbook_feed/
  app.py          # FastAPI app + lifespan (feed task, heartbeat task)
  config.py       # Settings from environment
  models.py       # Pydantic v2 WS/REST schemas (mirror API_CONTRACT)
  book.py         # In-memory aggregated L2 book
  sequencer.py    # Monotonic seq
  tick_source.py  # Synthetic / NDJSON replay / manual sources
  feed.py         # Tick -> book -> seq -> delta -> hub
  hub.py          # Per-client bounded queues, fan-out, slow-consumer drop
  ws.py           # WS /v1/ws: subscribe lifecycle, reader + writer per client
  rest.py         # GET /health, GET /v1/book/{symbol}
demo/ws_client.py # python -m demo.ws_client (applies deltas, detects seq gaps)
samples/          # demo_ticks.ndjson replay file
tests/            # pytest suite incl. ARCHITECTURE §7 worked example + e2e demo test
```

### Limitations (educational, not a production exchange)

- One process, one event loop, one instrument; no cross-process fan-out.
- No durable replay: reconnecting clients recover via a fresh snapshot.
- Snapshots are top-N; a client holding only the snapshot may not see levels beyond N until a delta touches them.
- Heartbeats go to every connected client (subscribed or not) through the same bounded queue, so they are subject to the slow-consumer policy.

---

## Recruiter snapshot

| Topic | Detail |
|-------|--------|
| Domain | Real-time market data / L2 book fan-out (fintech infra) |
| Focus | Protocol correctness, reconnect, backpressure, heartbeats |
| Depth | Snapshot+diff, sequence gaps, slow-consumer policy |
| Intent | Show systems thinking for remote hard-currency roles |

---

## License

MIT © 2026 Vikas Pal — see [LICENSE](LICENSE).
