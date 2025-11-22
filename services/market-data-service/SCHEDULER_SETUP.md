# Automated Data Collection Scheduler - Setup Guide

## 📋 Overview

The scheduler automates market data collection from Bybit, eliminating the need for manual API calls. It collects:

- **Ticker data** (current prices, 24h stats) - every 5 minutes
- **Kline data** (candlesticks) for multiple timeframes - every 5 minutes
- **Trading pairs**: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT
- **Timeframes**: 1m, 5m, 15m, 1h, 4h, Daily

---

## 🚀 Installation

### Step 1: Install APScheduler

Due to PEP 668 restrictions, you need to install APScheduler using one of these methods:

**Option A: Using pip with --break-system-packages (recommended for WSL)**
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/market-data-service
pip3 install --break-system-packages apscheduler==3.10.4
```

**Option B: Using system package manager**
```bash
sudo apt install python3-apscheduler
```

**Option C: Using virtual environment (best practice)**
```bash
# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Verify Installation
```bash
python3 -c "import apscheduler; print(f'APScheduler {apscheduler.__version__} installed')"
```

Expected output: `APScheduler 3.10.4 installed`

---

## 🎯 Usage

### Enable Scheduler in main.py

The scheduler has already been integrated into the main application. To activate it:

1. **Automatic Start** (on service startup):
   - The scheduler starts automatically when the service starts
   - Configured in `app/main.py` lifespan function

2. **Manual Control via API**:

   **Check scheduler status**:
   ```bash
   curl http://localhost:8003/api/v1/scheduler/status
   ```

   **Start scheduler**:
   ```bash
   curl -X POST http://localhost:8003/api/v1/scheduler/start
   ```

   **Stop scheduler**:
   ```bash
   curl -X POST http://localhost:8003/api/v1/scheduler/stop
   ```

   **Trigger manual collection**:
   ```bash
   curl -X POST http://localhost:8003/api/v1/scheduler/collect
   ```

---

## 📊 Collection Schedule

| Job | Frequency | Description |
|-----|-----------|-------------|
| Ticker Collection | Every 5 minutes | Current prices, 24h stats for all pairs |
| Kline Collection | Every 5 minutes (+2min offset) | Candlestick data for all pairs & timeframes |
| Full Collection | Every hour (top of hour) | Comprehensive backup collection |

---

## 🔍 Monitoring

### Check Logs

The scheduler logs all collection activities:

```bash
# Watch live logs
tail -f /path/to/logs/market-data-service.log

# Or check service output
docker logs -f market-data-service
```

**Expected log messages**:
```
🚀 Initializing data collection scheduler
✅ Scheduled: Ticker collection every 5 minutes
✅ Scheduled: Kline collection every 5 minutes
🎯 Scheduler started successfully
📊 Starting scheduled ticker data collection
✅ Collected ticker for BTCUSDT
📊 Ticker collection complete: 5 success, 0 errors
```

### Database Verification

Check that data is being collected:

```bash
# Connect to database
psql -h localhost -p 5432 -U cryptobot -d cryptobot

# Check ticker data
SELECT COUNT(*), symbol, MAX(timestamp) as latest
FROM tickers
GROUP BY symbol
ORDER BY symbol;

# Check kline data
SELECT symbol, interval, COUNT(*) as count, MAX(timestamp) as latest
FROM klines
GROUP BY symbol, interval
ORDER BY symbol, interval;
```

---

## ⚙️ Configuration

### Customize Trading Pairs

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
```

### Customize Collection Intervals

Edit `app/scheduler.py`:

```python
KLINE_INTERVALS = [
    "1",    # 1 minute
    "5",    # 5 minutes
    "15",   # 15 minutes
    "60",   # 1 hour
    "240",  # 4 hours
    "D",    # Daily
]
```

### Adjust Collection Frequency

Edit the IntervalTrigger in `start_scheduler()`:

```python
# Change from 5 minutes to 10 minutes
_scheduler.add_job(
    collect_ticker_data,
    trigger=IntervalTrigger(minutes=10),  # Changed from 5
    ...
)
```

---

## 🧪 Testing

### Test Manual Collection

Before enabling the scheduler, test manual collection:

```bash
# Test ticker collection
curl -X POST -H "X-API-Key: test-key-123" \
  "http://localhost:8003/api/v1/collect/ticker/BTCUSDT"

