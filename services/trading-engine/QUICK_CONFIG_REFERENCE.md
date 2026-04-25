# Trading Engine - Quick Configuration Reference

## Paper Trading Mode Verification (2025-11-21)

### Status Summary
- **Overall Status**: ✅ PRODUCTION READY FOR PAPER TRADING
- **Last Audit**: 2025-11-21 12:27 UTC
- **Configuration Version**: 2.0 (with SQZMOM integration)

---

## Critical Settings Checklist

### Trading Safety Settings
```
TRADING_MODE=PAPER                    ✅ Simulation mode (no real money)
AUTO_TRADING_ENABLED=false            ✅ Requires manual approval
BYBIT_TESTNET=true                    ✅ Testnet API (not mainnet)
```

### Risk Management Settings
```
MAX_POSITION_SIZE_PCT=2.0             ✅ Max 2% per trade (REQUIREMENT MET)
MAX_DAILY_LOSS_PCT=5.0                ✅ Max 5% daily loss (REQUIREMENT MET)
MAX_TOTAL_EXPOSURE_PCT=20.0           ✅ Max 20% total exposure
DEFAULT_STOP_LOSS_PCT=3.0             ✅ Default 3% stop loss
DEFAULT_TAKE_PROFIT_PCT=6.0           ✅ Default 6% take profit
```

### Signal Validation Settings
```
MIN_SIGNAL_CONFIDENCE=0.6             ✅ Minimum 60% confidence required
MIN_CONSENSUS_INDICATORS=3            ✅ Requires 3+ indicators agree
```

### Paper Trading Settings
```
PAPER_INITIAL_BALANCE=100.0         ✅ $100 virtual capital
PAPER_COMMISSION_PCT=0.1              ✅ 0.1% commission simulation
```

---

## Configuration File Locations

| File | Purpose | Status |
|------|---------|--------|
| `services/trading-engine/app/config.py` | Configuration schema with validation | ✅ Active |
| `services/trading-engine/.env` | Current environment settings | ✅ Paper mode |
| `services/trading-engine/.env.example` | Template for setup | ✅ Complete |
| `services/trading-engine/.env.test` | Test database config | ✅ Prepared |
| `services/bybit-connector/.env` | Bybit API configuration | ✅ Testnet enabled |

---

## Service Port Configuration

| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| Trading Engine | 8005 | ✅ Running | Main service |
| Bybit Connector | 8002 | ✅ Configured | Testnet API |
| Technical Analysis | 8004 | ✅ Dependency | Signal generation |
| Portfolio Manager | 8006 | ✅ Dependency | Position tracking |
| PostgreSQL | 5433 | ✅ Database | Trade persistence |
| Redis | 6379 DB 2 | ✅ Cache | Signal cache |

---

## SQZMOM Strategy Configuration

| Parameter | Value | Status |
|-----------|-------|--------|
| Status | Fully Configured | ✅ |
| Symbols | SOLUSDT, DOGEUSDT, BNBUSDT | ✅ |
| Paper Trading | ENABLED | ✅ |
| Auto Trading | DISABLED | ✅ |
| Max Positions | 3 | ✅ |
| SOLUSDT Backtest | +2,706% | ✅ |
| DOGEUSDT Backtest | +630% | ✅ |
| BNBUSDT Backtest | +330% | ✅ |

---

## Database Configuration

### PostgreSQL
```
Host: localhost
Port: 5433
Database: trading_engine
User: cryptobot
Password: cryptobot_dev_password (dev only)
Purpose: Persistent storage of trades, positions, portfolios
```

### Redis
```
Host: localhost
Port: 6379
Database: 2
Password: redis_dev_password
Purpose: High-speed signal caching
```

---

## Health Check Endpoints

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/health` | GET | Quick health check | ✅ |
| `/status` | GET | Trading engine status | ✅ |
| `/health/detailed` | GET | Comprehensive metrics | ✅ |
| `/api/v1/trading/status` | GET | Auto-trading stats | ✅ |

---

## Configuration Validation

### Active Pydantic Validators
```
✅ log_level validation (INFO, DEBUG, WARNING, ERROR, CRITICAL)
✅ trading_mode validation (PAPER or LIVE)
✅ Range validation for all percentage fields:
   - max_position_size_pct: 0.1-10.0%
   - max_daily_loss_pct: 1.0-20.0%
   - max_total_exposure_pct: 5.0-100.0%
   - default_stop_loss_pct: 0.5-10.0%
   - default_take_profit_pct: 1.0-50.0%
   - min_signal_confidence: 0.0-1.0
   - min_consensus_indicators: 1-10
