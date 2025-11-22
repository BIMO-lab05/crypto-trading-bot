# SQZMOM Strategy - Quick Reference Card

**Version:** 1.0.0 | **Date:** 2025-11-20

## Quick Status Check

```bash
# Verify deployment
./verify_sqzmom_deployment.sh

# Check configuration
curl http://localhost:8005/api/v1/strategies/sqzmom/config | jq

# Get all signals
curl http://localhost:8005/api/v1/strategies/sqzmom/signals | jq
```

## Enabled Symbols Only

| Symbol | Return | Win Rate | Position Size | Min Confidence |
|--------|--------|----------|---------------|----------------|
| **SOLUSDT** | +2,706% | 22% | 2.5% | 65% |
| **DOGEUSDT** | +630% | 28% | 1.5% | 75% |
| **BNBUSDT** | +330% | 31% | 2.0% | 70% |

❌ **DISABLED:** BTCUSDT, ETHUSDT, XRPUSDT, ADAUSDT (all lost >99%)

## Optimized Parameters

```python
min_momentum_threshold = 0.3    # More entry signals
stop_loss_pct = 1.5%            # Tighter stop loss
take_profit_pct = 3.0%          # Tighter take profit
max_positions = 3               # Risk management
min_confidence = 70%            # Quality filter
```

## Essential Commands

### Get Signals
```bash
# All symbols
curl http://localhost:8005/api/v1/strategies/sqzmom/signals

# Specific symbol
curl http://localhost:8005/api/v1/strategies/sqzmom/signal/SOLUSDT
```

### Enable/Disable
```bash
# Enable (manual approval)
curl -X POST http://localhost:8005/api/v1/strategies/sqzmom/enable

# Enable (auto trading) - USE WITH CAUTION
curl -X POST "http://localhost:8005/api/v1/strategies/sqzmom/enable?auto_trading=true"

# Disable
curl -X POST http://localhost:8005/api/v1/strategies/sqzmom/disable
```

### Execute Trade
```bash
# Manual trade execution
curl -X POST \
  "http://localhost:8005/api/v1/strategies/sqzmom/trade/SOLUSDT?force=true&account_balance=10000"
```

### Configuration
```bash
# Get strategy info
curl http://localhost:8005/api/v1/strategies/sqzmom/info

# Get current config
curl http://localhost:8005/api/v1/strategies/sqzmom/config

# Get symbol config
curl http://localhost:8005/api/v1/strategies/sqzmom/symbols/SOLUSDT/config
```

## Safety Checklist

- [ ] Trading Engine service running on port 8005
- [ ] Technical Analysis service running on port 8004
- [ ] Paper trading mode enabled (default)
- [ ] Auto trading disabled (default)
- [ ] Only enabled symbols in whitelist
- [ ] Max 3 concurrent positions configured
- [ ] Stop losses enabled (1.5%)
- [ ] Confidence threshold set (70%)

## Deployment Phases

1. **Testing** → Run tests and verification script
2. **Paper Trading** → Monitor signals for 2 weeks
3. **Manual Trading** → Execute trades with approval
4. **Auto Trading** → Enable automation gradually

## Signal Format

```json
{
  "symbol": "SOLUSDT",
  "action": "BUY|SELL|HOLD",
  "confidence": 0.85,
  "entry_price": 245.50,
  "stop_loss": 241.82,
  "take_profit": 252.87,
  "reason": "LONG Entry: Squeeze released, bullish momentum",
  "momentum": 0.4523,
  "squeeze_state": "OFF|ON|TRANSITIONAL"
}
```

## Key API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/strategies/sqzmom/info` | GET | Strategy information |
| `/api/v1/strategies/sqzmom/config` | GET | Current configuration |
| `/api/v1/strategies/sqzmom/signals` | GET | All signals |
| `/api/v1/strategies/sqzmom/signal/{symbol}` | GET | Single signal |
| `/api/v1/strategies/sqzmom/enable` | POST | Enable strategy |
| `/api/v1/strategies/sqzmom/disable` | POST | Disable strategy |
| `/api/v1/strategies/sqzmom/trade/{symbol}` | POST | Execute trade |
| `/api/v1/strategies/sqzmom/symbols/{symbol}/config` | GET | Symbol config |

## Monitoring Metrics

```bash
# Daily checks
curl http://localhost:8005/api/v1/performance
curl http://localhost:8005/api/v1/positions?status=open
curl http://localhost:8005/health/detailed
```

**Track:**
- Win rate: 25-35% target
- Max drawdown: <10% target
- Sharpe ratio: >2.0 target
- Position exposure: <7.5% max

## Troubleshooting

| Issue | Check |
|-------|-------|
| No signals | Technical Analysis service health |
| Signals not executing | auto_trading enabled, position limits |
| Poor performance | Compare to backtesting timeframe |
| HTTP errors | Service connectivity, logs |

## Risk Management

- **Position Size:** 1.5-2.5% per trade (symbol-specific)
- **Stop Loss:** 1.5% automatic
- **Take Profit:** 3.0-3.5% automatic
- **Max Positions:** 3 concurrent
- **Max Exposure:** 7.5% total (3 × 2.5%)

## Files Reference

```
/services/trading-engine/
├── app/strategies/
│   ├── sqzmom_config.py                    # Configuration
│   ├── sqzmom_strategy_integration.py      # Integration logic
│   └── __init__.py                         # Module exports
├── app/main.py                              # API endpoints (MODIFIED)
├── tests/test_sqzmom_strategy.py           # Unit tests
├── verify_sqzmom_deployment.sh             # Verification script
├── SQZMOM_DEPLOYMENT_GUIDE.md              # Full guide
├── SQZMOM_IMPLEMENTATION_SUMMARY.md        # Summary
└── SQZMOM_QUICK_REFERENCE.md               # This file
```

## Running Tests

```bash
cd /services/trading-engine

# Unit tests
pytest tests/test_sqzmom_strategy.py -v

# Verification script
./verify_sqzmom_deployment.sh
```

## Expected Performance

| Metric | Backtesting | Expected Live |
|--------|-------------|---------------|
| Win Rate | 22-31% | 20-35% |
| Return/Trade | Varies | 1-3% |
| Sharpe | 4.76-5.41 | 2.0-4.0 |
| Drawdown | N/A | 5-10% |

**Note:** Live trading ~50-70% of backtesting returns due to slippage and commissions.

## Important Notes

⚠️ **NEVER trade symbols outside whitelist**
⚠️ **Always start with paper trading**
⚠️ **Monitor daily for first 2 weeks**
⚠️ **Respect stop losses (automatic)**
⚠️ **Don't increase position sizes too quickly**

## Support

- Full guide: `SQZMOM_DEPLOYMENT_GUIDE.md`
- Implementation details: `SQZMOM_IMPLEMENTATION_SUMMARY.md`
- Logs: `services/trading-engine/logs/`

---

**Status:** ✅ Ready for Deployment
**Mode:** Paper Trading (Default)
**Auto Trading:** Disabled (Default)
