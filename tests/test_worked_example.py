"""ARCHITECTURE.md §7 — subscribe -> snapshot -> deltas -> late subscriber."""

from tests.conftest import receive_non_heartbeat, subscribe


def _apply(book: dict[str, dict[int, int]], delta: dict) -> None:
    for change in delta["changes"]:
        side = book["bids" if change["side"] == "BID" else "asks"]
        if change["quantity"] == 0:
            side.pop(change["price"], None)
        else:
            side[change["price"]] = change["quantity"]


def test_worked_example_subscribe_snapshot_deltas(harness):
    # Step 0: fresh server, empty book, last_seq = 0.
    assert harness.feed.last_seq == 0

    # Steps 1-2: connect and subscribe -> empty snapshot at seq 0.
    with harness.ws() as ws:
        snapshot = subscribe(ws, client_id="example-client-1")
        assert snapshot["type"] == "snapshot"
        assert snapshot["symbol"] == "DEMO/USD"
        assert (snapshot["seq"], snapshot["bids"], snapshot["asks"]) == (0, [], [])
        local = {"bids": {}, "asks": {}}

        # Step 3: seed bid.
        harness.inject(("BID", 100, 5))
        delta = receive_non_heartbeat(ws)
        assert delta["type"] == "delta" and delta["seq"] == 1
        assert delta["changes"] == [{"side": "BID", "price": 100, "quantity": 5}]
        _apply(local, delta)
        assert local == {"bids": {100: 5}, "asks": {}}

        # Step 4: ask + widen bid.
        harness.inject(("ASK", 101, 3), ("BID", 100, 8))
        delta = receive_non_heartbeat(ws)
        assert delta["seq"] == 2
        assert delta["changes"] == [
            {"side": "ASK", "price": 101, "quantity": 3},
            {"side": "BID", "price": 100, "quantity": 8},
        ]
        _apply(local, delta)

        # Step 5: remove level + add level.
        harness.inject(("BID", 100, 0), ("BID", 99, 4))
        delta = receive_non_heartbeat(ws)
        assert delta["seq"] == 3
        assert delta["changes"] == [
            {"side": "BID", "price": 100, "quantity": 0},
            {"side": "BID", "price": 99, "quantity": 4},
        ]
        _apply(local, delta)
        assert local == {"bids": {99: 4}, "asks": {101: 3}}

        # Step 6: late subscriber gets a snapshot at seq 3 (no bump).
        with harness.ws() as late:
            late_snapshot = subscribe(late, client_id="example-client-2")
            assert late_snapshot["type"] == "snapshot"
            assert late_snapshot["seq"] == 3
            assert late_snapshot["bids"] == [{"price": 99, "quantity": 4}]
            assert late_snapshot["asks"] == [{"price": 101, "quantity": 3}]

            # Next tick is seq 4 == snapshot.seq + 1 for the late client too.
            harness.inject(("ASK", 101, 2))
            assert receive_non_heartbeat(late)["seq"] == late_snapshot["seq"] + 1
            assert receive_non_heartbeat(ws)["seq"] == 4

    # Step 8: REST mirrors the current book.
    book = harness.client.get("/v1/book/DEMO%2FUSD").json()
    assert book["seq"] == 4
    assert book["bids"] == [{"price": 99, "quantity": 4}]
    assert book["asks"] == [{"price": 101, "quantity": 2}]
