from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class BitcoinCandleBase(BaseModel):
    """Shared fields for an OHLCV candle."""

    timestamp: datetime
    symbol: str
    interval: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class BitcoinCandleCreate(BitcoinCandleBase):
    """Payload used to create an OHLCV candle."""


class BitcoinCandleRead(BitcoinCandleBase):
    """OHLCV candle returned from persistence."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
