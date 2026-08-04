# Scheduler Customization Guide

## Quick Reference

### Common Use Cases

#### 1. Day Trading Setup (High Frequency)
```python
# Trading Pairs: Focus on high-volume pairs
TRADING_PAIRS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

# Timeframes: Short-term focus
KLINE_INTERVALS = ["1", "3", "5", "15"]

# Frequency: Every 1 minute
_scheduler.add_job(
    collect_ticker_data,
    trigger=IntervalTrigger(minutes=1),
    ...
)
```

**Data Volume**: ~4,320 ticker records/day + ~1.7M kline records/day
**Storage**: ~200 MB/day

---

#### 2. Swing Trading Setup (Medium Frequency)
```python
# Trading Pairs: Diversified portfolio
TRADING_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT",
    "ADAUSDT", "SOLUSDT", "XRPUSDT"
]

# Timeframes: Medium-term focus
KLINE_INTERVALS = ["15", "60", "240", "D"]

# Frequency: Every 5 minutes
_scheduler.add_job(
    collect_ticker_data,
    trigger=IntervalTrigger(minutes=5),
    ...
)
```

**Data Volume**: ~1,728 ticker records/day + ~691K kline records/day
**Storage**: ~80 MB/day

---

#### 3. Position Trading Setup (Low Frequency)
```python
# Trading Pairs: All major pairs
TRADING_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT",
    "SOLUSDT", "XRPUSDT", "DOTUSDT", "AVAXUSDT"
]

# Timeframes: Long-term focus
KLINE_INTERVALS = ["240", "D", "W"]

# Frequency: Every 15 minutes
_scheduler.add_job(
    collect_ticker_data,
    trigger=IntervalTrigger(minutes=15),
    ...
)
```

**Data Volume**: ~768 ticker records/day + ~230K kline records/day
**Storage**: ~30 MB/day

---

#### 4. Minimal Setup (Testing/Development)
```python
# Trading Pairs: Single pair for testing
TRADING_PAIRS = ["BTCUSDT"]

# Timeframes: Essential only
KLINE_INTERVALS = ["60", "D"]

# Frequency: Every 30 minutes
_scheduler.add_job(
    collect_ticker_data,
    trigger=IntervalTrigger(minutes=30),
    ...
)
```

**Data Volume**: ~48 ticker records/day + ~9.6K kline records/day
**Storage**: ~2 MB/day

---

## Performance Considerations

### API Rate Limits
- Bybit allows **10 requests/second** for market data
- Each collection cycle makes: `(1 + pairs*intervals)` requests
- Example: 5 pairs × 6 intervals = 31 requests per cycle

### Database Impact
```sql
-- Check table sizes
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;

-- Monitor collection rate
SELECT
    symbol,
    interval,
    COUNT(*) as total_records,
    MAX(timestamp) as latest_timestamp,
    MIN(timestamp) as oldest_timestamp
FROM klines
GROUP BY symbol, interval;
```

### Memory Usage
- **Ticker data**: ~200 bytes per record
- **Kline data**: ~150 bytes per record
- **Recommended**: Clean old data regularly (keep last 30-90 days)

---

## Advanced Scheduling

### Cron Expression Examples

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

### Multiple Job Schedules

```python
# Peak hours: More frequent collection
_scheduler.add_job(
    collect_ticker_data,
    trigger=CronTrigger(hour='9-17', minute='*/5'),  # Every 5 min, 9AM-5PM
    id='ticker_peak_hours',
)

# Off-peak: Less frequent collection
_scheduler.add_job(
    collect_ticker_data,
    trigger=CronTrigger(hour='0-8,18-23', minute='*/15'),  # Every 15 min, off-peak
    id='ticker_off_peak',
)
```

---

## Configuration File

You can also externalize configuration to a config file:

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

---

## Monitoring Commands

```bash
# Check scheduler status
curl http://localhost:8003/api/v1/scheduler/status | python3 -m json.tool

# Verify data is being collected
psql -U cryptobot -d cryptobot -c "
SELECT
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '5 minutes') as recent,
    COUNT(*) as total,
    symbol
FROM tickers
GROUP BY symbol;
"

# Check collection logs
tail -f logs/market-data-service.log | grep "collection complete"
```

---

## Troubleshooting

### Issue: Too much data
**Solution**: Reduce frequency or number of pairs/intervals

```python
# Before: 5 pairs × 6 intervals every 5 min = 6000 records/5min
# After: 3 pairs × 4 intervals every 10 min = 2400 records/10min
TRADING_PAIRS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
KLINE_INTERVALS = ["5", "15", "60", "D"]
```

### Issue: Missing data gaps
**Solution**: Increase frequency or add backup job

```python
# Add redundant backup collection
_scheduler.add_job(
    collect_all_data,
    trigger=IntervalTrigger(minutes=30),  # Every 30 minutes as backup
    id='backup_collection',
)
```

### Issue: Rate limit errors
**Solution**: Add delay between requests

```python
# In scheduler.py:collect_kline_data()
for symbol in TRADING_PAIRS:
    for interval in KLINE_INTERVALS:
        # ... collection logic ...
        await asyncio.sleep(0.5)  # Increase from 0.5s to 1s
```

---

**Last Updated**: 2025-11-06
**Version**: 1.0.0
