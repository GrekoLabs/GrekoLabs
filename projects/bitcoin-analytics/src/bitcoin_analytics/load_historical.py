import argparse

from backend.app.database import Base, SessionLocal, engine
from backend.app.models.bitcoin_candle import BitcoinCandle  # noqa: F401
from backend.app.services.bitcoin_candles import save_bitcoin_candles

from .collectors.binance import fetch_klines


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a small Binance candle batch.")
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help="Create missing tables for local development before loading.",
    )
    args = parser.parse_args()

    candles = fetch_klines(
        "BTCUSDT",
        "1h",
        limit=10,
        include_open_candle=False,
    )
    if args.create_tables:
        Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        result = save_bitcoin_candles(session, candles)

    print(f"received: {result.received}")
    print(f"inserted: {result.inserted}")
    print(f"skipped: {result.skipped}")


if __name__ == "__main__":
    main()