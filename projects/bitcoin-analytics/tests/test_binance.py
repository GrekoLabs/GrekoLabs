from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from src.collectors.binance import BASE_URL, fetch_klines


SAMPLE_KLINE = [
    1704067200000,
    "42000.12000000",
    "42100.50000000",
    "41950.00000000",
    "42050.25000000",
    "123.45670000",
    1704070799999,
    "5180000.00000000",
    3600,
    "60.00000000",
    "2520000.00000000",
    "0",
]
FUTURE_CLOSE_TIME = 4102444800000


def test_fetch_klines_normalizes_binance_kline() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        assert request.url.params["symbol"] == "BTCUSDT"
        assert request.url.params["interval"] == "1h"
        assert request.url.params["limit"] == "1"
        return httpx.Response(200, json=[SAMPLE_KLINE], request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        candles = fetch_klines("BTCUSDT", "1h", limit=1, client=client)

    candle = candles[0]
    assert candle.exchange == "binance"
    assert candle.symbol == "BTCUSDT"
    assert candle.interval == "1h"
    assert candle.timestamp == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert candle.timestamp.tzinfo is not None
    assert candle.open == Decimal("42000.12000000")
    assert candle.high == Decimal("42100.50000000")
    assert candle.low == Decimal("41950.00000000")
    assert candle.close == Decimal("42050.25000000")
    assert candle.volume == Decimal("123.45670000")
    assert all(isinstance(value, Decimal) for value in (candle.open, candle.high, candle.low, candle.close, candle.volume))


def test_fetch_klines_includes_closed_candle() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[SAMPLE_KLINE], request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        candles = fetch_klines("BTCUSDT", "1h", client=client)

    assert len(candles) == 1


def test_fetch_klines_excludes_open_candle_by_default() -> None:
    future_kline = SAMPLE_KLINE.copy()
    future_kline[6] = FUTURE_CLOSE_TIME

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[future_kline], request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        candles = fetch_klines("BTCUSDT", "1h", client=client)

    assert candles == []


def test_fetch_klines_can_include_open_candle() -> None:
    future_kline = SAMPLE_KLINE.copy()
    future_kline[6] = FUTURE_CLOSE_TIME

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[future_kline], request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        candles = fetch_klines("BTCUSDT", "1h", include_open_candle=True, client=client)

    assert len(candles) == 1
    assert candles[0].timestamp == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_fetch_klines_rejects_malformed_kline() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[[1704067200000, "42000"]], request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        with pytest.raises(ValueError, match="Malformed Binance kline"):
            fetch_klines("BTCUSDT", "1h", client=client)


def test_fetch_klines_raises_for_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -1121}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_klines("INVALID", "1h", client=client)