# Multi-Symbol Portfolio Trading System

## 🎯 Overview

Advanced portfolio management system for trading 5-10 cryptocurrency symbols simultaneously with:
- **Correlation-based diversification**
- **Portfolio-level risk management**
- **Intelligent capital allocation**
- **Real-time rebalancing**
- **Priority-based trading**

---

## 📊 Default Portfolio Configuration

### Symbol Allocation (8 Symbols)

#### Large Cap (40% allocation)
| Symbol   | Weight | Max Position | Priority | Correlation Group |
|----------|--------|--------------|----------|-------------------|
| BTCUSDT  | 20%    | $2,000       | 1        | large_cap         |
| ETHUSDT  | 20%    | $2,000       | 1        | large_cap         |

#### Mid Cap (30% allocation)
| Symbol   | Weight | Max Position | Priority | Correlation Group |
|----------|--------|--------------|----------|-------------------|
| BNBUSDT  | 10%    | $1,000       | 2        | mid_cap           |
| SOLUSDT  | 10%    | $1,000       | 2        | mid_cap           |
| ADAUSDT  | 10%    | $1,000       | 2        | mid_cap           |

#### Small Cap (30% allocation)
| Symbol   | Weight | Max Position | Priority | Correlation Group |
|----------|--------|--------------|----------|-------------------|
| AVAXUSDT | 10%    | $1,000       | 3        | small_cap         |
| DOTUSDT  | 10%    | $1,000       | 3        | small_cap         |
| LINKUSDT | 10%    | $1,000       | 3        | small_cap         |

**Total Portfolio Value:** $10,000 (paper trading)

---

## 🧮 Portfolio Optimization Features

### 1. Correlation Analysis

**Purpose:** Avoid over-concentration in correlated assets

**How it works:**
```python
# Calculates correlation matrix from price history
correlation = np.corrcoef(returns1, returns2)[0, 1]

# Example correlations:
BTC-ETH:  0.85 (high correlation - both large caps)
BTC-SOL:  0.65 (moderate correlation)
BTC-LINK: 0.45 (low correlation - better diversification)
```

**Decision Logic:**
- If portfolio correlation_risk > 0.8 → Only trade if improves diversification
- Avoid multiple positions in same correlation group when risk is high
- Track correlation matrix with 100-point price history

### 2. Diversification Scoring

**Metric:** Herfindahl-Hirschman Index (HHI)

**Calculation:**
```
concentration = Σ(exposure_i / total_exposure)²

diversification_score = 1 - (concentration - min) / (max - min)

Score ranges:
1.0 = Perfect diversification (equal exposure across all groups)
0.5 = Moderate concentration
0.0 = Fully concentrated (all in one group)
```

**Example:**
```
Portfolio A: 33% large_cap, 33% mid_cap, 33% small_cap
→ Diversification Score: 1.0 ✅ (Excellent)

Portfolio B: 80% large_cap, 10% mid_cap, 10% small_cap
→ Diversification Score: 0.4 ⚠️ (Poor)
```

### 3. Portfolio-Level Risk Controls

**Multi-Layer Protection:**

```python
# Layer 1: Portfolio Exposure Limit
max_total_exposure = 20% of capital
current_exposure = sum(all_open_positions)

if current_exposure >= max_total_exposure:
    → Block new trades

# Layer 2: Per-Symbol Allocation Limit
symbol_allocation[BTCUSDT] = 20% max
current_btc_exposure = btc_position_value

if current_btc_exposure >= symbol_max:
    → Block trades in BTCUSDT

# Layer 3: Correlation Risk Check
if correlation_risk > 0.8:
    if new_symbol_group == existing_position_group:
        → Block trade (avoid concentration)

# Layer 4: Per-Trade Risk Limit
max_per_trade = 2% of capital (from settings)
position_size = min(symbol_allocation, max_per_trade)
```

### 4. Intelligent Capital Allocation

**Position Sizing Algorithm:**

```python
def calculate_position_size(symbol, current_price, balance):
    # Get symbol target weight
    target_weight = allocations[symbol].target_weight  # e.g., 0.20

    # Calculate target value
    target_value = balance * target_weight  # e.g., $10,000 * 0.20 = $2,000

    # Apply constraints
    position_value = min(
        target_value,                    # Target allocation
        allocation.max_position_value,   # Symbol max
        balance * (max_position_size_pct / 100)  # Per-trade limit
    )

    # Convert to quantity
    quantity = position_value / current_price

    return quantity
```

