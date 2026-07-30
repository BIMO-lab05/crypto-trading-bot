# Alert Runbooks - Crypto Trading Bot

**Version:** 1.0
**Last Updated:** 2025-11-21
**Purpose:** Operational runbooks for investigating and resolving alerts

---

## Table of Contents

1. [Critical Alerts](#critical-alerts)
2. [Warning Alerts](#warning-alerts)
3. [Info Alerts](#info-alerts)
4. [Common Investigation Steps](#common-investigation-steps)
5. [Escalation Procedures](#escalation-procedures)

---

## Critical Alerts

### TradingEngineDown

**Severity:** Critical
**Impact:** No trades can be executed
**SLA:** Resolve within 15 minutes

#### Investigation Steps

1. **Check service status**
   ```bash
   docker ps | grep crypto-bot-trading
   docker logs --tail 100 crypto-bot-trading
   ```

2. **Check if container exited**
   ```bash
   docker ps -a | grep crypto-bot-trading
   docker inspect crypto-bot-trading | grep -A 10 "State"
   ```

3. **Check recent errors**
   ```bash
   docker logs crypto-bot-trading 2>&1 | grep -i error | tail -20
   ```

4. **Verify database connectivity**
   ```bash
   docker exec crypto-bot-trading ping -c 3 postgres
   curl http://localhost:5432  # Should respond or refuse connection
   ```

5. **Check Bybit API status**
   ```bash
   curl -s https://api.bybit.com/v5/market/time
   ```

#### Resolution Steps

1. **Restart the service**
   ```bash
   docker restart crypto-bot-trading

   # Verify it's running
   sleep 5
   docker ps | grep crypto-bot-trading
   curl http://localhost:8001/health
   ```

2. **If restart fails, check configuration**
   ```bash
   docker exec crypto-bot-trading env | grep -E "(DATABASE|BYBIT|API)"
   ```

3. **If still failing, check resource limits**
   ```bash
   docker stats crypto-bot-trading --no-stream
   ```

4. **Last resort: Rebuild and restart**
   ```bash
   cd /path/to/crypto-trading-bot
   docker-compose down trading-engine
   docker-compose up -d trading-engine
   ```

#### Post-Resolution

- Monitor service for 10 minutes
- Check Grafana dashboard for metrics recovery
- Review logs for root cause
- Document in incident log

#### Dashboard

- [Trading Performance Dashboard](http://localhost:3000/d/trading-performance)

---

### DailyLossExceeded

**Severity:** Critical
**Impact:** Portfolio losing money rapidly
**SLA:** Investigate within 5 minutes

#### Investigation Steps

1. **Check current portfolio status**
   ```bash
   curl http://localhost:8004/api/v1/portfolio/summary
   ```

2. **Review recent trades**
   ```bash
   curl http://localhost:8001/api/v1/trades/recent?limit=20
   ```

3. **Check market conditions**
   - Visit Bybit to check if market is extremely volatile
   - Check recent news for significant events
   - Verify trading pair prices

4. **Review trading signals**
   ```bash
   curl http://localhost:8003/api/v1/signals/recent
   ```

5. **Check if strategy is malfunctioning**
   ```bash
   docker logs crypto-bot-trading | grep -i "strategy\|signal" | tail -50
   ```

#### Resolution Steps

1. **Immediate: Consider emergency stop**
   ```bash
   # Pause trading
   curl -X POST http://localhost:8001/api/v1/trading/pause \
     -H "Content-Type: application/json" \
     -d '{"reason": "Emergency stop - daily loss exceeded"}'
   ```

2. **Close losing positions (if appropriate)**
   ```bash
   # Review open positions
   curl http://localhost:8004/api/v1/positions

   # Close specific position
   curl -X POST http://localhost:8004/api/v1/positions/{position_id}/close
   ```

3. **Analyze root cause**
   - Review trading strategy parameters
   - Check if stop-losses are working
   - Verify risk management rules

4. **Adjust strategy if needed**
   ```bash
   # Reduce position sizes
   # Tighten stop-losses
   # Adjust entry criteria
   ```

#### Post-Resolution

- Document what went wrong
- Update strategy parameters
- Consider backtesting with recent market conditions
- Monitor closely for next 24 hours

#### Dashboard

- [Trading Performance Dashboard](http://localhost:3000/d/trading-performance)
- [Risk Metrics Dashboard](http://localhost:3000/d/risk-metrics)

---

### ServiceDown

**Severity:** Critical
**Impact:** Specific service unavailable
**SLA:** Resolve within 10 minutes

#### Investigation Steps

1. **Identify which service is down**
   ```bash
   docker ps -a | grep crypto-bot
   ```

2. **Check service logs**
   ```bash
   docker logs --tail 100 crypto-bot-{service-name}
   ```

3. **Check resource usage**
   ```bash
   docker stats --no-stream | grep crypto-bot
   ```

4. **Check for OOM kills**
   ```bash
   dmesg | grep -i "killed process"
   docker inspect crypto-bot-{service-name} | grep OOMKilled
   ```

#### Resolution Steps

1. **Restart the service**
   ```bash
   docker restart crypto-bot-{service-name}
   ```

2. **If using docker-compose**
   ```bash
   docker-compose restart {service-name}
   ```

3. **Check if service is healthy**
   ```bash
   curl http://localhost:{port}/health
   ```

4. **Verify metrics are being collected**
   ```bash
   curl http://localhost:{port}/metrics | head -20
   ```

#### Post-Resolution

- Review why service went down
- Check if resource limits need adjustment
- Monitor service for stability

---

### HighErrorRate

**Severity:** Critical
**Impact:** Service experiencing high error rate
**SLA:** Investigate within 10 minutes

#### Investigation Steps

1. **Check error logs**
   ```bash
   docker logs --tail 200 crypto-bot-{service} 2>&1 | grep -i error
   ```

2. **Check error types**
   ```bash
   # Group by error message
   docker logs crypto-bot-{service} 2>&1 | grep ERROR | \
     cut -d':' -f4- | sort | uniq -c | sort -rn | head -10
   ```

3. **Check database connectivity**
   ```bash
   docker exec crypto-bot-{service} \
     pg_isready -h postgres -U cryptobot
   ```

4. **Check API endpoint errors**
   ```bash
   curl -s http://localhost:9090/api/v1/query \
     --data-urlencode 'query=rate(http_requests_total{status_code=~"5..", job="{service}"}[5m])' | \
     jq '.data.result'
   ```

5. **Check recent deployments**
   ```bash
   docker inspect crypto-bot-{service} | grep Created
   git log --oneline -10
   ```

#### Resolution Steps

1. **If database issue**
   ```bash
   # Check database connections
   docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
     -c "SELECT count(*) FROM pg_stat_activity;"

   # Kill idle connections if needed
   docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
     -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle';"
   ```

2. **If external API issue**
   ```bash
   # Check Bybit API status
   curl -s https://api.bybit.com/v5/market/time

   # Check rate limiting
   docker logs crypto-bot-bybit-connector | grep "429\|rate limit"
   ```

3. **If code issue from recent deployment**
   ```bash
   # Rollback to previous version
   git log --oneline -5
   git checkout <previous-commit>
   docker-compose build {service}
   docker-compose up -d {service}
   ```

4. **Restart service**
   ```bash
   docker restart crypto-bot-{service}
   ```

#### Post-Resolution

- Identify root cause
- Fix underlying issue
- Add monitoring for similar issues
- Update error handling if needed

---

### DatabaseDown

**Severity:** Critical
**Impact:** All services affected
**SLA:** Resolve within 5 minutes

#### Investigation Steps

1. **Check database container**
   ```bash
   docker ps -a | grep postgres
   docker logs --tail 100 crypto-bot-postgres
   ```

2. **Check disk space**
   ```bash
   df -h
   docker exec crypto-bot-postgres df -h
   ```

3. **Check database is accepting connections**
   ```bash
   docker exec crypto-bot-postgres pg_isready
   ```

4. **Check for corruption**
   ```bash
   docker exec crypto-bot-postgres \
     psql -U cryptobot -d cryptobot -c "SELECT 1;"
   ```

#### Resolution Steps

1. **Restart PostgreSQL**
   ```bash
   docker restart crypto-bot-postgres

   # Wait for startup
   sleep 10

   # Verify
   docker exec crypto-bot-postgres pg_isready
   ```

2. **If corruption detected**
   ```bash
   # Stop all services
   docker-compose down

   # Restore from backup
   ./restore_database.sh /path/to/latest/backup.sql

   # Start services
   docker-compose up -d
   ```

3. **If disk space issue**
   ```bash
   # Clean up old logs
   docker system prune -a

   # Resize disk if needed
   # (depends on hosting provider)
   ```

4. **Check connection limits**
   ```bash
   docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
     -c "SHOW max_connections;"

   docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
     -c "SELECT count(*) FROM pg_stat_activity;"
   ```

#### Post-Resolution

- Restore all service connectivity
- Verify data integrity
- Check for lost transactions during downtime
- Schedule immediate backup

#### Dashboard

- [Database Performance Dashboard](http://localhost:3000/d/database)

---

## Warning Alerts

### HighAPILatency

**Severity:** Warning
**Impact:** Slow API responses
**SLA:** Investigate within 30 minutes

#### Investigation Steps

1. **Check P99 latency**
   ```bash
   curl -s http://localhost:9090/api/v1/query \
     --data-urlencode 'query=histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))' | \
     jq '.data.result'
   ```

2. **Identify slow endpoints**
   ```bash
   curl -s http://localhost:9090/api/v1/query \
     --data-urlencode 'query=topk(10, rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m]))' | \
     jq '.data.result'
   ```

3. **Check database query performance**
   ```bash
   docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c \
     "SELECT query, mean_exec_time, calls FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
   ```

4. **Check cache hit rate**
   ```bash
   curl -s http://localhost:9090/api/v1/query \
     --data-urlencode 'query=rate(cache_hits_total[5m]) / (rate(cache_hits_total[5m]) + rate(cache_misses_total[5m]))' | \
     jq '.data.result'
   ```

5. **Check system resources**
   ```bash
   docker stats --no-stream
   ```

#### Resolution Steps

1. **Optimize slow queries**
   - Add indexes for frequently queried fields
   - Rewrite N+1 queries
   - Add query caching

2. **Increase cache TTL**
   ```bash
   # Update cache configuration
   # Restart affected services
   ```

3. **Scale up resources if needed**
   ```bash
   # Increase container memory limits
   # Add more database connections
   ```

4. **Add caching layer**
   - Use Redis for frequently accessed data
   - Implement API response caching

#### Post-Resolution

- Monitor latency improvements
- Document optimizations
- Consider load testing

---

### HighMemoryUsage

**Severity:** Warning
**Impact:** Service may run out of memory
**SLA:** Investigate within 1 hour

#### Investigation Steps

1. **Check current memory usage**
   ```bash
   docker stats --no-stream | grep crypto-bot
   ```

2. **Check memory trend**
   ```bash
   curl -s http://localhost:9090/api/v1/query \
     --data-urlencode 'query=process_resident_memory_bytes{job="{service}"}' | \
     jq '.data.result'
   ```

3. **Check for memory leaks**
   ```bash
   # Monitor memory over time
   watch -n 5 'docker stats --no-stream | grep {service}'
   ```

4. **Check garbage collection**
   ```bash
   docker logs crypto-bot-{service} | grep "gc\|garbage"
   ```

#### Resolution Steps

1. **Restart service to clear memory**
   ```bash
   docker restart crypto-bot-{service}
   ```

2. **Increase memory limits**
   ```yaml
   # In docker-compose.yml
   services:
     {service}:
       mem_limit: 2g  # Increase from 1g
   ```

3. **Investigate memory leaks**
   - Review recent code changes
   - Check for unclosed connections
   - Look for large data structures in memory

4. **Optimize memory usage**
   - Process data in chunks
   - Use generators instead of lists
   - Clean up old objects

#### Post-Resolution

- Monitor memory usage
- Set up alerts for gradual increases
- Consider profiling application

---

### LowWinRate

**Severity:** Warning
**Impact:** Trading strategy underperforming
**SLA:** Review within 4 hours

#### Investigation Steps

1. **Check current win rate**
   ```bash
   curl http://localhost:8001/api/v1/stats/performance
   ```

2. **Review recent trades**
   ```bash
   curl http://localhost:8001/api/v1/trades/recent?limit=50
   ```

3. **Analyze market conditions**
   - Check market volatility
   - Review trading pair performance
   - Check for significant news events

4. **Review strategy parameters**
   ```bash
   docker logs crypto-bot-trading | grep "strategy\|parameter"
   ```

#### Resolution Steps

1. **Backtest strategy with recent data**
   ```bash
   python scripts/backtest_strategy.py \
     --start "7 days ago" \
     --end "now"
   ```

2. **Adjust strategy parameters**
   - Tighten entry criteria
   - Adjust stop-loss levels
   - Modify position sizing

3. **Consider pausing trading**
   ```bash
   curl -X POST http://localhost:8001/api/v1/trading/pause
   ```

4. **Switch to different strategy**
   ```bash
   curl -X POST http://localhost:8001/api/v1/strategy/switch \
     -H "Content-Type: application/json" \
     -d '{"strategy": "conservative"}'
   ```

#### Post-Resolution

- Monitor performance improvements
- Document strategy changes
- Schedule strategy review

---

### BybitRateLimitHit

**Severity:** Warning
**Impact:** API calls being throttled
**SLA:** Resolve within 30 minutes

#### Investigation Steps

1. **Check rate limit errors**
   ```bash
   docker logs crypto-bot-bybit-connector | grep "429\|rate limit" | tail -20
   ```

2. **Check API call frequency**
   ```bash
   curl -s http://localhost:9090/api/v1/query \
     --data-urlencode 'query=rate(http_requests_total{job="bybit-connector"}[5m])' | \
     jq '.data.result'
   ```

3. **Identify which endpoints are hit most**
   ```bash
   docker logs crypto-bot-bybit-connector | \
     grep "GET\|POST" | cut -d' ' -f3 | sort | uniq -c | sort -rn
   ```

#### Resolution Steps

1. **Implement request queuing**
   - Add rate limiter middleware
   - Queue non-urgent requests

2. **Reduce polling frequency**
   ```python
   # Increase sleep time between requests
   # Use WebSocket instead of REST where possible
   ```

3. **Implement caching**
   ```python
   # Cache market data responses
   # Use Redis for frequently accessed data
   ```

4. **Review Bybit rate limits**
   - Check current tier
   - Consider upgrading API tier if needed

#### Post-Resolution

- Monitor API call rate
- Implement backoff strategy
- Add rate limit monitoring

---

## Common Investigation Steps

### Check Service Logs

```bash
# Last 100 lines
docker logs --tail 100 crypto-bot-{service}

# Follow logs in real-time
docker logs -f crypto-bot-{service}

# Search for errors
docker logs crypto-bot-{service} 2>&1 | grep -i error

# Filter by timestamp
docker logs --since "2025-11-21T10:00:00" crypto-bot-{service}
```

### Check Prometheus Metrics

```bash
# Service up/down
curl -s http://localhost:9090/api/v1/query \
  --data-urlencode 'query=up{job="{service}"}' | jq

# Request rate
curl -s http://localhost:9090/api/v1/query \
  --data-urlencode 'query=rate(http_requests_total{job="{service}"}[5m])' | jq

# Error rate
curl -s http://localhost:9090/api/v1/query \
  --data-urlencode 'query=rate(http_requests_total{job="{service}",status_code=~"5.."}[5m])' | jq
```

### Check Database

```bash
# Connect to database
docker exec -it crypto-bot-postgres psql -U cryptobot -d cryptobot

# Check active connections
SELECT count(*), state FROM pg_stat_activity GROUP BY state;

# Check slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

# Check database size
SELECT pg_size_pretty(pg_database_size('cryptobot'));
```

### Check Resource Usage

```bash
# Docker stats
docker stats --no-stream

# Disk usage
df -h

# Memory usage
free -h

# CPU usage
top -bn1 | head -20
```

---

## Escalation Procedures

### Escalation Matrix

| Severity | Response Time | Escalation Level | Contact |
|----------|--------------|------------------|---------|
| Critical | 5-15 minutes | L1 → L2 (after 15 min) | On-call engineer |
| Warning | 30-60 minutes | L1 → L2 (after 1 hour) | Team lead |
| Info | 4-24 hours | L1 only | Standard support |

### Contact Information

- **L1 Support**: alerts@cryptobot.com
- **L2 Engineering**: engineering@cryptobot.com
- **L3 Architecture**: architecture@cryptobot.com

### Incident Communication

1. **Acknowledge alert** (within 5 minutes)
2. **Update status page** (if public-facing)
3. **Communicate to stakeholders** (for critical alerts)
4. **Post-mortem** (within 48 hours of resolution)

---

## Additional Resources

- [Grafana Dashboards](http://localhost:3000)
- [Prometheus Alerts](http://localhost:9090/alerts)
- [AlertManager](http://localhost:9093)
- [Monitoring Guide](MONITORING_GUIDE.md)
- [Operations Runbook](/docs/operations/RUNBOOK.md)

---

**Document Status:** Production Ready
**Last Updated:** 2025-11-21
**Maintained By:** DevOps Team
