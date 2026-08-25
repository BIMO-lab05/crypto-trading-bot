"""
Unit Tests for Paper Trading Engine
Tests trading simulation logic without real money or database
"""

import pytest

# Un-skipped 2026-07-31. This module carried a blanket
# `pytestmark = pytest.mark.skip(...)` from a PR #86 CI fix-up, disabling all
# 15 tests. Of those, 8 already passed; the rest failed for three reasons,
# none of which was a bug in the engine:
#
#   - order sizes and P&L amounts still scaled for a $10,000 account;
#   - the mock_settings fixture predated leverage, so `default_leverage` was a
#     Mock and `Decimal(str(...))` raised InvalidOperation;
#   - one test asserted long-only behaviour that SHORT enforcement replaced
#     (380a674). It has been rewritten to cover what actually matters now:
#     a plain SELL opens a short, and a reduce_only SELL is rejected.
#
# This is the ledger the declared-capital guarantee rests on, so it gets to run.

from decimal import Decimal
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "shared"))

from app.config import get_settings
from app.paper_trading import PaperTradingEngine
from app.models import (
    OrderCreate,
    OrderStatus,
    OrderSide,
    OrderType,
    PositionSide,
)

#: Declared paper equity, routed through Settings (ADR-029) — never a bare
#: account-size literal. Every dollar expectation below is DERIVED from this
#: so the suite re-scales with the declared account automatically.
_BALANCE = Decimal(str(get_settings().paper_initial_balance))


