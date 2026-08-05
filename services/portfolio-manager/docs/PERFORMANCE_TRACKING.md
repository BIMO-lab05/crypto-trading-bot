# Historical Performance Tracking

## Overview

The Portfolio Manager service now includes comprehensive historical performance tracking capabilities. This feature enables:

- **Daily Performance Snapshots**: Automated capture of portfolio metrics every day at midnight UTC
- **Historical Data Retrieval**: Query past performance for trend analysis
- **Period-Based Analysis**: Calculate performance over specific time periods (week, month, year, all-time)
- **Persistent Storage**: All historical data stored in PostgreSQL for reliability

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Portfolio Manager                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────┐  │
│  │  Performance │───▶│  Performance     │───▶│ Database │  │
│  │  Handler     │    │  History Service │    │ Pool     │  │
│  └──────────────┘    └──────────────────┘    └──────────┘  │
│                              │                               │
│                              ▼                               │
│                      ┌──────────────────┐                    │
│                      │   Scheduler      │                    │
│                      │  (Daily 00:00)   │                    │
│                      └──────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────────┐
                    │ PostgreSQL Database  │
                    │                      │
                    │ portfolio.           │
                    │ performance_history  │
                    └──────────────────────┘
```

### Database Schema

```sql
CREATE TABLE portfolio.performance_history (
    id SERIAL PRIMARY KEY,
    portfolio_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Portfolio values
    total_value DECIMAL(30, 8) NOT NULL,
    cash_balance DECIMAL(30, 8) NOT NULL,
    positions_value DECIMAL(30, 8) NOT NULL,

    -- P&L metrics
    realized_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    unrealized_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    total_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    daily_pnl DECIMAL(30, 8),

    -- Return metrics
    roi_percent DECIMAL(10, 4),
    daily_return_percent DECIMAL(10, 4),

    -- Risk metrics
    sharpe_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),
    volatility DECIMAL(10, 4),

    -- Trading statistics
    win_rate DECIMAL(10, 4),
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,

    snapshot_type VARCHAR(20) DEFAULT 'DAILY',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(portfolio_id, date_trunc('day', timestamp))
);
```

## API Usage

### Get Performance with Historical Data

**Endpoint**: `GET /api/v1/performance`

**Query Parameters**:
- `portfolio_id` (string): Portfolio identifier (default: "default")
- `include_daily` (boolean): Include daily performance history
- `include_periods` (boolean): Include period performance statistics

**Example Request**:
```bash
curl "http://localhost:8006/api/v1/performance?portfolio_id=default&include_daily=true&include_periods=true"
```

**Example Response**:
```json
{
  "success": true,
  "portfolio_id": "default",
  "metrics": {
    "total_return": "5.00",
    "total_return_pct": "5.00",
    "sharpe_ratio": 1.5,
    "win_rate": 60.0,
    "total_trades": 10
  },
  "daily_performance": [
    {
      "date": "2025-11-18",
      "portfolio_value": "100.00",
      "daily_pnl": "1.00",
      "daily_return_pct": "1.00",
      "cumulative_return_pct": "0.00",
      "trades_count": 2
    },
    {
      "date": "2025-11-19",
      "portfolio_value": "102.00",
      "daily_pnl": "2.00",
      "daily_return_pct": "2.00",
      "cumulative_return_pct": "2.00",
      "trades_count": 3
    }
  ],
  "period_performance": {
    "week": {
      "period": "week",
      "start_date": "2025-11-13",
      "end_date": "2025-11-20",
      "start_value": "100.00",
      "end_value": "105.00",
      "total_return": "5.00",
      "total_return_pct": "5.00",
      "volatility": 0.15,
      "trades_count": 15
    },
    "month": {
      "period": "month",
      "start_date": "2025-10-20",
      "end_date": "2025-11-20",
      "start_value": "95.00",
      "end_value": "105.00",
      "total_return": "10.00",
      "total_return_pct": "10.53",
      "volatility": 0.18,
      "trades_count": 45
    }
  }
}
```

### Manual Snapshot Trigger

For testing or immediate snapshots outside the regular schedule:

**Endpoint**: `POST /api/v1/admin/snapshot`

**Example Request**:
```bash
curl -X POST "http://localhost:8006/api/v1/admin/snapshot?portfolio_id=default"
```

**Example Response**:
```json
{
  "success": true,
  "result": {
    "timestamp": "2025-11-20T10:30:00Z",
    "snapshot_type": "MANUAL",
    "portfolios_processed": 1,
    "portfolios_failed": 0,
    "duration_seconds": 0.15
  }
}
```

### Scheduler Status

Check the automated snapshot scheduler status:

**Endpoint**: `GET /api/v1/admin/scheduler/status`

**Example Response**:
```json
{
  "enabled": true,
  "is_running": true,
  "snapshot_time": "00:00 UTC",
  "next_run_time": "2025-11-21T00:00:00+00:00",
  "jobs_count": 1
}
```

## Configuration

### Database Setup

1. **Run Migration**:
```bash
psql -U cryptobot -d cryptobot -f infrastructure/migrations/002_performance_history.sql
```

2. **Enable Database in Configuration**:
```python
# services/portfolio-manager/app/config.py
use_database = True
database_url = "postgresql://cryptobot:password@localhost:5432/cryptobot"
```

### Scheduler Configuration

The scheduler runs daily at midnight UTC by default. To customize:

```python
# In main.py
snapshot_scheduler = PerformanceSnapshotScheduler(
    portfolio_manager=portfolio_manager,
    performance_history=performance_history,
    snapshot_hour=0,   # Hour (0-23)
    snapshot_minute=0  # Minute (0-59)
)
```

## Performance Considerations

### Query Optimization

The database schema includes optimized indexes:

```sql
-- Primary index for portfolio-time queries
CREATE INDEX idx_performance_portfolio_time
ON portfolio.performance_history(portfolio_id, timestamp DESC);

