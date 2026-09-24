"""Pydantic v2 models mirroring docs/API_CONTRACT.md. Field names are normative."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Side = Literal["BID", "ASK"]
Price = Annotated[int, Field(strict=True, ge=1)]
Quantity = Annotated[int, Field(strict=True, ge=0)]
ErrorCode = Literal["BAD_REQUEST", "UNKNOWN_SYMBOL", "SLOW_CONSUMER", "INTERNAL"]


class BookLevel(BaseModel):
    price: Price
    quantity: Annotated[int, Field(strict=True, ge=1)]


class Change(BaseModel):
    side: Side
    price: Price
    quantity: Quantity  # 0 means delete the level


class Tick(BaseModel):
    """One tick-source event; also the NDJSON line format for replay files."""

    changes: Annotated[list[Change], Field(min_length=1)]


# --- Client -> server -------------------------------------------------------


class _ClientMessage(BaseModel):
    # Unknown fields are ignored for forward compatibility.
    model_config = ConfigDict(extra="ignore")


class SubscribeMessage(_ClientMessage):
    type: Literal["subscribe"]
    symbol: str
    client_id: Annotated[str, Field(max_length=128)] | None = None


class UnsubscribeMessage(_ClientMessage):
    type: Literal["unsubscribe"]
    symbol: str


class PongMessage(_ClientMessage):
    type: Literal["pong"]
    ts: int | None = None


class ResnapshotMessage(_ClientMessage):
    type: Literal["resnapshot"]
    symbol: str


ClientMessage = Annotated[
    SubscribeMessage | UnsubscribeMessage | PongMessage | ResnapshotMessage,
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# --- Server -> client -------------------------------------------------------


class SnapshotMessage(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    symbol: str
    seq: int
    ts: int
    bids: list[BookLevel]
    asks: list[BookLevel]


class DeltaMessage(BaseModel):
    type: Literal["delta"] = "delta"
    symbol: str
    seq: int
    ts: int
    changes: list[Change]


class HeartbeatMessage(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    ts: int


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str
    ts: int


# --- REST -------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    symbol: str
    last_seq: int
    subscribers: int
    feed_alive: bool


class BookResponse(BaseModel):
    symbol: str
    seq: int
    ts: int
    bids: list[BookLevel]
    asks: list[BookLevel]
