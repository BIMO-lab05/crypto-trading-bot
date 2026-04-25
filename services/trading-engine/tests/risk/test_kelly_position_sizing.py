"""
Test Kelly Criterion Position Sizing Module
Purpose: Comprehensive tests for Kelly position sizing with edge case coverage

Coverage Target: >90%

Tests:
- Kelly calculation accuracy
- Fractional Kelly safety
- Dynamic Kelly adjustment
- Edge cases (0% win rate, 100% win rate, no trades)
- Position size limits
- Streak tracking
- API statistics generation
- Simulation mode
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List
import math

from app.risk.kelly_position_sizing import (
    KellyPositionSizer,
    KellyResult,
    TradeRecord,
    KellyMode,
    get_kelly_sizer,
    reset_kelly_sizer,
)


class TestKellyMath:
    """Test Kelly Criterion mathematical calculations"""

    def setup_method(self):
        """Reset sizer before each test"""
        reset_kelly_sizer()

    def test_kelly_formula_basic(self):
        """
        Test basic Kelly formula calculation

        f* = (b*p - q) / b

        Example:
        - Win rate (p) = 60%
        - Avg win = 2%, Avg loss = 1.5%
        - b = 2% / 1.5% = 1.333
        - q = 40%
        - Kelly = (1.333 * 0.6 - 0.4) / 1.333 = 0.3 (30%)
        """
        sizer = KellyPositionSizer(default_kelly_fraction=1.0)

        # Simulate trades with known parameters
        result = sizer.simulate_kelly(
            win_rate=0.60,
            avg_win_pct=2.0,
            avg_loss_pct=1.5,
            capital=10000,
            current_price=50000,
            mode=KellyMode.FULL
        )

        # Expected Kelly: (1.333 * 0.6 - 0.4) / 1.333 = 0.30
        expected_kelly = ((2.0 / 1.5) * 0.60 - 0.40) / (2.0 / 1.5)
        expected_kelly_pct = expected_kelly * 100

        # Should be capped at 10% max
        expected_position = min(expected_kelly_pct, 10.0)

        assert result.full_kelly_pct == pytest.approx(expected_kelly_pct, rel=0.01)
        assert result.position_size_pct == pytest.approx(expected_position, rel=0.01)

    def test_kelly_formula_high_edge(self):
        """
        Test Kelly with high edge (should be capped at 10%)

        With 80% win rate and 3:1 reward-risk, Kelly suggests ~60%
        but should be capped at 10% for safety
        """
        sizer = KellyPositionSizer()

        result = sizer.simulate_kelly(
            win_rate=0.80,
            avg_win_pct=3.0,
            avg_loss_pct=1.0,
            mode=KellyMode.FULL
        )

        # Full Kelly would be ~60%, but capped at 10%
        assert result.full_kelly_pct > 10.0, "High edge should suggest >10% Kelly"
        assert result.position_size_pct == 10.0, "Should be capped at MAX_POSITION_PCT"

    def test_kelly_formula_no_edge(self):
        """
        Test Kelly with no edge (50/50 with equal win/loss)

        Kelly should suggest 0% position
        """
        sizer = KellyPositionSizer()

        result = sizer.simulate_kelly(
            win_rate=0.50,
            avg_win_pct=1.0,
            avg_loss_pct=1.0,
            mode=KellyMode.FULL
        )

        # (1.0 * 0.5 - 0.5) / 1.0 = 0
        assert result.full_kelly_pct == pytest.approx(0.0, abs=0.01)
        # Should use minimum position
        assert result.position_size_pct == sizer.MIN_POSITION_PCT

    def test_kelly_formula_negative_edge(self):
        """
        Test Kelly with negative edge (should suggest minimum position)

        When expected value is negative, Kelly is 0 or negative
        """
        sizer = KellyPositionSizer()

        result = sizer.simulate_kelly(
            win_rate=0.30,  # Only 30% win rate
            avg_win_pct=1.0,
            avg_loss_pct=1.5,  # Losses bigger than wins
            mode=KellyMode.FULL
        )

        # Negative expectancy should result in 0 Kelly
        assert result.full_kelly_pct == 0.0
        assert result.edge < 0, "Edge should be negative"
        # Should use minimum position (or could return 0 in production)
        assert result.position_size_pct == sizer.MIN_POSITION_PCT


class TestFractionalKelly:
    """Test fractional Kelly variants for variance reduction"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_fractional_kelly_default(self):
        """Test default 25% fractional Kelly"""
        sizer = KellyPositionSizer(default_kelly_fraction=0.25)

        result = sizer.simulate_kelly(
            win_rate=0.60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            mode=KellyMode.FRACTIONAL
        )

        # Full Kelly at 30%, fractional at 7.5%
        expected_fractional = result.full_kelly_pct * 0.25

        assert result.kelly_fraction_used == 0.25
        assert result.position_size_pct == pytest.approx(
            max(sizer.MIN_POSITION_PCT, min(sizer.MAX_POSITION_PCT, expected_fractional)),
            rel=0.01
        )

    def test_fractional_kelly_50_percent(self):
        """Test 50% fractional Kelly (half Kelly)"""
        sizer = KellyPositionSizer(default_kelly_fraction=0.50)

        result = sizer.simulate_kelly(
            win_rate=0.55,
            avg_win_pct=1.5,
            avg_loss_pct=1.0,
            mode=KellyMode.FRACTIONAL
        )

        expected_fractional = result.full_kelly_pct * 0.50

        assert result.kelly_fraction_used == 0.50
        assert result.position_size_pct >= sizer.MIN_POSITION_PCT

    def test_fractional_kelly_reduces_variance(self):
        """Verify fractional Kelly is always less than full Kelly"""
        sizer = KellyPositionSizer(default_kelly_fraction=0.25)

        result_full = sizer.simulate_kelly(
            win_rate=0.65,
            avg_win_pct=2.5,
            avg_loss_pct=1.5,
            mode=KellyMode.FULL
        )

        result_fractional = sizer.simulate_kelly(
            win_rate=0.65,
            avg_win_pct=2.5,
            avg_loss_pct=1.5,
            mode=KellyMode.FRACTIONAL
        )

        assert result_fractional.position_size_pct <= result_full.position_size_pct