# Test kline collection
curl -X POST -H "X-API-Key: test-key-123" \
  "http://localhost:8003/api/v1/collect/kline/BTCUSDT?interval=5&limit=100"

# Verify data in database
psql -U cryptobot -d cryptobot -c "SELECT * FROM tickers ORDER BY timestamp DESC LIMIT 5;"
```

### Test Scheduler

```bash
# Start the service
python3 -m uvicorn app.main:app --port 8003

# Check scheduler status
curl http://localhost:8003/api/v1/scheduler/status

# Expected response:
{
  "running": true,
  "job_count": 3,
  "jobs": [
    {
      "id": "ticker_collection",
      "name": "Ticker Data Collection",
      "next_run": "2025-11-06 10:50:00",
      "trigger": "interval[0:05:00]"
    },
    ...
  ]
}
```

---

## 🐛 Troubleshooting

### Issue: Scheduler not starting

**Symptoms**: No scheduled jobs running, no collection logs

**Solutions**:
1. Check APScheduler is installed:
   ```bash
   python3 -c "import apscheduler"
   ```

2. Check service logs for errors:
   ```bash
   tail -100 /var/log/market-data-service/app.log
   ```

3. Verify Bybit Connector is healthy:
   ```bash
   curl http://localhost:8002/health
   ```

---

### Issue: Collections failing

**Symptoms**: Error logs, empty database

**Solutions**:
1. Check Bybit Connector is running:
   ```bash
   curl http://localhost:8002/api/v1/market/ticker?category=linear&symbol=BTCUSDT
   ```

2. Check database connection:
   ```bash
   psql -h localhost -p 5432 -U cryptobot -d cryptobot -c "SELECT 1;"
   ```

3. Check API rate limits (Bybit limits: 10 req/s for market data)

---

### Issue: Duplicate data or missing data

**Solutions**:
1. Check for multiple service instances:
   ```bash
   ps aux | grep uvicorn
   ```

2. Verify unique constraints in database:
   ```sql
   SELECT * FROM pg_indexes WHERE tablename IN ('tickers', 'klines');
   ```

3. Check scheduler job execution:
   ```bash
   curl http://localhost:8003/api/v1/scheduler/status
   ```

---

## 📈 Performance Considerations

### Data Volume Estimates

- **Tickers**: 5 pairs × 12 collections/hour = 60 rows/hour = 1,440 rows/day
- **Klines**: 5 pairs × 6 intervals × 200 candles = 6,000 rows per collection
- **Storage**: ~10-20 MB per day for full collection

### Database Maintenance

Run regular maintenance:

```sql
-- Analyze tables for query optimization
ANALYZE tickers;
ANALYZE klines;

-- Vacuum to reclaim space
VACUUM ANALYZE tickers;
VACUUM ANALYZE klines;

-- Check table sizes
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;
```

---

## 🎉 Success Criteria

Your scheduler is working correctly when you see:

1. ✅ Scheduler status shows 3 running jobs
2. ✅ Database shows increasing row counts for tickers and klines
3. ✅ Logs show successful collections every 5 minutes
4. ✅ No error messages in service logs
5. ✅ Latest timestamps in database are recent (< 5 minutes old)

---

## 🔄 Next Steps

Once the scheduler is running:

1. **Monitor for 24 hours** - Ensure stability
2. **Add more trading pairs** - Expand coverage
3. **Implement Technical Analysis Service** - Use collected data
4. **Set up alerts** - Notify on collection failures
5. **Create dashboards** - Visualize data collection metrics

---

**Created**: 2025-11-06
**Version**: 1.0.0
**Status**: Ready for production
