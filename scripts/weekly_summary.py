#!/usr/bin/env python3
"""
Weekly Trading Summary Generator
Generates comprehensive weekly performance analysis
"""

import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict

def get_portfolio_performance():
    """Fetch current portfolio performance"""
    try:
        response = requests.get('http://localhost:8000/api/portfolio', timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching portfolio: {e}")
        return None

def get_weekly_trades():
    """Fetch trades from the last 7 days"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        params = {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'limit': 1000
        }

        response = requests.get(
            'http://localhost:8000/api/portfolio/trades',
            params=params,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching trades: {e}")
        return None

def calculate_statistics(trades):
    """Calculate trading statistics from trades list"""
    if not trades:
        return None

    stats = {
        'total_trades': len(trades),
        'buy_trades': 0,
        'sell_trades': 0,
        'total_volume': 0,
        'profitable_trades': 0,
        'losing_trades': 0,
        'symbols_traded': set(),
        'daily_trades': defaultdict(int)
    }

    for trade in trades:
        # Count buy/sell
        side = trade.get('side', '').upper()
        if side == 'BUY':
            stats['buy_trades'] += 1
        elif side == 'SELL':
            stats['sell_trades'] += 1

        # Track volume
        stats['total_volume'] += float(trade.get('total_value', 0))

        # Track symbols
        stats['symbols_traded'].add(trade.get('symbol', 'UNKNOWN'))

        # Track daily distribution
        date = trade.get('executed_at', '')[:10]
        stats['daily_trades'][date] += 1

        # Track profitability (for sell orders with realized P&L)
        realized_pnl = float(trade.get('realized_pnl', 0))
        if side == 'SELL':
            if realized_pnl > 0:
                stats['profitable_trades'] += 1
            elif realized_pnl < 0:
                stats['losing_trades'] += 1

    return stats

def generate_weekly_summary():
    """Generate comprehensive weekly summary"""
    print("=" * 80)
    print(f"WEEKLY TRADING SUMMARY - Week Ending {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 80)
    print()

    # Portfolio Performance
    portfolio_data = get_portfolio_performance()
    if portfolio_data and 'portfolio' in portfolio_data:
        portfolio = portfolio_data['portfolio']

        print("📊 PORTFOLIO OVERVIEW")
        print("-" * 80)
        print(f"Starting Capital:    $10,000.00")
        print(f"Current Value:       ${float(portfolio.get('total_value', 0)):,.2f}")
        print(f"Cash Balance:        ${float(portfolio.get('cash_balance', 0)):,.2f}")
        print(f"Total P&L:           ${float(portfolio.get('total_pnl', 0)):,.2f}")
        print(f"Total Return:        {float(portfolio.get('total_return_pct', 0)):.2f}%")
        print()

        # Current Holdings
        holdings = portfolio.get('holdings', [])
        if holdings:
            print("📈 CURRENT HOLDINGS")
            print("-" * 80)
            for holding in holdings:
                symbol = holding.get('symbol', 'N/A')
                quantity = float(holding.get('quantity', 0))
                value = float(holding.get('current_value', 0))
                pnl = float(holding.get('unrealized_pnl', 0))
                pnl_pct = float(holding.get('unrealized_pnl_pct', 0))

                pnl_indicator = "🟢" if pnl >= 0 else "🔴"
                print(f"{pnl_indicator} {symbol}: {quantity:.4f} | "
                      f"Value: ${value:.2f} | P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")
            print()

    # Trading Activity
    trades_data = get_weekly_trades()
    if trades_data and 'trades' in trades_data:
        trades = trades_data['trades']
        stats = calculate_statistics(trades)

        if stats:
            print("💼 TRADING ACTIVITY (7 Days)")
            print("-" * 80)
            print(f"Total Trades:        {stats['total_trades']}")
            print(f"Buy Orders:          {stats['buy_trades']}")
            print(f"Sell Orders:         {stats['sell_trades']}")
            print(f"Total Volume:        ${stats['total_volume']:,.2f}")
            print(f"Symbols Traded:      {', '.join(sorted(stats['symbols_traded']))}")
            print()

            # Profitability (if available)
            if stats['sell_trades'] > 0:
                win_rate = (stats['profitable_trades'] / stats['sell_trades'] * 100) if stats['sell_trades'] > 0 else 0
                print("📈 TRADE PROFITABILITY")
                print("-" * 80)
                print(f"Profitable Trades:   {stats['profitable_trades']}")
                print(f"Losing Trades:       {stats['losing_trades']}")
                print(f"Win Rate:            {win_rate:.1f}%")
                print()

            # Daily Distribution
            if stats['daily_trades']:
                print("📅 DAILY TRADE DISTRIBUTION")
                print("-" * 80)
                for date in sorted(stats['daily_trades'].keys()):
                    count = stats['daily_trades'][date]
                    bar = "█" * min(count, 50)
                    print(f"{date}: {bar} ({count} trades)")
                print()

    # Risk Metrics
    print("⚠️  RISK METRICS")
    print("-" * 80)
    if portfolio_data and 'portfolio' in portfolio_data:
        portfolio = portfolio_data['portfolio']
        total_value = float(portfolio.get('total_value', 0))
        cash = float(portfolio.get('cash_balance', 0))
        exposure = total_value - cash
        exposure_pct = (exposure / total_value * 100) if total_value > 0 else 0

        print(f"Total Exposure:      ${exposure:.2f} ({exposure_pct:.1f}%)")
        print(f"Cash Reserve:        ${cash:.2f} ({100-exposure_pct:.1f}%)")
        print(f"Max Drawdown:        N/A (not yet implemented)")
        print(f"Sharpe Ratio:        N/A (not yet implemented)")

    print()
    print("=" * 80)
    print("📍 Dashboard:  http://localhost:3000")
    print("📍 API Docs:   http://localhost:8000/docs")
    print("=" * 80)
    print()

if __name__ == '__main__':
    try:
        generate_weekly_summary()
    except Exception as e:
        print(f"Error generating weekly summary: {e}")
        import sys
        sys.exit(1)
