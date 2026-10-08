from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from bitcoin_analytics.collectors.binance import (
    BASE_URL,
    BinanceThrottleError,
    fetch_klines,
)
from bitcoin_analytics.history import (
    GapRange,
    fetch_and_persist_range,
    interval_delta,
    parse_utc_datetime,
    persist_page,
    resolve_range,
    validate_candle,
)
from bitcoin_analytics.schemas import BitcoinCandleCreate

UTC = timezone.utc


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def mappings(self):
        return self.rows


class FakeSession:
    def __init__(self, inserted=10):
        self.inserted = inserted
        self.commits = 0
        self.statements = []

    def scalars(self, statement):
        return FakeResult([])

    def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(list(range(self.inserted)))

    def commit(self):
        self.commits += 1


def candle_at(timestamp: datetime, **updates) -> BitcoinCandleCreate:
    values = {
        "timestamp": timestamp,
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "interval": "1m",
        "open": Decimal("100"),
        "high": Decimal("110"),
        "low": Decimal("90"),
        "close": Decimal("105"),
        "volume": Decimal("1"),
    }
    values.update(updates)
    return BitcoinCandleCreate(**values)


def test_supported_intervals_and_utc_range_boundaries() -> None:
    for interval in ("1m", "5m", "15m", "1h", "4h", "1d"):
        assert interval_delta(interval) > timedelta(0)
    with pytest.raises(ValueError, match="interval must be one of"):
        interval_delta("2m")

    span = resolve_range("2024-01-01", "2024-01-02", "1d")
    assert span.start == datetime(2024, 1, 1, tzinfo=UTC)
    assert span.end == datetime(2024, 1, 2, tzinfo=UTC)
    assert parse_utc_datetime("2024-01-01T01:00:00+01:00") == span.start


def test_requested_end_is_capped_at_latest_closed_boundary() -> None:
    now = datetime(2024, 1, 1, 12, 34, 56, tzinfo=UTC)
    span = resolve_range(
        "2024-01-01T00:00:00Z",
        "2025-01-01T00:00:00Z",
        "1h",
        now=now,
    )
    assert span.end == datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


def test_fetch_and_persist_range_pages_without_crossing_end() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(minutes=4)
    calls = []

    def fetch_page(symbol, interval, **kwargs):
        calls.append(kwargs)
        page_start = datetime.fromtimestamp(kwargs["start_time"] / 1000, tz=UTC)
        page_end = datetime.fromtimestamp((kwargs["end_time"] + 1) / 1000, tz=UTC)
        return [
            candle_at(page_start + timedelta(minutes=offset))
            for offset in range(2)
            if page_start + timedelta(minutes=offset) < page_end
        ]

    session = FakeSession(inserted=2)
    summary = fetch_and_persist_range(
        session,
        symbol="BTCUSDT",
        interval="1m",
        gap=GapRange(start, end),
        limit=2,
        fetch_page=fetch_page,
    )

    assert len(calls) == 2
    assert calls[0]["start_time"] == int(start.timestamp() * 1000)
    assert calls[0]["end_time"] == int((start + timedelta(minutes=2)).timestamp() * 1000) - 1
    assert calls[1]["start_time"] == int((start + timedelta(minutes=2)).timestamp() * 1000)
    assert summary.pages == 2
    assert summary.received == 4
    assert summary.inserted == 4
    assert summary.skipped == 0
    assert session.commits == 2


def test_empty_page_is_unresolved_and_does_not_loop() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    calls = []

    def empty_page(*args, **kwargs):
        calls.append(kwargs)
        return []

    summary = fetch_and_persist_range(
        FakeSession(),
        symbol="BTCUSDT",
        interval="1m",
        gap=GapRange(start, start + timedelta(hours=1)),
        fetch_page=empty_page,
    )
    assert len(calls) == 1
    assert summary.pages == 1
    assert summary.unresolved == 1


def test_candle_validation_rejects_bad_ohlcv_and_unaligned_time() -> None:
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="high must"):
        validate_candle(candle_at(timestamp, high=Decimal("99")))
    with pytest.raises(ValueError, match="non-negative"):
        validate_candle(candle_at(timestamp, volume=Decimal("-1")))
    with pytest.raises(ValueError, match="aligned"):
        validate_candle(candle_at(timestamp + timedelta(seconds=1)))


def test_conflicting_stored_candles_are_reported_without_overwrite(caplog) -> None:
    candle = candle_at(datetime(2024, 1, 1, tzinfo=UTC))
    stored = SimpleNamespace(
        timestamp=candle.timestamp,
        open=Decimal("99"),
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )

    class ConflictSession(FakeSession):
        def __init__(self):
            super().__init__(inserted=0)

        def scalars(self, statement):
            return FakeResult([stored])

    result, conflicts = persist_page(ConflictSession(), [candle])
    assert conflicts == 1
    assert result.inserted == 0
    assert result.skipped == 1
    assert "Candle data conflict" in caplog.text


def test_fetch_klines_retries_429_using_retry_after(monkeypatch) -> None:
    responses = [429, 200]
    delays = []

    def handler(request):
        status = responses.pop(0)
        if status == 429:
            return httpx.Response(
                429,
                headers={"Retry-After": "3"},
                request=request,
            )
        return httpx.Response(200, json=[], request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        candles = fetch_klines(
            "BTCUSDT",
            "1m",
            client=client,
            sleep=delays.append,
        )
    assert candles == []
    assert delays == [3.0]


def test_http_418_stops_without_retry() -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(418, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        with pytest.raises(BinanceThrottleError, match="respect the IP ban"):
            fetch_klines("BTCUSDT", "1m", client=client)
    assert len(calls) == 1


def test_transient_transport_error_is_retried() -> None:
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200, json=[], request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL) as client:
        assert fetch_klines(
            "BTCUSDT",
            "1m",
            client=client,
            sleep=lambda _: None,
        ) == []
    assert len(calls) == 2
