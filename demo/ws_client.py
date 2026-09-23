"""Demo WebSocket client: subscribe, print the snapshot, apply N deltas, exit 0.

Run a server first (``uvicorn orderbook_feed.app:app``), then ``python -m demo.ws_client``.
Speaks only the public JSON protocol in docs/API_CONTRACT.md.

Environment overrides: FEED_WS_URL, FEED_SYMBOL, DEMO_DELTAS, DEMO_TIMEOUT_SEC.
"""

import asyncio
import json
import os
import sys

import websockets

DEFAULT_URL = "ws://127.0.0.1:8000/v1/ws"
# Treat silence for ~3 heartbeat intervals (default 5 s) as a dead connection.
DEFAULT_TIMEOUT_SEC = 15.0


class LocalBook:
    def __init__(self) -> None:
        self.bids: dict[int, int] = {}
        self.asks: dict[int, int] = {}

    def load(self, snapshot: dict) -> None:
        self.bids = {level["price"]: level["quantity"] for level in snapshot["bids"]}
        self.asks = {level["price"]: level["quantity"] for level in snapshot["asks"]}

    def apply(self, delta: dict) -> None:
        for change in delta["changes"]:
            levels = self.bids if change["side"] == "BID" else self.asks
            if change["quantity"] == 0:
                levels.pop(change["price"], None)
            else:
                levels[change["price"]] = change["quantity"]

    def render(self, depth: int = 5) -> str:
        asks = sorted(self.asks.items())[:depth]
        bids = sorted(self.bids.items(), reverse=True)[:depth]
        lines = [f"    ASK {price:>6} x {qty}" for price, qty in reversed(asks)]
        lines.append("    " + "-" * 18)
        lines += [f"    BID {price:>6} x {qty}" for price, qty in bids]
        return "\n".join(lines)


async def run(url: str, symbol: str, deltas: int, timeout: float) -> int:
    book = LocalBook()
    last_seq: int | None = None
    applied = 0

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "subscribe", "symbol": symbol, "client_id": "demo"}))
        print(f"-> subscribe {symbol} @ {url}")

        while applied < deltas:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            kind = msg["type"]

            if kind == "snapshot":
                book.load(msg)
                last_seq = msg["seq"]
                levels = f"bids={len(msg['bids'])} asks={len(msg['asks'])}"
                print(f"<- snapshot seq={msg['seq']} {levels}")
                print(book.render())
            elif kind == "delta":
                if last_seq is None or msg["seq"] <= last_seq:
                    continue  # waiting for a snapshot, or stale
                if msg["seq"] != last_seq + 1:
                    print(f"!! gap: expected seq={last_seq + 1}, got {msg['seq']}; resnapshot")
                    last_seq = None
                    await ws.send(json.dumps({"type": "resnapshot", "symbol": symbol}))
                    continue
                book.apply(msg)
                last_seq = msg["seq"]
                applied += 1
                changes = ", ".join(
                    f"{c['side']} {c['price']}={c['quantity']}" for c in msg["changes"]
                )
                print(f"<- delta seq={msg['seq']} [{changes}]")
            elif kind == "heartbeat":
                print(f"<- heartbeat ts={msg['ts']}")
            elif kind == "error":
                print(f"<- error {msg['code']}: {msg['message']}", file=sys.stderr)
                return 1

    print(f"final local book after seq={last_seq}:")
    print(book.render())
    return 0


def main() -> int:
    url = os.environ.get("FEED_WS_URL", DEFAULT_URL)
    symbol = os.environ.get("FEED_SYMBOL", "DEMO/USD")
    deltas = int(os.environ.get("DEMO_DELTAS", "5"))
    timeout = float(os.environ.get("DEMO_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC))
    try:
        return asyncio.run(run(url, symbol, deltas, timeout))
    except (OSError, TimeoutError, websockets.ConnectionClosed) as exc:
        print(f"demo client failed: {exc!r} (is the server running at {url}?)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
