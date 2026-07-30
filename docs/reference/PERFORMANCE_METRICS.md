# Performance Metrics Documentation

## Phase 5.2: Advanced Performance Metrics

This document explains all the professional-grade performance metrics implemented in the trading engine. These metrics are designed to provide institutional-quality performance analysis.

---

## Table of Contents

1. [Risk-Adjusted Returns](#risk-adjusted-returns)
2. [Drawdown Analysis](#drawdown-analysis)
3. [Win/Loss Metrics](#winloss-metrics)
4. [Risk Metrics](#risk-metrics)
5. [Trade Efficiency](#trade-efficiency)
6. [Benchmark Comparison](#benchmark-comparison)
7. [API Endpoints](#api-endpoints)
8. [Industry Benchmarks](#industry-benchmarks)

---

## Risk-Adjusted Returns

Risk-adjusted returns account for the risk taken to achieve returns, providing a more complete picture of strategy performance.

### Sharpe Ratio

**Formula:** `(Mean Return - Risk Free Rate) / Standard Deviation of Returns`

**Interpretation:**
- Measures excess return per unit of risk (volatility)
- Higher is better
- **Industry Benchmark:**
  - < 0: Poor (losing money on risk-adjusted basis)
  - 0-1: Acceptable
  - 1-2: Good
  - 2-3: Very Good
  - > 3: Excellent (rare, verify data)

**Example:**
```
Sharpe = 1.85 means for every unit of volatility risk,
the strategy generates 1.85 units of excess return.
```

### Sortino Ratio

**Formula:** `(Mean Return - Risk Free Rate) / Downside Deviation`

**Interpretation:**
- Similar to Sharpe but only penalizes downside volatility
- More appropriate for strategies with asymmetric returns
- **Advantage:** Doesn't penalize upside volatility (which is good for traders)
- **Industry Benchmark:**
  - > 2.0: Excellent
  - 1.5-2.0: Good
  - 1.0-1.5: Acceptable
  - < 1.0: Needs improvement

### Calmar Ratio

**Formula:** `Annualized Return / Maximum Drawdown`

**Interpretation:**
- Measures return relative to worst-case drawdown
- Higher is better
- **Industry Benchmark:**
  - > 3.0: Excellent
  - 2.0-3.0: Good
  - 1.0-2.0: Acceptable
  - < 1.0: High risk relative to reward

### Omega Ratio

**Formula:** `Sum of returns above threshold / Sum of returns below threshold`

**Interpretation:**
- Considers the entire distribution of returns
- Takes into account probability of gains vs losses
- **Industry Benchmark:**
  - > 1.5: Good
  - 1.0-1.5: Acceptable
  - < 1.0: More losses than gains

### Treynor Ratio

**Formula:** `(Mean Return - Risk Free Rate) / Beta`

**Interpretation:**
- Measures return per unit of systematic risk
- Useful when strategy is part of a diversified portfolio
- Higher is better

### Information Ratio

**Formula:** `Excess Return over Benchmark / Tracking Error`

**Interpretation:**
- Measures skill in generating excess returns vs benchmark
- **Industry Benchmark:**
  - > 0.5: Very good
  - 0.25-0.5: Good
  - 0-0.25: Acceptable
  - < 0: Underperforming benchmark

---

## Drawdown Analysis

Drawdown metrics measure capital preservation and recovery characteristics.

### Maximum Drawdown

**Definition:** Largest peak-to-trough decline in portfolio value

**Interpretation:**
- Shows worst-case historical loss
- Critical for risk management
- **Industry Benchmark:**
  - < 5%: Very conservative
  - 5-10%: Conservative
  - 10-20%: Moderate
  - 20-30%: Aggressive
  - > 30%: High risk

### Recovery Factor

**Formula:** `Net Profit / Maximum Drawdown`

**Interpretation:**
- How many times profit covers worst drawdown
- Higher is better
- **Industry Benchmark:**
  - > 3: Excellent
  - 2-3: Good
  - 1-2: Acceptable
  - < 1: Poor (profit doesn't cover drawdown)

### Ulcer Index

**Formula:** `sqrt(mean(drawdowns^2))`

**Interpretation:**
- Root mean square of drawdowns
- Combines depth and duration of drawdowns
- **Lower is better**
- Named because high values cause "ulcers" (stress)

### Pain Index

**Formula:** `Average of (Drawdown Depth * Drawdown Duration)`

**Interpretation:**
- Measures cumulative suffering from drawdowns
- Accounts for both severity and duration
- **Lower is better**

### Time Underwater

**Definition:** Percentage of time portfolio is below previous peak

**Interpretation:**
- Shows how often strategy experiences drawdowns
- **Industry Benchmark:**
  - < 30%: Excellent
  - 30-50%: Good
  - 50-70%: Moderate
  - > 70%: High drawdown frequency

---

## Win/Loss Metrics

These metrics analyze individual trade performance.

### Win Rate

**Formula:** `Number of Winners / Total Trades`

**Interpretation:**
- Percentage of trades that are profitable
- **Note:** Win rate alone doesn't determine profitability
- A 30% win rate can be profitable with large winners

**Industry Benchmark:**
- Trend following: 35-45%
- Mean reversion: 55-70%
- Scalping: 60-75%

### Profit Factor

**Formula:** `Gross Profit / Gross Loss`

**Interpretation:**
- How many dollars gained for each dollar lost
- **Industry Benchmark:**
  - > 2.0: Excellent
  - 1.5-2.0: Good
  - 1.0-1.5: Acceptable
  - < 1.0: Losing money

### Payoff Ratio

**Formula:** `Average Win / Average Loss`

**Interpretation:**
- Risk/reward ratio of trades
- Combined with win rate determines expectancy
- **Higher is better**

### Expectancy

**Formula:** `(Win Rate * Avg Win) - (Loss Rate * Avg Loss)`

**Interpretation:**
- Expected profit/loss per trade
- **Must be positive** for profitable system
- Example: Expectancy of $42 means average expected profit of $42 per trade

### Kelly Percentage

**Formula:** `W - (1-W)/R` where W = win rate, R = payoff ratio

**Interpretation:**
- Optimal position size for maximum geometric growth
- **Use Half-Kelly (0.5x)** for safety
- Never use full Kelly - too aggressive

**Industry Recommendation:**
- Conservative: 0.25 * Kelly
- Moderate: 0.50 * Kelly
- Aggressive: 0.75 * Kelly

### Consecutive Wins/Losses

**Definition:** Maximum streak of consecutive winning/losing trades

**Interpretation:**
- Helps set psychological expectations
- Important for position sizing decisions
- Large losing streaks require smaller position sizes

---

## Risk Metrics

These metrics quantify potential losses and risk exposure.

### Value at Risk (VaR)

**Definition:** Maximum expected loss at a confidence level

**Interpretation:**
- VaR 95% = 2.3% means: "With 95% confidence, daily loss won't exceed 2.3%"
- **Industry Benchmark:**
  - < 2%: Conservative
  - 2-5%: Moderate
  - > 5%: Aggressive

### Conditional VaR (CVaR)

**Definition:** Expected loss when loss exceeds VaR (Expected Shortfall)

**Interpretation:**
- More conservative than VaR
- Shows average loss in worst-case scenarios
- CVaR is always >= VaR

### Maximum Adverse Excursion (MAE)

**Definition:** Average maximum loss experienced during open trades

**Interpretation:**
- Helps optimize stop-loss placement
- Shows typical heat taken before exit
- **Lower is better**

### Maximum Favorable Excursion (MFE)

**Definition:** Average maximum profit during open trades

**Interpretation:**
- Helps optimize profit target placement
- Compare to actual realized profit to measure efficiency
- If MFE >> realized profit, leaving money on table

### Risk of Ruin

**Definition:** Probability of losing all capital

**Interpretation:**
- **Industry Benchmark:**
  - < 0.1%: Excellent
  - 0.1-1%: Good
  - 1-5%: Moderate
  - > 5%: Dangerous

### Beta

**Definition:** Sensitivity to benchmark (BTC) movements

**Interpretation:**
- Beta = 1: Moves with market
- Beta > 1: More volatile than market
- Beta < 1: Less volatile than market
- Beta < 0: Moves opposite to market

---

## Trade Efficiency

These metrics analyze how efficiently capital and time are utilized.

### Average Trade Duration

**Definition:** Mean holding time of trades

**Interpretation:**
- Varies by strategy type:
  - Scalping: Minutes
  - Day trading: Hours
  - Swing trading: Days
  - Position trading: Weeks/Months

### Trades Per Period

**Definition:** Number of trades per day/week/month

**Interpretation:**
- Higher frequency = more transaction costs
- Lower frequency = potentially larger position sizes

### Capital Utilization

**Definition:** Average percentage of capital deployed

**Interpretation:**
- 100% = fully invested
- < 50% = conservative / waiting for opportunities
- Balance between opportunity cost and risk

### Turnover Ratio

**Definition:** Annualized portfolio turnover

**Interpretation:**
- Higher = more active trading
- Higher = more transaction costs
- Tax implications in some jurisdictions

---

## Benchmark Comparison

These metrics compare strategy performance to market benchmark (BTC).

### Excess Return

**Formula:** `Strategy Return - Benchmark Return`

**Interpretation:**
- Positive = outperforming market
- Negative = underperforming market

### Alpha

**Definition:** Risk-adjusted excess return

**Interpretation:**
- **Positive alpha = skill**
- Negative alpha = destroying value vs passive holding

### Correlation

**Definition:** How closely strategy moves with benchmark

**Interpretation:**
- 1 = perfectly correlated
- 0 = uncorrelated (diversification benefit)
- -1 = negatively correlated (hedging potential)

### Up/Down Capture Ratios

**Definition:** Strategy's performance relative to benchmark in up/down markets

**Interpretation:**
- Up Capture > 100%: Outperforms in up markets
- Down Capture < 100%: Loses less in down markets
- **Ideal:** High up capture, low down capture

---

## API Endpoints

### Metrics Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/analytics/metrics/risk-adjusted` | Sharpe, Sortino, Calmar, Omega ratios |
| `GET /api/v1/analytics/metrics/drawdown` | Max DD, Ulcer Index, Pain Index |
| `GET /api/v1/analytics/metrics/win-loss` | Win rate, Profit factor, Kelly % |
| `GET /api/v1/analytics/metrics/risk` | VaR, CVaR, MAE, MFE, Risk of Ruin |
| `GET /api/v1/analytics/metrics/efficiency` | Trade duration, frequency, utilization |
| `GET /api/v1/analytics/metrics/all` | All metrics combined |
| `GET /api/v1/analytics/metrics/compare?period=30` | Period comparison |
| `GET /api/v1/analytics/metrics/benchmark` | vs BTC comparison |

### Report Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/analytics/report/daily` | Daily performance report |
| `GET /api/v1/analytics/report/monthly?year=2025&month=12` | Monthly report |
| `GET /api/v1/analytics/report/monte-carlo?simulations=1000&horizon=30` | Monte Carlo projections |

---

## Industry Benchmarks Summary

| Metric | Poor | Acceptable | Good | Excellent |
|--------|------|------------|------|-----------|
| Sharpe Ratio | < 0 | 0-1 | 1-2 | > 2 |
| Sortino Ratio | < 1 | 1-1.5 | 1.5-2 | > 2 |
| Calmar Ratio | < 1 | 1-2 | 2-3 | > 3 |
| Max Drawdown | > 30% | 20-30% | 10-20% | < 10% |
| Profit Factor | < 1 | 1-1.5 | 1.5-2 | > 2 |
| Win Rate | Strategy dependent | | | |
| Kelly % Usage | Full | 75% | 50% | 25% |
| Risk of Ruin | > 5% | 1-5% | 0.1-1% | < 0.1% |

---

## Example Output

```json
{
  "risk_adjusted": {
    "sharpe_ratio": 1.85,
    "sortino_ratio": 2.34,
    "calmar_ratio": 1.92,
    "omega_ratio": 1.67
  },
  "drawdown": {
    "max_drawdown": -12.5,
    "avg_drawdown": -3.2,
    "recovery_factor": 2.1,
    "longest_dd_days": 7
  },
  "win_loss": {
    "win_rate": 0.58,
    "profit_factor": 1.85,
    "payoff_ratio": 1.45,
    "expectancy": 0.042
  },
  "risk": {
    "var_95": -2.3,
    "cvar_95": -3.8,
    "risk_of_ruin": 0.001
  }
}
```

---

## References

- "Active Portfolio Management" by Grinold & Kahn
- "Quantitative Trading" by Ernest Chan
- "The Kelly Capital Growth Investment Criterion" by MacLean, Thorp, Ziemba
- CFA Institute Standards of Practice
- GIPS (Global Investment Performance Standards)
