from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models.bitcoin_candle import BitcoinCandle


class BitcoinCandleInput(Protocol):
    exchange: str
    symbol: str
    interval: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class PersistenceResult:
    received: int
    inserted: int
    skipped: int


def save_bitcoin_candles(
    session: Session,
    candles: Iterable[BitcoinCandleInput],
) -> PersistenceResult:
    """Persist candles idempotently using PostgreSQL's conflict handling."""

    candle_values = [
        {
            "exchange": candle.exchange,
            "symbol": candle.symbol,
            "interval": candle.interval,
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles
    ]
    received = len(candle_values)
    if not received:
        return PersistenceResult(received=0, inserted=0, skipped=0)

    statement = insert(BitcoinCandle).values(candle_values)
    statement = statement.on_conflict_do_nothing(
        index_elements=["exchange", "symbol", "interval", "timestamp"]
    ).returning(BitcoinCandle.id)
    result = session.execute(statement)
    session.commit()

    inserted = len(result.scalars().all())
    return PersistenceResult(
        received=received,
        inserted=inserted,
        skipped=received - inserted,
    )