**Example:**
```
Symbol: BTCUSDT
Current Price: $50,000
Portfolio Balance: $10,000
Target Weight: 20%

Calculation:
target_value = $10,000 * 0.20 = $2,000
max_allowed = min($2,000, $2,000, $200) = $200 (per-trade limit)
quantity = $200 / $50,000 = 0.004 BTC
```

### 5. Priority-Based Trading

**How Priority Works:**

```
Priority 1 (Highest):
- BTC, ETH (large caps)
- Trade first when signals appear
- Core portfolio holdings

Priority 2 (Medium):
- BNB, SOL, ADA (mid caps)
- Trade after Priority 1 filled
- Growth positions

Priority 3 (Lower):
- AVAX, DOT, LINK (small caps)
- Trade last
- Speculative positions
```

**Trading Cycle Example:**
```
Available capital: $10,000
No open positions

Cycle 1:
1. Check BTCUSDT (priority 1) → Signal: BUY 🟢 → Execute ($2,000)
2. Check ETHUSDT (priority 1) → Signal: HOLD 🟡 → Skip
3. Check BNBUSDT (priority 2) → Signal: BUY 🟢 → Execute ($1,000)
4. Check SOLUSDT (priority 2) → Signal: BUY 🟢 → Execute ($1,000)
5. Remaining symbols → Portfolio exposure limit reached → Stop

Result: 3 positions, $4,000 exposure (40%)
```

---

## 📈 Portfolio Metrics Dashboard

### Real-Time Metrics

```
Portfolio Status:
================
Total Value:      $10,500  (+5.0%)
Cash Balance:     $6,000
Total Exposure:   $4,500  (42.9%)
Unrealized P&L:   +$500
Realized P&L:     $0
Open Positions:   3

Diversification:  0.85    (85% - Excellent)
Correlation Risk: 0.35    (35% - Low)

Position Breakdown:
-------------------
BTCUSDT:  $2,100  (20%)  [large_cap]  +$100 (+5.0%)
BNBUSDT:  $1,200  (11%)  [mid_cap]    +$200 (+20%)
SOLUSDT:  $1,200  (11%)  [mid_cap]    +$200 (+20%)
```

### Warning Thresholds

```python
if exposure_pct > 80%:
    ⚠️ "High portfolio exposure"

if correlation_risk > 0.7:
    ⚠️ "High correlation risk - portfolio not diversified"

if diversification_score < 0.5:
    ⚠️ "Low diversification - concentrated positions"
```

---

## 🚀 Usage

### Starting Multi-Symbol Trading

```python
from app.multi_symbol_trader import get_multi_symbol_trader

# Get trader instance
trader = get_multi_symbol_trader()

# Start trading
await trader.start()

# Output:
# 🚀 Starting multi-symbol automated trading loop
# 📊 Multi-symbol automated trading loop started
#    Trading 8 symbols with portfolio optimization
```

### Checking Status

```python
status = trader.get_status()

print(status)
# {
#   "is_running": true,
#   "symbols": ["BTCUSDT", "ETHUSDT", ...],
#   "num_symbols": 8,
#   "total_trades_executed": 12,
#   "total_trades_rejected": 5,
#   "portfolio_metrics": {
#     "total_value": 10500.00,
#     "exposure_pct": 42.9,
#     "num_positions": 3,
#     "diversification_score": 0.85,
#     "correlation_risk": 0.35
#   },
#   "symbol_statistics": {
#     "BTCUSDT": {
#       "signals_checked": 10,
#       "trades_executed": 3,
#       "trades_rejected": 2
#     },
#     ...
#   }
# }
```

### Stopping Trading

```python
await trader.stop()

# 🛑 Stopping multi-symbol trading loop
# Trading loop task cancelled successfully
```

---

## 🔄 Trading Cycle Workflow

### Each Cycle (Every 5 minutes by default)

```
1. Portfolio Status Check
   ├─ Calculate current metrics
   ├─ Log portfolio status
   └─ Check warning thresholds

2. Get Trading Priority List
   ├─ Filter symbols without open positions
   ├─ Sort by priority
   └─ Return ordered list

3. For each symbol (in priority order):
   ├─ Check portfolio constraints
   │  ├─ Total exposure limit
   │  ├─ Symbol allocation limit
   │  ├─ Correlation risk
   │  └─ Already have position?
   │
   ├─ Get trading signal
   │  ├─ Fetch from Technical Analysis service
   │  ├─ Update price history
   │  └─ Check signal requirements
   │
   └─ Execute trade (if approved)
      ├─ Calculate position size
      ├─ Execute market order
      ├─ Update correlation matrix
      └─ Log statistics

4. Cycle Summary
   ├─ Log total signals checked
   ├─ Log trades executed/rejected
   └─ Wait for next cycle
```

