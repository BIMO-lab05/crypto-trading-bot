# Operational Runbook
**Crypto Trading Bot - Operations Manual**
**Version:** 1.0
**Last Updated:** 2025-11-16

---

## Table of Contents

1. [Service Management](#service-management)
2. [Monitoring & Alerts](#monitoring--alerts)
3. [Common Issues & Solutions](#common-issues--solutions)
4. [Deployment Procedures](#deployment-procedures)
5. [Emergency Procedures](#emergency-procedures)
6. [Maintenance Tasks](#maintenance-tasks)

---

## Service Management

### Starting Services

#### Development Environment
```bash
# Start all services
cd /mnt/d/Bimo_max/crypto-trading-bot
docker-compose up -d

# Start specific service
docker-compose up -d trading-engine

# Start with logs
docker-compose up trading-engine
```

#### Production Environment
```bash
# Start all services with proper ordering
docker-compose -f docker-compose.prod.yml up -d postgres redis rabbitmq
sleep 10
docker-compose -f docker-compose.prod.yml up -d bybit-connector market-data-service
sleep 10
docker-compose -f docker-compose.prod.yml up -d technical-analysis portfolio-manager
sleep 10
docker-compose -f docker-compose.prod.yml up -d trading-engine
sleep 10
docker-compose -f docker-compose.prod.yml up -d api-gateway
```

### Stopping Services

#### Graceful Shutdown (Recommended)
```bash
# Stop all services gracefully (allows 30s cleanup)
docker-compose stop

# Stop specific service
docker-compose stop trading-engine

# Verify shutdown
docker-compose ps
```

#### Emergency Stop
```bash
# Force stop (use only if graceful shutdown fails)
docker-compose kill

# Restart after emergency stop
docker-compose up -d
```

### Checking Service Status

```bash
# Check all services
docker-compose ps

# Check specific service logs
docker-compose logs -f trading-engine

# Check service health endpoints
curl http://localhost:8000/health  # API Gateway
curl http://localhost:8001/health  # Trading Engine
curl http://localhost:8002/health  # Market Data
curl http://localhost:8003/health  # Technical Analysis
curl http://localhost:8004/health  # Portfolio Manager
curl http://localhost:8005/health  # Bybit Connector
```

### Service Restart Procedures

#### Rolling Restart (Zero Downtime)
```bash
# Restart services one at a time
for service in api-gateway trading-engine market-data-service technical-analysis; do
    echo "Restarting ${service}..."
    docker-compose restart ${service}
    sleep 30  # Wait for health check
done
```

#### Full Restart
```bash
# Stop all
docker-compose down

# Start all
docker-compose up -d

# Verify
./scripts/healthcheck_all.sh
```

### Log Locations

```bash
# Service logs (JSON format)
tail -f services/api-gateway/logs/service.log
tail -f services/trading-engine/logs/service.log

# Docker logs
docker-compose logs -f --tail=100 trading-engine

# System logs
tail -f /var/log/crypto-bot/system.log

# Backup logs
tail -f /var/log/backups.log
```

---

## Monitoring & Alerts

### Prometheus Metrics

#### Accessing Metrics
```bash
# API Gateway metrics
curl http://localhost:8000/metrics

# Trading Engine metrics
curl http://localhost:8001/metrics

# All services
for port in 8000 8001 8002 8003 8004 8005; do
    echo "=== Port ${port} ==="
    curl -s http://localhost:${port}/metrics | grep -E "^(http_requests_total|http_request_duration)"
done
```

#### Key Metrics to Monitor

**Trading Engine:**
- `trades_executed_total` - Total trades executed
- `trade_latency_seconds` - Trade execution latency
- `active_positions_gauge` - Number of open positions
- `portfolio_value_gauge` - Current portfolio value

**API Gateway:**
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency
- `backend_requests_total` - Backend service calls
- `cache_hits_total` - Cache hit rate

**Market Data Service:**
- `market_updates_received_total` - Market data updates
- `websocket_connections_gauge` - Active WebSocket connections
- `data_processing_latency_seconds` - Data processing time

### Grafana Dashboards

#### Accessing Grafana
```
URL: http://localhost:3000
Username: admin
Password: [From .env file]
```

#### Key Dashboards
1. **System Overview** - Overall system health
2. **Trading Performance** - Trade metrics and P&L
3. **API Performance** - Request rates and latency
4. **Database Performance** - Query performance and connections
5. **Alert Status** - Active alerts and incidents

### Alert Configuration

#### Critical Alerts (Page On-Call)
- Trading engine down
- Database connection lost
- Bybit API connection lost
- Emergency stop triggered
- Daily loss > 5%

#### Warning Alerts (Slack/Email)
- High API latency (> 1s p99)
- Low cache hit rate (< 70%)
- Database pool utilization > 80%
- Disk space < 20%

#### Alert Response

```bash
# Check alert status
curl http://localhost:9093/api/v1/alerts  # Alertmanager

# Acknowledge alert
curl -X POST http://localhost:9093/api/v1/alerts \
    -H "Content-Type: application/json" \
    -d '{"status":"acknowledged","labels":{"alertname":"HighLatency"}}'

# Silence alert
curl -X POST http://localhost:9093/api/v1/silences \
    -H "Content-Type: application/json" \
    -d '{"matchers":[{"name":"alertname","value":"HighLatency"}],"duration":"2h"}'
```

---

## Common Issues & Solutions

### Issue 1: Trading Engine Won't Start

**Symptoms:**
- Service exits immediately after start
- Error in logs: "Database connection failed"

**Diagnosis:**
```bash
# Check database connectivity
docker-compose exec postgres psql -U cryptobot -c "SELECT 1;"

# Check service logs
docker-compose logs trading-engine
```

**Solution:**
```bash
# 1. Verify database is running
docker-compose ps postgres

# 2. If database is down, start it
docker-compose up -d postgres
sleep 10

# 3. Restart trading engine
docker-compose restart trading-engine

# 4. Verify health
curl http://localhost:8001/health
```

### Issue 2: High Memory Usage

**Symptoms:**
- Services becoming slow
- OOM (Out of Memory) errors

**Diagnosis:**
```bash
# Check memory usage
docker stats

# Check specific service
docker stats trading-engine
```

**Solution:**
```bash
# 1. Identify memory leak
docker stats --no-stream | sort -k 4 -h

# 2. Restart affected service
docker-compose restart [service-name]

# 3. If persistent, check for memory leaks in code
# 4. Increase memory limits in docker-compose.yml
```

### Issue 3: Slow API Responses

**Symptoms:**
- API requests taking > 1 second
- Timeout errors

**Diagnosis:**
```bash
# Check API latency
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/api/market/ticker/BTCUSDT

# Check database query performance
docker-compose exec postgres psql -U cryptobot -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"

# Check Redis connectivity
redis-cli ping
```

**Solution:**
```bash
# 1. Check cache hit rate
redis-cli info stats | grep keyspace_hits

# 2. If cache is cold, warm it up
./scripts/warm_cache.sh

# 3. Check database connections
docker-compose exec postgres psql -U cryptobot -c "SELECT count(*) FROM pg_stat_activity;"

# 4. If connection pool exhausted, increase pool size
# Edit shared/utils/db_pool.py: max_size = 100

# 5. Restart services
docker-compose restart api-gateway
```

### Issue 4: Database Connection Pool Exhausted

**Symptoms:**
- Error: "connection pool exhausted"
- Requests timing out

**Diagnosis:**
```bash
# Check active connections
docker-compose exec postgres psql -U cryptobot -c \
    "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Check pool stats via API
curl http://localhost:8000/api/internal/pool-stats
```

**Solution:**
```bash
# 1. Kill idle connections
docker-compose exec postgres psql -U cryptobot -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND state_change < NOW() - INTERVAL '10 minutes';"

# 2. Increase pool size (temporary)
# Edit docker-compose.yml environment variables

# 3. Restart services
docker-compose restart

# 4. Long-term: optimize queries to reduce connection time
```

### Issue 5: Bybit API Rate Limit

**Symptoms:**
- Error: "Rate limit exceeded"
- 429 responses from Bybit

**Diagnosis:**
```bash
# Check Bybit connector logs
docker-compose logs bybit-connector | grep -i "rate limit"

# Check request rate
curl http://localhost:8005/metrics | grep bybit_requests_total
```

**Solution:**
```bash
# 1. Reduce request frequency
# Edit services/bybit-connector/app/config.py: REQUEST_DELAY = 1.0

# 2. Implement exponential backoff (already in circuit breaker)

# 3. Use WebSocket for market data instead of REST

# 4. Restart connector
docker-compose restart bybit-connector
```

### Issue 6: Logs Filling Disk

**Symptoms:**
- Disk space warnings
- Services crashing with "No space left on device"

**Diagnosis:**
```bash
# Check disk usage
df -h

# Check log sizes
du -sh services/*/logs/

# Find largest logs
du -ah /var/log/ | sort -rh | head -20
```

**Solution:**
```bash
# 1. Rotate logs immediately
./scripts/rotate_logs.sh

# 2. Clean old logs
find services/*/logs/ -name "*.log" -mtime +7 -delete

# 3. Configure log rotation
# Add to /etc/logrotate.d/crypto-bot

# 4. Compress old logs
find services/*/logs/ -name "*.log" -mtime +1 -exec gzip {} \;
```

---

## Deployment Procedures

### Standard Deployment (Rolling Update)

```bash
# 1. Pull latest code
git pull origin main

# 2. Backup database
./scripts/backup/postgres_backup.sh

# 3. Run tests
pytest tests/integration/ -v

# 4. Deploy services one by one
for service in api-gateway trading-engine market-data-service; do
    echo "Deploying ${service}..."

    # Build new image
    docker-compose build ${service}

    # Rolling restart
    docker-compose up -d --no-deps ${service}

    # Wait for health check
    sleep 30

    # Verify
    curl http://localhost:800X/health

    if [ $? -ne 0 ]; then
        echo "Deployment failed for ${service}"
        # Rollback
        git checkout HEAD~1
        docker-compose build ${service}
        docker-compose up -d --no-deps ${service}
        exit 1
    fi
done

echo "Deployment complete"
```

### Blue-Green Deployment

```bash
# 1. Start green environment
docker-compose -f docker-compose.green.yml up -d

# 2. Verify green environment
./scripts/healthcheck_all.sh green

# 3. Run smoke tests
pytest tests/integration/ --env=green

# 4. Switch traffic (update load balancer)
./scripts/switch_to_green.sh

# 5. Monitor for 10 minutes
sleep 600

# 6. If successful, stop blue environment
docker-compose -f docker-compose.blue.yml down

# 7. If issues, rollback
./scripts/switch_to_blue.sh
```

### Rollback Procedure

```bash
# 1. Stop current version
docker-compose down

# 2. Revert code
git revert HEAD
# or
git checkout <previous-commit>

# 3. Restore database backup (if schema changed)
./scripts/recovery/restore_postgres.sh

# 4. Rebuild and start
docker-compose build
docker-compose up -d

# 5. Verify
./scripts/healthcheck_all.sh

echo "Rollback complete"
```

---

## Emergency Procedures

### Emergency Stop (All Trading)

```bash
# Method 1: API call
curl -X POST http://localhost:8000/api/portfolio/emergency-stop

# Method 2: Create stop file
touch /mnt/d/Bimo_max/crypto-trading-bot/EMERGENCY_STOP

# Method 3: Stop trading engine
docker-compose stop trading-engine

# Verify trading stopped
curl http://localhost:8000/api/trading/status
```

### Position Liquidation (Emergency)

```bash
# 1. Stop automated trading
curl -X POST http://localhost:8000/api/trading/stop

# 2. Get all open positions
curl http://localhost:8000/api/trading/positions?status=open

# 3. Close all positions manually via Bybit UI
# or
# 4. Use bulk close script
python scripts/emergency/close_all_positions.py

# 5. Verify all positions closed
curl http://localhost:8000/api/trading/positions?status=open
```

### Database Corruption

```bash
# 1. Stop all services
docker-compose down

# 2. Verify backup availability
ls -lh /backups/postgres/

# 3. Restore from latest backup
./scripts/recovery/restore_postgres.sh

# 4. Verify data integrity
./scripts/testing/verify_database.sh

# 5. Restart services
docker-compose up -d

# 6. Verify system health
./scripts/healthcheck_all.sh
```

---

## Maintenance Tasks

### Daily Tasks

```bash
# Run at 00:00 UTC via cron
0 0 * * * /scripts/maintenance/daily.sh

# daily.sh contents:
#!/bin/bash
# 1. Health check
./scripts/healthcheck_all.sh

# 2. Backup verification
python scripts/testing/test_backup_restore.py

# 3. Log rotation
./scripts/rotate_logs.sh

# 4. Disk cleanup
docker system prune -f --volumes --filter "until=24h"

# 5. Generate daily report
python scripts/reporting/daily_report.py
```

### Weekly Tasks

```bash
# Run every Sunday at 02:00 UTC
0 2 * * 0 /scripts/maintenance/weekly.sh

# weekly.sh contents:
#!/bin/bash
# 1. Full database backup
./scripts/backup/full_backup.sh

# 2. Update dependencies
pip install -U -r requirements.txt

# 3. Security scan
docker scan crypto-bot/trading-engine:latest

# 4. Performance review
python scripts/reporting/weekly_performance.py

# 5. Cleanup old backups
find /backups -mtime +30 -delete
```

### Monthly Tasks

```bash
# First Friday of month at 10:00 UTC
# 1. DR drill
./scripts/testing/monthly_dr_drill.sh

# 2. Security audit
./scripts/security/audit.sh

# 3. Dependency updates
./scripts/maintenance/update_dependencies.sh

# 4. Performance optimization review
./scripts/performance/analyze.sh

# 5. Cost analysis
./scripts/reporting/cost_analysis.sh
```

---

## Quick Reference

### Service Ports

| Service | Port | Protocol |
|---------|------|----------|
| API Gateway | 8000 | HTTP |
| Trading Engine | 8001 | HTTP |
| Market Data | 8002 | HTTP |
| Technical Analysis | 8003 | HTTP |
| Portfolio Manager | 8004 | HTTP |
| Bybit Connector | 8005 | HTTP |
| PostgreSQL | 5432 | TCP |
| Redis | 6379 | TCP |
| RabbitMQ | 5672 | AMQP |
| Prometheus | 9090 | HTTP |
| Grafana | 3000 | HTTP |

### Important Files

```
/mnt/d/Bimo_max/crypto-trading-bot/
├── .env                              # Environment configuration
├── docker-compose.yml                # Service definitions
├── EMERGENCY_STOP                    # Emergency stop flag
├── services/*/logs/service.log       # Service logs
├── /backups/postgres/                # Database backups
├── /backups/redis/                   # Redis backups
└── /var/log/backups.log              # Backup logs
```

### Critical Commands

```bash
# Emergency stop trading
curl -X POST http://localhost:8000/api/portfolio/emergency-stop

# Check system health
./scripts/healthcheck_all.sh

# Backup database now
./scripts/backup/postgres_backup.sh

# Restore from backup
./scripts/recovery/restore_postgres.sh

# View live logs
docker-compose logs -f trading-engine

# Restart service
docker-compose restart trading-engine
```

---

**Document Version:** 1.0
**Owner:** DevOps Team
**Next Review:** 2025-12-16

*Keep this runbook updated with every infrastructure change.*
