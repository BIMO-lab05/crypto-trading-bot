"""
Persistence tests for KellyPositionSizer.

Uses an in-memory aiosqlite DB and bypasses the autouse `mock_database_connection`
fixture from conftest.py by passing a real async session factory directly to the
sizer (the sizer accepts `db_session_factory` as a constructor arg, so it never
touches the patched global db_manager).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.connection import Base
from app.risk.kelly_models import KellyTradeHistory  # noqa: F401  (register on Base)
from app.risk.kelly_position_sizing import KellyPositionSizer, TradeRecord


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: KellyTradeHistory.__table__.create(sync_conn)
        )
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    yield factory
    await engine.dispose()


def _make_trade(idx: int, *, win: bool = True) -> TradeRecord:
    base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    return TradeRecord(
        trade_id=f"trade-{idx}",
        symbol="SOLUSDT",
        entry_time=base + timedelta(minutes=idx),
        exit_time=base + timedelta(minutes=idx + 5),
        entry_price=100.0 + idx,
        exit_price=102.0 + idx if win else 99.0 + idx,
        pnl=2.0 if win else -1.0,
        pnl_pct=2.0 if win else -1.0,
        is_win=win,
        strategy="stat_arb",
        kelly_suggested=3.0,
        actual_size=2.5,
    )


async def test_round_trip_persist_and_load(session_factory):
    sizer = KellyPositionSizer(db_session_factory=session_factory)
    original = _make_trade(1, win=True)

    await sizer._persist_trade_async(original)

    fresh = KellyPositionSizer(db_session_factory=session_factory)
    loaded_count = await fresh.load_trades_from_db(limit=10)

    assert loaded_count == 1
    assert len(fresh._trade_history) == 1
    replayed = fresh._trade_history[0]
    assert replayed.trade_id == original.trade_id
    assert replayed.symbol == original.symbol
    assert replayed.entry_price == original.entry_price
    assert replayed.exit_price == original.exit_price
    assert replayed.pnl == original.pnl
    assert replayed.pnl_pct == original.pnl_pct
    assert replayed.is_win == original.is_win
    assert replayed.strategy == original.strategy
    assert replayed.kelly_suggested == original.kelly_suggested
    assert replayed.actual_size == original.actual_size
    # SQLite drops tz info; production Postgres preserves it. Compare naive.
    assert replayed.entry_time.replace(tzinfo=None) == original.entry_time.replace(tzinfo=None)
    assert replayed.exit_time.replace(tzinfo=None) == original.exit_time.replace(tzinfo=None)

    assert fresh._total_trades == 1
    assert fresh._winning_trades == 1


async def test_load_from_empty_db_returns_zero(session_factory):
    sizer = KellyPositionSizer(db_session_factory=session_factory)
    loaded = await sizer.load_trades_from_db(limit=50)
    assert loaded == 0
    assert len(sizer._trade_history) == 0
    assert sizer._total_trades == 0


async def test_load_orders_oldest_first_and_caps_at_limit(session_factory):
    sizer = KellyPositionSizer(db_session_factory=session_factory)
    for i in range(5):
        await sizer._persist_trade_async(_make_trade(i, win=(i % 2 == 0)))

    fresh = KellyPositionSizer(db_session_factory=session_factory)
    loaded = await fresh.load_trades_from_db(limit=3)

    assert loaded == 3
    history = list(fresh._trade_history)
    assert [t.trade_id for t in history] == ["trade-2", "trade-3", "trade-4"]


async def test_replay_does_not_repersist(session_factory):
    """load_trades_from_db must replay through record_trade with _persist=False."""
    sizer = KellyPositionSizer(db_session_factory=session_factory)
    await sizer._persist_trade_async(_make_trade(1, win=True))

    fresh = KellyPositionSizer(db_session_factory=session_factory)
    await fresh.load_trades_from_db(limit=10)

    from sqlalchemy import func, select

    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(KellyTradeHistory)
        )
        count = result.scalar_one()

    assert count == 1
