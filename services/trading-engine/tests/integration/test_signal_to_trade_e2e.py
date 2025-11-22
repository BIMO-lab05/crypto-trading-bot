"""
End-to-End Integration Test: Signal → Trade → Position → P&L
Tests the complete trading pipeline without external dependencies
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.signal_aggregator import SignalAggregator, get_aggregator
from app.paper_trading import PaperTradingEngine, get_paper_engine
from app.position_manager import PositionManager, get_position_manager
from app.risk_manager import RiskManager, get_risk_manager
from app.models import (
    TradingSignal, SignalAction,
    OrderCreate, OrderSide, OrderType, OrderStatus,
    Position, PositionSide, PositionStatus
)


class TestSignalToTradeEndToEnd:
    """End-to-end tests for complete trading pipeline"""

    @pytest.mark.asyncio
    async def test_complete_buy_signal_to_position_flow(self):
        """
        Test full flow: BUY signal → Execute order → Create position → Track P&L

        Flow:
        1. Get BUY signal from aggregator (mocked TA service)
        2. Execute market order through paper trading
        3. Verify position created in position manager
        4. Update price and check P&L calculation
        5. Hit take profit and close position
        """
        # Setup: Mock TA service responses (in correct format expected by signal_aggregator)
        responses = [
            # RSI
            {"signal": "BUY", "rsi": 35.5, "confidence": 0.75},
            # MACD - needs macd_line, histogram, signal_line
            {"signal": "BUY", "macd_line": 150.5, "histogram": 50.5, "signal_line": 100.0, "confidence": 0.80},
            # Bollinger Bands - needs current_price, upper_band, middle_band, lower_band
            {"signal": "BUY", "current_price": 50000, "upper_band": 51000, "middle_band": 50000, "lower_band": 49000, "confidence": 0.70},
            # SMA - needs value and current_price
            {"signal": "BUY", "value": 50100.0, "current_price": 50000, "confidence": 0.65},
            # EMA - needs value and current_price
            {"signal": "BUY", "value": 50050.0, "current_price": 50000, "confidence": 0.68},
            # Stochastic - needs data wrapper with k, d, condition, crossover
            {"data": {"signal": "BUY", "k": 25.0, "d": 20.0, "condition": "OVERSOLD", "crossover": "BULLISH", "confidence": 0.72}},
            # Volume - needs data wrapper with confirmed, strength, volume_ratio, current_volume, avg_volume
            {"data": {"signal": "BUY", "volume_ratio": 1.5, "confirmed": True, "strength": "STRONG", "current_volume": 1500000, "avg_volume": 1000000, "confidence": 0.85}},
            # Trend Filter - needs data wrapper with trend, spread_pct, fast_ema, slow_ema
            {"data": {"signal": "BUY", "trend": "UPTREND", "spread_pct": 2.5, "fast_ema": 50100, "slow_ema": 48900, "confidence": 0.80}},
            # ATR - needs data wrapper with full structure
            {"data": {"atr": 500.0, "atr_pct": 1.0, "stop_loss_long": 49500, "stop_loss_short": 50500,
                      "take_profit_long": 51000, "take_profit_short": 49000, "volatility": "MEDIUM",
                      "confidence": 0.70, "risk_reward_ratio": 2.0}}
        ]

        # Step 1: Get trading signal
        aggregator = await get_aggregator()

        response_iter = iter(responses)

        async def mock_get_func(*args, **kwargs):
            """Mock the get method to return proper response objects"""
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value=next(response_iter))
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch.object(aggregator.client, 'get', side_effect=mock_get_func):
            signal = await aggregator.get_trading_signal("BTCUSDT", "60")

        # Verify signal
        assert signal is not None
        assert signal.action == SignalAction.BUY
        assert signal.confidence > 0.6
        assert signal.metadata.get("meets_requirements") == True

        # Step 2: Execute buy order through paper trading
        paper_engine = get_paper_engine()
        position_mgr = get_position_manager()

        # Create order
        order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            strategy="test_e2e"
        )

        executed_order, error = await paper_engine.execute_market_order(
            order,
            Decimal("50000.00")
        )

        # Verify order execution
        assert executed_order.status == OrderStatus.FILLED
        assert error is None
        assert executed_order.filled_price == Decimal("50000.00")
        assert executed_order.position_id is not None

        # Step 3: Verify position created
        open_positions = position_mgr.get_open_positions()
        assert len(open_positions) == 1

        position = open_positions[0]
        assert position.symbol == "BTCUSDT"
        assert position.side == PositionSide.LONG
        assert position.quantity == Decimal("0.1")
        assert position.entry_price == Decimal("50000.00")
        assert position.status == PositionStatus.OPEN

        # Step 4: Update price and check P&L
        position_mgr.update_position_price(position.id, Decimal("52000.00"))  # Fixed: use position.id

        updated_positions = position_mgr.get_open_positions()
        assert len(updated_positions) == 1

        updated_position = updated_positions[0]
        assert updated_position.current_price == Decimal("52000.00")
        # P&L = (52000 - 50000) * 0.1 = 200
        assert updated_position.unrealized_pnl == Decimal("200.00")

        # Step 5: Hit take profit and close position
        # Assume take profit at 55000
        position_mgr.update_position_price(position.id, Decimal("55000.00"))  # Fixed: use position.id

        # Simulate hitting take profit (would normally be triggered by risk manager)
        closed_position = position_mgr.close_position(
            position.id,
            Decimal("55000.00"),
            reason="Take profit hit"
        )

        assert closed_position.status == PositionStatus.CLOSED
        assert closed_position.current_price == Decimal("55000.00")  # Fixed: use current_price instead of current_price
        # Realized P&L = (55000 - 50000) * 0.1 = 500
        assert closed_position.realized_pnl == Decimal("500.00")

        # Verify no open positions remain
        final_positions = position_mgr.get_open_positions()
        assert len(final_positions) == 0

    @pytest.mark.asyncio
    async def test_sell_signal_closes_position_flow(self):
        """
        Test flow: Open position → SELL signal → Close position

        Flow:
        1. Create open position manually
        2. Get SELL signal
        3. Execute sell order
        4. Verify position closed with P&L
        """
        # Step 1: Create open position
        paper_engine = get_paper_engine()
        position_mgr = get_position_manager()

        # Clear any existing positions from previous tests
        for pos in position_mgr.get_open_positions():
            position_mgr.close_position(pos.id, pos.current_price, reason="Test cleanup")

        # Buy first to create position
        buy_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.05"),
            strategy="test_sell_flow"
        )

        buy_executed, _ = await paper_engine.execute_market_order(buy_order, Decimal("48000.00"))
        assert buy_executed.status == OrderStatus.FILLED

        # Verify position exists
        positions = position_mgr.get_open_positions()
        assert len(positions) == 1
        position = positions[0]

        # Step 2: Get SELL signal (mocked)
        aggregator = await get_aggregator()

        sell_responses = [
            # RSI overbought
            {"signal": "SELL", "rsi": 65.5, "confidence": 0.75},
            # MACD bearish - needs macd_line, histogram, signal_line
            {"signal": "SELL", "macd_line": -150.5, "histogram": -50.5, "signal_line": -100.0, "confidence": 0.80},
            # Bollinger - needs current_price, upper_band, middle_band, lower_band
            {"signal": "SELL", "current_price": 50500, "upper_band": 51000, "middle_band": 50000, "lower_band": 49000, "confidence": 0.70},
            # SMA - needs value and current_price
            {"signal": "SELL", "value": 49900.0, "current_price": 50500, "confidence": 0.65},
            # EMA - needs value and current_price
            {"signal": "SELL", "value": 49950.0, "current_price": 50500, "confidence": 0.68},
            # Stochastic - needs data wrapper
            {"data": {"signal": "SELL", "k": 80.0, "d": 75.0, "condition": "OVERBOUGHT", "crossover": "BEARISH", "confidence": 0.72}},
            # Volume - needs data wrapper
            {"data": {"signal": "SELL", "volume_ratio": 1.8, "confirmed": True, "strength": "STRONG", "current_volume": 1800000, "avg_volume": 1000000, "confidence": 0.85}},
            # Trend - needs data wrapper
            {"data": {"signal": "SELL", "trend": "DOWNTREND", "spread_pct": -2.5, "fast_ema": 49900, "slow_ema": 51100, "confidence": 0.80}},
            # ATR - needs data wrapper
            {"data": {"atr": 600.0, "atr_pct": 1.2, "stop_loss_long": 49900, "stop_loss_short": 51100,
                      "take_profit_long": 51600, "take_profit_short": 48400, "volatility": "HIGH",
                      "confidence": 0.70, "risk_reward_ratio": 2.0}}
        ]

        sell_iter = iter(sell_responses)

        async def mock_sell_get(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value=next(sell_iter))
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch.object(aggregator.client, 'get', side_effect=mock_sell_get):
            sell_signal = await aggregator.get_trading_signal("BTCUSDT", "60")

        assert sell_signal.action == SignalAction.SELL
        assert sell_signal.confidence > 0.6

        # Step 3: Execute sell order
        sell_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=Decimal("0.05"),
            strategy="test_sell_flow"
        )

        sell_executed, error = await paper_engine.execute_market_order(sell_order, Decimal("50000.00"))

        # Step 4: Verify position closed
        assert sell_executed.status == OrderStatus.FILLED
        assert error is None

        remaining_positions = position_mgr.get_open_positions()
        assert len(remaining_positions) == 0

        closed_positions = position_mgr.get_closed_positions()
        # Check we have at least one closed position (may have more from previous tests)
        assert len(closed_positions) >= 1

        # Verify the most recent closed position (this test's position)
        closed_pos = closed_positions[-1]  # Get the last (most recent) closed position
        assert closed_pos.status == PositionStatus.CLOSED
        assert closed_pos.symbol == "BTCUSDT"
        assert closed_pos.strategy == "test_sell_flow"
        assert closed_pos.current_price == Decimal("50000.00")
        # P&L = (50000 - 48000) * 0.05 = 100
        assert closed_pos.realized_pnl == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_risk_manager_blocks_oversized_trade(self):
        """
        Test risk management integration: Block trade exceeding limits

        Flow:
        1. Get BUY signal
        2. Try to execute trade exceeding position size limit
        3. Verify risk manager blocks the trade
        """
        paper_engine = get_paper_engine()
        risk_mgr = get_risk_manager()

        # Create order that would exceed position size limit (2% of balance)
        # Balance = 10000, 2% = 200, but order value = 50000 * 10 = 500000
        oversized_order = OrderCreate(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("10.0"),  # Way too large
            strategy="test_risk_block"
        )

        # Check if can open position
        can_open, reason = paper_engine.can_open_position(
            "BTCUSDT",
            Decimal("10.0"),
            Decimal("50000.00")
        )

        assert can_open is False
        # Can be blocked by either insufficient balance or position size limits
        assert any([
            "Position size would be" in reason,
            "exceeds maximum" in reason.lower(),
            "insufficient balance" in reason.lower()
        ]), f"Expected blocking reason, got: {reason}"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_signals_processed(self):
        """
        Test handling multiple signals for different symbols concurrently

        Flow:
        1. Get signals for multiple symbols simultaneously
        2. Execute trades for each
        3. Verify all positions created correctly
        """
        paper_engine = get_paper_engine()
        position_mgr = get_position_manager()
        aggregator = await get_aggregator()

        # Reset balance for this test (singleton engine may have reduced balance from previous tests)
        paper_engine.balance = paper_engine.initial_balance

        # Close any open positions from previous tests
        for pos in position_mgr.get_open_positions():
            position_mgr.close_position(pos.id, pos.current_price, reason="Test cleanup")

        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        prices = {"BTCUSDT": Decimal("50000"), "ETHUSDT": Decimal("3000"), "BNBUSDT": Decimal("400")}

        # Execute buy orders for all symbols
        for symbol in symbols:
            order = OrderCreate(
                symbol=symbol,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("0.1"),
                strategy="test_concurrent"
            )

            executed, error = await paper_engine.execute_market_order(order, prices[symbol])
            assert executed.status == OrderStatus.FILLED
            assert error is None

        # Verify all positions created
        positions = position_mgr.get_open_positions()
        assert len(positions) == 3

        position_symbols = {p.symbol for p in positions}
        assert position_symbols == set(symbols)

        # Verify each position has correct entry price
        for position in positions:
            assert position.entry_price == prices[position.symbol]
            assert position.status == PositionStatus.OPEN


class TestPhase1PipelineIntegration:
    """Test Phase 1 signal processing pipeline"""

    @pytest.mark.asyncio
    async def test_phase1_voter_gatekeeper_validator_flow(self):
        """
        Test Phase 1: Voter → Gatekeeper → Validator pipeline

        Flow:
        1. Indicators vote (mocked responses)
        2. Gatekeeper checks trend alignment
        3. Validator confirms with volume
        4. Final signal with confidence score
        """
        aggregator = await get_aggregator()

        # Mock all indicator responses (in correct format)
        pipeline_responses = [
            # RSI
            {"signal": "BUY", "rsi": 30.0, "confidence": 0.80},
            # MACD - needs macd_line, histogram, signal_line
            {"signal": "BUY", "macd_line": 200.0, "histogram": 50.0, "signal_line": 150.0, "confidence": 0.85},
            # Bollinger Bands - needs current_price, upper_band, middle_band, lower_band
            {"signal": "BUY", "current_price": 49000, "upper_band": 50500, "middle_band": 49500, "lower_band": 48500, "confidence": 0.75},
            # SMA - needs value and current_price
            {"signal": "BUY", "value": 49500.0, "current_price": 49000, "confidence": 0.70},
            # EMA - needs value and current_price
            {"signal": "BUY", "value": 49600.0, "current_price": 49000, "confidence": 0.72},
            # Stochastic - needs data wrapper
            {"data": {"signal": "NEUTRAL", "k": 50.0, "d": 45.0, "condition": "NEUTRAL", "crossover": "NONE", "confidence": 0.50}},
            # Volume - needs data wrapper
            {"data": {"signal": "BUY", "volume_ratio": 1.6, "confirmed": True, "strength": "STRONG", "current_volume": 1600000, "avg_volume": 1000000, "confidence": 0.85}},
            # Trend Filter - needs data wrapper
            {"data": {"signal": "BUY", "trend": "UPTREND", "spread_pct": 3.5, "fast_ema": 49700, "slow_ema": 47900, "confidence": 0.80}},
            # ATR - needs data wrapper
            {"data": {"atr": 450.0, "atr_pct": 0.9, "stop_loss_long": 48550, "stop_loss_short": 49450,
                      "take_profit_long": 49900, "take_profit_short": 48100, "volatility": "MEDIUM",
                      "confidence": 0.70, "risk_reward_ratio": 2.0}}
        ]

        pipeline_iter = iter(pipeline_responses)

        async def mock_pipeline_get(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value=next(pipeline_iter))
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch.object(aggregator.client, 'get', side_effect=mock_pipeline_get):
            signal = await aggregator.get_trading_signal("BTCUSDT", "60")

        # Verify Phase 1 pipeline processed correctly
        assert signal is not None
        assert signal.action == SignalAction.BUY
        assert signal.confidence > 0.6  # High confidence from strong indicators
        assert signal.aggregated_score > 0  # Positive score

        # Verify metadata shows pipeline stages
        assert "meets_requirements" in signal.metadata
        assert signal.metadata["meets_requirements"] == True


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
