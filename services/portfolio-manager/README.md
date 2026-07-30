# Portfolio Manager Service

> Merged from `QUICK_START_HISTORICAL_TRACKING.md` on 2026-07-30. Ports corrected to the current service map (portfolio-manager **8003**, market-data **8002**); older copies of this doc said 8006/8003.

## Overview

The Portfolio Manager is a comprehensive portfolio tracking and management service that provides real-time portfolio analytics, performance metrics, and rebalancing recommendations. It integrates with the Trading Engine to track all positions and maintains accurate portfolio state. The stack runs in **paper-trading mode** — balances and P&L are simulated.

## Features

### Core Capabilities
- **Portfolio Tracking**: Real-time tracking of cash balance, positions, and total portfolio value
- **Performance Analytics**: Comprehensive metrics including Sharpe ratio, Sortino ratio, max drawdown
- **Historical Tracking**: Daily performance snapshots persisted to PostgreSQL (see below)
- **Asset Management**: Individual asset tracking with P&L calculation and allocation monitoring
- **Rebalancing**: Automatic detection of allocation drift with actionable recommendations
- **Integration**: Seamless sync with Trading Engine for position updates

### Performance Metrics
- **Returns**: Total return, daily return, period-specific returns
- **Risk Metrics**: Volatility, Sharpe ratio, Sortino ratio, maximum drawdown
- **Trading Stats**: Win rate, profit factor, average win/loss
- **Benchmarking**: Alpha and beta calculations vs benchmark (future)

### Portfolio Management
- **Multi-Asset Support**: Track multiple cryptocurrencies in one portfolio
- **Cash Management**: Automatic cash balance tracking with transaction execution
- **Position Sizing**: Tracks average entry prices and calculates unrealized P&L
- **Allocation Strategies**: Support for equal-weight, market-cap, and custom allocations

## Architecture

```
┌─────────────────────────────────────────────┐
│      Portfolio Manager (Port 8003)          │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────┐  ┌──────────────┐        │
│  │   Portfolio  │  │ Performance  │        │
│  │    Manager   │  │  Calculator  │        │
│  └──────┬───────┘  └──────┬───────┘        │
│         │                  │                │
│         ▼                  ▼                │
│  ┌──────────────────────────────┐          │
│  │    Portfolio State           │          │
│  │  - Assets                    │          │
│  │  - Cash Balance              │          │
│  │  - Performance History       │          │
│  └──────────────────────────────┘          │
│                                             │
└─────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
  ┌─────────────┐    ┌─────────────┐
  │  Trading    │    │   Market    │
  │  Engine     │    │    Data     │
  │  (8005)     │    │   (8002)    │
  └─────────────┘    └─────────────┘
```

## API Endpoints

### Health & Status

#### GET /health
Health check with dependency status
```bash
curl http://localhost:8003/health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "portfolio-manager",
  "trading_engine_connection": true,
  "market_data_connection": true,
  "database_connection": true,
  "timestamp": 1730332800000
}
```

#### GET /status
Service status
```bash
curl http://localhost:8003/status
```

### Portfolio Endpoints

#### GET /api/v1/portfolio
Get portfolio details
```bash
curl "http://localhost:8003/api/v1/portfolio?portfolio_id=default"
```

**Response**:
```json
{
  "success": true,
  "portfolio": {
    "portfolio_id": "default",
    "cash_balance": "10000.0",
    "total_value": "10000.0",
    "total_pnl": "0",
    "total_return_pct": "0",
    "holdings": []
  }
}
```

#### GET /api/v1/portfolios
List all portfolios
```bash
curl http://localhost:8003/api/v1/portfolios
```

#### GET /api/v1/portfolio/balance
Get portfolio balance (cash, total value, unrealized/realized/total P&L, return %)
```bash
curl http://localhost:8003/api/v1/portfolio/balance
```

#### GET /api/v1/portfolio/holdings
Get all holdings
```bash
curl http://localhost:8003/api/v1/portfolio/holdings
```

**Response**:
```json
{
  "success": true,
  "portfolio_id": "default",
  "holdings": [
    {
      "symbol": "BTCUSDT",
      "quantity": "0.1",
      "current_price": "67000",
      "current_value": "6700",
      "unrealized_pnl": "200",
      "unrealized_pnl_pct": "3.08",
      "allocation_pct": "67.0"
    }
  ],
  "total_value": "10000.0",
  "count": 1
}
```

### Performance Endpoints

#### GET /api/v1/performance
Get performance metrics (optionally with history)
```bash
curl "http://localhost:8003/api/v1/performance?portfolio_id=default"

# With daily history and period stats
curl "http://localhost:8003/api/v1/performance?include_daily=true&include_periods=true" | jq
```

**Query Parameters**:
- `portfolio_id`: Portfolio ID (default: "default")
- `include_daily`: Include daily history (boolean)
- `include_periods`: Include period stats — week/month/year (boolean)

