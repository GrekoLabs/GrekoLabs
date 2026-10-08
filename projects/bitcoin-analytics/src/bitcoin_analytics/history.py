import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.bitcoin_candle import BitcoinCandle
from backend.app.services.bitcoin_candles import PersistenceResult, save_bitcoin_candles

from .collectors.binance import (
    MAX_LIMIT,
    VALID_INTERVALS,
    BinanceThrottleError,
    fetch_klines,
)
from .schemas import BitcoinCandleCreate

UTC = timezone.utc
DEFAULT_START = datetime(2020, 1, 1, tzinfo=UTC)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GapRange:
    start: datetime
    end: datetime


@dataclass
class RunSummary:
    pages: int = 0
    received: int = 0
    inserted: int = 0
    skipped: int = 0
    pending: int = 0
    unresolved: int = 0
    errors: int = 0
    conflicts: int = 0

    def add_persistence(self, result: PersistenceResult) -> None:
        self.received += result.received
        self.inserted += result.inserted
        self.skipped += result.skipped


def interval_delta(interval: str) -> timedelta:
    if interval not in VALID_INTERVALS:
        raise ValueError(f"interval must be one of: {', '.join(VALID_INTERVALS)}")
    return {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }[interval]


def parse_utc_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        normalized = value.strip()
        if len(normalized) == 10:
            normalized += "T00:00:00+00:00"
        elif normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError(f"invalid datetime: {value!r}") from error
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def floor_interval(value: datetime, interval: str) -> datetime:
    value = parse_utc_datetime(value)
    step = interval_delta(interval)
    if interval == "1d":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    elapsed_seconds = int((value - epoch).total_seconds())
    step_seconds = int(step.total_seconds())
    return epoch + timedelta(seconds=elapsed_seconds - elapsed_seconds % step_seconds)


def resolve_range(
    start: str | datetime,
    end: str | datetime | None,
    interval: str,
    *,
    now: datetime | None = None,
) -> GapRange:
    start_utc = parse_utc_datetime(start)
    latest_closed_boundary = floor_interval(now or datetime.now(UTC), interval)
    end_utc = latest_closed_boundary if end is None else parse_utc_datetime(end)
    validate_aligned(start_utc, interval)
    validate_aligned(end_utc, interval)
    end_utc = min(end_utc, latest_closed_boundary)
    if start_utc >= end_utc:
        raise ValueError("start must be earlier than the exclusive end")
    return GapRange(start=start_utc, end=end_utc)


def validate_aligned(timestamp: datetime, interval: str) -> None:
    step = interval_delta(interval)
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise ValueError("timestamps must be UTC")
    if interval == "1d":
        aligned = timestamp.time() == datetime.min.time()
    else:
        seconds = int(step.total_seconds())
        aligned = timestamp.microsecond == 0 and int(timestamp.timestamp()) % seconds == 0
    if not aligned:
        raise ValueError(f"timestamp {timestamp.isoformat()} is not aligned to {interval}")


def validate_candle(candle: BitcoinCandleCreate) -> None:
    if candle.exchange != "binance":
        raise ValueError(f"unexpected exchange: {candle.exchange}")
    validate_aligned(candle.timestamp, candle.interval)
    step = interval_delta(candle.interval)
    if candle.timestamp + step > datetime.now(UTC):
        raise ValueError("candle is not fully closed")

    try:
        values = {
            name: Decimal(str(getattr(candle, name)))
            for name in ("open", "high", "low", "close", "volume")
        }
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("OHLCV values must be numeric") from error
    if not all(value.is_finite() for value in values.values()):
        raise ValueError("OHLCV values must be finite")
    if values["volume"] < 0:
        raise ValueError("volume must be non-negative")
    if values["high"] < max(values["open"], values["close"], values["low"]):
        raise ValueError("high must be at least open, close, and low")
    if values["low"] > min(values["open"], values["close"], values["high"]):
        raise ValueError("low must be at most open, close, and high")


def persist_page(
    session: Session,
    candles: Iterable[BitcoinCandleCreate],
) -> tuple[PersistenceResult, int]:
    batch = list(candles)
    for candle in batch:
        validate_candle(candle)
    if not batch:
        return save_bitcoin_candles(session, batch), 0

    timestamps = [candle.timestamp for candle in batch]
    existing = session.scalars(
        select(BitcoinCandle).where(
            BitcoinCandle.exchange == batch[0].exchange,
            BitcoinCandle.symbol == batch[0].symbol,
            BitcoinCandle.interval == batch[0].interval,
            BitcoinCandle.timestamp.in_(timestamps),
        )
    ).all()
    by_timestamp = {candle.timestamp: candle for candle in existing}
    conflicts = 0
    seen: dict[datetime, BitcoinCandleCreate] = {}
    for incoming in batch:
        previous = seen.get(incoming.timestamp) or by_timestamp.get(incoming.timestamp)
        if previous is not None and any(
            getattr(previous, field) != getattr(incoming, field)
            for field in ("open", "high", "low", "close", "volume")
        ):
            conflicts += 1
            logger.error(
                "Candle data conflict: %s %s %s %s",
                incoming.exchange,
                incoming.symbol,
                incoming.interval,
                incoming.timestamp.isoformat(),
            )
        seen[incoming.timestamp] = incoming
    return save_bitcoin_candles(session, batch), conflicts


FetchPage = Callable[..., list[BitcoinCandleCreate]]


def fetch_and_persist_range(
    session: Session,
    *,
    symbol: str,
    interval: str,
    gap: GapRange,
    limit: int = MAX_LIMIT,
    client: httpx.Client | None = None,
    fetch_page: FetchPage = fetch_klines,
) -> RunSummary:
    step = interval_delta(interval)
    page_span = step * limit
    cursor = gap.start
    summary = RunSummary()

    while cursor < gap.end:
        page_end = min(cursor + page_span, gap.end)
        try:
            candles = fetch_page(
                symbol,
                interval,
                start_time=int(cursor.timestamp() * 1000),
                end_time=int(page_end.timestamp() * 1000) - 1,
                limit=limit,
                include_open_candle=False,
                client=client,
            )
            summary.pages += 1
            if not candles:
                summary.unresolved += 1
                logger.error(
                    "Binance returned no candles for unresolved range %s to %s",
                    cursor.isoformat(),
                    gap.end.isoformat(),
                )
                break

            for candle in candles:
                if candle.symbol != symbol or candle.interval != interval:
                    raise ValueError("Binance returned a candle for an unexpected market")
                if not cursor <= candle.timestamp < page_end:
                    raise ValueError("Binance returned a candle outside the requested page")
                validate_candle(candle)
            timestamps = [candle.timestamp for candle in candles]
            if timestamps != sorted(set(timestamps)):
                raise ValueError("Binance returned duplicate or unordered candle timestamps")
            result, conflicts = persist_page(session, candles)
            summary.add_persistence(result)
            summary.conflicts += conflicts
            cursor = page_end
        except BinanceThrottleError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            summary.errors += 1
            summary.unresolved += 1
            logger.error(
                "Failed to process range %s to %s: %s",
                cursor.isoformat(),
                page_end.isoformat(),
                error,
            )
            break

    return summary
