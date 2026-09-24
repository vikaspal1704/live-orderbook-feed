def test_health_ok(harness):
    response = harness.client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "symbol": "DEMO/USD",
        "last_seq": 0,
        "subscribers": 0,
        "feed_alive": True,
    }


def test_health_counts_subscribers(harness):
    with harness.ws() as ws:
        ws.send_json({"type": "subscribe", "symbol": "DEMO/USD"})
        ws.receive_json()

        assert harness.client.get("/health").json()["subscribers"] == 1


def test_rest_book_demo_usd(harness):
    harness.inject(("BID", 99, 4), ("BID", 100, 2), ("ASK", 101, 3), ("ASK", 102, 1))

    response = harness.client.get("/v1/book/DEMO%2FUSD")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "symbol": "DEMO/USD",
        "seq": 1,
        "ts": body["ts"],
        "bids": [{"price": 100, "quantity": 2}, {"price": 99, "quantity": 4}],
        "asks": [{"price": 101, "quantity": 3}, {"price": 102, "quantity": 1}],
    }
    assert "type" not in body


def test_rest_book_depth_trim(make_harness):
    harness = make_harness(book_depth_levels=2)
    harness.inject(*[("BID", 100 - offset, 1) for offset in range(5)])

    body = harness.client.get("/v1/book/DEMO%2FUSD").json()

    assert [level["price"] for level in body["bids"]] == [100, 99]


def test_rest_book_unknown_404(harness):
    response = harness.client.get("/v1/book/FOO%2FBAR")

    assert response.status_code == 404
    assert response.json() == {"detail": "unknown symbol: FOO/BAR"}
