"""Process-global book version counter (docs/ARCHITECTURE.md §4)."""


class Sequencer:
    """``last_seq`` starts at 0 (empty pre-tick book); each applied tick bumps it by 1."""

    def __init__(self) -> None:
        self._last_seq = 0

    @property
    def last_seq(self) -> int:
        return self._last_seq

    def next_seq(self) -> int:
        self._last_seq += 1
        return self._last_seq