class TestDynamicKelly:
    """Test dynamic Kelly adjustment based on streaks"""

    def setup_method(self):
        reset_kelly_sizer()

    def _create_winning_trades(self, count: int) -> List[TradeRecord]:
        """Helper to create winning trade records"""
        trades = []
        base_time = datetime.now()
        for i in range(count):
            trades.append(TradeRecord(
                trade_id=f"win_{i}",
                symbol="BTCUSDT/ETHUSDT",
                entry_time=base_time + timedelta(hours=i),
                exit_time=base_time + timedelta(hours=i, minutes=30),
                entry_price=50000,
                exit_price=51000,
                pnl=100,
                pnl_pct=2.0,
                is_win=True,
                strategy="stat_arb"
            ))
        return trades

    def _create_losing_trades(self, count: int) -> List[TradeRecord]:
        """Helper to create losing trade records"""
        trades = []
        base_time = datetime.now()
        for i in range(count):
            trades.append(TradeRecord(
                trade_id=f"loss_{i}",
                symbol="BTCUSDT/ETHUSDT",
                entry_time=base_time + timedelta(hours=i),
                exit_time=base_time + timedelta(hours=i, minutes=30),
                entry_price=50000,
                exit_price=49250,
                pnl=-75,
                pnl_pct=-1.5,
                is_win=False,
                strategy="stat_arb"
            ))
        return trades

    def test_dynamic_kelly_win_streak_increases_fraction(self):
        """Test that winning streak increases Kelly fraction"""
        sizer = KellyPositionSizer(
            default_kelly_fraction=0.25,
            max_kelly_fraction=0.50,
            min_kelly_fraction=0.10,
            streak_adjustment_factor=0.05
        )

        # Record 5 winning trades
        for trade in self._create_winning_trades(5):
            sizer.record_trade(trade)

        stats = sizer.get_performance_stats()

        # With 5 win streak and 0.05 adjustment factor:
        # new_fraction = 0.25 + (5 * 0.05) = 0.50
        expected_fraction = min(0.50, 0.25 + 5 * 0.05)

        assert stats['current_streak'] == 5
        assert stats['current_kelly_fraction'] == pytest.approx(expected_fraction, rel=0.01)

    def test_dynamic_kelly_lose_streak_decreases_fraction(self):
        """Test that losing streak decreases Kelly fraction"""
        sizer = KellyPositionSizer(
            default_kelly_fraction=0.25,
            max_kelly_fraction=0.50,
            min_kelly_fraction=0.10,
            streak_adjustment_factor=0.05
        )

        # Record 3 losing trades
        for trade in self._create_losing_trades(3):
            sizer.record_trade(trade)

        stats = sizer.get_performance_stats()

        # With -3 streak: 0.25 + (-3 * 0.05) = 0.10
        expected_fraction = max(0.10, 0.25 - 3 * 0.05)

        assert stats['current_streak'] == -3
        assert stats['current_kelly_fraction'] == pytest.approx(expected_fraction, rel=0.01)

    def test_dynamic_kelly_streak_reset_on_reversal(self):
        """Test that streak resets when direction changes"""
        sizer = KellyPositionSizer()

        # 3 wins
        for trade in self._create_winning_trades(3):
            sizer.record_trade(trade)

        assert sizer._current_streak == 3

        # 1 loss resets to -1
        sizer.record_trade(self._create_losing_trades(1)[0])

        assert sizer._current_streak == -1

    def test_dynamic_kelly_capped_at_max(self):
        """Test that Kelly fraction is capped at maximum"""
        sizer = KellyPositionSizer(
            default_kelly_fraction=0.25,
            max_kelly_fraction=0.50,
            streak_adjustment_factor=0.10
        )

        # Record 10 wins (would push fraction to 1.25 without cap)
        for trade in self._create_winning_trades(10):
            sizer.record_trade(trade)

        stats = sizer.get_performance_stats()

        assert stats['current_kelly_fraction'] == 0.50, "Should be capped at max"

    def test_dynamic_kelly_capped_at_min(self):
        """Test that Kelly fraction doesn't go below minimum"""
        sizer = KellyPositionSizer(
            default_kelly_fraction=0.25,
            min_kelly_fraction=0.10,
            streak_adjustment_factor=0.10
        )

        # Record 10 losses (would push fraction to -0.75 without floor)
        for trade in self._create_losing_trades(10):
            sizer.record_trade(trade)

        stats = sizer.get_performance_stats()

        assert stats['current_kelly_fraction'] == 0.10, "Should be floored at min"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_zero_win_rate(self):
        """Test handling of 0% win rate"""
        sizer = KellyPositionSizer()

        result = sizer.simulate_kelly(
            win_rate=0.0,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            mode=KellyMode.FULL
        )

        # 0% win rate should give 0 Kelly (or use minimum position)
        assert result.full_kelly_pct == 0.0
        assert result.position_size_pct == sizer.MIN_POSITION_PCT

    def test_hundred_percent_win_rate(self):
        """Test handling of 100% win rate"""
        sizer = KellyPositionSizer()

        result = sizer.simulate_kelly(
            win_rate=1.0,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            mode=KellyMode.FULL
        )

        # 100% win rate is invalid for Kelly (division issues)
        # Should return 0 or handle gracefully
        assert result.full_kelly_pct == 0.0 or result.position_size_pct <= sizer.MAX_POSITION_PCT

    def test_zero_avg_loss(self):
        """Test handling of zero average loss (division by zero)"""
        sizer = KellyPositionSizer()

        result = sizer.simulate_kelly(
            win_rate=0.60,
            avg_win_pct=2.0,
            avg_loss_pct=0.0,  # Would cause division by zero
            mode=KellyMode.FULL
        )

        # Should handle gracefully without crashing
        assert result.full_kelly_pct >= 0.0
        assert result.position_size_pct >= sizer.MIN_POSITION_PCT

    def test_insufficient_trades(self):
        """Test fallback when insufficient trade history"""
        sizer = KellyPositionSizer(fallback_position_pct=3.0)

        # No trades recorded
        result = sizer.calculate_position_size(
            capital=10000,
            current_price=50000,
            mode=KellyMode.FRACTIONAL
        )

        assert result.position_size_pct == 3.0, "Should use fallback size"
        assert result.confidence_level == 0.0, "No confidence with no data"
        assert "Insufficient" in result.reasoning

    def test_empty_trade_history(self):
        """Test calculation with empty trade history"""
        sizer = KellyPositionSizer()

        stats = sizer.get_performance_stats()

        assert stats['total_trades'] == 0
        assert stats['win_rate'] == 0.5, "Should use neutral assumption"
        assert stats['avg_win_pct'] == 2.0, "Should use default"
        assert stats['avg_loss_pct'] == 1.5, "Should use default"

    def test_very_small_position(self):
        """Test position calculation with very small capital"""
        sizer = KellyPositionSizer()

        result = sizer.calculate_position_size(
            capital=100,  # Very small capital
            current_price=50000,  # High price
            mode=KellyMode.FRACTIONAL
        )

        # Should still calculate valid position
        assert result.position_value >= 0
        assert result.quantity >= 0

    def test_negative_capital(self):
        """Test handling of negative or zero capital"""
        sizer = KellyPositionSizer()

        result = sizer.calculate_position_size(
            capital=0,
            current_price=50000,
            mode=KellyMode.FRACTIONAL
        )

        assert result.position_value == 0
        assert result.quantity == 0

    def test_zero_price(self):
        """Test handling of zero price"""
        sizer = KellyPositionSizer()

        # Should handle division by zero
        try:
            result = sizer.calculate_position_size(
                capital=10000,
                current_price=0,  # Invalid price
                mode=KellyMode.FRACTIONAL
            )
            # If it doesn't raise, quantity should be handled
            # (depends on implementation - could be inf or raise)
        except (ZeroDivisionError, decimal.InvalidOperation):
            # This is acceptable behavior
            pass


