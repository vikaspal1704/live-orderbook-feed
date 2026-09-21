# Test Plan

**Framework:** pytest + pytest-asyncio  
**Location:** `tests/`  
**Rule:** Prefer Arrange-Act-Assert; one behavior per test; use exact function names required by ACCEPTANCE_CRITERIA.  
**Stack:** FastAPI app via ASGI; prefer injecting a **manual** tick source so tests are deterministic (no wall-clock flakiness).

---

## 1. Matrix overview

| Area | Must cover |
|------|------------|
| Book unit | apply, remove (qty 0), sort order, depth trim |
| Sequencing | last_seq advances per tick; snapshot reuses last_seq |
| WS protocol | subscribe → snapshot → deltas; unknown symbol; unsubscribe |
| Heartbeat | server emits heartbeat |
| Backpressure | slow client dropped; fast client continues |
| REST | health, book 200, unknown 404 |
| Canonical | ARCHITECTURE worked example |
| Negative | bad JSON / unknown type → error |

---

## 2. Required tests (names + scenario)

### Book / ticks

| Test | Setup | Expect |
|------|-------|--------|
| `test_book_apply_level_and_remove` | apply BID 100 qty 5; then qty 0 | level present then absent |
| `test_book_snapshot_sort_order` | bids 100,99; asks 101,102 | bid prices `[100,99]`; ask `[101,102]` |
| `test_manual_tick_advances_seq` | 3 manual ticks | `last_seq == 3` |

### WebSocket protocol

| Test | Setup | Expect |
|------|-------|--------|
| `test_subscribe_receives_snapshot_then_deltas` | connect, subscribe, inject 1+ ticks | first book msg `snapshot`; later `delta` |
| `test_snapshot_seq_matches_book` | ticks to seq=2; subscribe | snapshot.seq == 2 |
| `test_delta_seq_monotonic` | subscribe; inject 3 ticks | delta seqs consecutive |
| `test_delta_quantity_zero_removes_level` | establish level; delta qty 0 | REST/book no longer has level |
| `test_subscribe_unknown_symbol_error` | subscribe `FOO/BAR` | `type=error`, `code=UNKNOWN_SYMBOL` |
| `test_unsubscribe_stops_deltas` | subscribe; unsubscribe; inject ticks | no deltas after unsubscribe |
| `test_bad_json_error` | send not-JSON or missing type | `code=BAD_REQUEST` |

### Heartbeat / backpressure

| Test | Setup | Expect |
|------|-------|--------|
| `test_heartbeat_received` | connect (subscribed or not — document choice: **after subscribe**); set short heartbeat interval in fixture | receive `heartbeat` within timeout |
| `test_slow_consumer_disconnected` | set tiny `CLIENT_QUEUE_MAX`; pause client reads; flood ticks | client disconnected; close code 1013 or equivalent assertion on hub removal |
| `test_fast_consumer_unaffected_by_slow` | two clients; slow one stalls; fast one reads | fast client still receives increasing seq |

### REST

| Test | Setup | Expect |
|------|-------|--------|
| `test_health_ok` | GET `/health` | 200; `status=="ok"`; `feed_alive is True` |
| `test_rest_book_demo_usd` | apply levels; GET `/v1/book/DEMO%2FUSD` | 200; matching bids/asks/seq |
| `test_rest_book_unknown_404` | GET `/v1/book/FOO%2FBAR` | 404 |

### Canonical

| Test | Setup | Expect |
|------|-------|--------|
| `test_worked_example_subscribe_snapshot_deltas` | Follow ARCHITECTURE §7: subscribe empty → tick bid → tick ask+bid → tick remove/add → second subscriber snapshot at seq=3 | Exact seq progression and level outcomes |

---

## 3. Fixtures (recommended)

| Fixture | Role |
|---------|------|
| `app` | FastAPI app with `TICK_MODE=manual`, short heartbeat, small queue for BP tests |
| `client` | `httpx.AsyncClient` ASGI transport |
| `ws_connect` | helper to open `/v1/ws` |
| `inject_tick` | call hub/book API to apply a change and fan-out |

Prefer **no real sleep** except heartbeat test (use monkeypatched interval 0.05s and wait ≤1s).

---

## 4. Edge cases (should include)

| Case | Notes |
|------|-------|
| Re-subscribe same symbol | Second snapshot at current seq |
| Multiple changes in one delta | `changes` length > 1 applied in order |
| Empty book snapshot | `bids=[]`, `asks=[]`, `seq=0` allowed |
| Depth trim | Levels beyond N omitted from snapshot |
| Client disconnect mid-stream | Hub scrubbed; no crash on next fan-out |
| Concurrent two subscribers | Same seq payloads (equal content) |

---

## 5. Non-goals for tests

- Load tests / thousands of clients not required for v1 acceptance
- Real Binance/Polygon integration tests not required
- Multi-worker tests not required for v1
- Property-based fuzzing optional

---

## 6. Commands

```bash
pip install -e ".[dev]"
pytest -q
pytest -q tests/test_worked_example.py  # optional path split
```

CI MUST run the full suite with no skips for required tests and **without** external market-data credentials.
