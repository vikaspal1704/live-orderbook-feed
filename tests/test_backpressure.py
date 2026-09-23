import json

import pytest
from starlette.websockets import WebSocketDisconnect

from orderbook_feed.feed import Feed
from orderbook_feed.hub import SLOW_CONSUMER_CLOSE_CODE, Hub
from tests.conftest import FakeClock, changes_of, subscribe


def test_slow_consumer_disconnected(make_harness):
    harness = make_harness(client_queue_max=4)

    with harness.ws() as ws:
        subscribe(ws)
        # Ten ticks in one event-loop turn: the writer cannot drain, the queue overflows.
        harness.inject_many([[("BID", 100, quantity)] for quantity in range(1, 11)])

        error = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "SLOW_CONSUMER"
    assert exc_info.value.code == SLOW_CONSUMER_CLOSE_CODE
    assert harness.feed.hub.subscriber_count == 0
    assert harness.feed.last_seq == 10


async def test_fast_consumer_unaffected_by_slow():
    hub = Hub(client_queue_max=4)
    feed = Feed("DEMO/USD", depth=10, hub=hub, clock=FakeClock())
    slow, fast = hub.connect(), hub.connect()
    hub.subscribe(slow, feed.snapshot().model_dump_json())
    hub.subscribe(fast, feed.snapshot().model_dump_json())
    await fast.next_message()  # fast consumer reads its snapshot

    received = []
    for quantity in range(1, 11):
        feed.apply_tick(changes_of(("BID", 100, quantity)))
        received.append(await fast.next_message())

    assert slow.dropped
    assert await slow.next_message() is None
    assert not fast.dropped
    assert [json.loads(text)["seq"] for text in received] == list(range(1, 11))
    assert hub.subscriber_count == 1


async def test_dropped_consumer_receives_nothing_further():
    hub = Hub(client_queue_max=1)
    feed = Feed("DEMO/USD", depth=10, hub=hub, clock=FakeClock())
    conn = hub.connect()
    hub.subscribe(conn, feed.snapshot().model_dump_json())

    feed.apply_tick(changes_of(("BID", 100, 1)))  # overflow -> drop
    feed.apply_tick(changes_of(("BID", 100, 2)))
    hub.broadcast_all('{"type":"heartbeat","ts":0}')

    assert await conn.next_message() is None
    assert conn.dropped
