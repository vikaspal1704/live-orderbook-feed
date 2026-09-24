"""In-memory aggregated L2 book: price -> quantity per side. Never touches the network."""

from .models import BookLevel, Change, Side


class OrderBook:
    def __init__(self) -> None:
        self._levels: dict[Side, dict[int, int]] = {"BID": {}, "ASK": {}}

    def apply(self, side: Side, price: int, quantity: int) -> None:
        """Set the level at (side, price) to ``quantity``; ``0`` deletes the level."""
        if quantity == 0:
            self._levels[side].pop(price, None)
        else:
            self._levels[side][price] = quantity

    def apply_changes(self, changes: list[Change]) -> None:
        for change in changes:
            self.apply(change.side, change.price, change.quantity)

    def quantity(self, side: Side, price: int) -> int:
        return self._levels[side].get(price, 0)

    def bids(self, depth: int | None = None) -> list[BookLevel]:
        """Top ``depth`` bid levels, best (highest) price first."""
        return self._top("BID", depth, descending=True)

    def asks(self, depth: int | None = None) -> list[BookLevel]:
        """Top ``depth`` ask levels, best (lowest) price first."""
        return self._top("ASK", depth, descending=False)

    def _top(self, side: Side, depth: int | None, *, descending: bool) -> list[BookLevel]:
        levels = self._levels[side]
        prices = sorted(levels, reverse=descending)[:depth]
        return [BookLevel(price=price, quantity=levels[price]) for price in prices]
