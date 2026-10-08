import argparse
import logging
import sys
import time
from collections.abc import Sequence

import httpx
from sqlalchemy.exc import SQLAlchemyError

from backend.app.database import SessionLocal

from .collectors.binance import (
    MAX_LIMIT,
    VALID_INTERVALS,
    BinanceThrottleError,
    fetch_klines,
)
from .gaps import find_gaps
from .history import DEFAULT_START, GapRange, RunSummary, fetch_and_persist_range, parse_utc_datetime, resolve_range

INTERVAL_ORDER = ("1d", "4h", "1h", "15m", "5m", "1m")
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill closed Binance Spot OHLCV candles.")
    parser.add_argument("--symbol", default="BTCUSDT", help="Spot market symbol (default: BTCUSDT)")
    parser.add_argument(
        "--interval",
        choices=(*VALID_INTERVALS, "all"),
        default="all",
        help="Candle interval, or all in recommended order (default: all)",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START.isoformat(),
        help="Inclusive UTC start timestamp (default: 2020-01-01)",
    )
    parser.add_argument(
        "--end",
        help="Exclusive UTC end timestamp (default: latest closed-candle boundary)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_LIMIT,
        help=f"Maximum candles per Binance request (1-{MAX_LIMIT}, default: {MAX_LIMIT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report missing ranges without downloading or writing candles",
    )
    return parser


def run(
    *,
    symbol: str,
    intervals: Sequence[str],
    start: str,
    end: str | None,
    limit: int,
    dry_run: bool = False,
    session_factory=SessionLocal,
    fetch_page=fetch_klines,
) -> int:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

    started = time.monotonic()
    total = RunSummary()
    failed = False
    throttled = False
    with session_factory() as session:
        client = httpx.Client(base_url="https://api.binance.com", timeout=10.0)
        try:
            for interval in intervals:
                span = resolve_range(start, end, interval)
                interval_started = time.monotonic()
                range_count = 0
                interval_summary = RunSummary()
                gaps = find_gaps(
                    session,
                    exchange="binance",
                    symbol=symbol,
                    interval=interval,
                    start=span.start,
                    end=span.end,
                )
                if dry_run:
                    for _ in gaps:
                        range_count += 1
                    interval_summary.pending = range_count
                else:
                    for gap in gaps:
                        range_count += 1
                        try:
                            page_summary = fetch_and_persist_range(
                                session,
                                symbol=symbol,
                                interval=interval,
                                gap=gap,
                                limit=limit,
                                client=client,
                                fetch_page=fetch_page,
                            )
                        except BinanceThrottleError:
                            interval_summary.errors += 1
                            interval_summary.unresolved += 1
                            throttled = True
                            logger.error(
                                "Binance rate limit or IP ban received; stopping further requests"
                            )
                            break
                        _merge(interval_summary, page_summary)
                    interval_summary.pending = sum(
                        1
                        for _ in find_gaps(
                            session,
                            exchange="binance",
                            symbol=symbol,
                            interval=interval,
                            start=span.start,
                            end=span.end,
                        )
                    )
                _merge(total, interval_summary)
                failed |= (
                    interval_summary.errors > 0
                    or interval_summary.unresolved > 0
                    or interval_summary.pending > 0 and not dry_run
                )
                logger.info(
                    "%s %s: gaps_detected=%d pages=%d received=%d inserted=%d "
                    "skipped=%d gaps_pending=%d unresolved=%d errors=%d "
                    "conflicts=%d duration=%.1fs",
                    symbol,
                    interval,
                    range_count,
                    interval_summary.pages,
                    interval_summary.received,
                    interval_summary.inserted,
                    interval_summary.skipped,
                    interval_summary.pending,
                    interval_summary.unresolved,
                    interval_summary.errors,
                    interval_summary.conflicts,
                    time.monotonic() - interval_started,
                )
                if throttled:
                    break
        finally:
            client.close()
    logger.info(
        "Backfill summary: pages=%d received=%d inserted=%d skipped=%d "
        "gaps_pending=%d unresolved=%d errors=%d conflicts=%d duration=%.1fs",
        total.pages,
        total.received,
        total.inserted,
        total.skipped,
        total.pending,
        total.unresolved,
        total.errors,
        total.conflicts,
        time.monotonic() - started,
    )
    return 1 if failed or total.conflicts else 0


def _merge(target: RunSummary, source: RunSummary) -> None:
    target.pages += source.pages
    target.received += source.received
    target.inserted += source.inserted
    target.skipped += source.skipped
    target.pending += source.pending
    target.unresolved += source.unresolved
    target.errors += source.errors
    target.conflicts += source.conflicts


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    if not args.symbol:
        raise SystemExit("--symbol must not be empty")
    try:
        parse_utc_datetime(args.start)
        if args.end:
            parse_utc_datetime(args.end)
        intervals = INTERVAL_ORDER if args.interval == "all" else (args.interval,)
        return run(
            symbol=args.symbol.upper(),
            intervals=intervals,
            start=args.start,
            end=args.end,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except (ValueError, RuntimeError) as error:
        logger.error("%s", error)
        return 2
    except SQLAlchemyError as error:
        logger.error("PostgreSQL operation failed (%s)", type(error).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
