# Acceptance Criteria

Binary checklist. v1 is **done** only when every box is true.

---

## A. PRD MUST → verifiable criteria

| PRD ID | Criterion | How to verify |
|--------|-----------|---------------|
| F-MUST-1 | Single instrument default `DEMO/USD` | `test_rest_book_demo_usd`, `test_subscribe_unknown_symbol_error` |
| F-MUST-2 | In-memory L2 from synthetic/replay/manual ticks | `test_book_apply_level_and_remove`, `test_manual_tick_advances_seq` |
| F-MUST-3 | WS subscribe → snapshot then deltas | `test_subscribe_receives_snapshot_then_deltas`, `test_worked_example_subscribe_snapshot_deltas` |
| F-MUST-4 | Monotonic `seq` on book messages | `test_delta_seq_monotonic`, `test_snapshot_seq_matches_book` |
| F-MUST-5 | Deltas carry side/price/qty; 0 removes level | `test_delta_quantity_zero_removes_level` |
| F-MUST-6 | Server heartbeats | `test_heartbeat_received` |
| F-MUST-7 | Slow-consumer disconnect without stalling others | `test_slow_consumer_disconnected`, `test_fast_consumer_unaffected_by_slow` |
| F-MUST-8 | REST health + book | `test_health_ok`, `test_rest_book_demo_usd`, `test_rest_book_unknown_404` |
| F-MUST-9 | No API keys required; deterministic manual mode | `test_manual_tick_advances_seq` (CI has no secrets) |
| F-MUST-10 | No matching engine in repo | Review: no match/trade order APIs; ARCHITECTURE non-component |

---

## B. Required pytest scenarios (by exact test function name)

These function names MUST exist under `tests/` and pass:

| Test function | Intent |
|---------------|--------|
| `test_book_apply_level_and_remove` | Unit: set level then qty 0 removes |
| `test_book_snapshot_sort_order` | Bids desc, asks asc |
| `test_manual_tick_advances_seq` | Inject ticks → last_seq 1..n |
| `test_subscribe_receives_snapshot_then_deltas` | WS: snapshot then at least one delta |
| `test_snapshot_seq_matches_book` | Subscribe snapshot.seq == health/last_seq |
| `test_delta_seq_monotonic` | Consecutive deltas increase by 1 |
| `test_delta_quantity_zero_removes_level` | Apply delta remove; REST book reflects |
| `test_subscribe_unknown_symbol_error` | error code `UNKNOWN_SYMBOL` |
| `test_heartbeat_received` | Receive `type=heartbeat` within interval budget |
| `test_slow_consumer_disconnected` | Fill queue → client dropped / close 1013 |
| `test_fast_consumer_unaffected_by_slow` | Second client still gets seq stream |
| `test_health_ok` | GET /health → 200, status ok, feed_alive true |
| `test_rest_book_demo_usd` | GET book returns bids/asks/seq |
| `test_rest_book_unknown_404` | Unknown symbol → 404 |
| `test_unsubscribe_stops_deltas` | After unsubscribe, no further deltas to that client |
| `test_worked_example_subscribe_snapshot_deltas` | ARCHITECTURE §7 steps (empty snap → ticks → late subscriber snap) |

Additional tests from TEST_PLAN are encouraged; the table above is the **minimum name set**.

---

## C. Demo

- [ ] `uvicorn orderbook_feed.app:app` (or documented entry) starts listening
- [ ] `python -m demo.ws_client` exits 0 against a running server (or documented test double)
- [ ] Stdout includes a snapshot and at least one delta
- [ ] Demo speaks only public JSON protocol

---

## D. Packaging & CI

- [ ] `pyproject.toml` present; `pip install -e ".[dev]"` works
- [ ] Runtime deps include FastAPI + uvicorn (stack lock)
- [ ] `pytest -q` green locally
- [ ] `.github/workflows/ci.yml` runs pytest on push/PR
- [ ] CI green on default branch after merge
- [ ] CI does **not** require market-data API keys

---

## E. Docs / README polish

- [ ] Root `README.md` replaced (no GitHub empty-repo placeholder text)
- [ ] README status updated when implementation lands (e.g. “Implemented — see tests/CI”)
- [ ] README links sibling mini-matching-engine and states no matching engine here
- [ ] `LICENSE` is MIT © Vikas Pal 2026
- [ ] `AGENTS.md` points to `docs/AGENT_BRIEF.md`
- [ ] Stack lock (FastAPI) reflected in README + TRD

---

## F. Definition of done (copy for agents)

```
DONE when:
1. All section A criteria pass via section B tests.
2. Section C demo runs.
3. Section D CI green (no vendor API keys).
4. Section E README is project README (not placeholder).
5. No WS/REST field divergence from API_CONTRACT.md.
6. No matching-engine code in this repository.
```