✅ Service port validation (1-65535)
```

---

## Startup Verification Checklist

When service starts, automatically verifies:
- ✅ Service binds to port 8005
- ✅ Trading mode logged (PAPER)
- ✅ Auto trading status logged (DISABLED)
- ✅ Database connection established
- ✅ Paper trading portfolio created ($10,000)
- ✅ Technical Analysis Service connection verified
- ✅ SQZMOM strategy configuration logged
- ✅ All dependencies health checked

---

## API Examples

### Check Trading Status
```bash
curl http://localhost:8005/status
```

Response shows:
- Current trading_mode (PAPER)
- Auto trading status
- Current balance
- Active strategy
- Open positions count

### Check Paper Trading Positions
```bash
curl http://localhost:8005/api/v1/positions
```

### Get SQZMOM Strategy Config
```bash
curl http://localhost:8005/api/v1/strategies/sqzmom/config
```

### Get Signal for a Symbol
```bash
curl http://localhost:8005/api/v1/strategies/sqzmom/signal/SOLUSDT
```

### Execute Paper Trade (Manual)
```bash
curl -X POST "http://localhost:8005/api/v1/strategies/sqzmom/trade/SOLUSDT?force=true"
```

---

## Deployment Progression

### Phase 1: Paper Trading (CURRENT)
```
Mode: PAPER
Auto Trading: DISABLED
Risk: $0 real capital
Duration: 2+ weeks
Status: ✅ READY
```

### Phase 2: Paper Trading Auto Execution
```
Mode: PAPER
Auto Trading: ENABLED (via API)
Risk: $0 real capital
Duration: 2+ weeks
Status: Available (manual enable)
```

### Phase 3: Live Trading
```
Mode: LIVE
Auto Trading: ENABLED
Risk: Real capital
Duration: Ongoing
Status: Requires explicit approval
```

---

## Transitioning to Live Trading

### Prerequisites
1. ✅ Complete 2+ weeks of paper trading
2. ✅ Validate 30+ trades with consistent profitability
3. ✅ Perform security audit of credentials
4. ✅ Review all risk management settings
5. ✅ Set up monitoring and alerting (Sentry, Slack, etc)

### Configuration Changes Required
```bash
# 1. Switch to LIVE mode
TRADING_MODE=LIVE

# 2. Switch to Bybit mainnet
BYBIT_TESTNET=false

# 3. Enable auto trading (optional)
AUTO_TRADING_ENABLED=true

# 4. Update API credentials to mainnet keys
# (Keep safely in environment variables, never in code)

# 5. Set up production database
POSTGRES_HOST=production-host
POSTGRES_PASSWORD=production-password
```

### Final Verification Before Going Live
- [ ] Confirm TRADING_MODE=LIVE
- [ ] Confirm BYBIT_TESTNET=false
- [ ] Verify mainnet API credentials are correct
- [ ] Test order placement with minimum size
- [ ] Confirm risk limits are appropriate
- [ ] Check monitoring systems are active
- [ ] Have rollback plan ready

---

## Safety Features

| Feature | Mechanism | Impact |
|---------|-----------|--------|
| Paper Mode | TRADING_MODE=PAPER | No real money risk |
| Testnet Only | BYBIT_TESTNET=true | No mainnet orders |
| Manual Approval | AUTO_TRADING_ENABLED=false | No surprise trades |
| Position Limits | MAX_POSITION_SIZE_PCT=2.0 | Controlled sizing |
| Daily Loss Halt | MAX_DAILY_LOSS_PCT=5.0 | Auto-stop at threshold |
| Signal Filtering | MIN_CONSENSUS_INDICATORS=3 | Quality validation |
| Commission Sim | PAPER_COMMISSION_PCT=0.1 | Realistic fees |
| Database Persistence | PostgreSQL storage | Complete audit trail |

---

## Troubleshooting

### Service won't start
Check that:
- Database (PostgreSQL 5433) is running
- Redis (6379) is running
- Technical Analysis service (8004) is running
- All environment variables are set in `.env`

### Paper trading not recording trades
Check that:
- Database connection is established
- PostgreSQL is accessible
- Paper trading portfolio exists (created at startup)

### Bybit connection failing
Check that:
- `BYBIT_TESTNET=true` is set (for development)
- API credentials are valid
- Network connectivity to testnet API

### Signal validation too strict
Adjust in `.env`:
- Lower `MIN_SIGNAL_CONFIDENCE` (currently 0.6)
- Lower `MIN_CONSENSUS_INDICATORS` (currently 3)

---

## Important Notes

1. **Never commit API keys** - Use environment variables only
2. **Verify testnet before mainnet** - Always start with BYBIT_TESTNET=true
3. **Monitor first trades carefully** - Watch system behavior closely
4. **Keep backups** - Database backups before live trading
5. **Test rollback procedures** - Know how to stop the system safely
6. **Review logs regularly** - Check for errors and performance issues
7. **Update documentation** - Keep configs documented as you change them

---

## References

- Full Configuration Report: `CONFIG_STATUS_REPORT.md`
- SQZMOM Strategy Guide: `SQZMOM_DEPLOYMENT_GUIDE.md`
- Service README: `README.md`
- Bybit API Setup: `../../docs/BYBIT_API_SETUP_GUIDE.md`

---

**Last Updated**: 2025-11-21 12:27 UTC
**Configuration Status**: ✅ VERIFIED READY FOR PAPER TRADING
**Safety Level**: MAXIMUM (Paper + Testnet + Manual Approval)
