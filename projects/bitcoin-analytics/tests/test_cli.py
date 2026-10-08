import httpx

from bitcoin_analytics import backfill, repair


def test_backfill_all_uses_required_interval_order(monkeypatch) -> None:
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(backfill, "run", fake_run)
    result = backfill.main(["--interval", "all", "--dry-run"])
    assert result == 0
    assert captured["intervals"] == ("1d", "4h", "1h", "15m", "5m", "1m")
    assert captured["dry_run"] is True


def test_repair_invokes_gap_repair_for_selected_interval(monkeypatch) -> None:
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(repair, "run", fake_run)
    assert repair.main(["--interval", "5m", "--start", "2024-01-01"]) == 0
    assert captured["intervals"] == ("5m",)
    assert captured["symbol"] == "BTCUSDT"


def test_backfill_rechecks_database_gaps_on_each_run(monkeypatch) -> None:
    from datetime import datetime, timezone

    from bitcoin_analytics.history import GapRange, RunSummary

    calls = []
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(backfill, "SessionLocal", SessionContext)

    def gaps(*args, **kwargs):
        calls.append("scan")
        if len(calls) == 1:
            yield GapRange(start, datetime(2024, 1, 2, tzinfo=timezone.utc))

    processed = []

    def process(*args, **kwargs):
        processed.append(kwargs["gap"])
        return RunSummary(pages=1, received=1, inserted=1)

    monkeypatch.setattr(backfill, "find_gaps", gaps)
    monkeypatch.setattr(backfill, "fetch_and_persist_range", process)
    common = {
        "symbol": "BTCUSDT",
        "intervals": ("1d",),
        "start": "2024-01-01",
        "end": "2024-01-02",
        "limit": 1000,
    }

    assert backfill.run(**common) == 0
    assert backfill.run(**common) == 0
    assert len(processed) == 1
    assert len(calls) == 4


def test_dry_run_does_not_fetch_or_persist(monkeypatch) -> None:
    from datetime import datetime, timezone

    from bitcoin_analytics.history import GapRange

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(backfill, "SessionLocal", SessionContext)
    monkeypatch.setattr(
        backfill,
        "find_gaps",
        lambda *args, **kwargs: iter(
            [GapRange(start, datetime(2024, 1, 2, tzinfo=timezone.utc))]
        ),
    )
    monkeypatch.setattr(
        backfill,
        "fetch_and_persist_range",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected request")),
    )
    assert (
        backfill.run(
            symbol="BTCUSDT",
            intervals=("1d",),
            start="2024-01-01",
            end="2024-01-02",
            limit=1000,
            dry_run=True,
        )
        == 0
    )


def test_rate_limit_stops_requests_for_remaining_gaps(monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from bitcoin_analytics.collectors.binance import BinanceThrottleError
    from bitcoin_analytics.history import GapRange

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(backfill, "SessionLocal", SessionContext)
    monkeypatch.setattr(
        backfill,
        "find_gaps",
        lambda *args, **kwargs: iter(
            [
                GapRange(start, start + timedelta(days=1)),
                GapRange(start + timedelta(days=2), start + timedelta(days=3)),
            ]
        ),
    )
    requests = []

    def blocked(*args, **kwargs):
        requests.append(1)
        raise BinanceThrottleError(
            "blocked",
            request=httpx.Request("GET", "https://api.binance.com/api/v3/klines"),
            response=httpx.Response(418),
        )

    monkeypatch.setattr(backfill, "fetch_and_persist_range", blocked)
    assert (
        backfill.run(
            symbol="BTCUSDT",
            intervals=("1d",),
            start="2024-01-01",
            end="2024-01-04",
            limit=1000,
        )
        == 1
    )
    assert len(requests) == 1
