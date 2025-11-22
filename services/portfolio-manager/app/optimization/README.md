# Portfolio Optimization Module

## Overview

Advanced portfolio optimization algorithms implementing Modern Portfolio Theory (MPT), Kelly Criterion, and quantitative allocation strategies for cryptocurrency portfolios.

## Features

- **Modern Portfolio Theory (Markowitz)**
  - Mean-variance optimization
  - Sharpe ratio maximization
  - Efficient frontier generation

- **Position Sizing Algorithms**
  - Kelly Criterion for optimal sizing
  - Risk parity allocation
  - Maximum diversification

- **Risk Analytics**
  - Value at Risk (VaR)
  - Conditional VaR (CVaR/Expected Shortfall)
  - Diversification metrics
  - Correlation analysis

## Quick Start

### Basic Usage

```python
from app.optimization import PortfolioOptimizer, OptimizationObjective
import pandas as pd

# Initialize optimizer
optimizer = PortfolioOptimizer(
    risk_free_rate=0.04,  # 4% annual
    confidence_level=0.95
)

# Load price data (pandas DataFrame with symbols as columns)
price_data = pd.read_csv('historical_prices.csv', index_col=0, parse_dates=True)

# Calculate returns
returns = optimizer.calculate_returns_from_prices(price_data)

# Optimize for maximum Sharpe ratio
result = optimizer.optimize_portfolio(
    returns=returns,
    objective=OptimizationObjective.MAX_SHARPE
)

# View results
print(f"Optimal weights: {result.weights}")
print(f"Expected return: {result.expected_return:.2%}")
print(f"Expected volatility: {result.expected_volatility:.2%}")
print(f"Sharpe ratio: {result.sharpe_ratio:.4f}")
```

### Optimization Objectives

```python
# Available objectives
OptimizationObjective.MAX_SHARPE          # Maximize Sharpe ratio
OptimizationObjective.MIN_VOLATILITY      # Minimize volatility
OptimizationObjective.MAX_RETURN          # Maximize return
OptimizationObjective.RISK_PARITY         # Equal risk contribution
OptimizationObjective.MAX_DIVERSIFICATION # Maximum diversification
OptimizationObjective.KELLY_CRITERION     # Kelly optimal sizing
```

### Custom Constraints

```python
from app.optimization.portfolio_optimizer import OptimizationConstraints

constraints = OptimizationConstraints(
    max_position_size=0.40,          # Max 40% per position
    min_position_size=0.10,          # Min 10% per position
    max_portfolio_volatility=0.30,   # Max 30% annual volatility
    min_assets=3,                    # At least 3 positions
    max_assets=7                     # At most 7 positions
)

result = optimizer.optimize_portfolio(
    returns=returns,
    objective=OptimizationObjective.MAX_SHARPE,
    constraints=constraints
)
```

### Efficient Frontier

```python
# Generate efficient frontier
frontier_points = optimizer.generate_efficient_frontier(
    returns=returns,
    num_points=50
)

# Plot frontier
import matplotlib.pyplot as plt

vols = [p.expected_volatility for p in frontier_points]
rets = [p.expected_return for p in frontier_points]

plt.plot(vols, rets)
plt.xlabel('Volatility')
plt.ylabel('Return')
plt.title('Efficient Frontier')
plt.show()
```

### Rebalancing

```python
# Calculate rebalancing trades
current_weights = {'BTCUSDT': 0.50, 'ETHUSDT': 0.30, 'BNBUSDT': 0.20}
target_weights = result.weights
portfolio_value = 10000.0

trades = optimizer.calculate_rebalancing_trades(
    current_weights=current_weights,
    target_weights=target_weights,
    portfolio_value=portfolio_value,
    min_trade_size=100.0
)

for symbol, (action, amount) in trades.items():
    print(f"{action} {symbol}: ${amount:.2f}")
```

## Algorithm Details

### Markowitz Mean-Variance Optimization

Minimizes portfolio variance for a given return level:

```
minimize: σ²_p = w^T Σ w
subject to:
  - Σ w_i = 1 (weights sum to 1)
  - μ^T w = target_return
  - w_min ≤ w_i ≤ w_max
```

### Sharpe Ratio Maximization

Maximizes risk-adjusted return:

```
maximize: (μ^T w - r_f) / √(w^T Σ w)
subject to:
  - Σ w_i = 1
  - w_min ≤ w_i ≤ w_max
```

### Risk Parity

Equalizes risk contribution from each asset:

```
minimize: Σ (RC_i - RC_target)²
where: RC_i = w_i * (Σw)_i / σ_p
```

### Kelly Criterion

Maximizes geometric growth rate:

```
f* = Σ^(-1) * (μ - r)

Using fractional Kelly (50%):
f_actual = 0.5 * f*
```

## Risk Metrics

### Value at Risk (VaR)

Maximum expected loss at confidence level:

```python
var_95 = result.value_at_risk_95  # 95% VaR
```

### Conditional VaR (CVaR)

Expected loss beyond VaR:

```python
cvar_95 = result.conditional_var_95  # 95% CVaR
```

### Diversification Ratio

Measure of diversification benefit:

```python
div_ratio = result.diversification_ratio
# Values > 1 indicate diversification benefit
```

### Effective Number of Assets

Concentration measure:

```python
eff_num = result.effective_num_assets
# Close to N = well diversified
# Close to 1 = concentrated
```

## Performance Tips

1. **Data Requirements**: Use at least 60-90 days of daily data or 252 days for annual estimates

2. **Covariance Estimation**: Consider using shrinkage methods for better estimates:
   ```python
   cov_matrix = optimizer.calculate_covariance_matrix(
       returns,
       method='shrinkage'  # More stable than 'sample'
   )
   ```

3. **Optimization Speed**:
   - Simple objectives (min_vol, max_sharpe): < 1 second
   - Efficient frontier (50 points): 5-15 seconds
   - Use caching for repeated optimizations

4. **Numerical Stability**: Set realistic constraints to avoid edge cases

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest services/portfolio-manager/tests/test_portfolio_optimizer.py -v

# Run with coverage
pytest services/portfolio-manager/tests/test_portfolio_optimizer.py --cov=app/optimization --cov-report=html

# Run specific test
pytest services/portfolio-manager/tests/test_portfolio_optimizer.py::TestPortfolioOptimizer::test_optimize_max_sharpe -v
```

## API Integration

See main application (`app/main.py`) for FastAPI endpoints:

- `POST /api/v1/portfolio/optimize` - Optimize portfolio
- `GET /api/v1/portfolio/efficient-frontier` - Generate frontier
- `POST /api/v1/portfolio/rebalance` - Execute rebalancing

## Examples

See `/scripts/optimization/optimize_portfolio_example.py` for complete examples.

## References

### Academic Papers
1. Markowitz, H. (1952). "Portfolio Selection"
2. Kelly, J.L. (1956). "A New Interpretation of Information Rate"
3. Sharpe, W.F. (1966). "Mutual Fund Performance"

### Libraries
- SciPy: Optimization algorithms
- CVXPY: Convex optimization
- PyPortfolioOpt: Reference implementation

## License

MIT License - See project LICENSE file
