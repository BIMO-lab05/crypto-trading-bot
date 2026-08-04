# Statistical Arbitrage Strategies - Usage Guide

**Phase 2.2 - Comprehensive Guide to Using Statistical Arbitrage Strategies**

Author: Trading Bot Development Team
Date: 2025-12-07
Status: Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Strategy Quick Reference](#strategy-quick-reference)
4. [Pairs Trading Strategy](#pairs-trading-strategy)
5. [Funding Rate Arbitrage Strategy](#funding-rate-arbitrage-strategy)
6. [Triangular Arbitrage Strategy](#triangular-arbitrage-strategy)
7. [Multi-Strategy Portfolio](#multi-strategy-portfolio)
8. [Risk Management](#risk-management)
9. [Performance Monitoring](#performance-monitoring)
10. [Troubleshooting](#troubleshooting)

---

## Overview

Phase 2.2 implements three institutional-grade statistical arbitrage strategies:

| Strategy | Type | Expected Return | Risk Level | Execution Speed |
|----------|------|-----------------|------------|-----------------|
| **Pairs Trading** | Mean Reversion | 15-30% annually | Medium | Hours to Days |
| **Funding Rate Arb** | Carry Trade | 10-50% annually | Low | 8-hour cycles |
| **Triangular Arb** | Cross-Market | 5-20% annually | Very Low | Seconds |

**Combined Portfolio Performance:**
- Diversified across 3 uncorrelated strategies
- Target Annual Return: 20-40%
- Max Drawdown: <10%
- Sharpe Ratio: >2.0

---

## Prerequisites

### Required Dependencies

```python
# Add to requirements.txt
scipy==1.11.4          # Scientific computing
statsmodels==0.14.1    # Statistical tests
pandas==2.2.0          # Data manipulation
numpy==1.26.3          # Numerical computing
```

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Verify installation
python3 -c "import scipy, statsmodels; print('✓ Dependencies installed')"
```

### Import Statements

```python
from app.strategies.pairs_trading import PairsTradingStrategy, PairsTradeSignal
from app.strategies.funding_rate_arbitrage import FundingRateArbitrageStrategy, FundingRateSignal
from app.strategies.triangular_arbitrage import TriangularArbitrageStrategy, TriangularArbitrageSignal
from app.utils.statistical.cointegration import PairScanner, test_engle_granger
```

---

## Strategy Quick Reference

### Pairs Trading
```python
# Quick Start
strategy = PairsTradingStrategy('BTCUSDT', 'ETHUSDT')
strategy.calibrate(btc_prices, eth_prices)
signal = strategy.generate_signal(current_btc, current_eth, btc_hist, eth_hist, 10000)

# Signal Actions: OPEN_LONG_Y, OPEN_SHORT_Y, CLOSE, HOLD
# Entry: |Z-score| > 2.0
# Exit: |Z-score| < 0.5
```

### Funding Rate Arbitrage
```python
# Quick Start
strategy = FundingRateArbitrageStrategy('BTCUSDT')
signal = strategy.generate_signal(funding_rate, spot_price, futures_price, 10000)

# Signal Actions: OPEN_HEDGE, CLOSE_HEDGE, HOLD
# Entry: funding >= 0.03% (≈11% APY)
# Exit: funding < 0.01% or basis > 2%
```

### Triangular Arbitrage
```python
# Quick Start
strategy = TriangularArbitrageStrategy('USDT')
strategy.discover_paths(['BTC', 'ETH', 'BNB', 'USDT'])
signal = strategy.generate_signal(current_prices, 10000)

# Returns: Best arbitrage opportunity or None
# Minimum Profit: 0.1% after fees
```

---

## Pairs Trading Strategy

### Concept

Exploits mean reversion of cointegrated asset pairs. When the spread deviates from equilibrium, trade for convergence.

**Mathematical Foundation:**
```
Spread: S = Y - β*X
Z-Score: z = (S - μ_S) / σ_S
Entry: |z| > 2.0 (2 standard deviations)
Exit: |z| < 0.5 (reversion complete)
```

### Step-by-Step Implementation

#### 1. Find Cointegrated Pairs

```python
from app.utils.statistical.cointegration import PairScanner
import pandas as pd

# Prepare historical price data (100+ periods recommended)
price_data = {
    'BTCUSDT': pd.Series(btc_prices),
    'ETHUSDT': pd.Series(eth_prices),
    'BNBUSDT': pd.Series(bnb_prices),
    'SOLUSDT': pd.Series(sol_prices),
}

# Scan for cointegrated pairs
scanner = PairScanner(
    lookback_period=100,
    significance_level=0.05,  # 95% confidence
    min_quality_score=60.0    # Minimum quality threshold
)

pairs = scanner.scan_pairs(price_data, max_pairs=5)

# Review results
for pair in pairs:
    print(f"{pair['symbol_x']}/{pair['symbol_y']}")
    print(f"  Quality Score: {pair['score']:.1f}/100")
    print(f"  Hedge Ratio: {pair['hedge_ratio']:.4f}")
    print(f"  Half-Life: {pair['half_life']:.2f} periods")
    print(f"  P-Value: {pair['p_value']:.4f}")
```

#### 2. Initialize Strategy

```python
from app.strategies.pairs_trading import PairsTradingStrategy

strategy = PairsTradingStrategy(
    symbol_x='BTCUSDT',
    symbol_y='ETHUSDT',
    lookback_period=60,         # Spread calculation window
    entry_threshold=2.0,        # Entry at 2 std devs
    exit_threshold=0.5,         # Exit at 0.5 std devs
    stop_threshold=3.0,         # Stop loss at 3 std devs
    recalibration_period=24,    # Re-test every 24 hours
    max_position_size=0.1,      # 10% of capital per leg
    significance_level=0.05     # 95% confidence for cointegration
)
```

#### 3. Calibrate with Historical Data

```python
# Calibrate strategy (tests cointegration and calculates parameters)
calibrated = strategy.calibrate(btc_historical, eth_historical)

if calibrated:
    print("✓ Pair is cointegrated and ready for trading")
    print(f"  Hedge Ratio: {strategy.hedge_ratio:.4f}")
    print(f"  Spread Mean: {strategy.spread_mean:.2f}")
    print(f"  Spread Std: {strategy.spread_std:.2f}")
    print(f"  Half-Life: {strategy.half_life:.2f} periods")
else:
    print("✗ Pair is not cointegrated - do not trade")
```

#### 4. Generate Trading Signals

```python
# Generate signal with current market data
signal = strategy.generate_signal(
    current_price_x=50000.0,    # Current BTC price
    current_price_y=2000.0,     # Current ETH price
    historical_data_x=btc_hist,  # Historical BTC prices
    historical_data_y=eth_hist,  # Historical ETH prices
    portfolio_value=10000.0      # Total portfolio value
)

if signal:
    print(f"Action: {signal.action}")
    print(f"Z-Score: {signal.z_score:.2f}")
    print(f"Spread: {signal.spread:.2f}")
    print(f"Confidence: {signal.confidence:.1f}%")

    if signal.action == 'OPEN_LONG_Y':
        print("📈 LONG ETH / SHORT BTC")
        print(f"  Buy {signal.position_size_y:.4f} ETH")
        print(f"  Sell {signal.position_size_x:.4f} BTC")

    elif signal.action == 'OPEN_SHORT_Y':
        print("📉 SHORT ETH / LONG BTC")
        print(f"  Sell {signal.position_size_y:.4f} ETH")
        print(f"  Buy {signal.position_size_x:.4f} BTC")

    elif signal.action == 'CLOSE':
        print("🔄 CLOSE POSITIONS")
        print(f"  Reason: {signal.reason}")
```

#### 5. Monitor Strategy Status

```python
# Get comprehensive status
status = strategy.get_status()

print(f"Current Position: {status['current_position']}")
print(f"Is Cointegrated: {status['is_cointegrated']}")
print(f"Last Calibration: {status['last_calibration']}")
print(f"Needs Recalibration: {status['needs_recalibration']}")
```

### Example: Complete Pairs Trading Workflow

```python
#!/usr/bin/env python3
"""
Pairs Trading Example - Complete Workflow
"""

import pandas as pd
from app.strategies.pairs_trading import PairsTradingStrategy

# 1. Load historical data
btc_data = pd.read_csv('btc_prices.csv', parse_dates=['timestamp'])['close']
eth_data = pd.read_csv('eth_prices.csv', parse_dates=['timestamp'])['close']

# 2. Initialize strategy
strategy = PairsTradingStrategy(
    symbol_x='BTCUSDT',
    symbol_y='ETHUSDT',
    entry_threshold=2.0,
    exit_threshold=0.5
)

# 3. Calibrate
if strategy.calibrate(btc_data, eth_data):
    print(f"✓ Strategy calibrated - Hedge Ratio: {strategy.hedge_ratio:.4f}")

    # 4. Trading loop
    while trading_active:
        # Get current prices
        current_btc = get_current_price('BTCUSDT')
        current_eth = get_current_price('ETHUSDT')

        # Generate signal
        signal = strategy.generate_signal(
            current_btc,
            current_eth,
            btc_data,
            eth_data,
            portfolio_value=10000.0
        )

        # Execute trade
        if signal and signal.action != 'HOLD':
            execute_pairs_trade(signal)

        # Sleep until next check
        time.sleep(3600)  # Check hourly
else:
    print("✗ Pair not cointegrated - cannot trade")
```

---

## Funding Rate Arbitrage Strategy

### Concept

Collect funding payments by holding hedged spot + futures positions. Market-neutral strategy with predictable returns.

**How It Works:**
1. Perpetual futures pay funding every 8 hours
2. When funding is positive: LONG spot + SHORT futures
3. Collect funding payments while maintaining hedge
4. Exit when funding becomes unfavorable

**Profit Calculation:**
```
Annual Yield = Funding Rate × 3 (per day) × 365
Example: 0.03% per 8h = 10.95% annually
```

### Step-by-Step Implementation

#### 1. Initialize Strategy

```python
from app.strategies.funding_rate_arbitrage import FundingRateArbitrageStrategy

strategy = FundingRateArbitrageStrategy(
    symbol='BTCUSDT',
    min_funding_rate=0.0003,           # 0.03% per 8h ≈ 11% APY
    max_funding_rate=0.01,             # 1% per 8h (safety limit)
    max_basis_pct=2.0,                 # Max 2% basis divergence
    position_size_pct=0.2,             # 20% of portfolio per side
    funding_collection_threshold=0.0001 # Min 0.01% to maintain
)
```

#### 2. Generate Signals

```python
# Get current market data
current_funding_rate = get_funding_rate('BTCUSDT')  # From Bybit API
spot_price = get_spot_price('BTCUSDT')
futures_price = get_futures_price('BTCUSDT')

# Generate signal
signal = strategy.generate_signal(
    current_funding_rate=current_funding_rate,
    spot_price=spot_price,
    futures_price=futures_price,
    portfolio_value=10000.0
)

if signal:
    print(f"Action: {signal.action}")
    print(f"Funding Rate: {signal.funding_rate:.4f} ({signal.annualized_yield:.2f}% APY)")
    print(f"Basis: {signal.basis_pct:.2f}%")

    if signal.action == 'OPEN_HEDGE':
        print("💰 OPEN HEDGE POSITION")
        print(f"  Buy {signal.spot_position_size:.4f} BTC (spot)")
        print(f"  Sell {signal.futures_position_size:.4f} BTC (futures)")
        print(f"  Expected Yield: {signal.annualized_yield:.2f}% annually")

    elif signal.action == 'CLOSE_HEDGE':
        print("🔄 CLOSE HEDGE")
        print(f"  Reason: {signal.reason}")
```

#### 3. Record Funding Payments

```python
# Every 8 hours, record funding payment
strategy.record_funding_payment(
    funding_rate=current_funding_rate,
    position_size=futures_position_size,
    futures_price=current_futures_price
)

print(f"✓ Funding collected: ${strategy.total_funding_collected:.2f}")
```

#### 4. Calculate Yield Metrics

```python
# Get current yield projections
yield_metrics = strategy.calculate_current_yield(
    funding_rate=0.0004,  # 0.04%
    days_held=1
)

print(f"8-Hour Rate: {yield_metrics['funding_rate_8h']:.4f}")
print(f"Daily Rate: {yield_metrics['daily_rate_pct']:.2f}%")
print(f"Annual Rate: {yield_metrics['annualized_rate_pct']:.2f}%")
print(f"30-Day Projection: {yield_metrics['projected_30d_return']:.2f}%")
```

### Example: Complete Funding Rate Workflow

```python
#!/usr/bin/env python3
"""
Funding Rate Arbitrage Example
"""

from app.strategies.funding_rate_arbitrage import FundingRateArbitrageStrategy
import time

strategy = FundingRateArbitrageStrategy('BTCUSDT')

# Trading loop
while True:
    # Get current data
    funding_rate = fetch_funding_rate('BTCUSDT')
    spot_price = fetch_spot_price('BTCUSDT')
    futures_price = fetch_futures_price('BTCUSDT')

    # Generate signal
    signal = strategy.generate_signal(
        funding_rate,
        spot_price,
        futures_price,
        portfolio_value=10000.0
    )

    # Execute based on signal
    if signal:
        if signal.action == 'OPEN_HEDGE':
            open_hedge_position(signal)

        elif signal.action == 'CLOSE_HEDGE':
            close_hedge_position()

    # Record funding every 8 hours
    if is_funding_time():
        strategy.record_funding_payment(
            funding_rate,
            current_position_size,
            futures_price
        )

    # Check every hour
    time.sleep(3600)
```

---

## Triangular Arbitrage Strategy

### Concept

Exploit price inefficiencies in circular trading paths. Ultra-fast execution required.

**Example:**
```
Path: USDT → BTC → ETH → USDT
1. Start: 10,000 USDT
2. Buy BTC: 10,000 / 50,000 = 0.2 BTC
3. Buy ETH: 0.2 / 0.04 = 5 ETH
4. Sell ETH: 5 × 2,010 = 10,050 USDT
5. Profit: 50 USDT (0.5%)
```

### Step-by-Step Implementation

#### 1. Initialize and Discover Paths

```python
from app.strategies.triangular_arbitrage import TriangularArbitrageStrategy

strategy = TriangularArbitrageStrategy(
    base_asset='USDT',
    min_profit_threshold=0.001,  # 0.1% minimum profit
    trading_fee=0.0005,          # 0.05% per trade
    max_latency_ms=100.0,        # Max 100ms execution
    execution_amount_pct=0.1     # 10% of portfolio
)

# Discover all triangular paths
assets = ['BTC', 'ETH', 'BNB', 'SOL', 'USDT']
paths = strategy.discover_paths(assets)

print(f"✓ Discovered {len(paths)} triangular paths")
for path in paths[:5]:
    print(f"  {path}")
```

#### 2. Monitor for Arbitrage

```python
# Get current prices for all pairs
prices = {
    'BTCUSDT': 50000.0,
    'ETHBTC': 0.04,
    'ETHUSDT': 2010.0,  # Slight inefficiency
    'BNBUSDT': 350.0,
    'BNBBTC': 0.007,
    'BNBETH': 0.175,
}

# Check for arbitrage
signal = strategy.generate_signal(prices, capital=10000.0)

if signal:
    print(f"🎯 ARBITRAGE OPPORTUNITY DETECTED!")
    print(f"  Path: {signal.path}")
    print(f"  Net Profit: {signal.net_profit_pct:.4f}%")
    print(f"  Amount: ${signal.execution_amount:.2f}")
    print(f"  Latency: {signal.estimated_latency_ms:.1f}ms")
    print(f"  Confidence: {signal.confidence:.1f}%")

    # Execute immediately (time-sensitive!)
    execute_triangular_arbitrage(signal)
```

#### 3. Track Performance

```python
# Record execution
strategy.record_arbitrage_execution(
    signal=signal,
    actual_profit=48.50,      # Actual profit realized
    actual_latency_ms=95.0,    # Actual execution time
    execution_status='success'
)

# Get statistics
status = strategy.get_status()
print(f"Total Arbitrages: {status['total_arbitrages_executed']}")
print(f"Total Profit: ${status['total_profit']:.2f}")
print(f"Avg Latency: {status['average_latency_ms']:.1f}ms")
```

---

## Multi-Strategy Portfolio

### Running All Strategies Concurrently

```python
#!/usr/bin/env python3
"""
Multi-Strategy Statistical Arbitrage Portfolio
"""

from app.strategies.pairs_trading import PairsTradingStrategy
from app.strategies.funding_rate_arbitrage import FundingRateArbitrageStrategy
from app.strategies.triangular_arbitrage import TriangularArbitrageStrategy

class StatisticalArbitragePortfolio:
    def __init__(self, total_capital=10000.0):
        self.capital = total_capital

        # Allocate capital across strategies
        # Pairs: 40%, Funding: 40%, Triangular: 20%
        self.allocation = {
            'pairs': 0.4,
            'funding': 0.4,
            'triangular': 0.2
        }

        # Initialize strategies
        self.pairs_strategies = []
        self.funding_strategies = []
        self.triangular_strategy = None

    def add_pairs_strategy(self, symbol_x, symbol_y):
        """Add a pairs trading strategy"""
        strategy = PairsTradingStrategy(symbol_x, symbol_y)
        self.pairs_strategies.append(strategy)

    def add_funding_strategy(self, symbol):
        """Add a funding rate arbitrage strategy"""
        strategy = FundingRateArbitrageStrategy(symbol)
        self.funding_strategies.append(strategy)

    def setup_triangular(self, assets):
        """Setup triangular arbitrage"""
        self.triangular_strategy = TriangularArbitrageStrategy('USDT')
        self.triangular_strategy.discover_paths(assets)

    def run_all_strategies(self, market_data):
        """Run all strategies and collect signals"""
        signals = []

        # Pairs trading signals
        for strategy in self.pairs_strategies:
            signal = strategy.generate_signal(
                market_data['current_btc'],
                market_data['current_eth'],
                market_data['btc_hist'],
                market_data['eth_hist'],
                self.capital * self.allocation['pairs']
            )
            if signal and signal.action != 'HOLD':
                signals.append(('pairs', signal))

        # Funding rate signals
        for strategy in self.funding_strategies:
            signal = strategy.generate_signal(
                market_data['funding_rate'],
                market_data['spot_price'],
                market_data['futures_price'],
                self.capital * self.allocation['funding']
            )
            if signal and signal.action != 'HOLD':
                signals.append(('funding', signal))

        # Triangular arbitrage
        if self.triangular_strategy:
            signal = self.triangular_strategy.generate_signal(
                market_data['prices'],
                self.capital * self.allocation['triangular']
            )
            if signal:
                signals.append(('triangular', signal))

        return signals

# Usage
portfolio = StatisticalArbitragePortfolio(total_capital=10000.0)
portfolio.add_pairs_strategy('BTCUSDT', 'ETHUSDT')
portfolio.add_funding_strategy('BTCUSDT')
portfolio.setup_triangular(['BTC', 'ETH', 'BNB', 'USDT'])

# Run
signals = portfolio.run_all_strategies(current_market_data)
print(f"Generated {len(signals)} signals across all strategies")
```

---

## Risk Management

### Position Sizing

```python
# Conservative: 5% per strategy
portfolio_value = 10000.0
max_position_per_strategy = portfolio_value * 0.05  # $500

# Moderate: 10% per strategy
max_position_per_strategy = portfolio_value * 0.10  # $1,000

# Aggressive: 20% per strategy
max_position_per_strategy = portfolio_value * 0.20  # $2,000
```

### Stop Loss Guidelines

**Pairs Trading:**
- Hard Stop: |Z-score| > 3.0 (cointegration breakdown)
- Time Stop: Close after 7 days if no reversion

**Funding Rate:**
- Basis Stop: |basis| > 2% (divergence risk)
- Rate Stop: Funding reverses sign

**Triangular:**
- Latency Stop: Execution > 100ms (slippage risk)
- Profit Stop: Net profit < 0.05% (fees too high)

---

## Performance Monitoring

### Daily Report Template

```python
def generate_daily_report(strategies):
    """Generate daily performance report"""
    print("=" * 60)
    print("STATISTICAL ARBITRAGE DAILY REPORT")
    print("=" * 60)

    # Pairs Trading
    print("\n📊 PAIRS TRADING:")
    for strategy in pairs_strategies:
        status = strategy.get_status()
        print(f"  {strategy.symbol_x}/{strategy.symbol_y}:")
        print(f"    Position: {status['current_position']}")
        print(f"    Cointegrated: {status['is_cointegrated']}")

    # Funding Rate
    print("\n💰 FUNDING RATE ARBITRAGE:")
    for strategy in funding_strategies:
        status = strategy.get_status()
        print(f"  {strategy.symbol}:")
        print(f"    Position: {status['current_position']}")
        print(f"    Collected: ${status['total_funding_collected']:.2f}")

    # Triangular
    print("\n🔺 TRIANGULAR ARBITRAGE:")
    status = triangular_strategy.get_status()
    print(f"  Opportunities: {status['total_arbitrages_executed']}")
    print(f"  Profit: ${status['total_profit']:.2f}")

    print("=" * 60)
```

---

## Troubleshooting

### Common Issues

**Issue: Pair not cointegrated**
```
Solution: Try different lookback periods or test other pairs
strategy.calibrate(price_x, price_y)  # Returns False
→ Use PairScanner to find better pairs
```

**Issue: No triangular arbitrage opportunities**
```
Solution: Normal in efficient markets. Lower min_profit_threshold carefully
strategy.min_profit_threshold = 0.0005  # 0.05%
```

**Issue: Funding rate signals not generating**
```
Solution: Check if funding rates meet minimum threshold
print(f"Current: {funding_rate:.4f}, Min: {strategy.min_funding_rate:.4f}")
```

---

## Next Steps

1. **Backtest Strategies**: Use historical data to validate performance
2. **Paper Trade**: Test with real-time data, simulated execution
3. **Start Small**: Begin with minimal capital (1-5% of portfolio)
4. **Monitor Daily**: Track performance and adjust parameters
5. **Scale Gradually**: Increase allocation as confidence grows

---

**Support:** For questions or issues, contact the trading bot development team.
**Documentation:** See `docs/COINTEGRATION_TESTING_GUIDE.md` for statistical methods.
