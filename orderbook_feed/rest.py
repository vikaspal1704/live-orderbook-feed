"""Thin REST: ``GET /health`` and ``GET /v1/book/{symbol}``.

Handlers are ``async def`` so they run on the event loop that owns the book.
"""

from fastapi import APIRouter, HTTPException, Request

from .feed import Feed
from .models import BookResponse, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    feed: Feed = request.app.state.feed
    return HealthResponse(
        symbol=feed.symbol,
        last_seq=feed.last_seq,
        subscribers=feed.hub.subscriber_count,
        feed_alive=feed.alive,
    )


@router.get(
    "/v1/book/{symbol:path}",
    response_model=BookResponse,
    responses={404: {"description": "Unknown symbol"}},
)
async def get_book(symbol: str, request: Request) -> BookResponse:
    feed: Feed = request.app.state.feed
    if symbol != feed.symbol:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")
    return feed.book_response()
