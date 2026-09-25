"""Application services."""

from .bitcoin_candles import PersistenceResult, save_bitcoin_candles

__all__ = ["PersistenceResult", "save_bitcoin_candles"]