**Response** (metrics portion):
```json
{
  "success": true,
  "portfolio_id": "default",
  "metrics": {
    "total_return": "200.0",
    "total_return_pct": "2.0",
    "volatility": 0.15,
    "sharpe_ratio": 1.2,
    "sortino_ratio": 1.5,
    "max_drawdown": -5.2,
    "total_trades": 10,
    "win_rate": 60.0,
    "profit_factor": 1.8
  }
}
```

#### GET /api/v1/performance/assets
Get performance by asset
```bash
curl http://localhost:8003/api/v1/performance/assets
```

### Allocation Endpoints

#### GET /api/v1/allocation
Get portfolio allocation
```bash
curl http://localhost:8003/api/v1/allocation
```

#### GET /api/v1/rebalance
Get rebalancing recommendations
```bash
curl http://localhost:8003/api/v1/rebalance
```

**Response**:
```json
{
  "success": true,
  "portfolio_id": "default",
  "needs_rebalancing": true,
  "recommendations": [
    {
      "symbol": "BTCUSDT",
      "current_allocation_pct": "55.0",
      "target_allocation_pct": "50.0",
      "drift_pct": "5.0",
      "action": "SELL",
      "quantity": "0.05",
      "estimated_cost": "1.68"
    }
  ],
  "total_transactions": 1,
  "estimated_total_cost": "1.68"
}
```

### Transaction Endpoints

#### POST /api/v1/transaction/buy
Execute buy transaction (simulated — paper mode)
```bash
curl -X POST "http://localhost:8003/api/v1/transaction/buy?symbol=BTCUSDT&quantity=0.1&price=67000"
```

#### POST /api/v1/transaction/sell
Execute sell transaction (simulated — paper mode)
```bash
curl -X POST "http://localhost:8003/api/v1/transaction/sell?symbol=BTCUSDT&quantity=0.1"
```

### Integration Endpoints

#### POST /api/v1/sync
Sync with Trading Engine
```bash
curl -X POST http://localhost:8003/api/v1/sync
```

### Admin / History Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/admin/snapshot` | POST | Trigger manual performance snapshot |
| `/api/v1/admin/scheduler/status` | GET | Check snapshot scheduler |

## Historical Performance Tracking

Daily performance snapshots are persisted to PostgreSQL and served through `/api/v1/performance`.

### Setup

**1. Run database migration:**
```bash
psql -U cryptobot -d cryptobot -f infrastructure/migrations/002_performance_history.sql
```
Expected output:
```
NOTICE: Migration 002_performance_history.sql completed successfully
NOTICE: Created: portfolio.performance_history table
```

**2. Enable database:**
```bash
export USE_DATABASE=true
export DATABASE_URL="postgresql://cryptobot:cryptobot_dev_password@crypto-bot-postgres:5432/cryptobot"
```

**3. Install scheduler dependency:**
```bash
cd services/portfolio-manager
pip install apscheduler==3.10.4
```

**4. Start the service** and look for:
```
✅ Database connection pool created
✅ Performance History service initialized
✅ Performance Snapshot Scheduler started
✅ Portfolio Manager Service ready
```

**5. Verify:**
```bash
# Check scheduler status
curl http://localhost:8003/api/v1/admin/scheduler/status

# Trigger manual snapshot
curl -X POST http://localhost:8003/api/v1/admin/snapshot

# Get performance with history
curl "http://localhost:8003/api/v1/performance?include_daily=true&include_periods=true"
```

### Useful SQL

```sql
-- Recent snapshots
SELECT portfolio_id, timestamp, total_value, daily_pnl, roi_percent
FROM portfolio.performance_history
ORDER BY timestamp DESC LIMIT 10;

-- Week performance
SELECT * FROM portfolio.get_period_stats('default', 7);

-- Latest snapshot per portfolio
SELECT * FROM portfolio.latest_performance;
```

### Troubleshooting History

- **No automated snapshots at midnight**: check `curl http://localhost:8003/api/v1/admin/scheduler/status`, grep logs for "scheduler", verify DB connection via `/health`.
- **`daily_performance` / `period_performance` null**: confirm `USE_DATABASE=true`, table exists (`\dt portfolio.performance_history`), data present (`SELECT COUNT(*) FROM portfolio.performance_history;`), and request includes `?include_daily=true&include_periods=true`.
- **Database connection failed**: `docker ps | grep postgres`, `echo $DATABASE_URL`, `psql $DATABASE_URL -c "SELECT 1;"`.

### Relevant Files

```
services/portfolio-manager/
├── app/
│   ├── services/performance_history.py     # Main history service
│   ├── scheduler/performance_snapshot.py   # Daily snapshot scheduler
│   └── handlers/performance.py             # API handler
├── tests/test_performance_history.py       # 96% coverage
└── docs/PERFORMANCE_TRACKING.md            # Full documentation

infrastructure/migrations/002_performance_history.sql   # Schema
```

## Configuration

### Environment Variables