class TestPositionSizeLimits:
    """Test position size limit enforcement"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_max_position_size_enforced(self):
        """Test that maximum position size is enforced"""
        sizer = KellyPositionSizer()

        # High edge would suggest >10%
        result = sizer.simulate_kelly(
            win_rate=0.80,
            avg_win_pct=5.0,
            avg_loss_pct=1.0,
            mode=KellyMode.FULL
        )

        assert result.position_size_pct <= sizer.MAX_POSITION_PCT

    def test_min_position_size_enforced(self):
        """Test that minimum position size is enforced"""
        sizer = KellyPositionSizer()

        # No edge would suggest 0%
        result = sizer.simulate_kelly(
            win_rate=0.50,
            avg_win_pct=1.0,
            avg_loss_pct=1.0,
            mode=KellyMode.FULL
        )

        assert result.position_size_pct >= sizer.MIN_POSITION_PCT

    def test_risk_limit_with_stop_loss(self):
        """Test position size limited by stop loss risk"""
        sizer = KellyPositionSizer()

        # First, add enough trades for Kelly calculation
        base_time = datetime.now()
        for i in range(15):
            sizer.record_trade(TradeRecord(
                trade_id=f"trade_{i}",
                symbol="TEST",
                entry_time=base_time + timedelta(hours=i),
                exit_time=base_time + timedelta(hours=i, minutes=30),
                entry_price=100,
                exit_price=102 if i % 3 != 0 else 98,  # 66% win rate
                pnl=2 if i % 3 != 0 else -2,
                pnl_pct=2.0 if i % 3 != 0 else -2.0,
                is_win=i % 3 != 0,
            ))

        result = sizer.calculate_position_size(
            capital=10000,
            current_price=50000,
            mode=KellyMode.FRACTIONAL,
            stop_loss_pct=5.0  # 5% stop loss
        )

        # Max risk = 2%, stop = 5%
        # Max position = 2% / 5% = 40%
        # But capped at 10%
        max_by_risk = 2.0 / 5.0 * 100  # 40%
        expected_max = min(max_by_risk, sizer.MAX_POSITION_PCT)

        assert result.position_size_pct <= expected_max


class TestTradeRecording:
    """Test trade recording and statistics tracking"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_record_winning_trade(self):
        """Test recording a winning trade"""
        sizer = KellyPositionSizer()

        trade = TradeRecord(
            trade_id="test_win_1",
            symbol="BTCUSDT/ETHUSDT",
            entry_time=datetime.now(),
            exit_time=datetime.now() + timedelta(hours=1),
            entry_price=50000,
            exit_price=51000,
            pnl=100,
            pnl_pct=2.0,
            is_win=True
        )

        sizer.record_trade(trade)

        assert sizer._total_trades == 1
        assert sizer._winning_trades == 1
        assert sizer._losing_trades == 0
        assert sizer._current_streak == 1

    def test_record_losing_trade(self):
        """Test recording a losing trade"""
        sizer = KellyPositionSizer()

        trade = TradeRecord(
            trade_id="test_loss_1",
            symbol="BTCUSDT/ETHUSDT",
            entry_time=datetime.now(),
            exit_time=datetime.now() + timedelta(hours=1),
            entry_price=50000,
            exit_price=49000,
            pnl=-100,
            pnl_pct=-2.0,
            is_win=False
        )

        sizer.record_trade(trade)

        assert sizer._total_trades == 1
        assert sizer._winning_trades == 0
        assert sizer._losing_trades == 1
        assert sizer._current_streak == -1

    def test_rolling_window_limit(self):
        """Test that rolling window is limited to 50 trades"""
        sizer = KellyPositionSizer()

        # Record 60 trades
        base_time = datetime.now()
        for i in range(60):
            trade = TradeRecord(
                trade_id=f"trade_{i}",
                symbol="TEST",
                entry_time=base_time + timedelta(hours=i),
                exit_time=base_time + timedelta(hours=i, minutes=30),
                entry_price=100,
                exit_price=102,
                pnl=2,
                pnl_pct=2.0,
                is_win=True
            )
            sizer.record_trade(trade)

        stats = sizer.get_performance_stats()

        assert stats['rolling_trades'] == 50, "Should only keep last 50"
        assert stats['total_trades'] == 60, "Should count all trades"

    def test_reset_clears_history(self):
        """Test that reset clears all trade history"""
        sizer = KellyPositionSizer()

        # Record some trades
        for i in range(10):
            sizer.record_trade(TradeRecord(
                trade_id=f"trade_{i}",
                symbol="TEST",
                entry_time=datetime.now(),
                exit_time=datetime.now() + timedelta(hours=1),
                entry_price=100,
                exit_price=102,
                pnl=2,
                pnl_pct=2.0,
                is_win=True
            ))

        sizer.reset()

        assert sizer._total_trades == 0
        assert len(sizer._trade_history) == 0
        assert sizer._current_streak == 0


