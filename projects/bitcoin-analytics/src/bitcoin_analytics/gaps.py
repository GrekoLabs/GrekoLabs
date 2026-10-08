from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from .history import GapRange, interval_delta, validate_aligned

MAX_WINDOW_POINTS = 10_000

_MISSING_RANGES_SQL = text(
    """
    WITH expected AS (
        SELECT timestamp
        FROM generate_series(
            CAST(:window_start AS timestamptz),
            CAST(:window_end AS timestamptz) - (:step_seconds * INTERVAL '1 second'),
            :step_seconds * INTERVAL '1 second'
        ) AS series(timestamp)
    ),
    missing AS (
        SELECT expected.timestamp
        FROM expected
        LEFT JOIN bitcoin_candles AS candle
            ON candle.exchange = :exchange
            AND candle.symbol = :symbol
            AND candle.interval = :interval
            AND candle.timestamp = expected.timestamp
        WHERE candle.id IS NULL
    ),
    marked AS (
        SELECT
            timestamp,
            CASE
                WHEN lag(timestamp) OVER (ORDER BY timestamp) IS NULL
                    OR timestamp > lag(timestamp) OVER (ORDER BY timestamp)
                        + (:step_seconds * INTERVAL '1 second')
                THEN 1
                ELSE 0
            END AS new_group
        FROM missing
    ),
    grouped AS (
        SELECT
            timestamp,
            sum(new_group) OVER (ORDER BY timestamp) AS group_id
        FROM marked
    )
    SELECT min(timestamp) AS range_start,
           max(timestamp) + (:step_seconds * INTERVAL '1 second') AS range_end
    FROM grouped
    GROUP BY group_id
    ORDER BY range_start
    """
)


def find_gaps(
    session: Session,
    *,
    exchange: str,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    max_window_points: int = MAX_WINDOW_POINTS,
) -> Iterator[GapRange]:
    step = interval_delta(interval)
    validate_aligned(start, interval)
    validate_aligned(end, interval)
    if start >= end:
        raise ValueError("start must be earlier than the exclusive end")
    if max_window_points < 1:
        raise ValueError("max_window_points must be positive")

    window_span = step * max_window_points
    window_start = start
    while window_start < end:
        window_end = min(window_start + window_span, end)
        result = session.execute(
            _MISSING_RANGES_SQL,
            {
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "window_start": window_start,
                "window_end": window_end,
                "step_seconds": int(step.total_seconds()),
            },
        )
        rows = result.mappings().all()
        for row in rows:
            yield GapRange(start=row["range_start"], end=row["range_end"])
        window_start = window_end
