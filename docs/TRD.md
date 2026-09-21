# Technical Requirements Document (TRD)

**Product:** Live Orderbook Feed  
**Version:** 1.0

---

## 1. Language & runtime

- **Python 3.11+** (use `list[str]`, `X | Y` union syntax)
- CPython only for v1

## 2. Stack lock (normative)

| Layer | Choice | Notes |
|-------|--------|-------|
| Web framework | **FastAPI** | Locked for v1 — do not switch to aiohttp without updating this TRD + ARCHITECTURE |
| WebSockets | **Starlette WebSockets** (via FastAPI) | Same process as REST |
| ASGI server | **uvicorn** | Standard entry: `uvicorn orderbook_feed.app:app` |
| Validation / schemas | **Pydantic v2** | Request/response and WS message models |
| HTTP test client | **httpx ASGI transport** | REST tests |
| WS tests | `starlette.testclient` / `httpx` + websockets, or `pytest` + ASGI websocket client | See TEST_PLAN |

**Rationale for FastAPI over aiohttp:** single stack for thin REST + WS, Pydantic integration, recruiter familiarity, Starlette-native WebSocket support. aiohttp is a valid alternative ecosystem but is **out of scope for v1** once this lock is set.

## 3. Packaging

| Item | Requirement |
|------|-------------|
| Manifest | `pyproject.toml` at repo root |
| Package name | `orderbook-feed` (distribution); import package `orderbook_feed` |
| Build backend | `hatchling` **or** `setuptools` (pick one; document in pyproject) |
| Install | `pip install -e ".[dev]"` |
| Runtime deps | `fastapi`, `uvicorn[standard]`, `pydantic>=2` |
| Dev extras | `pytest`, `pytest-asyncio`, `httpx`, optionally `ruff`, `pytest-cov`, `websockets` |
| Python requires | `requires-python = ">=3.11"` |

### Suggested `pyproject.toml` shape (non-normative layout)

```toml
[project]
name = "orderbook-feed"
version = "0.1.0"
description = "Educational real-time L2 order-book WebSocket fan-out service"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "Vikas Pal" }]
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "pydantic>=2",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-asyncio>=0.23", "httpx>=0.27", "ruff>=0.1", "websockets>=12"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["orderbook_feed"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

## 4. Repository layout

```
live-orderbook-feed/
├── AGENTS.md
├── LICENSE
├── README.md
├── pyproject.toml
├── .github/
│   └── workflows/
│       └── ci.yml
├── orderbook_feed/
│   ├── __init__.py
│   ├── app.py              # FastAPI app factory / app instance
│   ├── config.py           # Settings (symbol, heartbeat, queue depth, tick rate)
│   ├── models.py           # Pydantic WS/REST schemas (mirror API_CONTRACT)
│   ├── book.py             # In-memory L2 book
│   ├── sequencer.py        # Monotonic seq generator
│   ├── tick_source.py      # Synthetic + optional file-replay
│   ├── hub.py              # Subscription hub / fan-out / per-client queues
│   ├── ws.py               # WebSocket route handlers
│   └── rest.py             # /health and /v1/book/{symbol}
├── demo/
│   ├── __init__.py
│   └── ws_client.py        # python -m demo.ws_client
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_book.py
│   ├── test_protocol_snapshot_delta.py
│   ├── test_sequence.py
│   ├── test_heartbeat.py
│   ├── test_backpressure.py
│   ├── test_rest.py
│   ├── test_tick_source.py
│   └── test_worked_example.py
├── samples/                  # optional: sample replay file
│   └── demo_ticks.ndjson
└── docs/
    └── *.md