class TestPaperTradingEngine:
    """Test suite for PaperTradingEngine"""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings configuration"""
        settings = Mock()
        settings.paper_initial_balance = float(_BALANCE)
        settings.paper_commission_pct = 0.1  # 0.1%
        # Leverage was added to the engine after these tests were written. A
        # bare Mock() returns a Mock for it, so `Decimal(str(...))` in
        # execute_market_order raised decimal.InvalidOperation -- which is what
        # actually broke four of these tests. Pin 1x so the arithmetic below
        # stays in notional terms and reads plainly.
        #
        # Stage 0 (2026-08-07): the engine now gates that read on
        # leverage_enabled. Pinned explicitly rather than left to Mock's truthy
        # auto-attribute, so the 1x arithmetic below is stated, not inferred.
        settings.leverage_enabled = True
        settings.default_leverage = 1.0
        # The engine clamps to [min, max] the way auto_trader does; a bare
        # Mock() here would reach Decimal(str(Mock)) and raise InvalidOperation.
        settings.min_leverage = 1.0
        settings.max_leverage = 20.0
        # PAPER-01 (2026-08-03): the paper engine now fills at an adverse,
        # per-symbol price by default. This suite pins the 2026-07-28
        # *accounting* arithmetic -- margin returned, commission, which side
        # gets credited -- not fill realism, and slippage would perturb every
        # expected figure below without testing anything new. So it opts out
        # explicitly, using the same escape hatch an A/B run would use.
        # Fill realism (and the fact that the production default is ON) is
        # pinned in tests/unit/test_paper_slippage.py.
        settings.paper_slippage_enabled = False
        settings.paper_slippage_bps_by_symbol = {}
        settings.paper_slippage_default_bps = 10.0
        # PAPER-02 (2026-08-17): pinned explicitly for the same reason as the
        # leverage fields above — a bare Mock()'s auto-attribute is truthy, so
        # an unpinned paper_funding_enabled would make the close path fetch
        # funding and crash on mock_open_position.opened_at (not a real
        # datetime here). This suite pins accounting arithmetic that predates
        # funding; funding itself is covered in tests/test_paper_funding.py.
        settings.paper_funding_enabled = False
        return settings

    @pytest.fixture
    def mock_position_manager(self):
        """Mock position manager"""
        manager = Mock()
        manager.get_total_unrealized_pnl.return_value = Decimal("0")
        manager.get_open_positions.return_value = []
        manager.get_closed_positions.return_value = []
        return manager

    @pytest.fixture
    def mock_risk_manager(self):
        """Mock risk manager"""
        manager = Mock()
        manager.check_position_limits.return_value = (True, None)
        return manager

    @pytest.fixture
    def mock_trade_repo(self):
        """Mock trade repository"""
        repo = Mock()
        repo.log_trade = AsyncMock()
        return repo

    @pytest.fixture
    def mock_portfolio_repo(self):
        """Mock portfolio repository"""
        return Mock()

    @pytest.fixture
    def trading_engine(
        self,
        mock_settings,
        mock_position_manager,
        mock_risk_manager,
        mock_trade_repo,
        mock_portfolio_repo,
    ):
        """Create PaperTradingEngine with mocked dependencies"""
        with (
            patch("app.paper_trading.get_settings", return_value=mock_settings),
            patch(
                "app.paper_trading.get_position_manager",
                return_value=mock_position_manager,
            ),
            patch("app.paper_trading.get_risk_manager", return_value=mock_risk_manager),
            patch(
                "app.paper_trading.get_trade_repository", return_value=mock_trade_repo
            ),
            patch(
                "app.paper_trading.get_portfolio_repository",
                return_value=mock_portfolio_repo,
            ),
        ):
            engine = PaperTradingEngine()
            return engine

    def test_initialization(self, trading_engine, mock_settings):
        """Test engine initializes with correct settings"""
        assert trading_engine.balance == _BALANCE
        assert trading_engine.initial_balance == _BALANCE
        assert trading_engine.commission_pct == Decimal("0.001")  # 0.1% as decimal

    def test_get_balance(self, trading_engine):
        """Test getting current balance"""
        balance = trading_engine.get_balance()
        assert balance == _BALANCE
        assert isinstance(balance, Decimal)

    def test_get_total_equity_no_positions(self, trading_engine, mock_position_manager):
        """Test total equity with no open positions"""
        mock_position_manager.get_total_unrealized_pnl.return_value = Decimal("0")

        equity = trading_engine.get_total_equity()

        assert equity == _BALANCE
        mock_position_manager.get_total_unrealized_pnl.assert_called_once()

    def test_get_total_equity_with_unrealized_pnl(
        self, trading_engine, mock_position_manager
    ):
        """Test total equity includes unrealized P&L"""
        # The unrealized figure is an explicit scenario delta; the expectation
        # derives from the declared balance so it survives any re-scale.
        mock_position_manager.get_total_unrealized_pnl.return_value = Decimal("5.50")

        equity = trading_engine.get_total_equity()

        assert equity == _BALANCE + Decimal("5.50")

    def test_calculate_commission(self, trading_engine):
        """Test commission calculation"""
        # 0.1% commission on $5000 order = $5
        commission = trading_engine.calculate_commission(Decimal("5000.00"))

        assert commission == Decimal("5.00")

    def test_calculate_commission_small_order(self, trading_engine):
        """Test commission on small order"""
        # 0.1% commission on $100 order = $0.10
        commission = trading_engine.calculate_commission(Decimal("100.00"))

        assert commission == Decimal("0.10")

    @pytest.mark.asyncio
    async def test_execute_buy_order_success(
        self, trading_engine, mock_position_manager
    ):
        """Test successful BUY order execution"""
        # Create mock position
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        # Create BUY order
        # 0.001 BTC @ $50,000 = $50 notional — clears the ~$5 venue floor and
        # is affordable at any balance the config declares (>= $100 per the
        # config bound), so the arithmetic below stays exact and readable.
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            type=OrderType.MARKET,  # Fixed: 'type' not 'order_type'
            strategy="test",
        )

        # Execute order at $50,000
        executed_order, error = await trading_engine.execute_market_order(
            order=order, current_price=Decimal("50000.00")
        )

        # Verify success
        assert error is None
        assert executed_order.status == OrderStatus.FILLED
        assert executed_order.filled_price == Decimal("50000.00")
        assert executed_order.filled_quantity == Decimal("0.001")

        # Balance deducted: margin (50 / 1x leverage) + 0.1% commission (0.05)
        assert trading_engine.balance == _BALANCE - Decimal("50.05")

        # Verify position created
        # entry_signal_confidence was added to the create_position contract
        # 2026-05-15 for post-hoc analysis; it is None when no signal supplied.
        mock_position_manager.create_position.assert_called_once_with(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.001"),
            strategy="test",
            entry_signal_confidence=None,
            # entry_fee joined the contract 2026-08-05 (H7 fee-netting):
            # 0.1% of the $50 notional at the fixture's commission rate.
            entry_fee=Decimal("0.05"),
            # Stage 0 (2026-08-07): the engine now stamps the dollar margin it
            # debited onto the position, and the close leg credits back that
            # recorded amount instead of recomputing notional/default_leverage.
            # At 1x the margin IS the notional.
            posted_margin=Decimal("50.00"),
            leverage=Decimal("1"),
        )

    @pytest.mark.asyncio
    async def test_execute_buy_order_insufficient_balance(self, trading_engine):
        """Test BUY order fails with insufficient balance"""
        # Create BUY order that exceeds balance: 2x the declared equity in
        # notional, whatever the declared equity is.
        price = Decimal("50000.00")
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=(_BALANCE * 2) / price,
            type=OrderType.MARKET,  # Fixed: 'type' not 'order_type'
        )

        # Execute order
        executed_order, error = await trading_engine.execute_market_order(
            order=order, current_price=price
        )

        # Verify failure
        assert error is not None
        assert "Insufficient balance" in error
        assert executed_order.status == OrderStatus.FAILED

        # Verify balance unchanged
        assert trading_engine.balance == _BALANCE

    @pytest.mark.asyncio
    async def test_execute_sell_order_success(
        self, trading_engine, mock_position_manager
    ):
        """Test successful SELL order execution"""
        # First execute BUY to create position
        trading_engine.balance = _BALANCE
        mock_buy_position = Mock()
        mock_buy_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_buy_position

        buy_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            type=OrderType.MARKET,  # Fixed: 'type' not 'order_type'
        )

        await trading_engine.execute_market_order(buy_order, Decimal("50000.00"))

        # Now mock the position as open
        mock_open_position = Mock()
        mock_open_position.id = mock_buy_position.id
        mock_open_position.symbol = "BTCUSDT"
        mock_open_position.side = PositionSide.LONG
        mock_open_position.quantity = Decimal("0.001")
        mock_open_position.remaining_quantity = Decimal("0.001")
        mock_open_position.entry_price = Decimal("50000.00")
        # H7 fee-netting computes the closed-minus-before P&L delta, so the
        # pre-close value must be a real Decimal, not a Mock attribute.
        mock_open_position.realized_pnl = Decimal("0")
        mock_position_manager.get_open_positions.return_value = [mock_open_position]
        # Stage 0 (2026-08-07): the close leg asks the position manager what
        # this position POSTED rather than recomputing it from the global
        # leverage. At 1x on a $50 notional that is $50 — the same figure the
        # old `entry_price * qty / leverage` produced, so the expected balance
        # below is unchanged.
        mock_position_manager.consume_posted_margin.return_value = Decimal("50.00")

        # Mock closed position with profit (rescaled from 200.00 for the $100
        # account: 0.001 BTC moving 50,000 -> 52,000 is a $2 gain)
        mock_closed_position = Mock()
        mock_closed_position.id = mock_buy_position.id
        mock_closed_position.realized_pnl = Decimal("2.00")
        mock_position_manager.close_position.return_value = mock_closed_position

        # Create SELL order
        sell_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=Decimal("0.001"),
            type=OrderType.MARKET,  # Fixed: 'type' not 'order_type'
        )

        # Execute SELL at higher price ($52,000)
        initial_balance = trading_engine.balance
        executed_order, error = await trading_engine.execute_market_order(
            sell_order, Decimal("52000.00")
        )

        # Verify success
        assert error is None
        assert executed_order.status == OrderStatus.FILLED

        # Side-aware close (2026-07-28): credits margin_returned +
        # realized_pnl - commission, NOT the raw close notional.
        #   margin_returned = 50,000 * 0.001 / 1x leverage = 50.00
        #   realized_pnl                                   =  2.00
        #   commission      = 52,000 * 0.001 * 0.1%        =  0.052
        expected_balance = initial_balance + Decimal("51.948")
        assert trading_engine.balance == expected_balance

        # Verify position closed
        mock_position_manager.close_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_sell_order_no_position_opens_short(
        self, trading_engine, mock_position_manager
    ):
        """
        A plain SELL with no open position OPENS A SHORT.

        This test previously asserted the order failed with "No open LONG
        position" -- the long-only behaviour that predates SHORT enforcement
        (Jan 2026, commit 380a674). That expectation is obsolete, not broken:
        the engine deliberately trades both directions now.
        """
        mock_position_manager.get_open_positions.return_value = []
        mock_short = Mock()
        mock_short.id = uuid4()
        mock_position_manager.create_position.return_value = mock_short

        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=Decimal("0.001"),
            type=OrderType.MARKET,  # Fixed: 'type' not 'order_type'
        )

        executed_order, error = await trading_engine.execute_market_order(
            order=order, current_price=Decimal("50000.00")
        )

        assert error is None
        assert executed_order.status == OrderStatus.FILLED
        assert (
            mock_position_manager.create_position.call_args.kwargs["side"]
            == PositionSide.SHORT
        )

    @pytest.mark.asyncio
    async def test_reduce_only_sell_with_no_position_is_rejected(
        self, trading_engine, mock_position_manager
    ):
        """
        The safety property that replaced the old assertion.

        A reduce_only SELL must never open a counter-position. Before the
        2026-07-28 accounting overhaul this silently flipped every stop-loss
        exit into a brand-new short.
        """
        mock_position_manager.get_open_positions.return_value = []

        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=Decimal("0.001"),
            type=OrderType.MARKET,
            reduce_only=True,
        )

        executed_order, error = await trading_engine.execute_market_order(
            order=order, current_price=Decimal("50000.00")
        )

        assert error is not None
        assert executed_order.status == OrderStatus.FAILED
        mock_position_manager.create_position.assert_not_called()

    def test_can_open_position_success(self, trading_engine, mock_risk_manager):
        """Test can open position with sufficient balance"""
        can_open, reason = trading_engine.can_open_position(
            symbol="BTCUSDT", quantity=Decimal("0.001"), price=Decimal("50000.00")
        )

        assert can_open is True
        assert reason is None

    def test_can_open_position_insufficient_balance(self, trading_engine):
        """Test cannot open position with insufficient balance"""
        # 2x the declared equity in notional — too large at any account size.
        price = Decimal("50000.00")
        can_open, reason = trading_engine.can_open_position(
            symbol="BTCUSDT",
            quantity=(_BALANCE * 2) / price,
            price=price,
        )

        assert can_open is False
        assert "Insufficient balance" in reason

    def test_can_open_position_risk_limit(self, trading_engine, mock_risk_manager):
        """Test cannot open position when risk manager blocks"""
        # Mock risk manager rejection
        mock_risk_manager.check_position_limits.return_value = (
            False,
            "Too many positions",
        )

        can_open, reason = trading_engine.can_open_position(
            symbol="BTCUSDT", quantity=Decimal("0.001"), price=Decimal("50000.00")
        )

        assert can_open is False
        assert reason == "Too many positions"

    def test_get_performance_summary_no_trades(
        self, trading_engine, mock_position_manager
    ):
        """Test performance summary with no trades"""
        summary = trading_engine.get_performance_summary()

        assert summary["initial_balance"] == float(_BALANCE)
        assert summary["current_balance"] == float(_BALANCE)
        assert summary["total_equity"] == float(_BALANCE)
        assert summary["total_pnl"] == 0.0
        assert summary["roi"] == 0.0
        assert summary["total_trades"] == 0
        assert summary["winning_trades"] == 0
        assert summary["losing_trades"] == 0
        assert summary["win_rate"] == 0.0

    def test_get_performance_summary_with_trades(
        self, trading_engine, mock_position_manager
    ):
        """Test performance summary with completed trades"""
        # Mock closed positions with wins and losses
        winning_pos = Mock()
        winning_pos.realized_pnl = Decimal("200.00")

        losing_pos = Mock()
        losing_pos.realized_pnl = Decimal("-100.00")

        another_win = Mock()
        another_win.realized_pnl = Decimal("150.00")

        mock_position_manager.get_closed_positions.return_value = [
            winning_pos,
            losing_pos,
            another_win,
        ]

        # Simulate a 25% gain on the declared balance; the ROI expectation is
        # then scale-free (profit / initial * 100 = 25.0 at any account size).
        profit = _BALANCE * Decimal("0.25")
        trading_engine.balance = _BALANCE + profit

        summary = trading_engine.get_performance_summary()

        assert summary["initial_balance"] == float(_BALANCE)
        assert summary["current_balance"] == float(_BALANCE + profit)
        assert summary["total_pnl"] == float(profit)
        assert summary["roi"] == 25.0  # profit/initial * 100
        assert summary["total_trades"] == 3
        assert summary["winning_trades"] == 2
        assert summary["losing_trades"] == 1
        assert summary["win_rate"] == 66.67  # 2/3 * 100


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