---

## 🎯 Decision Logic Examples

### Example 1: High Correlation Risk

**Scenario:**
```
Current Portfolio:
- BTCUSDT: $2,000 (large_cap)
- ETHUSDT: $2,000 (large_cap)

BTC-ETH Correlation: 0.85 (high)
Correlation Risk: 0.85 > 0.8 threshold
```

**New Signal:**
```
BNBUSDT: BUY signal (strong)
Correlation Group: mid_cap
```

**Decision:**
```python
correlation_risk = 0.85  # High!

# Check if BNBUSDT group has existing position
mid_cap_positions = [BNBUSDT would be first]

# Since correlation_risk > 0.8 but BNBUSDT is in different group:
should_trade = True  # ✅ Improves diversification!

Result: Trade executed - diversification improves from 0.5 → 0.75
```

### Example 2: Allocation Limit Reached

**Scenario:**
```
BTCUSDT Position: $2,000
BTCUSDT Max Allocation: $2,000
```

**New Signal:**
```
BTCUSDT: BUY signal (strong)
```

**Decision:**
```python
current_btc_exposure = $2,000
max_btc_allocation = $2,000

if current_btc_exposure >= max_btc_allocation:
    should_trade = False
    reason = "Symbol allocation limit reached"

Result: Trade rejected - already at max allocation
```

### Example 3: Portfolio Exposure Limit

**Scenario:**
```
Total Portfolio Value: $10,000
Current Exposure: $8,500 (85%)
Max Exposure Limit: 80%
```

**New Signal:**
```
SOLUSDT: BUY signal
```

**Decision:**
```python
exposure_pct = 85%
max_exposure_pct = 80%

if exposure_pct >= max_exposure_pct:
    should_trade = False
    reason = "Portfolio exposure 85% >= max 80%"

Result: Trade rejected - portfolio at capacity
```

---

## 📊 Performance Metrics

### Key Performance Indicators (KPIs)

```python
# Trading Efficiency
signals_checked_per_cycle = 8  # All symbols
avg_execution_rate = trades_executed / signals_checked
target_execution_rate = 0.3  # 30% of signals should execute

# Portfolio Health
target_diversification = 0.8  # 80%+
target_correlation_risk = 0.4  # Below 40%
target_exposure_range = (40%, 80%)  # Active but not overexposed

# Per-Symbol Performance
for symbol in symbols:
    win_rate = profitable_trades / total_trades
    avg_pnl = total_pnl / total_trades
    sharpe_ratio = calculate_sharpe(returns)
```

### Monitoring Dashboard

```
Multi-Symbol Portfolio Dashboard
================================

Overall Performance:
- Total Return: +5.2%
- Win Rate: 65%
- Sharpe Ratio: 1.8
- Max Drawdown: -2.1%

Portfolio Health:
- Diversification: 0.82 ✅
- Correlation Risk: 0.38 ✅
- Exposure: 45% ✅

Top Performers:
1. SOLUSDT: +22% (3 trades, 100% win rate)
2. BNBUSDT: +18% (2 trades, 100% win rate)
3. BTCUSDT: +5% (5 trades, 80% win rate)

Bottom Performers:
1. LINKUSDT: -3% (2 trades, 0% win rate)
2. DOTUSDT: +1% (1 trade, 100% win rate)
```

---

## 🔧 Configuration

### Customizing Portfolio

```python
from app.portfolio_optimizer import get_portfolio_optimizer

optimizer = get_portfolio_optimizer()

# Add new symbol
optimizer.allocations["MATICUSDT"] = SymbolAllocation(
    symbol="MATICUSDT",
    target_weight=0.05,  # 5%
    current_weight=0.0,
    max_position_value=Decimal("500"),
    priority=3,
    correlation_group="small_cap"
)

# Modify existing allocation
optimizer.allocations["BTCUSDT"].target_weight = 0.25  # Increase to 25%
optimizer.allocations["BTCUSDT"].priority = 1  # Keep highest priority
```

### Adjusting Risk Parameters

```python
# In .env file or environment variables:

MAX_TOTAL_EXPOSURE_PCT=30.0      # Default: 20%
MAX_POSITION_SIZE_PCT=3.0        # Default: 2%
MIN_SIGNAL_CONFIDENCE=0.7        # Default: 0.6
```

### Correlation Sensitivity

```python
# In multi_symbol_trader.py:

# Increase correlation threshold (more strict)
correlation_threshold = 0.7  # Default: 0.8

# Require more price history for correlation
min_history_for_correlation = 50  # Default: 30
```

---

## ⚠️ Risk Management

### Multi-Layer Protection

