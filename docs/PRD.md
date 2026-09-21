# Product Requirements Document (PRD)

**Product:** Live Orderbook Feed  
**Owner:** Vikas Pal  
**Version:** 1.0 (docs-first)  
**Status:** Spec locked for v1 implementation

---

## 1. Goals

1. Deliver a correct, educational **real-time L2 order-book WebSocket fan-out service** in Python.
2. Maintain an **in-memory book** from a **synthetic (or file-replay) tick generator** — no paid market-data vendor for the core path.
3. Demonstrate production-relevant protocol concerns: **snapshot + incremental updates**, **sequence numbers**, **heartbeats**, **reconnect**, and **backpressure / slow-consumer** handling.
4. Make the repo **recruiter-credible**: clear docs, runnable server + demo client, green CI, MIT license.
5. Make the repo **agent-implementable**: unambiguous contracts, acceptance criteria, and test names — no guesswork on message schemas or fan-out rules.

## 2. Non-goals

- Real exchange or vendor market-data APIs as a v1 dependency (Binance, Polygon, etc.)
- Matching engine, order entry, risk, positions, or settlement (see sibling [mini-matching-engine](https://github.com/vikaspal1704/mini-matching-engine))
- Multi-instrument books in v1
- Persistent store / recovery of book state across process restart
- Authentication, API keys, multi-tenancy, or user accounts
- Binary protocols (FIX, SBE, Protobuf) in v1 — JSON over WebSocket only
- Production latency SLAs, kernel bypass, or hardware optimization
- Graphical trading UI

## 3. Personas

| Persona | Needs |
|---------|--------|
| **Recruiter / hiring manager** | Understand what was built in ≤2 minutes from README; see seriousness (docs, tests, CI, license). |
| **Engineer interviewer** | Probe fan-out, sequence gaps, slow consumers, reconnect; walk the worked subscribe example. |
| **AI implementer** | Follow AGENT_BRIEF → contracts → acceptance; implement without inventing protocol semantics. |

## 4. User stories / use cases

### WebSocket market-data client

| ID | Story |
|----|--------|
| US-WS-1 | As a client, I **connect** to the WebSocket endpoint and **subscribe** to `DEMO/USD`, then receive a full **snapshot** followed by **deltas** with monotonically increasing sequence numbers. |
| US-WS-2 | As a client, I detect a **sequence gap** and recover by requesting (or reconnecting for) a fresh **snapshot**. |
| US-WS-3 | As a client, I receive **heartbeats** so I can detect a dead connection and reconnect. |
| US-WS-4 | As a client, I can **unsubscribe** or disconnect cleanly without crashing the server or other clients. |

### Slow consumer / backpressure

| ID | Story |
|----|--------|
| US-BP-1 | As the server operator, when a client cannot keep up, the server applies a **defined slow-consumer policy** (drop that client and/or send an error) without stalling the fan-out loop for healthy clients. |

### REST (thin)

| ID | Story |
|----|--------|
| US-REST-1 | As an operator or probe, I call `GET /health` and learn the process is up and the feed loop is alive. |
| US-REST-2 | As a client bootstrap, I call `GET /v1/book/{symbol}` and get the current L2 snapshot JSON (same shape as the WS snapshot payload). |

### Demo

| ID | Story |
|----|--------|
| US-DEMO-1 | As a recruiter or interviewer, I run the server and `python -m demo.ws_client` and see subscribe → snapshot → deltas printed without writing code. |
| US-DEMO-2 | As an engineer, the demo client speaks only the public JSON protocol in `API_CONTRACT.md`. |

## 5. Functional requirements

### MUST

| ID | Requirement |
|-------------|-------------|
| F-MUST-1 | Single instrument in v1: symbol string **`DEMO/USD`** (configurable at startup, default this value). |
| F-MUST-2 | Maintain an in-memory L2 book (bids/asks aggregated by price level) updated only by the **synthetic/file-replay** tick source. |
| F-MUST-3 | WebSocket endpoint accepts subscribe and fans out: (a) one **snapshot** on successful subscribe, then (b) **delta** messages for subsequent book changes. |
| F-MUST-4 | Every book-affecting outbound message carries a **monotonically increasing `seq`** (uint64-style positive int starting at 1 for the first book event after process start). Snapshot and following deltas share one sequence space. |
| F-MUST-5 | Delta messages include enough fields to apply level updates (side, price, new quantity; quantity `0` means remove level). |
| F-MUST-6 | Server sends **heartbeat** messages on a configurable interval (default 5s) to each connected client; clients may also send client heartbeats (optional ping). |
| F-MUST-7 | **Slow-consumer handling**: per-client outbound queue with a max depth; when exceeded, disconnect that client with a defined close/error reason — do not block the global feed loop. |
| F-MUST-8 | Thin REST: `GET /health` and `GET /v1/book/{symbol}` per `API_CONTRACT.md`. |
| F-MUST-9 | Synthetic tick generator runs without any external API keys; deterministic mode available for tests (seeded or scripted ticks). |
| F-MUST-10 | No matching engine logic in this repository. |

### SHOULD

| ID | Requirement |
|-------------|-------------|
| F-SHOULD-1 | On subscribe, if client already subscribed to the same symbol, send a fresh snapshot (idempotent re-subscribe) or a defined error — pick one and lock in API_CONTRACT (locked: **fresh snapshot**). |
| F-SHOULD-2 | File-replay mode: read newline-delimited tick events from a path for demos/tests. |
| F-SHOULD-3 | Demo WS client prints snapshot then N deltas and exits 0. |
| F-SHOULD-4 | Structured logging of connect, subscribe, disconnect, slow-consumer drop, and seq on errors. |

### COULD

| ID | Requirement |
|-------------|-------------|
| F-COULD-1 | Optional adapter interface for a future live venue feed (e.g. public Binance book) — **not required** for v1 acceptance; core path must not need API keys. |
| F-COULD-2 | Client-initiated `resnapshot` request without full reconnect. |
| F-COULD-3 | Prometheus `/metrics` counters (clients connected, messages sent, slow drops). |
| F-COULD-4 | Multi-symbol subscribe in a later version. |

## 6. Non-functional requirements

| ID | Requirement |
|-------------|-------------|
| NF-1 | **Correctness of fan-out and protocol over micro-optimizations.** Prefer clear, testable code. |
| NF-2 | **Educational:** protocol (snapshot vs delta, seq) and one full worked client example must be in docs. |
| NF-3 | **Async** ASGI server; single process v1. |
| NF-4 | **Deterministic under test:** scripted tick injection → predictable `seq` and payloads. |
| NF-5 | Python 3.11+, typed public models (Pydantic v2 preferred with FastAPI). |
| NF-6 | **Educational, not production exchange** — document limitations in README/ARCHITECTURE. |

## 7. Out of scope (explicit)

- No paid market-data vendor / API keys for core path  
- No matching engine in this repo  
- No UI  
- No DB persistence of book state  
- No auth  
- No multi-instrument v1

## 8. Worked example (summary)

Full step-by-step lives in [`ARCHITECTURE.md`](ARCHITECTURE.md) § Worked example. Summary:

1. Client connects to `ws://localhost:8000/v1/ws`.  
2. Client sends `{"type":"subscribe","symbol":"DEMO/USD","client_id":"c1"}`.  
3. Server replies with `snapshot` (`seq=1`, full bids/asks).  
4. Synthetic ticks produce `delta` messages `seq=2`, `seq=3`, …  
5. Heartbeats arrive periodically with `type=heartbeat`.

## 9. Success metrics (v1)

- All MUST requirements mapped in `ACCEPTANCE_CRITERIA.md` and checked off  
- Named pytest scenarios from `TEST_PLAN.md` exist and pass  
- Server starts via uvicorn; demo client runs  
- CI green on GitHub Actions  
- README reflects implemented state (not empty placeholder)
