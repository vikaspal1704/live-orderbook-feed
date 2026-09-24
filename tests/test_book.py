from orderbook_feed.book import OrderBook
from orderbook_feed.models import BookLevel
from tests.conftest import changes_of


def test_book_apply_level_and_remove():
    book = OrderBook()

    book.apply("BID", 100, 5)
    assert book.bids() == [BookLevel(price=100, quantity=5)]

    book.apply("BID", 100, 0)
    assert book.bids() == []


def test_book_snapshot_sort_order():
    book = OrderBook()
    book.apply_changes(
        changes_of(("BID", 99, 1), ("BID", 100, 1), ("ASK", 102, 1), ("ASK", 101, 1))
    )

    assert [level.price for level in book.bids()] == [100, 99]
    assert [level.price for level in book.asks()] == [101, 102]


def test_book_set_overwrites_quantity():
    book = OrderBook()

    book.apply("ASK", 101, 3)
    book.apply("ASK", 101, 8)

    assert book.asks() == [BookLevel(price=101, quantity=8)]


def test_book_remove_absent_level_is_noop():
    book = OrderBook()

    book.apply("ASK", 101, 0)

    assert book.asks() == []


def test_book_depth_trim():
    book = OrderBook()
    for offset in range(1, 6):
        book.apply("BID", 100 - offset, offset)
        book.apply("ASK", 100 + offset, offset)

    assert [level.price for level in book.bids(depth=2)] == [99, 98]
    assert [level.price for level in book.asks(depth=2)] == [101, 102]


def test_book_changes_applied_in_order():
    book = OrderBook()

    book.apply_changes(changes_of(("BID", 100, 5), ("BID", 100, 0), ("BID", 100, 7)))

    assert book.bids() == [BookLevel(price=100, quantity=7)]
