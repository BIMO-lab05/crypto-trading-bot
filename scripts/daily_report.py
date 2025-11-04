#!/usr/bin/env python3
"""
Daily Trading Report Generator
Generates a daily summary of trading bot performance
"""

import requests
import json
from datetime import datetime, timedelta
import sys

def get_portfolio_performance():
    """Fetch portfolio performance metrics"""
    try:
        response = requests.get('http://localhost:8000/api/portfolio', timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching portfolio: {e}")
        return None

def get_recent_trades(days=1):
    """Fetch recent trades from the last N days"""
    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        params = {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'limit': 100
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

def generate_report():
    """Generate daily trading report"""
    print("=" * 80)
    print(f"DAILY TRADING REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    # Fetch portfolio data
    portfolio_data = get_portfolio_performance()
    if portfolio_data and 'portfolio' in portfolio_data:
        portfolio = portfolio_data['portfolio']

        print("📊 PORTFOLIO SUMMARY")
        print("-" * 80)
        print(f"Cash Balance:        ${float(portfolio.get('cash_balance', 0)):,.2f}")
        print(f"Total Value:         ${float(portfolio.get('total_value', 0)):,.2f}")
        print(f"Total P&L:           ${float(portfolio.get('total_pnl', 0)):,.2f}")
        print(f"Total Return:        {float(portfolio.get('total_return_pct', 0)):.2f}%")

        # Display current positions
        holdings = portfolio.get('holdings', [])
        if holdings:
            print()
            print("📈 CURRENT POSITIONS")
            print("-" * 80)
            for holding in holdings:
                symbol = holding.get('symbol', 'N/A')
                quantity = float(holding.get('quantity', 0))
                avg_price = float(holding.get('average_price', 0))
                current_value = float(holding.get('current_value', 0))
                pnl = float(holding.get('unrealized_pnl', 0))
                pnl_pct = float(holding.get('unrealized_pnl_pct', 0))

                pnl_indicator = "🟢" if pnl >= 0 else "🔴"
                print(f"{pnl_indicator} {symbol}: {quantity:.4f} @ ${avg_price:.2f} | "
                      f"Value: ${current_value:.2f} | P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")
        else:
            print()
            print("📈 CURRENT POSITIONS: None")

        print()

    # Fetch recent trades
    trades_data = get_recent_trades(days=1)
    if trades_data and 'trades' in trades_data:
        trades = trades_data['trades']

        print("💼 TRADES (Last 24 Hours)")
        print("-" * 80)

        if trades:
            for trade in trades[:10]:  # Show last 10 trades
                timestamp = trade.get('executed_at', 'N/A')
                symbol = trade.get('symbol', 'N/A')
                side = trade.get('side', 'N/A').upper()
                quantity = float(trade.get('quantity', 0))
                price = float(trade.get('price', 0))
                value = float(trade.get('total_value', 0))

                side_indicator = "🟢 BUY " if side == "BUY" else "🔴 SELL"
                print(f"{side_indicator} | {timestamp} | {symbol} | "
                      f"{quantity:.4f} @ ${price:.2f} | Total: ${value:.2f}")
        else:
            print("No trades executed in the last 24 hours")

        # Trade statistics
        if trades:
            total_trades = len(trades)
            buy_trades = sum(1 for t in trades if t.get('side', '').upper() == 'BUY')
            sell_trades = sum(1 for t in trades if t.get('side', '').upper() == 'SELL')

            print()
            print("📊 TRADE STATISTICS (24h)")
            print("-" * 80)
            print(f"Total Trades:        {total_trades}")
            print(f"Buy Orders:          {buy_trades}")
            print(f"Sell Orders:         {sell_trades}")

    print()
    print("=" * 80)
    print("📍 Bot Status: http://localhost:3000")
    print("📍 API Docs:   http://localhost:8000/docs")
    print("=" * 80)
    print()

if __name__ == '__main__':
    try:
        generate_report()
    except Exception as e:
        print(f"Error generating report: {e}")
        sys.exit(1)