Create `.env` file:
```env
# Service Configuration
SERVICE_NAME=portfolio-manager
SERVICE_PORT=8003
LOG_LEVEL=INFO

# External Service URLs
TRADING_ENGINE_URL=http://localhost:8005
MARKET_DATA_URL=http://localhost:8002

# Portfolio Settings
INITIAL_CAPITAL=10000.0
REBALANCE_THRESHOLD_PCT=5.0
MAX_POSITIONS=10
MAX_SINGLE_ASSET_PCT=20.0

# Performance Calculation
RISK_FREE_RATE=0.02
BENCHMARK_SYMBOL=BTCUSDT

# Database (required for historical performance tracking)
DATABASE_URL=postgresql://cryptobot:cryptobot_dev_password@crypto-bot-postgres:5432/cryptobot
USE_DATABASE=true
```

## Installation

### Prerequisites
- Python 3.12+
- Trading Engine running on port 8005
- Market Data Service running on port 8002

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Start Service
```bash
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

## How It Works

### Portfolio Tracking

1. **Cash Balance**: Tracks available cash for trading
2. **Asset Holdings**: Each asset with quantity, entry price, current price
3. **P&L Calculation**: Real-time unrealized and realized P&L
4. **Performance History**: Daily snapshots (midnight) for trend analysis

### Performance Calculation

```python
sharpe_ratio  = (portfolio_return - risk_free_rate) / volatility
sortino_ratio = (portfolio_return - risk_free_rate) / downside_deviation
drawdown      = (current_value - peak_value) / peak_value
max_drawdown  = min(all_drawdowns)
```

### Rebalancing Logic

1. Calculate current allocations for all assets
2. Compare with target allocations (if set)
3. Identify assets with drift > threshold (default 5%)
4. Generate buy/sell recommendations to restore target allocation
5. Calculate estimated transaction costs

## Example Usage

### Complete Portfolio Management Flow

```bash
curl http://localhost:8003/health                       # 1. Health
curl http://localhost:8003/api/v1/portfolio             # 2. Portfolio state
curl -X POST http://localhost:8003/api/v1/sync          # 3. Sync with Trading Engine
curl http://localhost:8003/api/v1/portfolio/holdings    # 4. Holdings
curl http://localhost:8003/api/v1/performance           # 5. Performance
curl http://localhost:8003/api/v1/allocation            # 6. Allocation
curl http://localhost:8003/api/v1/rebalance             # 7. Rebalance recommendations
```

### Python Integration

```python
import httpx
import asyncio

async def manage_portfolio():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8003/api/v1/portfolio")
        portfolio = response.json()["portfolio"]

        print(f"Total Value: ${portfolio['total_value']}")
        print(f"Total P&L: ${portfolio['total_pnl']}")
        print(f"Return: {portfolio['total_return_pct']}%")

        response = await client.get("http://localhost:8003/api/v1/performance")
        metrics = response.json()["metrics"]

        print(f"Sharpe Ratio: {metrics['sharpe_ratio']}")
        print(f"Win Rate: {metrics['win_rate']}%")
        print(f"Max Drawdown: {metrics['max_drawdown']}%")

        response = await client.get("http://localhost:8003/api/v1/rebalance")
        rebalance = response.json()

        if rebalance["needs_rebalancing"]:
            print(f"Rebalancing needed: {rebalance['total_transactions']} transactions")
            for rec in rebalance["recommendations"]:
                print(f"  {rec['action']} {rec['quantity']} {rec['symbol']}")

asyncio.run(manage_portfolio())
```

## Testing

```bash
# Integration tests
cd services/portfolio-manager
bash test_integration.sh

# Unit tests
pytest tests/ -v --cov=app
```

## Monitoring

Service logs are written to `logs/service.log`:
```bash
tail -f logs/service.log
```

Key log messages: portfolio initialized, `Fetched N positions from Trading Engine` (sync), `Updated prices for N assets`, BUY/SELL transaction confirmations.

## Performance Benchmarks

(As measured 2025-11; latency, not trading performance)

- **Portfolio State Update**: <10ms
- **Performance Calculation**: <50ms (with historical data)
- **API Response Time**: <100ms (excluding external service calls)
- **Sync with Trading Engine**: ~500ms

## Future Enhancements

- [ ] Multiple portfolio support
- [ ] Custom allocation strategies
- [ ] Portfolio optimization (mean-variance, Kelly criterion)
- [ ] Risk-adjusted portfolio construction
- [ ] Tax-loss harvesting
- [ ] Performance attribution analysis
- [ ] Benchmark comparison (BTC, ETH, market indices)
- [ ] WebSocket real-time updates
- [ ] CSV export of historical snapshots

## License

Part of the Crypto Trading Bot project.

## Support

For issues or questions:
1. Check logs: `logs/service.log`
2. Verify all services are running
3. Review API documentation: http://localhost:8003/docs
4. Check service health: http://localhost:8003/health
5. Full history docs: `docs/PERFORMANCE_TRACKING.md`
