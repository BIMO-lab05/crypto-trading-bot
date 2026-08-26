"""RES-09: /api/v1/transactions hydrates from the shared trades table.

Field mapping is against the controller-verified LIVE schema of
public.trades (columns: id, trade_id, portfolio_id, symbol, side, quantity,
price, total_value, fee, realized_pnl, strategy, signal_confidence,
executed_at, metadata) — not the stale SQLAlchemy model the brief was
originally drafted against. There is no action/total_cost/pnl_percentage/
position_id column on the live table.
"""

import datetime as dt
import logging
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

import app.handlers.transaction_history as transaction_history_module
from app.handlers.transaction_history import get_transaction_history
from app.services.trade_history_db import fetch_transactions


class FakePool:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_args = None

    async def fetch(self, query, *args):
        self.last_query = query
        self.last_args = args
        return self._rows


def _row(**kw):
    # asyncpg returns NAIVE datetimes for "timestamp without time zone"
    # columns; executed_at is stored as UTC but arrives with no tzinfo.
    base = dict(
        trade_id="11111111-2222-3333-4444-555555555555",
        portfolio_id="paper_trading",
        symbol="SOLUSDT",
        side="SELL",
        quantity=Decimal("0.05"),
        price=Decimal("180.0"),
        total_value=Decimal("9.0"),
        realized_pnl=Decimal("0.25"),
        executed_at=dt.datetime(2026, 8, 22, 1, 0),
    )
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_fetch_maps_row_to_transaction():
    pool = FakePool([_row()])
    txns = await fetch_transactions(pool, "paper_trading", limit=50, symbol=None)
    t = txns[0]
    assert t.transaction_id == "11111111-2222-3333-4444-555555555555"
    assert t.portfolio_id == "paper_trading"
    assert t.symbol == "SOLUSDT"
    assert t.action == "SELL"
    assert t.quantity == "0.05"
    assert t.price == "180.0"
    assert t.total_amount == "9.0"
    assert t.realized_pnl == "0.25"
    # Live trades table has no pnl_percentage column — never fabricated.
    assert t.realized_pnl_pct is None
    # Naive executed_at must be treated as UTC, not local container tz.
    expected = int(dt.datetime(2026, 8, 22, 1, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
    assert t.timestamp == expected


@pytest.mark.asyncio
async def test_fetch_buy_row_has_no_pnl():
    pool = FakePool([_row(side="BUY", realized_pnl=None)])
    txns = await fetch_transactions(pool, "paper_trading", limit=None, symbol=None)
    assert txns[0].action == "BUY"
    assert txns[0].realized_pnl is None
    assert txns[0].realized_pnl_pct is None


@pytest.mark.asyncio
async def test_fetch_parameterizes_symbol_and_limit():
    pool = FakePool([])
    await fetch_transactions(pool, "paper_trading", limit=10, symbol="SOLUSDT")
    assert "$2" in pool.last_query  # symbol is a bind param, never interpolated
    assert "SOLUSDT" in pool.last_args
    assert 10 in pool.last_args


@pytest.mark.asyncio
async def test_fetch_no_symbol_filter_omits_second_param():
    pool = FakePool([])
    await fetch_transactions(pool, "paper_trading", limit=None, symbol=None)
    assert "symbol = $2" not in pool.last_query
    assert pool.last_args == ("paper_trading",)


@pytest.mark.asyncio
async def test_fetch_empty_rows_returns_empty_list():
    pool = FakePool([])
    txns = await fetch_transactions(pool, "paper_trading", limit=50, symbol=None)
    assert txns == []


# ---------------------------------------------------------------------------
# Handler-seam tests: `get_transaction_history` must pick DB hydration when a
# pool is available and fall back to the in-memory manager (with a one-time
# warning) when it is not. The pre-existing handler test module
# (test_transaction_history_handler.py) is skipped whole-module since PR #86,
# so this seam otherwise has zero coverage.
# ---------------------------------------------------------------------------


def _mock_portfolio_manager(in_memory_transactions=None):
    manager = Mock()
    manager.get_portfolio.return_value = Mock()  # any truthy portfolio
    manager.get_transaction_history.return_value = in_memory_transactions or []
    return manager


@pytest.mark.asyncio
async def test_handler_hydrates_from_db_pool_when_available():
    pool = FakePool([_row()])
    manager = _mock_portfolio_manager()

    with (
        patch.object(transaction_history_module, "get_db_pool", return_value=pool),
        patch.object(transaction_history_module, "get_portfolio_manager", return_value=manager),
    ):
        response = await get_transaction_history("paper_trading", limit=50, symbol=None)

    assert response.total_count == 1
    assert response.transactions[0].action == "SELL"
    manager.get_transaction_history.assert_not_called()


@pytest.mark.asyncio
async def test_handler_falls_back_to_memory_when_no_pool(caplog):
    transaction_history_module._warned_no_db_pool = False
    manager = _mock_portfolio_manager()

    with (
        patch.object(transaction_history_module, "get_db_pool", return_value=None),
        patch.object(transaction_history_module, "get_portfolio_manager", return_value=manager),
        caplog.at_level(logging.WARNING),
    ):
        await get_transaction_history("paper_trading", limit=50, symbol=None)
        await get_transaction_history("paper_trading", limit=50, symbol=None)

    assert manager.get_transaction_history.call_count == 2
    warnings = [r for r in caplog.records if "trades hydration unavailable" in r.message]
    assert len(warnings) == 1  # warned once, not on every call
