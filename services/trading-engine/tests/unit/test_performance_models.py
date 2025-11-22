"""
Unit Tests for Performance Models
Tests PerformanceMetrics calculation methods
"""

import pytest
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.models.performance import PerformanceMetrics


class TestPerformanceMetrics:
    """Test suite for PerformanceMetrics model"""

    def test_calculate_metrics_with_trades(self):
        """Test metric calculation with trades"""
        metrics = PerformanceMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            current_balance=Decimal("12000.00"),
            initial_balance=Decimal("10000.00")
        )

        metrics.calculate_metrics()

        # Win rate = (6 / 10) * 100 = 60%
        assert metrics.win_rate == 60.0

        # ROI = ((12000 - 10000) / 10000) * 100 = 20%
        assert metrics.roi == pytest.approx(20.0, rel=1e-2)

    def test_calculate_metrics_no_trades(self):
        """Test metric calculation with no trades"""
        metrics = PerformanceMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            current_balance=Decimal("10000.00"),
            initial_balance=Decimal("10000.00")
        )

        metrics.calculate_metrics()

        # Win rate should remain 0 when no trades
        assert metrics.win_rate == 0.0

        # ROI = 0 when balance unchanged
        assert metrics.roi == 0.0

    def test_calculate_metrics_zero_initial_balance(self):
        """Test metric calculation with zero initial balance"""
        metrics = PerformanceMetrics(
            total_trades=5,
            winning_trades=3,
            losing_trades=2,
            current_balance=Decimal("5000.00"),
            initial_balance=Decimal("0")
        )

        metrics.calculate_metrics()

        # Win rate should calculate normally
        assert metrics.win_rate == 60.0

        # ROI should remain 0 when initial balance is 0 (avoid division by zero)
        assert metrics.roi == 0.0


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
