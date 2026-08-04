# Portfolio Optimization Guide

## Overview

The Portfolio Optimization module implements advanced portfolio management algorithms based on Modern Portfolio Theory (MPT), Kelly Criterion, and other quantitative strategies for optimizing cryptocurrency portfolios.

## Table of Contents

- [Features](#features)
- [Optimization Strategies](#optimization-strategies)
- [API Endpoints](#api-endpoints)
- [Usage Examples](#usage-examples)
- [Mathematical Foundations](#mathematical-foundations)
- [Configuration](#configuration)
- [Best Practices](#best-practices)

## Features

### Core Capabilities

1. **Modern Portfolio Theory (MPT)**
   - Markowitz Mean-Variance Optimization
   - Efficient Frontier Generation
   - Sharpe Ratio Maximization

2. **Position Sizing**
   - Kelly Criterion for optimal position sizing
   - Risk-based position limits
   - Dynamic rebalancing

3. **Risk Management**
   - Value at Risk (VaR) calculation
   - Conditional Value at Risk (CVaR)
   - Maximum Drawdown analysis
   - Volatility constraints

4. **Diversification Strategies**
   - Risk Parity allocation
   - Maximum Diversification portfolio
   - Correlation-based constraints

5. **Portfolio Analytics**
   - Diversification ratio
   - Effective number of assets
   - Risk contribution analysis

## Optimization Strategies

### 1. Maximum Sharpe Ratio (max_sharpe)

**Description**: Maximizes the risk-adjusted return (Sharpe Ratio)

**Formula**:
```
Sharpe Ratio = (Portfolio Return - Risk-Free Rate) / Portfolio Volatility

Maximize: SR = (R_p - R_f) / σ_p
```

**Use Case**: Best for investors seeking optimal risk-adjusted returns

**Example Result**:
```json
{
  "weights": {
    "BTCUSDT": 0.45,
    "ETHUSDT": 0.35,
    "BNBUSDT": 0.20
  },
  "expected_return": 0.2850,
  "expected_volatility": 0.3200,
  "sharpe_ratio": 0.7656
}
```

### 2. Minimum Volatility (min_volatility)

**Description**: Minimizes portfolio volatility (risk)

**Formula**:
```
Minimize: σ_p = √(w^T Σ w)

where:
- w = portfolio weights
- Σ = covariance matrix
```

**Use Case**: Conservative investors prioritizing capital preservation

**Example Result**:
```json
{
  "weights": {
    "BTCUSDT": 0.25,
    "ETHUSDT": 0.30,
    "BNBUSDT": 0.45
  },
  "expected_return": 0.1800,
  "expected_volatility": 0.2100,
  "sharpe_ratio": 0.6571
}
```

### 3. Risk Parity (risk_parity)

**Description**: Equal risk contribution from all assets

**Formula**:
```
Target: RC_i = RC_j for all assets i, j

Risk Contribution_i = w_i * (Σw)_i / σ_p
```

**Use Case**: Balanced diversification across all holdings

**Example Result**:
```json
{
  "weights": {
    "BTCUSDT": 0.28,
    "ETHUSDT": 0.35,
    "BNBUSDT": 0.37
  },
  "expected_return": 0.2200,
  "expected_volatility": 0.2650,
  "sharpe_ratio": 0.6792
}
```

### 4. Maximum Diversification (max_diversification)

**Description**: Maximizes the diversification ratio

**Formula**:
```
Diversification Ratio = (Weighted Avg Volatility) / (Portfolio Volatility)

Maximize: DR = Σ(w_i * σ_i) / σ_p
```

**Use Case**: Investors seeking maximum diversification benefits

**Example Result**:
```json
{
  "weights": {
    "BTCUSDT": 0.30,
    "ETHUSDT": 0.32,
    "BNBUSDT": 0.38
  },
  "diversification_ratio": 1.45,
  "expected_return": 0.2100,
  "expected_volatility": 0.2550
}
```

### 5. Kelly Criterion (kelly_criterion)

**Description**: Optimal position sizing for maximum geometric growth

**Formula**:
```
f* = Σ^(-1) * (μ - r)

where:
- f* = optimal fractions
- Σ = covariance matrix
- μ = expected returns
- r = risk-free rate
```

**Use Case**: Aggressive growth strategy (use fractional Kelly for safety)

**Example Result**:
```json
{
  "weights": {
    "BTCUSDT": 0.50,
    "ETHUSDT": 0.35,
    "BNBUSDT": 0.15
  },
  "expected_return": 0.3200,
  "expected_volatility": 0.3800,
  "sharpe_ratio": 0.7368
}
```

### 6. Maximum Return (max_return)

**Description**: Maximizes expected portfolio return (subject to constraints)

**Use Case**: Risk-tolerant investors with volatility constraints

## API Endpoints

### 1. Optimize Portfolio

**Endpoint**: `POST /api/v1/portfolio/optimize`

**Description**: Calculate optimal portfolio allocation

**Parameters**:
```json
{
  "portfolio_id": "default",
  "objective": "max_sharpe",
  "lookback_days": 60,
  "max_position_size": 0.30,
  "min_position_size": 0.05,
  "max_portfolio_volatility": null
}
```

**Response**:
```json
{
  "success": true,
  "portfolio_id": "default",
  "objective": "max_sharpe",
  "optimization_result": {
    "weights": {
      "BTCUSDT": 0.4234,
      "ETHUSDT": 0.3456,
      "BNBUSDT": 0.2310
    },
    "expected_return": "0.2845",
    "expected_volatility": "0.3156",
    "sharpe_ratio": "0.7742",
    "value_at_risk_95": "0.0234",
    "conditional_var_95": "0.0312",
    "diversification_ratio": "1.3456",
    "effective_num_assets": "2.87"
  },
  "rebalancing_trades": [
    {
      "symbol": "BTCUSDT",
      "action": "BUY",
      "amount_usd": "523.40"
    },
    {
      "symbol": "ETHUSDT",
      "action": "SELL",
      "amount_usd": "234.50"
    }
  ],
  "constraints_met": true,
  "optimization_time": "0.45s",
  "message": "Optimization successful"
}
```

### 2. Get Efficient Frontier

**Endpoint**: `GET /api/v1/portfolio/efficient-frontier`

**Description**: Generate efficient frontier points

**Parameters**:
```
- portfolio_id: string (default: "default")
- num_points: integer (10-100, default: 50)
- lookback_days: integer (30-365, default: 60)
```

**Response**:
```json
{
  "success": true,
  "portfolio_id": "default",
  "num_points": 50,
  "frontier_points": [
    {
      "expected_return": "0.1500",
      "expected_volatility": "0.2000",
      "sharpe_ratio": "0.5750",
      "weights": {
        "BTCUSDT": 0.20,
        "ETHUSDT": 0.30,
        "BNBUSDT": 0.50
      }
    },
    // ... more points
  ],
  "message": "Generated 50 efficient frontier points"
}
```

### 3. Execute Rebalancing

**Endpoint**: `POST /api/v1/portfolio/rebalance`

**Description**: Rebalance portfolio to target weights

**Request Body**:
```json
{
  "target_weights": {
    "BTCUSDT": 0.40,
    "ETHUSDT": 0.35,
    "BNBUSDT": 0.25
  },
  "execute": false
}
```

**Response**:
```json
{
  "success": true,
  "portfolio_id": "default",
  "executed": false,
  "current_weights": {
    "BTCUSDT": 0.45,
    "ETHUSDT": 0.30,
    "BNBUSDT": 0.25
  },
  "target_weights": {
    "BTCUSDT": 0.40,
    "ETHUSDT": 0.35,
    "BNBUSDT": 0.25
  },
  "trades": [
    {
      "symbol": "BTCUSDT",
      "action": "SELL",
      "amount_usd": "500.00"
    },
    {
      "symbol": "ETHUSDT",
      "action": "BUY",
      "amount_usd": "500.00"
    }
  ],
  "message": "Planned 2 rebalancing trades"
}
```

## Usage Examples

### Example 1: Optimize for Maximum Sharpe Ratio

```python
import httpx

async def optimize_portfolio():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8003/api/v1/portfolio/optimize",
            params={
                "portfolio_id": "default",
                "objective": "max_sharpe",
                "lookback_days": 90,
                "max_position_size": 0.40,
                "min_position_size": 0.10
            }
        )

        result = response.json()
        print(f"Optimal weights: {result['optimization_result']['weights']}")
        print(f"Sharpe ratio: {result['optimization_result']['sharpe_ratio']}")

        return result

# Run optimization
result = await optimize_portfolio()
```

### Example 2: Generate Efficient Frontier

```python
async def get_efficient_frontier():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8003/api/v1/portfolio/efficient-frontier",
            params={
                "portfolio_id": "default",
                "num_points": 30,
                "lookback_days": 60
            }
        )

        data = response.json()

        # Plot efficient frontier
        import matplotlib.pyplot as plt

        points = data['frontier_points']
        volatilities = [float(p['expected_volatility']) for p in points]
        returns = [float(p['expected_return']) for p in points]

        plt.figure(figsize=(10, 6))
        plt.plot(volatilities, returns, 'b-', linewidth=2)
        plt.xlabel('Expected Volatility (Risk)')
        plt.ylabel('Expected Return')
        plt.title('Efficient Frontier')
        plt.grid(True)
        plt.show()

# Generate and plot
await get_efficient_frontier()
```

### Example 3: Rebalance Portfolio

```python
async def rebalance_portfolio():
    # Step 1: Get optimal weights
    async with httpx.AsyncClient() as client:
        optimize_response = await client.post(
            "http://localhost:8003/api/v1/portfolio/optimize",
            params={"objective": "max_sharpe"}
        )

        optimal_weights = optimize_response.json()['optimization_result']['weights']

        # Step 2: Execute rebalancing (dry run first)
        rebalance_response = await client.post(
            "http://localhost:8003/api/v1/portfolio/rebalance",
            json={
                "target_weights": optimal_weights,
                "execute": False  # Dry run
            }
        )

        trades = rebalance_response.json()['trades']
        print(f"Required trades: {trades}")

        # Step 3: Confirm and execute
        # confirm = input("Execute rebalancing? (yes/no): ")
        # if confirm.lower() == "yes":
        #     execute_response = await client.post(
        #         "http://localhost:8003/api/v1/portfolio/rebalance",
        #         json={
        #             "target_weights": optimal_weights,
        #             "execute": True
        #         }
        #     )

# Run rebalancing
await rebalance_portfolio()
```

### Example 4: Compare Multiple Strategies

```python
async def compare_strategies():
    objectives = [
        "max_sharpe",
        "min_volatility",
        "risk_parity",
        "max_diversification"
    ]

    results = {}

    async with httpx.AsyncClient() as client:
        for objective in objectives:
            response = await client.post(
                "http://localhost:8003/api/v1/portfolio/optimize",
                params={"objective": objective}
            )

            results[objective] = response.json()['optimization_result']

    # Compare results
    import pandas as pd

    comparison = pd.DataFrame({
        objective: {
            'Return': float(result['expected_return']),
            'Volatility': float(result['expected_volatility']),
            'Sharpe': float(result['sharpe_ratio'])
        }
        for objective, result in results.items()
    }).T

    print(comparison)

# Compare strategies
await compare_strategies()
```

## Mathematical Foundations

### Portfolio Return and Risk

**Portfolio Expected Return**:
```
R_p = Σ(w_i * R_i)

where:
- R_p = portfolio return
- w_i = weight of asset i
- R_i = return of asset i
```

**Portfolio Volatility**:
```
σ_p = √(w^T Σ w)

where:
- σ_p = portfolio standard deviation
- w = weight vector
- Σ = covariance matrix
```

### Sharpe Ratio

```
Sharpe Ratio = (R_p - R_f) / σ_p

where:
- R_p = portfolio return
- R_f = risk-free rate
- σ_p = portfolio volatility
```

**Interpretation**:
- SR > 1.0: Good risk-adjusted performance
- SR > 2.0: Excellent performance
- SR < 0: Portfolio underperforming risk-free rate

### Value at Risk (VaR)

95% VaR represents the maximum expected loss over a time period at 95% confidence level.

```
VaR_95% = μ - z * σ

where:
- μ = expected return
- z = 1.645 (z-score for 95% confidence)
- σ = volatility
```

### Conditional Value at Risk (CVaR)

Expected loss given that the loss exceeds VaR.

```
CVaR_95% = μ - σ * φ(z) / (1 - 0.95)

where:
- φ(z) = standard normal PDF
```

### Diversification Ratio

```
DR = (Σ w_i * σ_i) / σ_p

where:
- σ_i = volatility of asset i
- σ_p = portfolio volatility
```

**Interpretation**:
- DR = 1: No diversification benefit
- DR > 1: Portfolio is diversified
- DR = N: Perfect diversification (uncorrelated assets)

### Effective Number of Assets

Based on Herfindahl-Hirschman Index (HHI):

```
N_eff = 1 / Σ(w_i^2)

where:
- w_i = weight of asset i
```

**Interpretation**:
- N_eff = 1: Concentrated in single asset
- N_eff = N: Perfectly diversified (equal weights)

## Configuration

### Optimization Parameters

```python
# Default parameters
RISK_FREE_RATE = 0.04  # 4% annual
CONFIDENCE_LEVEL = 0.95  # 95% confidence
LOOKBACK_DAYS = 60  # 60 days of historical data
MAX_POSITION_SIZE = 0.30  # 30% maximum per position
MIN_POSITION_SIZE = 0.05  # 5% minimum per position
```

### Constraints Configuration

```python
from app.optimization import OptimizationConstraints

# Custom constraints
constraints = OptimizationConstraints(
    max_position_size=0.40,          # 40% max per asset
    min_position_size=0.10,          # 10% min per asset
    max_portfolio_volatility=0.25,   # 25% max volatility
    target_return=0.20,              # 20% target return
    min_assets=3,                    # At least 3 assets
    max_assets=7,                    # At most 7 assets
    max_sector_allocation=0.50,      # 50% max per sector
    max_turnover=1.0,                # 100% max turnover
    min_trade_size=100.0             # $100 min trade size
)
```

## Best Practices

### 1. Data Quality

- Use at least 60 days of historical data (252 days recommended)
- Ensure price data is clean and adjusted for splits/dividends
- Handle missing data appropriately (forward fill or interpolation)
- Use consistent time intervals (hourly, daily, etc.)

### 2. Optimization Frequency

**Recommended Rebalancing Schedule**:
- **Monthly**: Standard approach for most portfolios
- **Quarterly**: For tax-efficient strategies
- **Weekly**: For active trading strategies
- **Threshold-based**: Rebalance when drift exceeds 5-10%

### 3. Risk Management

- **Always use constraints**: Set realistic position size limits
- **Fractional Kelly**: Use 50% of Kelly weights for safety
- **Monitor VaR/CVaR**: Keep risk metrics within acceptable bounds
- **Diversification**: Maintain at least 3-5 positions
- **Correlation**: Avoid highly correlated assets

### 4. Backtesting

Before applying optimization results:

1. **Historical simulation**: Test on past data
2. **Walk-forward analysis**: Rolling optimization windows
3. **Transaction costs**: Include fees in calculations
4. **Slippage**: Account for execution price differences
5. **Market impact**: Consider for large positions

### 5. Monitoring

**Track these metrics regularly**:
- Actual vs. expected returns
- Realized vs. expected volatility
- Sharpe ratio over time
- Maximum drawdown
- Turnover and transaction costs
- Rebalancing frequency

### 6. Common Pitfalls

**Avoid these mistakes**:
- **Over-optimization**: Don't optimize on too little data
- **Ignoring transaction costs**: Include fees in calculations
- **Static allocations**: Update regularly as market conditions change
- **Correlation instability**: Correlations change over time
- **Black swan events**: Optimization assumes normal distributions
- **Look-ahead bias**: Don't use future data in backtests

## Advanced Topics

### 1. Robust Optimization

Use multiple estimation methods and average results:

```python
methods = ['sample', 'shrinkage', 'exponential']
results = []

for method in methods:
    cov_matrix = optimizer.calculate_covariance_matrix(
        returns,
        method=method
    )
    result = optimizer.optimize_portfolio(...)
    results.append(result)

# Average weights
avg_weights = {
    symbol: np.mean([r.weights[symbol] for r in results])
    for symbol in results[0].weights.keys()
}
```

### 2. Black-Litterman Model

Incorporate market views into optimization:

```python
# TODO: Implement Black-Litterman in future version
# Combines market equilibrium with investor views
```

### 3. Multi-Period Optimization

Optimize across multiple time horizons:

```python
# Optimize for different periods
short_term = optimizer.optimize_portfolio(
    returns[-30:],  # Last 30 days
    objective=OptimizationObjective.MAX_SHARPE
)

long_term = optimizer.optimize_portfolio(
    returns,  # All data
    objective=OptimizationObjective.MAX_SHARPE
)

# Blend allocations
blended_weights = {
    symbol: 0.6 * long_term.weights[symbol] + 0.4 * short_term.weights[symbol]
    for symbol in long_term.weights.keys()
}
```

### 4. Regime Detection

Adjust strategy based on market regime:

```python
# Detect high volatility regime
recent_vol = returns[-30:].std() * np.sqrt(252)

if recent_vol > 0.40:  # High volatility
    # Use defensive strategy
    result = optimizer.optimize_portfolio(
        returns,
        objective=OptimizationObjective.MIN_VOLATILITY
    )
else:  # Normal regime
    # Use aggressive strategy
    result = optimizer.optimize_portfolio(
        returns,
        objective=OptimizationObjective.MAX_SHARPE
    )
```

## Performance Benchmarks

Expected optimization times (on standard hardware):

- **Single optimization**: 0.1 - 1.0 seconds
- **Efficient frontier (50 points)**: 5 - 15 seconds
- **Multiple objectives comparison**: 1 - 3 seconds

Memory requirements:

- **Small portfolio (3-7 assets)**: < 50 MB
- **Medium portfolio (10-20 assets)**: 50-100 MB
- **Large portfolio (20+ assets)**: 100-500 MB

## Troubleshooting

### Common Issues

**1. Optimization fails to converge**
- **Solution**: Relax constraints or use different method
- **Check**: Ensure positive definite covariance matrix

**2. Unrealistic weights**
- **Solution**: Tighten position size constraints
- **Check**: Review input data for outliers

**3. High turnover**
- **Solution**: Add transaction cost penalty
- **Check**: Use threshold-based rebalancing

**4. Poor out-of-sample performance**
- **Solution**: Use longer historical period
- **Check**: Validate with walk-forward analysis

## References

### Academic Papers

1. Markowitz, H. (1952). "Portfolio Selection". Journal of Finance
2. Kelly, J.L. (1956). "A New Interpretation of Information Rate"
3. Sharpe, W.F. (1966). "Mutual Fund Performance"

### Books

1. "Modern Portfolio Theory and Investment Analysis" - Elton et al.
2. "Quantitative Portfolio Management" - Qian et al.
3. "Active Portfolio Management" - Grinold & Kahn

### Online Resources

1. PyPortfolioOpt Documentation: https://pyportfolioopt.readthedocs.io/
2. Quantopian Lectures: https://www.quantopian.com/lectures
3. QuantLib: https://www.quantlib.org/

## Support

For issues or questions:

- GitHub Issues: https://github.com/your-repo/crypto-trading-bot/issues
- Documentation: /docs/
- API Reference: http://localhost:8003/docs

## License

MIT License - See LICENSE file for details