class TestAPIStatistics:
    """Test API statistics generation"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_get_kelly_stats_empty(self):
        """Test statistics with no trades"""
        sizer = KellyPositionSizer()

        stats = sizer.get_kelly_stats()

        assert 'kelly' in stats
        assert 'performance' in stats
        assert 'trades' in stats
        assert 'streak' in stats
        assert 'limits' in stats
        assert 'timestamp' in stats

        assert stats['trades']['total_trades'] == 0
        assert stats['trades']['has_sufficient_data'] is False

    def test_get_kelly_stats_with_trades(self):
        """Test statistics with trade history"""
        sizer = KellyPositionSizer()

        # Add trades
        base_time = datetime.now()
        for i in range(20):
            sizer.record_trade(TradeRecord(
                trade_id=f"trade_{i}",
                symbol="TEST",
                entry_time=base_time + timedelta(hours=i),
                exit_time=base_time + timedelta(hours=i, minutes=30),
                entry_price=100,
                exit_price=102 if i % 2 == 0 else 99,
                pnl=2 if i % 2 == 0 else -1,
                pnl_pct=2.0 if i % 2 == 0 else -1.0,
                is_win=i % 2 == 0
            ))

        stats = sizer.get_kelly_stats()

        assert stats['trades']['total_trades'] == 20
        assert stats['trades']['has_sufficient_data'] is True
        assert stats['performance']['win_rate'] == pytest.approx(0.50, rel=0.01)
        assert stats['kelly']['full_kelly_pct'] >= 0

    def test_performance_stats_caching(self):
        """Test that performance stats are cached"""
        sizer = KellyPositionSizer()

        # First call
        stats1 = sizer.get_performance_stats()
        cache_time = sizer._stats_cache_time

        # Second call should use cache
        stats2 = sizer.get_performance_stats()

        assert sizer._stats_cache_time == cache_time

        # Force recalculate
        stats3 = sizer.get_performance_stats(force_recalculate=True)

        assert sizer._stats_cache_time != cache_time


class TestGlobalInstance:
    """Test global singleton management"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_get_kelly_sizer_creates_instance(self):
        """Test that get_kelly_sizer creates singleton"""
        sizer1 = get_kelly_sizer()
        sizer2 = get_kelly_sizer()

        assert sizer1 is sizer2, "Should return same instance"

    def test_reset_kelly_sizer_clears_instance(self):
        """Test that reset clears the global instance"""
        sizer1 = get_kelly_sizer()
        sizer1.record_trade(TradeRecord(
            trade_id="test",
            symbol="TEST",
            entry_time=datetime.now(),
            exit_time=datetime.now() + timedelta(hours=1),
            entry_price=100,
            exit_price=102,
            pnl=2,
            pnl_pct=2.0,
            is_win=True
        ))

        reset_kelly_sizer()

        sizer2 = get_kelly_sizer()

        assert sizer1 is not sizer2, "Should create new instance after reset"
        assert sizer2._total_trades == 0, "New instance should be fresh"


