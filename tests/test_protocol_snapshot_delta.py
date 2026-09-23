import pytest

from tests.conftest import fence, receive_non_heartbeat, subscribe


def test_subscribe_receives_snapshot_then_deltas(harness):
    with harness.ws() as ws:
        snapshot = subscribe(ws)
        harness.inject(("BID", 100, 5))
        delta = receive_non_heartbeat(ws)

    assert snapshot == {
        "type": "snapshot",
        "symbol": "DEMO/USD",
        "seq": 0,
        "ts": snapshot["ts"],
        "bids": [],
        "asks": [],
    }
    assert delta == {
        "type": "delta",
        "symbol": "DEMO/USD",
        "seq": 1,
        "ts": delta["ts"],
        "changes": [{"side": "BID", "price": 100, "quantity": 5}],
    }
    assert isinstance(delta["ts"], int)


def test_delta_quantity_zero_removes_level(harness):
    harness.inject(("BID", 100, 5), ("ASK", 101, 3))
    with harness.ws() as ws:
        subscribe(ws)
        harness.inject(("BID", 100, 0))
        delta = receive_non_heartbeat(ws)

    assert delta["changes"] == [{"side": "BID", "price": 100, "quantity": 0}]
    book = harness.client.get("/v1/book/DEMO%2FUSD").json()
    assert book["bids"] == []
    assert book["asks"] == [{"price": 101, "quantity": 3}]


def test_multiple_changes_in_one_delta_keep_order(harness):
    with harness.ws() as ws:
        subscribe(ws)
        harness.inject(("ASK", 101, 3), ("BID", 100, 8))
        delta = receive_non_heartbeat(ws)

    assert delta["changes"] == [
        {"side": "ASK", "price": 101, "quantity": 3},
        {"side": "BID", "price": 100, "quantity": 8},
    ]


def test_subscribe_unknown_symbol_error(harness):
    with harness.ws() as ws:
        msg = subscribe(ws, symbol="FOO/BAR")

    assert msg["type"] == "error"
    assert msg["code"] == "UNKNOWN_SYMBOL"
    assert "FOO/BAR" in msg["message"]
    assert isinstance(msg["ts"], int)
    assert harness.client.get("/health").json()["subscribers"] == 0


def test_unsubscribe_stops_deltas(harness):
    with harness.ws() as ws:
        subscribe(ws)
        ws.send_json({"type": "unsubscribe", "symbol": "DEMO/USD"})
        fence(ws)  # unsubscribe has been processed

        harness.inject(("BID", 100, 5))
        harness.inject(("BID", 100, 6))

        # The next frame is the fence reply, so no delta was queued after unsubscribe.
        fence(ws)

    assert harness.feed.last_seq == 2


@pytest.mark.parametrize(
    "frame",
    [
        "not json",
        "[]",
        '{"symbol": "DEMO/USD"}',
        '{"type": "ping"}',
        '{"type": "subscribe"}',
        '{"type": "subscribe", "symbol": "DEMO/USD", "client_id": 5}',
    ],
)
def test_bad_json_error(harness, frame):
    with harness.ws() as ws:
        ws.send_text(frame)
        msg = receive_non_heartbeat(ws)
        # Connection stays open after a BAD_REQUEST.
        snapshot = subscribe(ws)

    assert msg["type"] == "error"
    assert msg["code"] == "BAD_REQUEST"
    assert snapshot["type"] == "snapshot"


def test_unknown_fields_are_ignored(harness):
    with harness.ws() as ws:
        ws.send_json({"type": "subscribe", "symbol": "DEMO/USD", "extra": {"x": 1}})
        msg = receive_non_heartbeat(ws)

    assert msg["type"] == "snapshot"


def test_pong_is_accepted_silently(harness):
    with harness.ws() as ws:
        ws.send_json({"type": "pong", "ts": 1760000000500})
        fence(ws)


def test_two_subscribers_receive_identical_deltas(harness):
    with harness.ws() as ws_a, harness.ws() as ws_b:
        subscribe(ws_a, client_id="a")
        subscribe(ws_b, client_id="b")
        harness.inject(("BID", 100, 5))

        assert receive_non_heartbeat(ws_a) == receive_non_heartbeat(ws_b)


def test_client_disconnect_mid_stream_does_not_break_fanout(harness):
    with harness.ws() as ws_b:
        subscribe(ws_b, client_id="b")
        with harness.ws() as ws_a:
            subscribe(ws_a, client_id="a")
            harness.inject(("BID", 100, 1))
            receive_non_heartbeat(ws_a)

        harness.inject(("BID", 100, 2))

        assert receive_non_heartbeat(ws_b)["seq"] == 1
        assert receive_non_heartbeat(ws_b)["seq"] == 2
