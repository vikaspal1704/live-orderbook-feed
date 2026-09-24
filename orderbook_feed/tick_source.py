"""Tick sources: produce L2 level changes. They never talk to clients.

- ``SyntheticTickSource``: seeded random walk around a mid price (no API keys).
- ``ReplayTickSource``: newline-delimited JSON file, one ``Tick`` per line.
- ``ManualTickSource``: yields nothing; tests inject ticks via ``Feed.apply_tick``.
"""

import asyncio
import random
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from .config import Settings
from .models import Change, Side, Tick


class TickSource(Protocol):
    def ticks(self) -> AsyncIterator[Tick]: ...


class ManualTickSource:
    """Never yields: ticks are injected directly (deterministic tests)."""

    async def ticks(self) -> AsyncIterator[Tick]:
        await asyncio.Event().wait()
        yield  # pragma: no cover - unreachable, makes this an async generator


class SyntheticTickSource:
    """Seeded random L2 updates in a band of ``depth`` levels either side of a mid price.

    The first tick seeds the full band; later ticks update 1-3 levels and occasionally
    move the mid by one tick, removing levels that fall outside the band so the
    synthetic book never crosses.
    """

    MAX_QUANTITY = 50

    def __init__(
        self, *, interval_ms: int, depth: int, seed: int | None = None, mid: int = 100
    ) -> None:
        if mid <= depth:
            raise ValueError("mid must exceed depth so all prices stay >= 1")
        self._interval_sec = interval_ms / 1000
        self._depth = depth
        self._rng = random.Random(seed)
        self._mid = mid
        self._levels: dict[tuple[Side, int], int] = {}

    async def ticks(self) -> AsyncIterator[Tick]:
        yield self.initial_tick()
        while True:
            await asyncio.sleep(self._interval_sec)
            yield self.next_tick()

    def initial_tick(self) -> Tick:
        changes: dict[tuple[Side, int], int] = {}
        for offset in range(1, self._depth + 1):
            changes[("BID", self._mid - offset)] = self._random_quantity()
            changes[("ASK", self._mid + offset)] = self._random_quantity()
        return self._commit(changes)

    def next_tick(self) -> Tick:
        changes: dict[tuple[Side, int], int] = {}
        if self._rng.random() < 0.2:
            self._mid = max(self._depth + 1, self._mid + self._rng.choice((-1, 1)))
            for side, price in self._levels:
                if not self._in_band(side, price):
                    changes[(side, price)] = 0

        for _ in range(self._rng.randint(1, 3)):
            side: Side = self._rng.choice(("BID", "ASK"))
            offset = self._rng.randint(1, self._depth)
            price = self._mid - offset if side == "BID" else self._mid + offset
            quantity = 0 if self._rng.random() < 0.15 else self._random_quantity()
            if quantity == 0 and (side, price) not in self._levels:
                continue  # deleting an absent level is a no-op
            changes[(side, price)] = quantity

        if not changes:
            return self.next_tick()
        return self._commit(changes)

    def _in_band(self, side: Side, price: int) -> bool:
        if side == "BID":
            return self._mid - self._depth <= price < self._mid
        return self._mid < price <= self._mid + self._depth

    def _random_quantity(self) -> int:
        return self._rng.randint(1, self.MAX_QUANTITY)

    def _commit(self, changes: dict[tuple[Side, int], int]) -> Tick:
        for key, quantity in changes.items():
            if quantity == 0:
                self._levels.pop(key, None)
            else:
                self._levels[key] = quantity
        return Tick(
            changes=[
                Change(side=side, price=price, quantity=quantity)
                for (side, price), quantity in changes.items()
            ]
        )


class ReplayTickSource:
    """Replays an NDJSON file (``{"changes": [...]}`` per line), then stops."""

    def __init__(self, path: str | Path, *, interval_ms: int) -> None:
        self._ticks = load_replay_file(path)
        self._interval_sec = interval_ms / 1000

    async def ticks(self) -> AsyncIterator[Tick]:
        for index, tick in enumerate(self._ticks):
            if index:
                await asyncio.sleep(self._interval_sec)
            yield tick


def load_replay_file(path: str | Path) -> list[Tick]:
    ticks: list[Tick] = []
    with open(path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                ticks.append(Tick.model_validate_json(line))
            except ValidationError as exc:
                raise ValueError(f"{path}:{line_no}: invalid tick: {exc}") from exc
    return ticks


def build_tick_source(settings: Settings) -> TickSource:
    if settings.tick_mode == "manual":
        return ManualTickSource()
    if settings.tick_mode == "replay":
        assert settings.replay_path is not None  # enforced by Settings
        return ReplayTickSource(settings.replay_path, interval_ms=settings.tick_interval_ms)
    return SyntheticTickSource(
        interval_ms=settings.tick_interval_ms,
        depth=settings.book_depth_levels,
        seed=settings.synthetic_seed,
    )
