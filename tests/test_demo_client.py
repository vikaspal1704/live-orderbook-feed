"""End-to-end: real uvicorn server + demo client over a real WebSocket."""

import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from demo.ws_client import run
from orderbook_feed.app import create_app
from orderbook_feed.config import Settings


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def live_server_url() -> Iterator[str]:
    port = _free_port()
    settings = Settings(tick_mode="synthetic", tick_interval_ms=10, synthetic_seed=1)
    config = uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.01)
    try:
        yield f"ws://127.0.0.1:{port}/v1/ws"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


async def test_demo_client_end_to_end(live_server_url, capsys):
    exit_code = await run(live_server_url, "DEMO/USD", deltas=3, timeout=5)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "<- snapshot seq=" in out
    assert out.count("<- delta seq=") == 3


async def test_demo_client_unknown_symbol_fails(live_server_url, capsys):
    exit_code = await run(live_server_url, "FOO/BAR", deltas=1, timeout=5)

    assert exit_code == 1
    assert "UNKNOWN_SYMBOL" in capsys.readouterr().err
