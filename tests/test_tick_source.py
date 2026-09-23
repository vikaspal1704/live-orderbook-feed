import json

import pytest

from orderbook_feed.book import OrderBook
from orderbook_feed.config import Settings
from orderbook_feed.tick_source import (
    ManualTickSource,
    ReplayTickSource,
    SyntheticTickSource,
    build_tick_source,
    load_replay_file,
)


def _run_synthetic(seed: int, ticks: int = 200):
    source = SyntheticTickSource(interval_ms=0, depth=5, seed=seed)
    return [source.initial_tick()] + [source.next_tick() for _ in range(ticks)]


def test_synthetic_is_deterministic_with_seed():
    assert _run_synthetic(seed=7) == _run_synthetic(seed=7)


def test_synthetic_book_never_crosses_and_quantities_valid():
    book = OrderBook()
    for tick in _run_synthetic(seed=42, ticks=1000):
        assert tick.changes
        book.apply_changes(tick.changes)
        bids, asks = book.bids(), book.asks()
        if bids and asks:
            assert bids[0].price < asks[0].price
        assert all(level.price >= 1 and level.quantity >= 1 for level in bids + asks)


def test_synthetic_initial_tick_fills_band():
    tick = SyntheticTickSource(interval_ms=0, depth=3, seed=1, mid=100).initial_tick()

    bids = sorted(c.price for c in tick.changes if c.side == "BID")
    asks = sorted(c.price for c in tick.changes if c.side == "ASK")
    assert (bids, asks) == ([97, 98, 99], [101, 102, 103])


async def test_synthetic_async_iterator_yields_ticks():
    source = SyntheticTickSource(interval_ms=0, depth=3, seed=1)
    ticks = []
    async for tick in source.ticks():
        ticks.append(tick)
        if len(ticks) == 3:
            break

    assert len(ticks) == 3


async def test_replay_reads_ndjson(tmp_path):
    path = tmp_path / "ticks.ndjson"
    path.write_text(
        json.dumps({"changes": [{"side": "BID", "price": 100, "quantity": 5}]})
        + "\n\n"
        + json.dumps({"changes": [{"side": "BID", "price": 100, "quantity": 0}]})
        + "\n"
    )

    ticks = [tick async for tick in ReplayTickSource(path, interval_ms=0).ticks()]

    assert [[c.quantity for c in t.changes] for t in ticks] == [[5], [0]]


@pytest.mark.parametrize(
    "line",
    [
        '{"changes": []}',
        '{"changes": [{"side": "bid", "price": 100, "quantity": 5}]}',
        '{"changes": [{"side": "BID", "price": 0, "quantity": 5}]}',
        '{"changes": [{"side": "BID", "price": 100, "quantity": -1}]}',
        '{"changes": [{"side": "BID", "price": 100.5, "quantity": 1}]}',
        "not json",
    ],
)
def test_replay_rejects_invalid_lines(tmp_path, line):
    path = tmp_path / "bad.ndjson"
    path.write_text(line + "\n")

    with pytest.raises(ValueError, match="bad.ndjson:1"):
        load_replay_file(path)


def test_sample_replay_file_is_valid():
    assert len(load_replay_file("samples/demo_ticks.ndjson")) >= 3


def test_build_tick_source_by_mode(tmp_path):
    path = tmp_path / "t.ndjson"
    path.write_text('{"changes": [{"side": "ASK", "price": 101, "quantity": 1}]}\n')

    assert isinstance(build_tick_source(Settings(tick_mode="manual")), ManualTickSource)
    assert isinstance(build_tick_source(Settings(tick_mode="synthetic")), SyntheticTickSource)
    assert isinstance(
        build_tick_source(Settings(tick_mode="replay", replay_path=str(path))), ReplayTickSource
    )


def test_settings_reject_invalid_values():
    with pytest.raises(ValueError):
        Settings(tick_mode="replay")
    with pytest.raises(ValueError):
        Settings(tick_mode="live")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Settings(client_queue_max=0)


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("TICK_MODE", "manual")
    monkeypatch.setenv("CLIENT_QUEUE_MAX", "8")
    monkeypatch.setenv("HEARTBEAT_INTERVAL_SEC", "0.5")

    settings = Settings.from_env()

    assert settings.tick_mode == "manual"
    assert settings.client_queue_max == 8
    assert settings.heartbeat_interval_sec == 0.5
    assert settings.symbol == "DEMO/USD"
