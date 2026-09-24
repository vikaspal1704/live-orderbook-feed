from tests.conftest import subscribe


def test_heartbeat_received(make_harness):
    harness = make_harness(heartbeat_interval_sec=0.05)

    with harness.ws() as ws:
        subscribe(ws)
        # With a 50 ms interval a heartbeat arrives well within the test timeout.
        msg = ws.receive_json()

    assert msg["type"] == "heartbeat"
    assert isinstance(msg["ts"], int)
    assert "seq" not in msg
    assert harness.feed.last_seq == 0
