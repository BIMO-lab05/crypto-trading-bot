"""
Manual spot transaction gate (FIX 11, 2026-08-12 profit-path repair)

The portfolio is a mirror of the trading-engine book: the engine sync
overwrites local state within 60s, so manual buy/sell/rebalance-execute
produce fake fills that are guaranteed to drift and then vanish. The
mutating paths must return 409 with an explicit reason; read-only
recommendations (execute=false) stay available.
"""

from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app

GATE_REASON = (
    "manual spot transactions disabled: portfolio mirrors the trading-engine "
    "book; local trades are overwritten by sync within 60s"
)


def _mock_manager():
    """Manager that would happily fill the trade — proves the gate, not a
    downstream failure, is what rejects the request."""
    mock_portfolio = Mock()
    mock_portfolio.assets = {
        "BTCUSDT": Mock(current_allocation_pct=Decimal("60")),
        "ETHUSDT": Mock(current_allocation_pct=Decimal("40")),
    }
    mock_portfolio.total_value = Decimal("100")
    manager = Mock()
    manager.get_portfolio.return_value = mock_portfolio
    manager._fetch_current_price = AsyncMock(return_value=Decimal("50000"))
    manager.execute_transaction.return_value = (True, "Transaction successful", None)
    return manager


class TestManualTransactionsGated:
    """Mutating spot paths must 409; the local ledger is engine-owned."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_buy_returns_409_with_reason(self):
        manager = _mock_manager()
        with patch("app.main.portfolio_manager", manager):
            response = self.client.post(
                "/api/v1/transaction/buy",
                params={"symbol": "BTCUSDT", "quantity": "0.0001", "price": "50000"},
            )

        assert response.status_code == 409
        assert response.json()["detail"] == GATE_REASON
        manager.execute_transaction.assert_not_called()

    def test_sell_returns_409_with_reason(self):
        manager = _mock_manager()
        with patch("app.main.portfolio_manager", manager):
            response = self.client.post(
                "/api/v1/transaction/sell",
                params={"symbol": "BTCUSDT", "quantity": "0.0001", "price": "50000"},
            )

        assert response.status_code == 409
        assert response.json()["detail"] == GATE_REASON
        manager.execute_transaction.assert_not_called()

    def test_rebalance_execute_true_returns_409(self):
        manager = _mock_manager()
        optimizer = Mock()
        optimizer.calculate_rebalancing_trades.return_value = {
            "BTCUSDT": ("SELL", 10.0),
            "ETHUSDT": ("BUY", 10.0),
        }
        with (
            patch("app.main.portfolio_manager", manager),
            patch("app.main.portfolio_optimizer", optimizer),
        ):
            response = self.client.post(
                "/api/v1/portfolio/rebalance",
                params={"execute": "true"},
                json={"BTCUSDT": 0.5, "ETHUSDT": 0.5},
            )

        assert response.status_code == 409
        assert response.json()["detail"] == GATE_REASON
        manager.execute_transaction.assert_not_called()

    def test_rebalance_recommendations_still_available(self):
        """execute=false (dry run) is read-only and must keep working."""
        manager = _mock_manager()
        optimizer = Mock()
        optimizer.calculate_rebalancing_trades.return_value = {
            "BTCUSDT": ("SELL", 10.0),
            "ETHUSDT": ("BUY", 10.0),
        }
        with (
            patch("app.main.portfolio_manager", manager),
            patch("app.main.portfolio_optimizer", optimizer),
        ):
            response = self.client.post(
                "/api/v1/portfolio/rebalance",
                params={"execute": "false"},
                json={"BTCUSDT": 0.5, "ETHUSDT": 0.5},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["executed"] is False
        assert len(data["trades"]) == 2
        manager.execute_transaction.assert_not_called()
