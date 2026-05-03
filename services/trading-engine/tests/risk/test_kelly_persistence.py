"""
Round-trip tests for KellyPositionSizer state persistence.

Uses an in-memory SQLite engine so no real PostgreSQL is required. The
production schema lives in database/migrations/006_create_kelly_state.sql;
ensure_schema() in kelly_persistence creates the equivalent table on the
SQLite engine for tests.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.risk.kelly_persistence import ensure_schema
from app.risk.kelly_position_sizing import (
    KellyPositionSizer,
    TradeRecord,
)


@pytest.fixture
def session_factory():
    """In-memory SQLite engine + sync session factory shared across the test."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        # StaticPool keeps the same in-memory database across sessions.
        connect_args={"check_same_thread": False},
        poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
    )
    with engine.begin() as conn:
        ensure_schema(conn)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield factory
    engine.dispose()


def _winning_trade(i: int, pct: float = 2.0) -> TradeRecord:
    return TradeRecord(
        trade_id=f"win-{i}",
        symbol="SOLUSDT",
        entry_time=datetime.utcnow() - timedelta(hours=i),
        exit_time=datetime.utcnow() - timedelta(hours=i, minutes=-30),
        entry_price=100.0,
        exit_price=100.0 * (1 + pct / 100),
        pnl=pct,
        pnl_pct=pct,
        is_win=True,
    )


def _losing_trade(i: int, pct: float = 1.5) -> TradeRecord:
    return TradeRecord(
        trade_id=f"loss-{i}",
        symbol="SOLUSDT",
        entry_time=datetime.utcnow() - timedelta(hours=i),
        exit_time=datetime.utcnow() - timedelta(hours=i, minutes=-30),
        entry_price=100.0,
        exit_price=100.0 * (1 - pct / 100),
        pnl=-pct,
        pnl_pct=-pct,
        is_win=False,
    )


def test_save_then_load_restores_aggregates(session_factory):
    sizer = KellyPositionSizer(db_session_factory=session_factory)
    for i in range(6):
        sizer.record_trade(_winning_trade(i))
    for i in range(4):
        sizer.record_trade(_losing_trade(i))

    snapshot = {
        "total_trades": sizer._total_trades,
        "winning_trades": sizer._winning_trades,
        "losing_trades": sizer._losing_trades,
        "total_wins_pct": sizer._total_wins_pct,
        "total_losses_pct": sizer._total_losses_pct,
        "current_streak": sizer._current_streak,
        "current_kelly_fraction": sizer._current_kelly_fraction,
        "rolling_len": len(sizer._trade_history),
    }

    fresh = KellyPositionSizer(db_session_factory=session_factory)
    restored = fresh.load_trades_from_db()

    assert restored == snapshot["rolling_len"]
    assert fresh._total_trades == snapshot["total_trades"]
    assert fresh._winning_trades == snapshot["winning_trades"]
    assert fresh._losing_trades == snapshot["losing_trades"]
    assert fresh._total_wins_pct == pytest.approx(snapshot["total_wins_pct"])
    assert fresh._total_losses_pct == pytest.approx(snapshot["total_losses_pct"])
    assert fresh._current_streak == snapshot["current_streak"]
    assert fresh._current_kelly_fraction == pytest.approx(snapshot["current_kelly_fraction"])


def test_load_with_no_row_returns_zero(session_factory):
    fresh = KellyPositionSizer(db_session_factory=session_factory)
    assert fresh.load_trades_from_db() == 0
    assert fresh._total_trades == 0


def test_save_is_upsert(session_factory):
    sizer = KellyPositionSizer(db_session_factory=session_factory)
    sizer.record_trade(_winning_trade(1))
    sizer.record_trade(_winning_trade(2))
    sizer.record_trade(_losing_trade(1))

    # Trigger a second persist with different state — should overwrite the
    # 'global' row, not insert a duplicate.
    sizer.record_trade(_losing_trade(2))

    fresh = KellyPositionSizer(db_session_factory=session_factory)
    fresh.load_trades_from_db()

    # 4 trades total: 2 wins, 2 losses.
    assert fresh._total_trades == 4
    assert fresh._winning_trades == 2
    assert fresh._losing_trades == 2


def test_rolling_window_trades_round_trip(session_factory):
    sizer = KellyPositionSizer(db_session_factory=session_factory)
    sizer.record_trade(_winning_trade(1, pct=3.0))
    sizer.record_trade(_losing_trade(1, pct=1.0))

    fresh = KellyPositionSizer(db_session_factory=session_factory)
    fresh.load_trades_from_db()

    assert len(fresh._trade_history) == 2
    assert fresh._trade_history[0].is_win is True
    assert fresh._trade_history[0].pnl_pct == pytest.approx(3.0)
    assert fresh._trade_history[1].is_win is False
    assert fresh._trade_history[1].pnl_pct == pytest.approx(-1.0)
