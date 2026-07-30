# Automated Data Collection Scheduler - Setup Guide

> Merged from `SCHEDULER_CUSTOMIZATION_GUIDE.md` on 2026-07-30.

## Overview

The scheduler automates market data collection from Bybit, eliminating the need for manual API calls. It collects:

- **Ticker data** (current prices, 24h stats) - every 5 minutes
- **Kline data** (candlesticks) for multiple timeframes - every 5 minutes
- **Trading pairs**: configured in `app/scheduler.py` (examples below use BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT)
- **Timeframes**: 1m, 5m, 15m, 1h, 4h, Daily

> Note (2026-07-30): market-data-service deliberately ingests a **wider symbol universe** than the trading-engine trades (research + cross-asset lookback). Position-taking is restricted to the 5 validated symbols BTC, ETH, SOL, BNB, ADA (as of 2026-05-03); XRP/DOGE are ingest-only.

Service runs on **port 8002** (see `docker-compose.unified.yml`, the canonical compose file).

## Installation

### Step 1: Install APScheduler

Due to PEP 668 restrictions, install APScheduler using one of these methods:

**Option A: pip with --break-system-packages (WSL)**
```bash
cd services/market-data-service
pip3 install --break-system-packages apscheduler==3.10.4
```

**Option B: System package manager**
```bash
sudo apt install python3-apscheduler
```

**Option C: Virtual environment (best practice)**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Verify Installation
```bash
python3 -c "import apscheduler; print(f'APScheduler {apscheduler.__version__} installed')"
```

Expected output: `APScheduler 3.10.4 installed`

## Usage

The scheduler is integrated into `app/main.py` (lifespan function) and starts automatically with the service.

**Manual control via API** (service port 8002):

```bash
# Check scheduler status
curl http://localhost:8002/api/v1/scheduler/status

# Start scheduler
curl -X POST http://localhost:8002/api/v1/scheduler/start

# Stop scheduler
curl -X POST http://localhost:8002/api/v1/scheduler/stop

# Trigger manual collection
curl -X POST http://localhost:8002/api/v1/scheduler/collect
```

Scheduler-control and collection endpoints require the `X-API-Key` header (see README).

## Collection Schedule

| Job | Frequency | Description |
|-----|-----------|-------------|
| Ticker Collection | Every 5 minutes | Current prices, 24h stats for all pairs |
| Kline Collection | Every 5 minutes (+2min offset) | Candlestick data for all pairs & timeframes |
| Full Collection | Every hour (top of hour) | Comprehensive backup collection |

## Configuration

### Trading Pairs and Intervals

Edit `app/scheduler.py`:

```python
TRADING_PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    # Add more pairs here
]

KLINE_INTERVALS = [
    "1",    # 1 minute
    "5",    # 5 minutes
    "15",   # 15 minutes
    "60",   # 1 hour
    "240",  # 4 hours
    "D",    # Daily
]
```

### Collection Frequency

Edit the IntervalTrigger in `start_scheduler()`:

```python
# Change from 5 minutes to 10 minutes
_scheduler.add_job(
    collect_ticker_data,
    trigger=IntervalTrigger(minutes=10),  # Changed from 5
    ...
)
```

### Preset Profiles by Trading Style

| Profile | Pairs | Intervals | Frequency | Approx. volume |
|---------|-------|-----------|-----------|----------------|
| **Day trading** (high freq) | BTCUSDT, ETHUSDT, BNBUSDT | `1, 3, 5, 15` | every 1 min | ~4,320 ticker + ~1.7M kline rows/day, ~200 MB/day |
| **Swing trading** (medium) | 6 majors (add ADA, SOL, XRP) | `15, 60, 240, D` | every 5 min | ~1,728 ticker + ~691K kline rows/day, ~80 MB/day |
| **Position trading** (low) | 8 majors (add DOT, AVAX) | `240, D, W` | every 15 min | ~768 ticker + ~230K kline rows/day, ~30 MB/day |
| **Minimal** (testing/dev) | BTCUSDT | `60, D` | every 30 min | ~48 ticker + ~9.6K kline rows/day, ~2 MB/day |

### Advanced Scheduling (cron triggers)

```python
# Every weekday at 9 AM
trigger=CronTrigger(day_of_week='mon-fri', hour=9, minute=0)

# Every Monday and Friday at 5 PM
trigger=CronTrigger(day_of_week='mon,fri', hour=17, minute=0)

# First day of every month at midnight
trigger=CronTrigger(day=1, hour=0, minute=0)

# Every 4 hours during trading hours (9 AM - 5 PM)
trigger=CronTrigger(hour='9,13,17', minute=0)
```

Peak/off-peak split with multiple jobs:

```python
# Peak hours: more frequent collection
_scheduler.add_job(
    collect_ticker_data,
    trigger=CronTrigger(hour='9-17', minute='*/5'),  # Every 5 min, 9AM-5PM
    id='ticker_peak_hours',
)

# Off-peak: less frequent collection
_scheduler.add_job(
    collect_ticker_data,
    trigger=CronTrigger(hour='0-8,18-23', minute='*/15'),  # Every 15 min, off-peak
    id='ticker_off_peak',
)
```

### Externalized Configuration

