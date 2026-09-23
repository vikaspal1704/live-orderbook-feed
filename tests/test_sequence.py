from orderbook_feed.sequencer import Sequencer
from tests.conftest import fence, receive_non_heartbeat, subscribe


def test_sequencer_starts_at_zero_and_increments():
    sequencer = Sequencer()

    assert sequencer.last_seq == 0
    assert [sequencer.next_seq() for _ in range(3)] == [1, 2, 3]
    assert sequencer.last_seq == 3


def test_manual_tick_advances_seq(harness):
    for price in (100, 99, 98):
        harness.inject(("BID", price, 1))

    assert harness.feed.last_seq == 3
    assert harness.client.get("/health").json()["last_seq"] == 3


def test_snapshot_seq_matches_book(harness):
    harness.inject(("BID", 100, 5))
    harness.inject(("ASK", 101, 3))

    with harness.ws() as ws:
        snapshot = subscribe(ws)

    assert snapshot["type"] == "snapshot"
    assert snapshot["seq"] == 2
    assert snapshot["seq"] == harness.client.get("/health").json()["last_seq"]


def test_delta_seq_monotonic(harness):
    harness.inject(("BID", 100, 1))
    with harness.ws() as ws:
        snapshot = subscribe(ws)
        for quantity in (2, 3, 4):
            harness.inject(("BID", 100, quantity))

        seqs = [receive_non_heartbeat(ws)["seq"] for _ in range(3)]

    assert seqs == [snapshot["seq"] + 1, snapshot["seq"] + 2, snapshot["seq"] + 3]


def test_resubscribe_sends_fresh_snapshot_at_current_seq(harness):
    with harness.ws() as ws:
        first = subscribe(ws)
        harness.inject(("ASK", 101, 3))
        assert receive_non_heartbeat(ws)["seq"] == 1

        second = subscribe(ws)
        fence(ws)

    assert (first["type"], first["seq"]) == ("snapshot", 0)
    assert (second["type"], second["seq"]) == ("snapshot", 1)
    assert second["asks"] == [{"price": 101, "quantity": 3}]


def test_resnapshot_sends_snapshot_without_seq_bump(harness):
    harness.inject(("BID", 100, 5))
    with harness.ws() as ws:
        subscribe(ws)
        ws.send_json({"type": "resnapshot", "symbol": "DEMO/USD"})
        msg = receive_non_heartbeat(ws)

    assert msg["type"] == "snapshot"
    assert msg["seq"] == 1
    assert harness.feed.last_seq == 1
