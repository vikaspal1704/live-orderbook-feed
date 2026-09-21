# API Contract

**Normative.** Implementations MUST match these JSON field names and behaviors.  
Transport: JSON text frames over WebSocket; JSON over HTTP for REST.

---

## 1. Common conventions

| Topic | Rule |
|-------|------|
| Symbol | String; v1 sole value `DEMO/USD` |
| Prices / quantities | JSON **numbers that are integers** (no fractional floats in v1) |
| Timestamps `ts` | Integer **Unix epoch milliseconds** (UTC) |
| `seq` | Non-negative integer; book version (see ARCHITECTURE §4) |
| Side | `"BID"` or `"ASK"` only |
| Unknown fields | Clients/servers SHOULD ignore unknown fields (forward compatible) |

---

## 2. WebSocket endpoint

| Item | Value |
|------|-------|
| URL | `WS /v1/ws` |
| Subprotocol | none required |
| Encoding | UTF-8 JSON text frames |

### 2.1 Client → server messages

#### `subscribe`

```json
{
  "type": "subscribe",
  "symbol": "DEMO/USD",
  "client_id": "optional-string-id"
}
```

| Field | Required | Rules |
|-------|----------|-------|
| `type` | yes | Must be `"subscribe"` |
| `symbol` | yes | Must equal configured instrument or error `UNKNOWN_SYMBOL` |
| `client_id` | no | Opaque string for logs; max 128 chars recommended |

**Server behavior:** Register client for symbol; send one `snapshot` with `seq = last_seq`. Re-subscribe to same symbol → send a **fresh snapshot** (idempotent).

#### `unsubscribe`

```json
{
  "type": "unsubscribe",
  "symbol": "DEMO/USD"
}
```

Stop fan-out for this client for that symbol; connection may remain open.

#### `pong` (optional client heartbeat response)

```json
{
  "type": "pong",
  "ts": 1760000000500
}
```

Server MAY ignore; reserved for liveness extensions.

#### `resnapshot` (COULD — not required for v1 acceptance)

```json
{
  "type": "resnapshot",
  "symbol": "DEMO/USD"
}
```

If implemented: send a fresh `snapshot` with current `last_seq` without disconnecting.

### 2.2 Server → client messages

#### `snapshot`

```json
{
  "type": "snapshot",
  "symbol": "DEMO/USD",
  "seq": 3,
  "ts": 1760000000400,
  "bids": [
    {"price": 99, "quantity": 4}
  ],
  "asks": [
    {"price": 101, "quantity": 3}
  ]
}
```

| Field | Type | Rules |
|-------|------|-------|
| `type` | string | `"snapshot"` |
| `symbol` | string | Instrument |
| `seq` | int | Current book version (`>= 0`) |
| `ts` | int | Event time ms |
| `bids` | array | Sorted **price descending**; elements `BookLevel` |
| `asks` | array | Sorted **price ascending**; elements `BookLevel` |

`BookLevel`:

| Field | Type | Rules |
|-------|------|-------|
| `price` | int | `>= 1` |
| `quantity` | int | `>= 1` (empty levels omitted; never send qty 0 in snapshot) |

#### `delta`

```json
{
  "type": "delta",
  "symbol": "DEMO/USD",
  "seq": 4,
  "ts": 1760000000600,
  "changes": [
    {"side": "BID", "price": 99, "quantity": 10},
    {"side": "ASK", "price": 101, "quantity": 0}
  ]
}
```

| Field | Type | Rules |
|-------|------|-------|
| `type` | string | `"delta"` |
| `symbol` | string | Instrument |
| `seq` | int | `>= 1` after first tick; strictly increases per tick |
| `ts` | int | Event time ms |
| `changes` | array | Length `>= 1`; applied in array order |

`Change`:

| Field | Type | Rules |
|-------|------|-------|
| `side` | string | `"BID"` \| `"ASK"` |
| `price` | int | `>= 1` |
| `quantity` | int | `>= 0`; **`0` means delete level** |