class TestConfidenceAdjustment:
    """Test signal confidence adjustment"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_high_confidence_increases_position(self):
        """Test that high confidence increases position size"""
        sizer = KellyPositionSizer()

        # Add sufficient trades
        base_time = datetime.now()
        for i in range(15):
            sizer.record_trade(TradeRecord(
                trade_id=f"trade_{i}",
                symbol="TEST",
                entry_time=base_time + timedelta(hours=i),
                exit_time=base_time + timedelta(hours=i, minutes=30),
                entry_price=100,
                exit_price=102 if i % 3 != 0 else 99,
                pnl=2 if i % 3 != 0 else -1,
                pnl_pct=2.0 if i % 3 != 0 else -1.0,
                is_win=i % 3 != 0
            ))

        result_no_conf = sizer.calculate_position_size(
            capital=10000,
            current_price=50000,
            mode=KellyMode.FRACTIONAL,
            signal_confidence=None
        )

        result_high_conf = sizer.calculate_position_size(
            capital=10000,
            current_price=50000,
            mode=KellyMode.FRACTIONAL,
            signal_confidence=0.9  # 90% confidence
        )

        # High confidence should increase position
        assert result_high_conf.metadata['confidence_adjustment'] > 1.0

    def test_low_confidence_decreases_position(self):
        """Test that low confidence decreases position size"""
        sizer = KellyPositionSizer()

        # Add sufficient trades
        base_time = datetime.now()
        for i in range(15):
            sizer.record_trade(TradeRecord(
                trade_id=f"trade_{i}",
                symbol="TEST",
                entry_time=base_time + timedelta(hours=i),
                exit_time=base_time + timedelta(hours=i, minutes=30),
                entry_price=100,
                exit_price=102 if i % 3 != 0 else 99,
                pnl=2 if i % 3 != 0 else -1,
                pnl_pct=2.0 if i % 3 != 0 else -1.0,
                is_win=i % 3 != 0
            ))

        result_low_conf = sizer.calculate_position_size(
            capital=10000,
            current_price=50000,
            mode=KellyMode.FRACTIONAL,
            signal_confidence=0.3  # 30% confidence
        )

        # Low confidence should decrease position
        assert result_low_conf.metadata['confidence_adjustment'] < 1.0


class TestSimulationMode:
    """Test Kelly simulation for what-if analysis"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_simulate_does_not_affect_state(self):
        """Test that simulation doesn't modify sizer state"""
        sizer = KellyPositionSizer()

        initial_trades = sizer._total_trades

        result = sizer.simulate_kelly(
            win_rate=0.65,
            avg_win_pct=2.5,
            avg_loss_pct=1.5
        )

        assert sizer._total_trades == initial_trades, "Simulation shouldn't change state"

    def test_simulate_returns_correct_structure(self):
        """Test simulation returns proper KellyResult"""
        sizer = KellyPositionSizer()

        result = sizer.simulate_kelly(
            win_rate=0.60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            capital=10000,
            current_price=50000,
            mode=KellyMode.FRACTIONAL
        )

        assert isinstance(result, KellyResult)
        assert result.metadata.get('simulated') is True
        assert result.win_rate == 0.60
        assert result.avg_win_pct == 2.0
        assert result.avg_loss_pct == 1.0


