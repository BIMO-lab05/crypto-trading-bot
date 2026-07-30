# Risk & Metrics Service

**Port:** 8009
**Version:** 1.0.0

## Overview

The Risk & Metrics Service is a comprehensive risk management and performance analytics layer that monitors capital, exposure, calculates performance metrics, and provides real-time risk alerts.

## Features

### 1. Capital Monitoring
- Total capital tracking
- Available vs. allocated capital
- Reserved capital for risk management
- Capital utilization percentage

### 2. Exposure Management
- Long/short exposure tracking
- Net and gross exposure calculation
- Leverage monitoring
- Concentration risk detection
- Position size compliance

### 3. Performance Metrics
- **Sharpe Ratio** - Risk-adjusted return metric
- **Sortino Ratio** - Downside risk-adjusted return
- **Calmar Ratio** - Return vs. max drawdown
- Win rate and profit factor
- Average win/loss analysis

### 4. Drawdown Tracking
- Current drawdown percentage
- Maximum drawdown since inception
- Underwater period (days below peak)
- Recovery factor calculation

### 5. Value at Risk (VaR)
- 95% and 99% confidence levels
- Conditional VaR (CVaR/Expected Shortfall)
- Historical simulation method
- Time-scaled calculations

### 6. Risk Scoring
- Composite risk score (0-100)
- Component scores:
  - Capital risk
  - Exposure risk
  - Concentration risk
  - Volatility risk
  - Drawdown risk
- Risk level classification (LOW/MEDIUM/HIGH/CRITICAL)

### 7. Risk Alerts
- Real-time threshold violation detection
- Categorized alerts (Capital, Exposure, Concentration, etc.)
- Severity levels
- Actionable recommendations

### 8. Circuit Breaker
- Automatic trading halt on critical conditions
- Triggers:
  - Daily loss > 5%
  - Drawdown > 10%
  - Excessive exposure
- Configurable cooldown period
- Manual override capability

## API Endpoints

### Health & Status
```
GET  /health                  - Service health check
GET  /status                  - Detailed service status
```

### Risk Monitoring
```
GET  /risk/scorecard          - Complete risk assessment
GET  /risk/capital            - Capital metrics
GET  /risk/exposure           - Exposure analysis
GET  /risk/drawdown           - Drawdown metrics
GET  /risk/var                - Value at Risk calculation
```

### Performance
```
GET  /performance/metrics     - Performance statistics
GET  /performance/sharpe      - Sharpe ratio calculation
GET  /performance/returns     - Historical returns
```

### Alerts & Circuit Breaker
```
GET  /alerts                  - Active risk alerts
GET  /alerts/history          - Alert history
GET  /circuit-breaker         - Circuit breaker status
POST /circuit-breaker/reset   - Reset circuit breaker (admin)
```

### Configuration
```
GET  /config/limits           - Current risk limits
PUT  /config/limits           - Update risk limits (admin)
```

## Risk Limits Configuration

Default risk limits (configurable):

```python
max_position_size = 0.02      # 2% max per position
max_portfolio_risk = 0.05     # 5% max portfolio risk
max_drawdown_threshold = 0.10 # 10% max drawdown alert
max_daily_loss = 0.05         # 5% daily loss limit
max_exposure = 0.20           # 20% max total exposure
```

## Integration

### With Portfolio Manager
Fetches portfolio data, positions, and historical values for calculations.

### With Trading Engine
Provides pre-trade risk checks and trading permissions based on circuit breaker status.

### With API Gateway
Exposes risk metrics to frontend dashboard for real-time monitoring.

## Risk Metrics Calculations

### Sharpe Ratio
```
Sharpe = (Return - Risk_Free_Rate) / Volatility
```

### Sortino Ratio
```
Sortino = (Return - Risk_Free_Rate) / Downside_Deviation
```

### Calmar Ratio
```
Calmar = Annualized_Return / Maximum_Drawdown
```

### Value at Risk (95%)
```
VaR_95 = Portfolio_Value × Percentile_5(Returns) × √(Time_Horizon)
```

### Maximum Drawdown
```
Max_DD = Max((Peak_Value - Trough_Value) / Peak_Value)
```

## Usage Example

```python
import httpx

# Get complete risk assessment
response = httpx.get("http://localhost:8009/risk/scorecard")
scorecard = response.json()

print(f"Risk Level: {scorecard['overall_risk_level']}")
print(f"Risk Score: {scorecard['risk_score']}/100")
print(f"Sharpe Ratio: {scorecard['performance_metrics']['sharpe_ratio']}")
print(f"Current Drawdown: {scorecard['drawdown_metrics']['current_drawdown']*100}%")

# Check if trading is allowed
breaker = httpx.get("http://localhost:8009/circuit-breaker").json()
if not breaker['can_trade']:
    print(f"⚠️ Trading halted: {breaker['reason']}")
```

## Installation

```bash
cd services/risk-metrics-service
pip install -r requirements.txt
```

## Running the Service

```bash
# Development
uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8007 --workers 4
```

## Environment Variables

```bash
RISK_FREE_RATE=0.04                  # 4% annual
TARGET_SHARPE_RATIO=1.5
MAX_PORTFOLIO_RISK=0.05
MAX_POSITION_SIZE=0.02
MAX_DRAWDOWN_THRESHOLD=0.10
MAX_DAILY_LOSS=0.05
MAX_EXPOSURE=0.20
ENABLE_CIRCUIT_BREAKER=true
CIRCUIT_BREAKER_COOLDOWN=3600        # seconds
```

## Dependencies

- FastAPI - Web framework
- NumPy - Numerical calculations
- Pydantic - Data validation
- httpx - HTTP client for service communication

## Monitoring

The service provides comprehensive logging of:
- Risk calculations
- Alert triggers
- Circuit breaker activations
- Threshold violations
- Performance degradation

## Security

- Risk limit updates require admin authentication
- Circuit breaker reset requires elevated privileges
- Sensitive metrics are logged but not exposed publicly
- Rate limiting on all endpoints

## Future Enhancements

- [ ] Monte Carlo VaR simulation
- [ ] Stress testing scenarios
- [ ] Correlation analysis
- [ ] Greeks calculation for options
- [ ] Machine learning-based risk prediction
- [ ] Real-time WebSocket streaming
- [ ] Custom risk models
- [ ] Backtesting integration

## License

Part of the Crypto Trading Bot project.

---

**Service Status:** ⚠️ In Development
**Integration:** Portfolio Manager, Trading Engine, API Gateway
**Critical:** Yes - Halts trading on risk threshold breaches
