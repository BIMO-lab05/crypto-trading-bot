"""
Regression tests for GET /api/v1/trading/trades/history
(app/handlers/performance_dashboard.py::get_trade_history_endpoint).

Bug 2026-08-18 (root cause of every daily report's
"trade history unavailable, best/worst=0" note):

1. The response builder read ``pos.id`` but the ORM model
   (app/database/models.py Position) keys its PK as ``position_id`` —
   every non-empty read raised AttributeError and returned 500.
2. The ``status=ALL`` branch called
   ``position_repo.get_positions_by_status(...)``, a method that has
   never existed on PositionRepository — that path always 500'd.

Fix: build items from ``pos.position_id``; ALL = lenient open read +
closed read combined. These tests exercise all three status paths
against a stub repository so either regression 500s again loudly.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.handlers.performance_dashboard import get_trade_history_endpoint


class _StubDBPosition:
    """Mimics app.database.models.Position: PK is position_id, no .id."""

    def __init__(self, status="CLOSED"):
        self.position_id = uuid4()
        self.symbol = "ADAUSDT"
        self.side = "LONG"
        self.strategy = "ensemble"
        self.entry_price = Decimal("0.63412345")
        self.exit_price = Decimal("0.64123456") if status == "CLOSED" else None
        self.quantity = Decimal("15.0")
        self.realized_pnl = Decimal("0.1066") if status == "CLOSED" else None
        self.opened_at = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)
        self.closed_at = (
            datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
            if status == "CLOSED"
            else None
        )
        self.status = status


class _StubRepo:
    def __init__(self, open_positions, closed_positions):
        self._open = open_positions
        self._closed = closed_positions

    async def get_open_positions_or_empty(self, portfolio_id="paper_trading"):
        return list(self._open)

    async def get_closed_positions(self, portfolio_id="paper_trading", limit=50):
        return list(self._closed)[:limit]


def _patched_repo(repo):
    return patch(
        "app.handlers.performance_dashboard.get_position_repository",
        return_value=repo,
    )


@pytest.mark.unit
class TestTradeHistoryEndpoint:
    async def test_closed_path_serves_position_id(self):
        closed = [_StubDBPosition("CLOSED"), _StubDBPosition("CLOSED")]
        with _patched_repo(_StubRepo([], closed)):
            resp = await get_trade_history_endpoint(
                limit=100, offset=0, status="CLOSED"
            )
        assert resp.success is True
        assert resp.total_count == 2
        assert resp.trades[0].id == str(closed[0].position_id)
        assert resp.trades[0].realized_pnl == pytest.approx(0.1066)

    async def test_all_path_combines_open_and_closed(self):
        open_ = [_StubDBPosition("OPEN")]
        closed = [_StubDBPosition("CLOSED")]
        with _patched_repo(_StubRepo(open_, closed)):
            resp = await get_trade_history_endpoint(limit=100, offset=0, status="ALL")
        assert resp.success is True
        assert resp.total_count == 2
        assert {t.status for t in resp.trades} == {"OPEN", "CLOSED"}

    async def test_open_path_serves_open_positions(self):
        open_ = [_StubDBPosition("OPEN")]
        with _patched_repo(_StubRepo(open_, [])):
            resp = await get_trade_history_endpoint(limit=100, offset=0, status="OPEN")
        assert resp.total_count == 1
        assert resp.trades[0].exit_price is None

    async def test_pagination_applies_after_combination(self):
        closed = [_StubDBPosition("CLOSED") for _ in range(5)]
        with _patched_repo(_StubRepo([], closed)):
            resp = await get_trade_history_endpoint(limit=2, offset=1, status="CLOSED")
        # The repo read is capped at limit+offset, so total_count reflects
        # the fetched window (3), not the table size.
        assert resp.total_count == 3
        assert len(resp.trades) == 2
        assert resp.trades[0].id == str(closed[1].position_id)