```python
# config.py
SCHEDULER_CONFIG = {
    "trading_pairs": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
    "kline_intervals": ["1", "5", "15", "60"],
    "ticker_frequency_minutes": 5,
    "kline_frequency_minutes": 5,
    "hourly_backup": True
}

# scheduler.py
from app.config import SCHEDULER_CONFIG

TRADING_PAIRS = SCHEDULER_CONFIG["trading_pairs"]
KLINE_INTERVALS = SCHEDULER_CONFIG["kline_intervals"]

_scheduler.add_job(
    collect_ticker_data,
    trigger=IntervalTrigger(minutes=SCHEDULER_CONFIG["ticker_frequency_minutes"]),
    ...
)
```

## Monitoring

### Logs

```bash
# Watch live logs
tail -f /path/to/logs/market-data-service.log

# Or via docker
docker compose -f docker-compose.unified.yml logs -f market-data-service

# Only collection completions
tail -f logs/market-data-service.log | grep "collection complete"
```

Expected log messages: scheduler init, per-job scheduling confirmations, `Ticker collection complete: 5 success, 0 errors`, etc.

### Scheduler Status

```bash
curl http://localhost:8002/api/v1/scheduler/status | python3 -m json.tool
```

Expected response shape:
```json
{
  "running": true,
  "job_count": 3,
  "jobs": [
    {
      "id": "ticker_collection",
      "name": "Ticker Data Collection",
      "next_run": "...",
      "trigger": "interval[0:05:00]"
    }
  ]
}
```

### Database Verification

```bash
psql -h localhost -p 5432 -U cryptobot -d cryptobot
```

```sql
-- Ticker data per symbol
SELECT COUNT(*), symbol, MAX(timestamp) as latest
FROM tickers GROUP BY symbol ORDER BY symbol;

-- Kline data per symbol/interval
SELECT symbol, interval, COUNT(*) as count, MAX(timestamp) as latest
FROM klines GROUP BY symbol, interval ORDER BY symbol, interval;

-- Rows collected in the last 5 minutes
SELECT COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '5 minutes') as recent,
       COUNT(*) as total, symbol
FROM tickers GROUP BY symbol;
```

## Testing

### Manual Collection

```bash
# Test ticker collection
curl -X POST -H "X-API-Key: test-key-123" \
  "http://localhost:8002/api/v1/collect/ticker/BTCUSDT"

# Test kline collection
curl -X POST -H "X-API-Key: test-key-123" \
  "http://localhost:8002/api/v1/collect/kline/BTCUSDT?interval=5&limit=100"

# Verify data in database
psql -U cryptobot -d cryptobot -c "SELECT * FROM tickers ORDER BY timestamp DESC LIMIT 5;"
```

### Scheduler

```bash
# Start the service
python3 -m uvicorn app.main:app --port 8002

# Check scheduler status
curl http://localhost:8002/api/v1/scheduler/status
```

## Performance Considerations

### API Rate Limits
- Bybit allows **10 requests/second** for market data
- Each collection cycle makes `(1 + pairs × intervals)` requests (e.g. 5 pairs × 6 intervals = 31 requests/cycle)
- On rate-limit errors, increase the inter-request delay in `scheduler.py:collect_kline_data()`:
  ```python
  await asyncio.sleep(0.5)  # increase e.g. to 1.0
  ```

### Data Volume & Storage
- Tickers: ~200 bytes/record; klines: ~150 bytes/record
- Default profile: ~1,440 ticker rows/day, ~6,000 kline rows per collection, ~10-20 MB/day
- Recommended: clean old data regularly (keep last 30-90 days)

### Database Maintenance

```sql
ANALYZE tickers;
ANALYZE klines;
VACUUM ANALYZE tickers;
VACUUM ANALYZE klines;

-- Check table sizes
SELECT tablename,
       pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;
```

## Troubleshooting

### Scheduler not starting
**Symptoms**: no scheduled jobs running, no collection logs
1. Check APScheduler is installed: `python3 -c "import apscheduler"`
2. Check service logs for errors
3. Verify Bybit Connector is healthy: `curl http://localhost:8001/health`

### Collections failing
**Symptoms**: error logs, empty database
1. Check Bybit Connector: `curl "http://localhost:8001/api/v1/market/ticker?category=linear&symbol=BTCUSDT"`
2. Check database connection: `psql -h localhost -p 5432 -U cryptobot -d cryptobot -c "SELECT 1;"`
3. Check Bybit rate limits (10 req/s for market data)

### Duplicate or missing data
1. Check for multiple service instances: `ps aux | grep uvicorn`
2. Verify unique constraints: `SELECT * FROM pg_indexes WHERE tablename IN ('tickers', 'klines');`
3. Check job execution: `curl http://localhost:8002/api/v1/scheduler/status`

### Too much data
Reduce frequency or number of pairs/intervals (e.g. 3 pairs × 4 intervals every 10 min instead of 5 × 6 every 5 min).

### Data gaps
Add a redundant backup collection job:
```python
_scheduler.add_job(
    collect_all_data,
    trigger=IntervalTrigger(minutes=30),
    id='backup_collection',
)
```

## Health Checklist

The scheduler is working correctly when:

1. Scheduler status shows 3 running jobs
2. Database shows increasing row counts for tickers and klines
3. Logs show successful collections every 5 minutes
4. No error messages in service logs
5. Latest timestamps in database are < 5 minutes old
