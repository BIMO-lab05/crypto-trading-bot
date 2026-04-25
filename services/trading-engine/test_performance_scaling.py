#!/usr/bin/env python3
"""
Test script to verify the Performance-Based Scaling implementation
"""

from decimal import Decimal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

# Import directly from the current structure
from app.risk.kelly_position_sizing import KellyPositionSizer, KellyMode, TradeRecord
from app.position_sizing import PositionSizer, SizingMethod
from datetime import datetime


def test_kelly_streak_logic():
    """Test the Kelly position sizer with win/loss streak logic"""
    print("Testing Kelly Position Sizer with streak logic...")
    
    # Initialize Kelly position sizer with default values
    sizer = KellyPositionSizer(
        default_kelly_fraction=0.25,  # 25% default Kelly
        max_kelly_fraction=0.50,
        min_kelly_fraction=0.10
    )
    
    # Simulate 2 winning trades to trigger win streak
    for i in range(2):
        trade = TradeRecord(
            trade_id=f"win_{i}",
            symbol="BTCUSDT",
            entry_time=datetime.now(),
            exit_time=datetime.now(),
            entry_price=50000.0,
            exit_price=52000.0,  # Profit
            pnl=200.0,
            pnl_pct=4.0,
            is_win=True,
            strategy="test"
        )
        sizer.record_trade(trade)
    
    print(f"After 2 winning trades, current Kelly fraction: {sizer._current_kelly_fraction:.2f}")
    print(f"Expected: 0.30 (25% * 1.20 for win streak)")
    
    # Calculate position size with dynamic mode to use streak-adjusted Kelly
    result = sizer.calculate_position_size(
        capital=10000.0,
        current_price=50000.0,
        mode=KellyMode.DYNAMIC
    )
    
    print(f"Position size with win streak: {result.position_size_pct:.2f}%")
    
    # Reset and simulate 2 losing trades
    sizer = KellyPositionSizer(
        default_kelly_fraction=0.25,  # 25% default Kelly
        max_kelly_fraction=0.50,
        min_kelly_fraction=0.10
    )
    
    # Simulate 2 losing trades to trigger loss streak
    for i in range(2):
        trade = TradeRecord(
            trade_id=f"loss_{i}",
            symbol="BTCUSDT",
            entry_time=datetime.now(),
            exit_time=datetime.now(),
            entry_price=50000.0,
            exit_price=48000.0,  # Loss
            pnl=-200.0,
            pnl_pct=-4.0,
            is_win=False,
            strategy="test"
        )
        sizer.record_trade(trade)
    
    print(f"After 2 losing trades, current Kelly fraction: {sizer._current_kelly_fraction:.2f}")
    print(f"Expected: 0.18 (25% * 0.70 for loss streak)")
    
    # Calculate position size with dynamic mode to use streak-adjusted Kelly
    result = sizer.calculate_position_size(
        capital=10000.0,
        current_price=50000.0,
        mode=KellyMode.DYNAMIC
    )
    
    print(f"Position size with loss streak: {result.position_size_pct:.2f}%")


def test_daily_pnl_scaling():
    """Test the daily P&L scaling functionality"""
    print("\nTesting Position Sizer with daily P&L scaling...")
    
    sizer = PositionSizer()
    
    # Test with positive daily P&L (gain > 0.5%)
    result_positive = sizer.calculate_position_size(
        method=SizingMethod.FIXED,
        current_balance=Decimal("10000"),
        current_price=Decimal("50000"),
        signal_confidence=0.7,
        daily_pnl=Decimal("100"),  # $100 gain on $10000 = 1% gain
        total_capital=10000.0
    )
    
    print(f"Position size with positive daily P&L (1% gain): {result_positive.position_size_pct:.2f}%")
    print(f"Reasoning: {result_positive.reasoning}")
    
    # Test with negative daily P&L (loss > 0.5%)
    result_negative = sizer.calculate_position_size(
        method=SizingMethod.FIXED,
        current_balance=Decimal("10000"),
        current_price=Decimal("50000"),
        signal_confidence=0.7,
        daily_pnl=Decimal("-100"),  # $100 loss on $10000 = 1% loss
        total_capital=10000.0
    )
    
    print(f"Position size with negative daily P&L (1% loss): {result_negative.position_size_pct:.2f}%")
    print(f"Reasoning: {result_negative.reasoning}")
    
    # Test with neutral daily P&L (between -0.5% and 0.5%)
    result_neutral = sizer.calculate_position_size(
        method=SizingMethod.FIXED,
        current_balance=Decimal("10000"),
        current_price=Decimal("50000"),
        signal_confidence=0.7,
        daily_pnl=Decimal("20"),  # $20 gain on $10000 = 0.2% gain (within threshold)
        total_capital=10000.0
    )
    
    print(f"Position size with neutral daily P&L (0.2% gain): {result_neutral.position_size_pct:.2f}%")
    print(f"Reasoning: {result_neutral.reasoning}")


def main():
    """Run all tests"""
    print("=== Testing Performance-Based Scaling Implementation ===\n")
    
    test_kelly_streak_logic()
    test_daily_pnl_scaling()
    
    print("\n=== All tests completed ===")


if __name__ == "__main__":
    main()