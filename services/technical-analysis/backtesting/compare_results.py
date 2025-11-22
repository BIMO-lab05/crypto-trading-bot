#!/usr/bin/env python3
"""
Compare backtest results: Test Data vs Real Data
Shows the impact of using realistic market data
"""

import json

# Load old results (with unrealistic test data)
with open('backtest_results_OLD_TEST_DATA.json', 'r') as f:
    old_results = json.load(f)

# Load new results (with real Bybit data)
with open('btc_eth_real_data_results.json', 'r') as f:
    new_results = json.load(f)

print("\n" + "=" * 80)
print("BACKTEST COMPARISON: TEST DATA vs REAL DATA")
print("=" * 80)
print()

print("Data Source Comparison:")
print("-" * 40)
print("OLD: Test data with unrealistic price swings")
print("     BTC: $63K to $332K (400%+ swing)")
print("     Period: 30 days")
print()
print("NEW: Real Bybit market data")
print("     BTC: $89K to $126K (42% range)")
print("     Period: 90 days")
print("=" * 80)
print()

# Compare BTC
print("BTCUSDT COMPARISON")
print("-" * 80)

btc_old = old_results['individual_results']['BTCUSDT']
btc_new = new_results['results']['BTCUSDT']

print(f"{'Metric':<25} {'Test Data':>15} {'Real Data':>15} {'Change':>15}")
print("-" * 80)
print(f"{'Total Return':<25} {btc_old['total_return_pct']:>14.2f}% {btc_new['total_return_pct']:>14.2f}% {btc_new['total_return_pct'] - btc_old['total_return_pct']:>+14.2f}%")
print(f"{'Final Capital':<25} ${btc_old['final_capital']:>13,.2f} ${btc_new['final_capital']:>13,.2f}")
print(f"{'Win Rate':<25} {btc_old['win_rate']:>14.2f}% {btc_new['win_rate']:>14.2f}% {btc_new['win_rate'] - btc_old['win_rate']:>+14.2f}%")
print(f"{'Total Trades':<25} {btc_old['total_trades']:>15} {btc_new['total_trades']:>15} {btc_new['total_trades'] - btc_old['total_trades']:>+15}")
print(f"{'Profit Factor':<25} {btc_old['profit_factor']:>15.2f} {btc_new['profit_factor']:>15.2f} {btc_new['profit_factor'] - btc_old['profit_factor']:>+15.2f}")
print(f"{'Sharpe Ratio':<25} {btc_old['sharpe_ratio']:>15.2f} {btc_new['sharpe_ratio']:>15.2f} {btc_new['sharpe_ratio'] - btc_old['sharpe_ratio']:>+15.2f}")
print(f"{'Max Drawdown':<25} {btc_old['max_drawdown']:>14.2f}% {btc_new['max_drawdown']:>14.2f}% {btc_new['max_drawdown'] - btc_old['max_drawdown']:>+14.2f}%")
print()

# Compare ETH
print("ETHUSDT COMPARISON")
print("-" * 80)

eth_old = old_results['individual_results']['ETHUSDT']
eth_new = new_results['results']['ETHUSDT']

print(f"{'Metric':<25} {'Test Data':>15} {'Real Data':>15} {'Change':>15}")
print("-" * 80)
print(f"{'Total Return':<25} {eth_old['total_return_pct']:>14.2f}% {eth_new['total_return_pct']:>14.2f}% {eth_new['total_return_pct'] - eth_old['total_return_pct']:>+14.2f}%")
print(f"{'Final Capital':<25} ${eth_old['final_capital']:>13,.2f} ${eth_new['final_capital']:>13,.2f}")
print(f"{'Win Rate':<25} {eth_old['win_rate']:>14.2f}% {eth_new['win_rate']:>14.2f}% {eth_new['win_rate'] - eth_old['win_rate']:>+14.2f}%")
print(f"{'Total Trades':<25} {eth_old['total_trades']:>15} {eth_new['total_trades']:>15} {eth_new['total_trades'] - eth_old['total_trades']:>+15}")
print(f"{'Profit Factor':<25} {eth_old['profit_factor']:>15.2f} {eth_new['profit_factor']:>15.2f} {eth_new['profit_factor'] - eth_old['profit_factor']:>15.2f}")
print(f"{'Sharpe Ratio':<25} {eth_old['sharpe_ratio']:>15.2f} {eth_new['sharpe_ratio']:>15.2f} {eth_new['sharpe_ratio'] - eth_old['sharpe_ratio']:>+15.2f}")
print(f"{'Max Drawdown':<25} {eth_old['max_drawdown']:>14.2f}% {eth_new['max_drawdown']:>14.2f}% {eth_new['max_drawdown'] - eth_old['max_drawdown']:>+14.2f}%")
print()

# Key insights
print("=" * 80)
print("KEY INSIGHTS")
print("=" * 80)
print()

print("1. IMPROVED BUT STILL LOSING")
print("   - Real data shows better results than test data (less catastrophic)")
print("   - BUT both are still deeply unprofitable (-70% losses)")
print()

print("2. DATA QUALITY IMPACT")
print("   - Test data: -100% (capital wiped out)")
print("   - Real data: -70% (still losing but more realistic)")
print("   - Difference: ~30% improvement from realistic data")
print()

print("3. WIN RATE ANALYSIS")
print("   - BTC win rate decreased: 40% → 22% (worse with real data)")
print("   - ETH win rate decreased: 56% → 31% (worse with real data)")
print("   - Reason: Test data volatility created false opportunities")
print()

print("4. TRADE COUNT")
print("   - BTC trades increased: 423 → 584 (more opportunities in 90 days)")
print("   - ETH trades increased: 359 → 594 (more opportunities in 90 days)")
print("   - Longer test period = more trades")
print()

print("5. PROFIT FACTOR")
print("   - BTC: 0.75 → 0.39 (got worse with real data)")
print("   - ETH: 0.70 → 0.55 (got worse with real data)")
print("   - Both < 1.0 = losing strategy")
print()

print("=" * 80)
print("FINAL VERDICT")
print("=" * 80)
print()
print("❌ DO NOT ADD BTC or ETH to trading symbols")
print()
print("Reasons:")
print("1. Both show 70%+ losses on real data")
print("2. Win rates too low (22% BTC, 31% ETH)")
print("3. Profit factors < 1.0")
print("4. Extremely negative Sharpe ratios")
print("5. Tested during bearish period (-18% BTC, -29% ETH market)")
print()
print("Alternative:")
print("- Continue trading profitable symbols: SOL, DOGE, BNB")
print("- Consider parameter optimization if still interested in BTC/ETH")
print("- Test different strategies better suited for major pairs")
print("- Wait for bull market and re-test")
print()
print("=" * 80)
print()
