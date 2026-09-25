from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from backend.app.services.bitcoin_candles import save_bitcoin_candles


class FakeResult:
    def scalars(self):
        return self

    def all(self):
        return [1, 2]


class FakeSession:
    executed_statement = None
    committed = False

    def execute(self, statement):
        self.executed_statement = statement
        return FakeResult()

    def commit(self):
        self.committed = True


def make_candle(symbol: str) -> SimpleNamespace:
    return SimpleNamespace(
        exchange="binance",
        symbol=symbol,
        interval="1h",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        open=Decimal("42000.00"),
        high=Decimal("42100.00"),
        low=Decimal("41900.00"),
        close=Decimal("42050.00"),
        volume=Decimal("123.45"),
    )


def test_save_bitcoin_candles_uses_postgres_conflict_handling() -> None:
    session = FakeSession()

    result = save_bitcoin_candles(
        session,
        [make_candle("BTCUSDT"), make_candle("ETHUSDT")],
    )

    compiled = str(
        session.executed_statement.compile(dialect=postgresql.dialect())
    )
    assert result.received == 2
    assert result.inserted == 2
    assert result.skipped == 0
    assert session.committed is True
    assert "ON CONFLICT (exchange, symbol, interval, timestamp) DO NOTHING" in compiled


def test_save_bitcoin_candles_does_not_execute_for_empty_input() -> None:
    session = FakeSession()

    result = save_bitcoin_candles(session, [])

    assert result.received == 0
    assert result.inserted == 0
    assert result.skipped == 0
    assert session.executed_statement is None
    assert session.committed is False