**1. Pre-Trade Checks:**
```
✓ Portfolio exposure < max_total_exposure
✓ Symbol allocation < symbol_max
✓ Correlation risk acceptable
✓ Signal meets confidence threshold
✓ No existing position in symbol
```

**2. During Trade:**
```
✓ Position size calculated by allocation
✓ Stop-loss and take-profit set
✓ Commission factored in
✓ Slippage considered (paper trading)
```

**3. Post-Trade:**
```
✓ Update correlation matrix
✓ Recalculate portfolio metrics
✓ Check warning thresholds
✓ Log all statistics
```

### Emergency Halt Conditions

```python
# System halts ALL trading if:
daily_loss_pct > MAX_DAILY_LOSS_PCT  # Default: 5%

# Individual symbol blocked if:
symbol_exposure >= symbol_max_allocation
portfolio_exposure >= max_total_exposure
correlation_risk > 0.8 AND same_group_position_exists
```

---

## 🧪 Testing

### Unit Tests

```python
# Test portfolio optimizer
pytest tests/unit/test_portfolio_optimizer.py

# Test multi-symbol trader
pytest tests/unit/test_multi_symbol_trader.py
```

### Integration Tests

```python
# Test end-to-end multi-symbol trading
pytest tests/integration/test_multi_symbol_flow.py

# Test correlation calculation
pytest tests/integration/test_correlation_analysis.py
```

### Manual Testing

```python
# Test portfolio setup
from app.portfolio_optimizer import get_portfolio_optimizer

optimizer = get_portfolio_optimizer()
allocations = optimizer.setup_default_portfolio()

print(f"Portfolio: {len(allocations)} symbols")
for symbol, alloc in allocations.items():
    print(f"  {symbol}: {alloc.target_weight:.1%} (group: {alloc.correlation_group})")
```

---

## 📚 Advanced Topics

### Custom Allocation Strategies

**Equal Weight:**
```python
# All symbols get equal allocation
num_symbols = len(symbols)
weight = 1.0 / num_symbols  # e.g., 8 symbols = 12.5% each
```

**Market Cap Weighted:**
```python
# Weight by market capitalization
btc_weight = btc_market_cap / total_market_cap
eth_weight = eth_market_cap / total_market_cap
```

**Risk Parity:**
```python
# Equal risk contribution from each symbol
symbol_weight = (1 / symbol_volatility) / sum(1 / volatilities)
```

### Dynamic Rebalancing

```python
def should_rebalance(current_weights, target_weights):
    """Check if portfolio needs rebalancing"""
    for symbol in symbols:
        deviation = abs(current_weights[symbol] - target_weights[symbol])
        if deviation > 0.05:  # 5% threshold
            return True
    return False

# Rebalancing logic
if should_rebalance(current, target):
    # Close overweight positions
    # Open underweight positions
    # Maintain target allocation
```

---

## 🎓 Best Practices

1. **Start Conservative**
   - Begin with large caps only
   - Use lower allocation percentages
   - Increase exposure gradually

2. **Monitor Correlation**
   - Review correlation matrix weekly
   - Adjust groups if correlations change
   - Avoid over-concentration

3. **Diversify Timeframes**
   - Use multi-timeframe confirmation
   - Different symbols may perform better on different timeframes
   - Align trading intervals with symbol volatility

4. **Regular Rebalancing**
   - Review allocations monthly
   - Adjust based on performance
   - Consider market conditions

5. **Track Performance**
   - Log all trades
   - Calculate per-symbol metrics
   - Review correlation effectiveness

---

## 🔗 Integration with Existing Systems

```
Multi-Symbol Portfolio Trading
       ↓
   ┌─────────────────────────────┐
   │  Portfolio Optimizer         │
   │  - Correlation analysis      │
   │  - Diversification scoring   │
   │  - Capital allocation        │
   └────────┬────────────────────┘
            ↓
   ┌─────────────────────────────┐
   │  Multi-Symbol Trader         │
   │  - Signal aggregation        │
   │  - Priority-based trading    │
   │  - Position sizing           │
   └────────┬────────────────────┘
            ↓
   ┌─────────────────────────────┐
   │  Existing Systems            │
   │  ├─ Signal Aggregator        │
   │  ├─ Risk Manager             │
   │  ├─ Position Manager         │
   │  ├─ Paper Trading Engine     │
   │  └─ Database Persistence     │
   └──────────────────────────────┘
```

---

**Status:** ✅ Fully implemented with database persistence and correlation analysis
**Last Updated:** 2025-11-16
**Estimated Time to Implement:** 4-6 hours ✅ COMPLETE
