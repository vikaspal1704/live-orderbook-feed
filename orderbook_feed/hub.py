"""Fan-out hub: per-client bounded queues and the slow-consumer drop policy.

The feed loop only ever calls ``put_nowait``; it never awaits a client. A client whose
queue overflows is removed from the hub and its writer is told to close with 1013.
"""

import asyncio
import logging

from .models import HeartbeatMessage

logger = logging.getLogger(__name__)

SLOW_CONSUMER_CLOSE_CODE = 1013

_DROPPED = object()


class Connection:
    """One WebSocket client: an outbound queue of pre-serialized JSON text frames."""

    def __init__(self, queue_max: int) -> None:
        self._queue: asyncio.Queue[str | object] = asyncio.Queue(maxsize=queue_max)
        self.subscribed = False
        self.client_id: str | None = None
        self.dropped = False

    async def next_message(self) -> str | None:
        """Next frame to send, or ``None`` once dropped as a slow consumer."""
        item = await self._queue.get()
        return None if item is _DROPPED else item  # type: ignore[return-value]

    def _put(self, text: str) -> bool:
        try:
            self._queue.put_nowait(text)
        except asyncio.QueueFull:
            return False
        return True

    def _mark_dropped(self) -> None:
        self.dropped = True
        self.subscribed = False
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(_DROPPED)


class Hub:
    def __init__(self, client_queue_max: int) -> None:
        self._client_queue_max = client_queue_max
        self._connections: set[Connection] = set()

    @property
    def subscriber_count(self) -> int:
        return sum(1 for conn in self._connections if conn.subscribed)

    def connect(self) -> Connection:
        conn = Connection(self._client_queue_max)
        self._connections.add(conn)
        return conn

    def disconnect(self, conn: Connection) -> None:
        conn.subscribed = False
        self._connections.discard(conn)

    def subscribe(self, conn: Connection, snapshot_text: str) -> None:
        """Mark subscribed and enqueue the snapshot atomically (no await in between),
        so the first delta the client sees is exactly ``snapshot.seq + 1``."""
        conn.subscribed = True
        self.send(conn, snapshot_text)

    def unsubscribe(self, conn: Connection) -> None:
        conn.subscribed = False

    def send(self, conn: Connection, text: str) -> None:
        if conn.dropped:
            return
        if not conn._put(text):
            self._drop(conn)

    def broadcast(self, text: str) -> None:
        """Enqueue a book message to every subscribed client."""
        for conn in [c for c in self._connections if c.subscribed]:
            self.send(conn, text)

    def broadcast_all(self, text: str) -> None:
        """Enqueue a message (heartbeat) to every connected client."""
        for conn in list(self._connections):
            self.send(conn, text)

    def _drop(self, conn: Connection) -> None:
        logger.warning(
            "slow consumer dropped: client_id=%s queue_max=%d",
            conn.client_id,
            self._client_queue_max,
        )
        self._connections.discard(conn)
        conn._mark_dropped()


async def run_heartbeats(hub: Hub, interval_sec: float, clock) -> None:
    while True:
        await asyncio.sleep(interval_sec)
        hub.broadcast_all(HeartbeatMessage(ts=clock()).model_dump_json())
