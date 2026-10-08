from datetime import datetime, timedelta, timezone

from bitcoin_analytics.gaps import _MISSING_RANGES_SQL, find_gaps

UTC = timezone.utc


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows_by_window):
        self.rows_by_window = iter(rows_by_window)
        self.params = []

    def execute(self, statement, params):
        self.params.append(params)
        assert "generate_series" in str(statement)
        assert "LEFT JOIN bitcoin_candles" in str(statement)
        return FakeResult(next(self.rows_by_window))


def test_detects_initial_internal_and_final_grouped_gaps() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    step = timedelta(minutes=1)
    session = FakeSession(
        [[
            {"range_start": start, "range_end": start + step},
            {"range_start": start + 2 * step, "range_end": start + 4 * step},
            {"range_start": start + 5 * step, "range_end": start + 6 * step},
        ]]
    )

    gaps = list(
        find_gaps(
            session,
            exchange="binance",
            symbol="BTCUSDT",
            interval="1m",
            start=start,
            end=start + 6 * step,
        )
    )
    assert [(gap.start, gap.end) for gap in gaps] == [
        (start, start + step),
        (start + 2 * step, start + 4 * step),
        (start + 5 * step, start + 6 * step),
    ]


def test_gap_scan_uses_bounded_windows() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    session = FakeSession([[], []])
    list(
        find_gaps(
            session,
            exchange="binance",
            symbol="BTCUSDT",
            interval="1m",
            start=start,
            end=start + timedelta(minutes=5),
            max_window_points=3,
        )
    )
    assert len(session.params) == 2
    assert session.params[0]["window_end"] == start + timedelta(minutes=3)
    assert session.params[1]["window_start"] == start + timedelta(minutes=3)
    assert "lag(timestamp)" in str(_MISSING_RANGES_SQL)