class TestIntegrationScenarios:
    """Integration test scenarios simulating real trading"""

    def setup_method(self):
        reset_kelly_sizer()

    def test_typical_stat_arb_scenario(self):
        """
        Test typical statistical arbitrage scenario

        Simulate 30 trades with realistic stat arb performance:
        - 58% win rate
        - 1.8% average win
        - 1.2% average loss
        """
        sizer = KellyPositionSizer()

        base_time = datetime.now()
        trades_data = [
            (True, 1.8), (True, 2.1), (False, -1.0), (True, 1.5), (False, -1.3),
            (True, 2.0), (True, 1.6), (True, 1.9), (False, -1.1), (True, 1.7),
            (False, -1.4), (True, 2.2), (True, 1.8), (False, -0.9), (True, 1.6),
            (True, 1.9), (False, -1.2), (True, 2.0), (True, 1.7), (False, -1.5),
            (True, 1.8), (False, -1.1), (True, 2.1), (True, 1.6), (False, -1.3),
            (True, 1.9), (True, 2.0), (False, -1.0), (True, 1.7), (True, 1.8),
        ]

        for i, (is_win, pnl_pct) in enumerate(trades_data):
            sizer.record_trade(TradeRecord(
                trade_id=f"stat_arb_{i}",
                symbol="BTCUSDT/ETHUSDT",
                entry_time=base_time + timedelta(hours=i*4),
                exit_time=base_time + timedelta(hours=i*4+2),
                entry_price=50000,
                exit_price=50000 * (1 + pnl_pct/100),
                pnl=500 * (pnl_pct/100),
                pnl_pct=pnl_pct,
                is_win=is_win,
                strategy="pairs_trading"
            ))

        # Calculate position for next trade
        result = sizer.calculate_position_size(
            capital=10000,
            current_price=50000,
            mode=KellyMode.DYNAMIC
        )

        stats = sizer.get_performance_stats()

        # Verify reasonable results
        assert stats['win_rate'] > 0.55, "Should have positive win rate"
        assert stats['profit_factor'] > 1.0, "Should be profitable"
        assert result.position_size_pct > 0, "Should suggest positive position"
        assert result.position_size_pct <= 10.0, "Should respect max limit"
        assert result.edge > 0, "Should have positive edge"

    def test_recovery_from_drawdown(self):
        """
        Test position sizing adjustment during drawdown recovery

        Start with winning streak, then hit drawdown, then recover
        """
        sizer = KellyPositionSizer(
            default_kelly_fraction=0.25,
            min_kelly_fraction=0.10,
            max_kelly_fraction=0.40
        )

        base_time = datetime.now()

        # Phase 1: Winning streak (5 wins)
        for i in range(5):
            sizer.record_trade(TradeRecord(
                trade_id=f"win_{i}",
                symbol="TEST",
                entry_time=base_time + timedelta(hours=i),
                exit_time=base_time + timedelta(hours=i, minutes=30),
                entry_price=100,
                exit_price=102,
                pnl=2,
                pnl_pct=2.0,
                is_win=True
            ))

        fraction_after_wins = sizer._current_kelly_fraction
        assert fraction_after_wins > 0.25, "Fraction should increase after wins"

        # Phase 2: Drawdown (4 losses)
        for i in range(4):
            sizer.record_trade(TradeRecord(
                trade_id=f"loss_{i}",
                symbol="TEST",
                entry_time=base_time + timedelta(hours=5+i),
                exit_time=base_time + timedelta(hours=5+i, minutes=30),
                entry_price=100,
                exit_price=98,
                pnl=-2,
                pnl_pct=-2.0,
                is_win=False
            ))

        fraction_after_losses = sizer._current_kelly_fraction
        assert fraction_after_losses < fraction_after_wins, "Fraction should decrease"
        assert sizer._current_streak == -4

        # Phase 3: Recovery (3 wins)
        for i in range(3):
            sizer.record_trade(TradeRecord(
                trade_id=f"recovery_{i}",
                symbol="TEST",
                entry_time=base_time + timedelta(hours=9+i),
                exit_time=base_time + timedelta(hours=9+i, minutes=30),
                entry_price=100,
                exit_price=102,
                pnl=2,
                pnl_pct=2.0,
                is_win=True
            ))

        fraction_after_recovery = sizer._current_kelly_fraction
        assert fraction_after_recovery > fraction_after_losses, "Should recover"
        assert sizer._current_streak == 3


# Run specific test for debugging
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
