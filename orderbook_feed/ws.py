"""WebSocket route ``/v1/ws``: subscribe lifecycle and per-client writer."""

import logging
from collections.abc import Awaitable, Callable

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .feed import Feed
from .hub import SLOW_CONSUMER_CLOSE_CODE, Connection
from .models import (
    ErrorCode,
    ErrorMessage,
    PongMessage,
    ResnapshotMessage,
    SubscribeMessage,
    UnsubscribeMessage,
    client_message_adapter,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    feed: Feed = websocket.app.state.feed
    await websocket.accept()
    conn = feed.hub.connect()
    logger.info("client connected")

    try:
        # Reader and writer run concurrently; whichever ends first ends the connection.
        async with anyio.create_task_group() as tg:
            for loop in (_read_loop, _write_loop):
                tg.start_soon(_run_until_done, loop, websocket, feed, conn, tg.cancel_scope)
    finally:
        feed.hub.disconnect(conn)
        logger.info("client disconnected: client_id=%s", conn.client_id)


async def _run_until_done(
    loop: Callable[[WebSocket, Feed, Connection], Awaitable[None]],
    websocket: WebSocket,
    feed: Feed,
    conn: Connection,
    scope: anyio.CancelScope,
) -> None:
    try:
        await loop(websocket, feed, conn)
    except (WebSocketDisconnect, OSError) as exc:
        logger.debug("connection closed during %s: %r", loop.__name__, exc)
    except Exception:
        logger.exception("unexpected error in %s", loop.__name__)
    finally:
        scope.cancel()


async def _read_loop(websocket: WebSocket, feed: Feed, conn: Connection) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        text = message.get("text")
        if text is None:
            _send_error(feed, conn, "BAD_REQUEST", "binary frames are not supported")
            continue
        handle_client_text(feed, conn, text)


async def _write_loop(websocket: WebSocket, feed: Feed, conn: Connection) -> None:
    while True:
        text = await conn.next_message()
        if text is None:
            error = _error(feed, "SLOW_CONSUMER", "client queue overflow; reconnect to resume")
            await websocket.send_text(error.model_dump_json())
            await websocket.close(code=SLOW_CONSUMER_CLOSE_CODE)
            return
        await websocket.send_text(text)


def handle_client_text(feed: Feed, conn: Connection, text: str) -> None:
    """Parse one client frame and enqueue any response on ``conn``."""
    try:
        msg = client_message_adapter.validate_json(text)
    except ValidationError as exc:
        _send_error(feed, conn, "BAD_REQUEST", f"invalid message: {exc.errors()[0]['msg']}")
        return

    if isinstance(msg, PongMessage):
        return
    if msg.symbol != feed.symbol:
        _send_error(feed, conn, "UNKNOWN_SYMBOL", f"symbol not supported: {msg.symbol}")
        return

    if isinstance(msg, SubscribeMessage):
        conn.client_id = msg.client_id
        feed.hub.subscribe(conn, feed.snapshot().model_dump_json())
        logger.info("client subscribed: client_id=%s seq=%d", conn.client_id, feed.last_seq)
    elif isinstance(msg, UnsubscribeMessage):
        feed.hub.unsubscribe(conn)
        logger.info("client unsubscribed: client_id=%s", conn.client_id)
    elif isinstance(msg, ResnapshotMessage):
        if not conn.subscribed:
            _send_error(feed, conn, "BAD_REQUEST", "resnapshot requires an active subscription")
            return
        feed.hub.send(conn, feed.snapshot().model_dump_json())


def _error(feed: Feed, code: ErrorCode, message: str) -> ErrorMessage:
    return ErrorMessage(code=code, message=message, ts=feed.clock())


def _send_error(feed: Feed, conn: Connection, code: ErrorCode, message: str) -> None:
    feed.hub.send(conn, _error(feed, code, message).model_dump_json())
