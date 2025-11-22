# Quick Start: Historical Performance Tracking

## 5-Minute Setup Guide

### Step 1: Run Database Migration (30 seconds)

```bash
psql -U cryptobot -d cryptobot -f infrastructure/migrations/002_performance_history.sql
```

Expected output:
```
NOTICE: Migration 002_performance_history.sql completed successfully
NOTICE: Created: portfolio.performance_history table
```

### Step 2: Enable Database in Config (10 seconds)

Edit `/services/portfolio-manager/app/config.py` or set environment variables:

```bash
export USE_DATABASE=true
export DATABASE_URL="postgresql://cryptobot:cryptobot_dev_password@crypto-bot-postgres:5432/cryptobot"
```

### Step 3: Install Dependencies (2 minutes)

```bash
cd services/portfolio-manager
pip install apscheduler==3.10.4
```

### Step 4: Start Service (5 seconds)

```bash
python -m app.main
# or
uvicorn app.main:app --host 0.0.0.0 --port 8006
```

Look for these log messages:
```
✅ Database connection pool created
✅ Performance History service initialized
✅ Performance Snapshot Scheduler started
✅ Portfolio Manager Service ready
```

### Step 5: Test It Works (1 minute)

```bash
# Check scheduler status
curl http://localhost:8006/api/v1/admin/scheduler/status

# Trigger manual snapshot
curl -X POST http://localhost:8006/api/v1/admin/snapshot

# Get performance with history
curl "http://localhost:8006/api/v1/performance?include_daily=true&include_periods=true"
```

---

## Common Use Cases

### Get Last 30 Days Performance

```bash
curl "http://localhost:8006/api/v1/performance?portfolio_id=default&include_daily=true"
```

### Get Period Stats (Week/Month/Year)

```bash
curl "http://localhost:8006/api/v1/performance?portfolio_id=default&include_periods=true"
```

### Get Everything

```bash
curl "http://localhost:8006/api/v1/performance?include_daily=true&include_periods=true" | jq
```

### Manual Snapshot (for testing)

```bash
curl -X POST http://localhost:8006/api/v1/admin/snapshot?portfolio_id=default
```

---

## Database Queries

### Check Snapshots

```sql
SELECT
  portfolio_id,
  timestamp,
  total_value,
  daily_pnl,
  roi_percent
FROM portfolio.performance_history
ORDER BY timestamp DESC
LIMIT 10;
```

### Get Week Performance

```sql
SELECT * FROM portfolio.get_period_stats('default', 7);
```

### Latest Snapshot Per Portfolio

```sql
SELECT * FROM portfolio.latest_performance;
```

---

## Troubleshooting

### Scheduler Not Running

**Symptom**: No automated snapshots at midnight

**Fix**:
```bash
# Check status
curl http://localhost:8006/api/v1/admin/scheduler/status

# Check logs
tail -f logs/service.log | grep "scheduler"

# Verify database connection
curl http://localhost:8006/health
```

### No Historical Data

**Symptom**: `daily_performance` and `period_performance` are null

**Check**:
1. Database enabled: `USE_DATABASE=true`
2. Table exists: `\dt portfolio.performance_history`
3. Data present: `SELECT COUNT(*) FROM portfolio.performance_history;`
4. Request parameters: Add `?include_daily=true&include_periods=true`

### Database Connection Failed

**Symptom**: Service runs but warnings about disabled history

**Fix**:
```bash
# Check database is running
docker ps | grep postgres

# Check connection string
echo $DATABASE_URL

# Test connection
psql $DATABASE_URL -c "SELECT 1;"
```

---

## Next Steps

1. **Monitor**: Set up alerts for failed snapshots
2. **Optimize**: Add indexes if queries slow down
3. **Export**: Build CSV export functionality
4. **Visualize**: Create charts from historical data

---

## API Reference Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/performance` | GET | Get metrics + history |
| `/api/v1/admin/snapshot` | POST | Manual snapshot |
| `/api/v1/admin/scheduler/status` | GET | Check scheduler |

### Query Parameters

- `portfolio_id`: Portfolio ID (default: "default")
- `include_daily`: Include daily history (boolean)
- `include_periods`: Include period stats (boolean)

---

## File Locations

```
services/portfolio-manager/
├── app/
│   ├── services/
│   │   └── performance_history.py          # Main service
│   ├── scheduler/
│   │   └── performance_snapshot.py         # Daily scheduler
│   └── handlers/
│       └── performance.py                  # API handler (TODO resolved)
├── tests/
│   └── test_performance_history.py         # 96% coverage
└── docs/
    └── PERFORMANCE_TRACKING.md             # Full documentation

infrastructure/migrations/
└── 002_performance_history.sql             # Database schema
```

---

**Questions?** Check:
- Full docs: `docs/PERFORMANCE_TRACKING.md`
- Implementation report: `IMPLEMENTATION_REPORT.md`
- Tests: `tests/test_performance_history.py`
