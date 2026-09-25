from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..schemas import BitcoinCandleCreate

BASE_URL = "https://api.binance.com"
KLINES_PATH = "/api/v3/klines"
DEFAULT_TIMEOUT = 10.0
MAX_LIMIT = 1000


def fetch_klines(
    symbol: str,
    interval: str,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 500,
    *,
    include_open_candle: bool = False,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[BitcoinCandleCreate]:
    """Fetch and normalize public Binance Spot klines."""

    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

    params: dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time

    owns_client = client is None
    request_client = client or httpx.Client(base_url=BASE_URL, timeout=timeout)
    try:
        response = request_client.get(KLINES_PATH, params=params)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise ValueError("Binance returned invalid JSON") from error
    finally:
        if owns_client:
            request_client.close()

    if not isinstance(payload, list):
        raise ValueError("Binance response must be a list of klines")

    current_time = datetime.now(timezone.utc)
    return [
        _normalize_kline(kline, index=index, symbol=symbol, interval=interval)
        for index, kline in enumerate(payload)
        if include_open_candle or _is_kline_closed(kline, index=index, current_time=current_time)
    ]


def _normalize_kline(
    kline: Any,
    *,
    index: int,
    symbol: str,
    interval: str,
) -> BitcoinCandleCreate:
    if not isinstance(kline, list) or len(kline) < 7:
        raise ValueError(f"Malformed Binance kline at index {index}")

    try:
        open_time = int(kline[0])
        timestamp = _timestamp_from_milliseconds(open_time)
        values = [_decimal_value(kline[position]) for position in range(1, 6)]
        return BitcoinCandleCreate(
            exchange="binance",
            symbol=symbol,
            interval=interval,
            timestamp=timestamp,
            open=values[0],
            high=values[1],
            low=values[2],
            close=values[3],
            volume=values[4],
        )
    except (IndexError, TypeError, ValueError, InvalidOperation) as error:
        raise ValueError(f"Malformed Binance kline at index {index}") from error


def _is_kline_closed(kline: Any, *, index: int, current_time: datetime) -> bool:
    if not isinstance(kline, list) or len(kline) < 7:
        raise ValueError(f"Malformed Binance kline at index {index}")

    try:
        close_time = _timestamp_from_milliseconds(int(kline[6]))
    except (IndexError, TypeError, ValueError, OverflowError, OSError) as error:
        raise ValueError(f"Malformed Binance kline at index {index}") from error

    return close_time <= current_time


def _timestamp_from_milliseconds(open_time: int) -> datetime:
    seconds, milliseconds = divmod(open_time, 1000)
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
        microsecond=milliseconds * 1000
    )


def _decimal_value(value: Any) -> Decimal:
    decimal_value = Decimal(str(value))
    if not decimal_value.is_finite():
        raise ValueError("OHLCV values must be finite decimals")
    return decimal_value