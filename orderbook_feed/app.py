"""FastAPI application. Run with ``uvicorn orderbook_feed.app:app``."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__, rest, ui, ws
from .config import Settings
from .feed import Clock, Feed, now_ms
from .hub import Hub, run_heartbeats
from .tick_source import TickSource, build_tick_source

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    tick_source: TickSource | None = None,
    clock: Clock = now_ms,
) -> FastAPI:
    settings = settings or Settings.from_env()
    hub = Hub(settings.client_queue_max)
    feed = Feed(settings.symbol, settings.book_depth_levels, hub, clock)
    source = tick_source or build_tick_source(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("starting feed: symbol=%s mode=%s", settings.symbol, settings.tick_mode)
        feed.start(source)
        heartbeats = asyncio.create_task(
            run_heartbeats(hub, settings.heartbeat_interval_sec, clock), name="heartbeats"
        )
        try:
            yield
        finally:
            heartbeats.cancel()
            await asyncio.gather(heartbeats, return_exceptions=True)
            await feed.stop()

    app = FastAPI(
        title="Live Orderbook Feed",
        description="Educational L2 order-book WebSocket fan-out service (WS: /v1/ws).",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.feed = feed
    app.include_router(rest.router)
    app.include_router(ws.router)
    app.include_router(ui.router)
    return app


app = create_app()
