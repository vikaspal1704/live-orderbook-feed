"""Runtime settings, read from environment variables (see docs/TRD.md §5)."""

import os
from dataclasses import dataclass, field
from typing import Literal

TickMode = Literal["synthetic", "replay", "manual"]
_TICK_MODES = ("synthetic", "replay", "manual")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else float(raw)


@dataclass(frozen=True)
class Settings:
    symbol: str = "DEMO/USD"
    host: str = "0.0.0.0"
    port: int = 8000
    heartbeat_interval_sec: float = 5.0
    client_queue_max: int = 64
    tick_interval_ms: int = 100
    tick_mode: TickMode = "synthetic"
    replay_path: str | None = None
    book_depth_levels: int = 10
    synthetic_seed: int | None = field(default=None)

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("SYMBOL must be non-empty")
        if self.tick_mode not in _TICK_MODES:
            raise ValueError(f"TICK_MODE must be one of {_TICK_MODES}, got {self.tick_mode!r}")
        if self.tick_mode == "replay" and not self.replay_path:
            raise ValueError("REPLAY_PATH is required when TICK_MODE=replay")
        if self.heartbeat_interval_sec <= 0:
            raise ValueError("HEARTBEAT_INTERVAL_SEC must be > 0")
        if self.client_queue_max < 1:
            raise ValueError("CLIENT_QUEUE_MAX must be >= 1")
        if self.tick_interval_ms < 0:
            raise ValueError("TICK_INTERVAL_MS must be >= 0")
        if self.book_depth_levels < 1:
            raise ValueError("BOOK_DEPTH_LEVELS must be >= 1")

    @classmethod
    def from_env(cls) -> "Settings":
        seed = os.environ.get("SYNTHETIC_SEED")
        return cls(
            symbol=os.environ.get("SYMBOL", cls.symbol),
            host=os.environ.get("HOST", cls.host),
            port=_env_int("PORT", cls.port),
            heartbeat_interval_sec=_env_float("HEARTBEAT_INTERVAL_SEC", cls.heartbeat_interval_sec),
            client_queue_max=_env_int("CLIENT_QUEUE_MAX", cls.client_queue_max),
            tick_interval_ms=_env_int("TICK_INTERVAL_MS", cls.tick_interval_ms),
            tick_mode=os.environ.get("TICK_MODE", cls.tick_mode),  # type: ignore[arg-type]
            replay_path=os.environ.get("REPLAY_PATH") or None,
            book_depth_levels=_env_int("BOOK_DEPTH_LEVELS", cls.book_depth_levels),
            synthetic_seed=int(seed) if seed else None,
        )
