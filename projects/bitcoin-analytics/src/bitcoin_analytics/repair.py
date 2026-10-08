import argparse
import logging
import sys
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from .backfill import INTERVAL_ORDER, run
from .collectors.binance import MAX_LIMIT, VALID_INTERVALS
from .history import DEFAULT_START


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Repair missing Binance Spot OHLCV candles.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", choices=(*VALID_INTERVALS, "all"), default="all")
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", help="Exclusive UTC end timestamp (default: latest closed-candle boundary)")
    parser.add_argument("--limit", type=int, default=MAX_LIMIT)
    args = parser.parse_args(argv)

    intervals = INTERVAL_ORDER if args.interval == "all" else (args.interval,)
    try:
        return run(
            symbol=args.symbol.upper(),
            intervals=intervals,
            start=args.start,
            end=args.end,
            limit=args.limit,
        )
    except (ValueError, RuntimeError) as error:
        logging.getLogger(__name__).error("%s", error)
        return 2
    except SQLAlchemyError as error:
        logging.getLogger(__name__).error(
            "PostgreSQL operation failed (%s)",
            type(error).__name__,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
