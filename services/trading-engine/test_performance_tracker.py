#!/usr/bin/env python3
"""
Test Performance Tracker
Purpose: Quick test of performance tracking functionality
"""

from decimal import Decimal
from datetime import datetime, timedelta
from uuid import uuid4
from app.performance_tracker import PerformanceTracker, get_performance_tracker
from app.models import Position, PositionStatus, PositionSide

def test_performance_tracker():
    """Test performance tracking with sample trades"""
    print("=" * 80)
    print("PERFORMANCE TRACKER TEST")
    print("=" * 80)

    # Create tracker
    tracker = PerformanceTracker(initial_balance=Decimal("10000"))

    # Create sample trades
    print("\n📊 Creating sample trades...")

    trades_data = [
        # (symbol, side, entry, exit, qty, duration_hours, strategy)
        ("BTCUSDT", PositionSide.LONG, 50000, 51000, 0.1, 2, "trend_following"),  # Win
        ("ETHUSDT", PositionSide.LONG, 3000, 2950, 0.5, 1, "trend_following"),    # Loss
        ("BTCUSDT", PositionSide.SHORT, 51000, 50500, 0.1, 3, "mean_reversion"),  # Win
        ("SOLUSDT", PositionSide.LONG, 100, 105, 5, 4, "breakout"),               # Win
        ("ADAUSDT", PositionSide.LONG, 0.5, 0.48, 1000, 2, "breakout"),           # Loss
        ("BTCUSDT", PositionSide.LONG, 50500, 52000, 0.1, 5, "trend_following"),  # Win
        ("ETHUSDT", PositionSide.SHORT, 2950, 2900, 0.5, 2, "mean_reversion"),    # Win
        ("LINKUSDT", PositionSide.LONG, 15, 14.5, 20, 1, "breakout"),             # Loss
    ]

    base_time = datetime.now() - timedelta(days=7)

    for i, (symbol, side, entry, exit, qty, hours, strategy) in enumerate(trades_data):
        # Create position
        entry_time = base_time + timedelta(hours=i*6)
        exit_time = entry_time + timedelta(hours=hours)

        position = Position(
            id=uuid4(),
            symbol=symbol,
            side=side,
            quantity=Decimal(str(qty)),
            entry_price=Decimal(str(entry)),
            opened_at=entry_time,
            closed_at=exit_time,
            status=PositionStatus.CLOSED,
            strategy=strategy
        )

        # Add trade to tracker
        trade = tracker.add_trade(position, Decimal(str(exit)), exit_time)

        result = "✅ WIN" if trade.is_winner else "❌ LOSS"
        print(f"   {i+1}. {symbol} {side.value}: ${trade.pnl:+,.2f} ({trade.pnl_pct:+.2f}%) {result}")

    # Calculate and display metrics
    print("\n" + "=" * 80)
    print("📈 PERFORMANCE METRICS")
    print("=" * 80)

    metrics = tracker.calculate_metrics()

    print(f"\n📊 Overall Performance:")
    print(f"   Total Trades: {metrics.total_trades}")
    print(f"   Winning Trades: {metrics.winning_trades} ({metrics.win_rate:.2f}%)")
    print(f"   Losing Trades: {metrics.losing_trades} ({metrics.loss_rate:.2f}%)")
    print(f"   Breakeven Trades: {metrics.breakeven_trades}")

    print(f"\n💰 Profit & Loss:")
    print(f"   Total P&L: ${metrics.total_pnl:+,.2f} ({metrics.total_pnl_pct:+.2f}%)")
    print(f"   Gross Profit: ${metrics.gross_profit:,.2f}")
    print(f"   Gross Loss: ${metrics.gross_loss:,.2f}")
    print(f"   Profit Factor: {metrics.profit_factor:.2f}")

    print(f"\n📊 Win/Loss Averages:")
    print(f"   Average Win: ${metrics.avg_win:,.2f} ({metrics.avg_win_pct:+.2f}%)")
    print(f"   Average Loss: ${metrics.avg_loss:,.2f} ({metrics.avg_loss_pct:.2f}%)")

    print(f"\n⚠️  Risk Metrics:")
    print(f"   Max Consecutive Wins: {metrics.max_consecutive_wins}")
    print(f"   Max Consecutive Losses: {metrics.max_consecutive_losses}")
    print(f"   Max Drawdown: ${metrics.max_drawdown:,.2f} ({metrics.max_drawdown_pct:.2f}%)")

    print(f"\n📈 Risk-Adjusted Returns:")
    print(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"   Sortino Ratio: {metrics.sortino_ratio:.2f}")

    print(f"\n⏱️  Trade Duration:")
    print(f"   Average: {metrics.avg_duration_seconds // 3600}h {(metrics.avg_duration_seconds % 3600) // 60}m")
    print(f"   Max: {metrics.max_duration_seconds // 3600}h {(metrics.max_duration_seconds % 3600) // 60}m")
    print(f"   Min: {metrics.min_duration_seconds // 3600}h {(metrics.min_duration_seconds % 3600) // 60}m")

    # Per-symbol breakdown
    print("\n" + "=" * 80)
    print("🔍 PER-SYMBOL PERFORMANCE")
    print("=" * 80)

    symbols = tracker.get_all_symbols()
    for symbol in sorted(symbols):
        perf = tracker.get_symbol_performance(symbol)
        print(f"\n{symbol}:")
        print(f"   Trades: {perf.metrics.total_trades}")
        print(f"   Win Rate: {perf.metrics.win_rate:.2f}%")
        print(f"   Total P&L: ${perf.metrics.total_pnl:+,.2f} ({perf.metrics.total_pnl_pct:+.2f}%)")
        print(f"   Avg Win: ${perf.metrics.avg_win:,.2f}")
        print(f"   Avg Loss: ${perf.metrics.avg_loss:,.2f}")

    # Per-strategy breakdown
    print("\n" + "=" * 80)
    print("🎯 PER-STRATEGY PERFORMANCE")
    print("=" * 80)

    strategies = tracker.get_all_strategies()
    for strategy in sorted(strategies):
        perf = tracker.get_strategy_performance(strategy)
        print(f"\n{strategy}:")
        print(f"   Trades: {perf.metrics.total_trades}")
        print(f"   Win Rate: {perf.metrics.win_rate:.2f}%")
        print(f"   Total P&L: ${perf.metrics.total_pnl:+,.2f}")
        print(f"   Profit Factor: {perf.metrics.profit_factor:.2f}")

    # Equity curve
    print("\n" + "=" * 80)
    print("📈 EQUITY CURVE (Last 5 Points)")
    print("=" * 80)

    for point in tracker.equity_curve[-5:]:
        print(f"   {point.timestamp.strftime('%Y-%m-%d %H:%M')}: "
              f"${point.balance:,.2f} (P&L: ${point.total_pnl:+,.2f}, "
              f"DD: ${point.drawdown:,.2f} / {point.drawdown_pct:.2f}%)")

    print("\n" + "=" * 80)
    print("✅ Performance tracker test completed successfully")
    print("=" * 80)

    return True


if __name__ == "__main__":
    test_performance_tracker()