```

Agents **must** use package name `orderbook_feed` unless they document a justified rename in ARCHITECTURE (not recommended).

## 5. Configuration (defaults)

| Setting | Default | Meaning |
|---------|---------|---------|
| `SYMBOL` | `DEMO/USD` | Sole instrument |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address |
| `HEARTBEAT_INTERVAL_SEC` | `5.0` | Server → client heartbeat period |
| `CLIENT_QUEUE_MAX` | `64` | Per-client outbound message queue depth before slow-consumer disconnect |
| `TICK_INTERVAL_MS` | `100` | Synthetic generator cadence (wall-clock mode) |
| `TICK_MODE` | `synthetic` | `synthetic` \| `replay` \| `manual` (manual = tests inject ticks) |
| `REPLAY_PATH` | unset | NDJSON path when `TICK_MODE=replay` |
| `BOOK_DEPTH_LEVELS` | `10` | Max levels per side in snapshots (top N) |

Environment variables or a small `Settings` class (pydantic-settings optional) are fine.

## 6. Core components (contract summary)

Full message schemas: [`API_CONTRACT.md`](API_CONTRACT.md). Behavior: [`ARCHITECTURE.md`](ARCHITECTURE.md).

| Component | Responsibility |
|-----------|----------------|
| `OrderBook` | Apply level updates; produce snapshot DTO; never talks to network |
| `Sequencer` | `next_seq() -> int` starting at 1 |
| `TickSource` | Yield book mutations (synthetic / replay / manual) |
| `Hub` | Register clients; enqueue snapshot+deltas; enforce queue max; broadcast without blocking feed |
| `WS handler` | Parse subscribe/unsubscribe; pump client queue to socket |
| `REST` | Health + snapshot read of current book |

## 7. Concurrency model

- **Single asyncio event loop** (uvicorn worker = 1 for v1 docs/demo).
- Feed task: read ticks → apply to book → assign `seq` → fan-out enqueue to all subscribers.
- Per-client: outbound `asyncio.Queue(maxsize=CLIENT_QUEUE_MAX)`; writer task drains to WebSocket.
- **On `QueueFull`:** disconnect that client (slow consumer); continue serving others.
- Do **not** use threads for the book; keep book mutations on the event-loop task that owns the book (or a single dedicated feed task).

## 8. Error model

| Situation | Behavior |
|-----------|----------|
| Unknown WS `type` | Send `{"type":"error","code":"BAD_REQUEST","message":"..."}`; connection may stay open |
| Subscribe unknown symbol | `error` code `UNKNOWN_SYMBOL` |
| REST unknown symbol | HTTP 404 with JSON `{"detail":"..."}` |
| Slow consumer | Close WebSocket with code **1013** (Try Again Later) or **1008** (Policy Violation) — **locked: 1013**; optional final `error` frame `SLOW_CONSUMER` if still writable |
| Malformed JSON | `error` code `BAD_REQUEST` |

## 9. Logging / observability

- `logging` info: startup, client connect/disconnect, subscribe, slow-consumer drop, feed mode.
- Debug: per-message seq (optional; avoid flooding at info).
- No OpenTelemetry requirement for v1.
- COULD: `/metrics` later.

## 10. CI (GitHub Actions)

Workflow `.github/workflows/ci.yml` MUST:

1. Trigger on `push` and `pull_request` to `main` (and optionally all branches).
2. Use Python 3.11 (matrix 3.11 / 3.12 nice-to-have).
3. `pip install -e ".[dev]"` then `pytest -q`.
4. Optionally run `ruff check .` if ruff is in dev deps.

## 11. Demo module

- Entry: `python -m demo.ws_client`
- Connects to `ws://127.0.0.1:8000/v1/ws` (override via env)
- Sends subscribe for `DEMO/USD`
- Prints first snapshot and a few deltas; exits 0
- Speaks only JSON protocol from API_CONTRACT

## 12. Relationship to mini-matching-engine

- **Conceptual sibling only.** Matching happens in [mini-matching-engine](https://github.com/vikaspal1704/mini-matching-engine).
- This repo **must not** import or vendor matching logic.
- Tick generator synthesizes L2 level changes; it does **not** match orders.

## 13. Non-requirements (tech)

- No Redis / Kafka / NATS for v1 fan-out (in-process hub only)
- No Protobuf / Avro
- No Decimal required — **integer prices and quantities** (ticks / lots), same spirit as matching-engine sibling
- No multi-worker shared book (would need external bus — out of scope)