-- Index for period range queries
CREATE INDEX idx_performance_portfolio_date_range
ON portfolio.performance_history(portfolio_id, timestamp)
WHERE snapshot_type = 'DAILY';
```

### Performance Benchmarks

- **Snapshot Insert**: < 10ms
- **Daily Performance Query (30 days)**: < 50ms
- **Period Calculation (1 year)**: < 100ms

### Data Retention

By default, all historical data is retained. For automatic cleanup:

```sql
-- Archive snapshots older than 2 years
SELECT portfolio.archive_old_performance();
```

## Error Handling

The system is designed to be resilient:

1. **Database Unavailable**: Service runs without historical tracking
2. **Snapshot Failure**: Logged but doesn't disrupt service
3. **Query Errors**: Returns empty historical data rather than failing

## Testing

### Unit Tests

```bash
# Run performance history tests
pytest tests/test_performance_history.py -v --cov

# Expected coverage: >90%
```

### Integration Testing

```bash
# Test manual snapshot
curl -X POST http://localhost:8006/api/v1/admin/snapshot

# Verify data stored
psql -U cryptobot -d cryptobot -c \
  "SELECT * FROM portfolio.performance_history ORDER BY timestamp DESC LIMIT 5;"

# Test retrieval
curl "http://localhost:8006/api/v1/performance?include_daily=true&include_periods=true"
```

## Monitoring

### Key Metrics to Monitor

1. **Snapshot Success Rate**: Should be 100%
2. **Snapshot Duration**: Should be < 1 second
3. **Query Performance**: p95 < 100ms
4. **Database Growth**: ~1KB per portfolio per day

### Logging

All operations are logged with appropriate levels:

```
INFO: Performance snapshot saved for default: value=10500.00, pnl=500.00
WARNING: No performance data found for test_portfolio in period week
ERROR: Failed to save performance snapshot for default: connection timeout
```

## Troubleshooting

### Snapshots Not Being Created

1. Check scheduler status:
   ```bash
   curl http://localhost:8006/api/v1/admin/scheduler/status
   ```

2. Check database connectivity:
   ```bash
   psql -U cryptobot -d cryptobot -c "SELECT 1;"
   ```

3. Review logs:
   ```bash
   tail -f logs/service.log | grep "snapshot"
   ```

### Missing Historical Data

1. Verify database table exists:
   ```sql
   SELECT EXISTS (
     SELECT FROM information_schema.tables
     WHERE table_schema = 'portfolio'
     AND table_name = 'performance_history'
   );
   ```

2. Check data:
   ```sql
   SELECT COUNT(*) FROM portfolio.performance_history
   WHERE portfolio_id = 'default';
   ```

### Performance Issues

1. Check index usage:
   ```sql
   EXPLAIN ANALYZE
   SELECT * FROM portfolio.performance_history
   WHERE portfolio_id = 'default'
   ORDER BY timestamp DESC LIMIT 30;
   ```

2. Vacuum table if needed:
   ```sql
   VACUUM ANALYZE portfolio.performance_history;
   ```

## Future Enhancements

Potential improvements for future versions:

1. **Real-time Snapshots**: WebSocket updates for intraday tracking
2. **Advanced Metrics**: More sophisticated risk metrics (VaR, CVaR, Calmar ratio)
3. **Comparison Tools**: Compare multiple portfolios or against benchmarks
4. **Export Functionality**: Export historical data to CSV/Excel
5. **Visualization**: Built-in charting endpoints
6. **Alerts**: Notify on performance thresholds

## References

- [PostgreSQL AsyncPG Documentation](https://magicstack.github.io/asyncpg/)
- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)

## Support

For issues or questions:
- Check logs: `logs/service.log`
- Review test suite: `tests/test_performance_history.py`
- Inspect database: PostgreSQL on port 5432
