"""Feed: owns the book and sequencer; turns ticks into sequenced deltas for the hub.

All mutation happens on the event loop (feed task or test injection), never on threads.
"""

import asyncio
import logging
import time
from collections.abc import Callable

from .book import OrderBook
from .hub import Hub
from .models import BookResponse, Change, DeltaMessage, SnapshotMessage
from .sequencer import Sequencer
from .tick_source import TickSource

logger = logging.getLogger(__name__)

Clock = Callable[[], int]


def now_ms() -> int:
    return time.time_ns() // 1_000_000


class Feed:
    def __init__(self, symbol: str, depth: int, hub: Hub, clock: Clock = now_ms) -> None:
        self.symbol = symbol
        self.depth = depth
        self.hub = hub
        self.clock = clock
        self.book = OrderBook()
        self.sequencer = Sequencer()
        self._task: asyncio.Task[None] | None = None

    @property
    def last_seq(self) -> int:
        return self.sequencer.last_seq

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    def apply_tick(self, changes: list[Change]) -> DeltaMessage:
        """Apply one tick, advance ``seq`` and fan the delta out to subscribers."""
        if not changes:
            raise ValueError("a tick must contain at least one change")
        self.book.apply_changes(changes)
        delta = DeltaMessage(
            symbol=self.symbol, seq=self.sequencer.next_seq(), ts=self.clock(), changes=changes
        )
        self.hub.broadcast(delta.model_dump_json())
        logger.debug("applied tick seq=%d changes=%d", delta.seq, len(changes))
        return delta

    def snapshot(self) -> SnapshotMessage:
        """Current top-N book at ``last_seq`` (does not advance ``seq``)."""
        return SnapshotMessage(**self.book_response().model_dump())

    def book_response(self) -> BookResponse:
        return BookResponse(
            symbol=self.symbol,
            seq=self.last_seq,
            ts=self.clock(),
            bids=self.book.bids(self.depth),
            asks=self.book.asks(self.depth),
        )

    def start(self, source: TickSource) -> None:
        self._task = asyncio.create_task(self._run(source), name="feed")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self, source: TickSource) -> None:
        try:
            async for tick in source.ticks():
                self.apply_tick(tick.changes)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("feed loop crashed at seq=%d", self.last_seq)
            raise
        logger.info("tick source exhausted at seq=%d; serving final book", self.last_seq)
        await asyncio.Event().wait()
