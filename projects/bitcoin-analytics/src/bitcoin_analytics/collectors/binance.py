import email.utils
import logging
import math
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..schemas import BitcoinCandleCreate

BASE_URL = "https://api.binance.com"
KLINES_PATH = "/api/v3/klines"
DEFAULT_TIMEOUT = 10.0
MAX_LIMIT = 1000
VALID_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")
logger = logging.getLogger(__name__)


class BinanceThrottleError(httpx.HTTPStatusError):
    """Raised when Binance signals an active rate limit or IP ban."""


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
    max_retries: int = 5,
    backoff_base: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[BitcoinCandleCreate]:
    """Fetch and normalize public Binance Spot klines."""

    if interval not in VALID_INTERVALS:
        raise ValueError(f"interval must be one of: {', '.join(VALID_INTERVALS)}")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if not math.isfinite(backoff_base) or backoff_base < 0:
        raise ValueError("backoff_base must be a finite non-negative number")

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
        response = _request_with_retries(
            request_client,
            params,
            max_retries=max_retries,
            backoff_base=backoff_base,
            sleep=sleep,
        )
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


def _request_with_retries(
    client: httpx.Client,
    params: dict[str, Any],
    *,
    max_retries: int,
    backoff_base: float,
    sleep: Callable[[float], None],
) -> httpx.Response:
    for attempt in range(max_retries + 1):
        try:
            response = client.get(KLINES_PATH, params=params)
        except httpx.TransportError:
            if attempt >= max_retries:
                raise
            delay = backoff_base * (2**attempt)
            logger.warning("Binance transport error; retrying in %.2f seconds", delay)
            sleep(delay)
            continue

        status = response.status_code
        if status == 418:
            raise BinanceThrottleError(
                "Binance returned HTTP 418; request stopped to respect the IP ban",
                request=response.request,
                response=response,
            )
        if status == 429 or status >= 500:
            if attempt >= max_retries:
                if status == 429:
                    raise BinanceThrottleError(
                        "Binance returned HTTP 429 after retries; stopping requests",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
            delay = _retry_delay(response, attempt=attempt, backoff_base=backoff_base)
            logger.warning(
                "Binance returned HTTP %d; retrying in %.2f seconds",
                status,
                delay,
            )
            sleep(delay)
            continue
        response.raise_for_status()
        return response

    raise RuntimeError("Binance request exhausted retries without a response")


def _retry_delay(
    response: httpx.Response,
    *,
    attempt: int,
    backoff_base: float,
) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = email.utils.parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(
                    0.0,
                    (retry_at - datetime.now(timezone.utc)).total_seconds(),
                )
            except (AttributeError, TypeError, ValueError, OverflowError):
                pass
    return backoff_base * (2**attempt)


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