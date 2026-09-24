import itertools
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from orderbook_feed.app import create_app
from orderbook_feed.config import Settings
from orderbook_feed.models import Change, DeltaMessage

SYMBOL = "DEMO/USD"
BASE_SETTINGS = Settings(
    symbol=SYMBOL,
    tick_mode="manual",
    heartbeat_interval_sec=60.0,  # effectively off unless a test shortens it
    client_queue_max=64,
    book_depth_levels=10,
)

TickSpec = tuple[str, int, int]


class FakeClock:
    """Deterministic epoch-ms clock: 1760000000000, +100 per call."""

    def __init__(self) -> None:
        self._ticks = itertools.count(1760000000000, 100)

    def __call__(self) -> int:
        return next(self._ticks)


def changes_of(*specs: TickSpec) -> list[Change]:
    return [Change(side=side, price=price, quantity=quantity) for side, price, quantity in specs]


class Harness:
    """A running app (lifespan started) plus a helper to inject manual ticks on its loop."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.feed = client.app.state.feed

    def inject(self, *specs: TickSpec) -> DeltaMessage:
        return self.client.portal.call(self.feed.apply_tick, changes_of(*specs))

    def inject_many(self, ticks: list[list[TickSpec]]) -> None:
        """Apply several ticks in one event-loop call, so no writer runs in between."""

        def apply_all() -> None:
            for specs in ticks:
                self.feed.apply_tick(changes_of(*specs))

        self.client.portal.call(apply_all)

    def ws(self):
        return self.client.websocket_connect("/v1/ws")


@pytest.fixture
def make_harness() -> Iterator[Callable[..., Harness]]:
    with ExitStack() as stack:

        def factory(**overrides) -> Harness:
            app = create_app(replace(BASE_SETTINGS, **overrides), clock=FakeClock())
            return Harness(stack.enter_context(TestClient(app)))

        yield factory


@pytest.fixture
def harness(make_harness) -> Harness:
    return make_harness()


def subscribe(ws, symbol: str = SYMBOL, client_id: str | None = "test") -> dict:
    ws.send_json({"type": "subscribe", "symbol": symbol, "client_id": client_id})
    return receive_non_heartbeat(ws)


def receive_non_heartbeat(ws) -> dict:
    while True:
        msg = ws.receive_json()
        if msg["type"] != "heartbeat":
            return msg


def fence(ws) -> None:
    """Round-trip a request so everything the client sent before is processed."""
    ws.send_json({"type": "subscribe", "symbol": "FENCE/XXX"})
    msg = receive_non_heartbeat(ws)
    assert msg["type"] == "error" and msg["code"] == "UNKNOWN_SYMBOL", msg