#### `heartbeat`

```json
{
  "type": "heartbeat",
  "ts": 1760000000500
}
```

| Field | Type | Rules |
|-------|------|-------|
| `type` | string | `"heartbeat"` |
| `ts` | int | Server time ms |

Does **not** include `seq`. Does **not** mutate client book.

#### `error`

```json
{
  "type": "error",
  "code": "UNKNOWN_SYMBOL",
  "message": "symbol not supported: FOO/BAR",
  "ts": 1760000000700
}
```

| `code` | When |
|--------|------|
| `BAD_REQUEST` | Malformed JSON or unknown `type` / missing fields |
| `UNKNOWN_SYMBOL` | Subscribe symbol not configured |
| `SLOW_CONSUMER` | Optional last message before close on queue overflow |
| `INTERNAL` | Unexpected server failure |

### 2.3 WebSocket close codes

| Code | Meaning |
|------|---------|
| `1000` | Normal close |
| `1013` | Slow consumer / try again later (**locked** for queue overflow) |
| `1008` | Policy violation (optional alternate; prefer 1013 for slow consumer) |

---

## 3. REST endpoints

### `GET /health`

**200 OK**

```json
{
  "status": "ok",
  "symbol": "DEMO/USD",
  "last_seq": 3,
  "subscribers": 2,
  "feed_alive": true
}
```

| Field | Type | Rules |
|-------|------|-------|
| `status` | string | `"ok"` when process serving |
| `symbol` | string | Configured instrument |
| `last_seq` | int | Current book seq |
| `subscribers` | int | Current WS subscriber count for symbol |
| `feed_alive` | bool | Feed task heartbeat flag |

### `GET /v1/book/{symbol}`

Path parameter `symbol` must be URL-decoded (e.g. `DEMO%2FUSD` → `DEMO/USD`).

**200 OK**

```json
{
  "symbol": "DEMO/USD",
  "seq": 3,
  "ts": 1760000000400,
  "bids": [
    {"price": 99, "quantity": 4}
  ],
  "asks": [
    {"price": 101, "quantity": 3}
  ]
}
```

Same level sorting rules as WS snapshot. No `type` field on REST.

**404 Not Found** if symbol ≠ configured instrument:

```json
{
  "detail": "unknown symbol: FOO/BAR"
}
```

---

## 4. Pydantic / Python model names (recommended)

Not required to export as a library API, but models SHOULD exist for validation:

```text
Side: Literal["BID", "ASK"]
BookLevel: price: int, quantity: int
Change: side: Side, price: int, quantity: int
SubscribeMessage, UnsubscribeMessage
SnapshotMessage, DeltaMessage, HeartbeatMessage, ErrorMessage
HealthResponse, BookResponse
```

---

## 5. Behavioral invariants

1. **Single sequence space:** Deltas after a snapshot with `seq = S` (S ≥ 1) arrive as S+1, S+2, … with no gaps on a healthy connection.
2. **Snapshot completeness:** Applying no deltas, client book equals snapshot levels.
3. **Delta apply:** For each change in order: if `quantity == 0` remove `(side, price)`; else set level qty.
4. **Fan-out isolation:** Disconnecting client A must not prevent client B from receiving the same `seq`.
5. **Slow consumer:** Queue overflow → that client dropped; feed continues.
6. **No matching engine:** No order ids, trades, or match events in this API.
7. **Determinism under manual ticks:** Same tick inject sequence → same `seq` and payloads.

---

## 6. Non-guarantees

- Delivery after disconnect (no durable replay).
- Exactly-once across reconnects (reconnect → new snapshot; client resets).
- Multi-worker consistency.
- Wall-clock tick timing precision under load.

---

## 7. OpenAPI

FastAPI SHOULD expose OpenAPI for REST routes only. WebSocket message schemas are defined in this document (not necessarily in OpenAPI).
