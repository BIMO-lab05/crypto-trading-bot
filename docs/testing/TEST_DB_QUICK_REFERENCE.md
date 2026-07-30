# Test Database Quick Reference

**Status:** ✅ OPERATIONAL | **Startup Time:** 15s | **Success Rate:** 91%

---

## Quick Commands

```bash
# Start databases
./scripts/test-db-start.sh

# Verify health (24 automated tests)
./scripts/verify-test-db.sh

# Stop databases
./scripts/test-db-stop.sh

# Quick status check
docker ps --filter "name=crypto-bot-test"
```

---

## Connection Strings

```python
# PostgreSQL
POSTGRES_URL = "postgresql://cryptobot_test:test_password_123@localhost:5434/cryptobot_test"

# TimescaleDB
TIMESCALEDB_URL = "postgresql://cryptobot_test:test_password_123@localhost:5435/market_data_test"

# Redis
REDIS_URL = "redis://localhost:6380/0"
```

---

## Manual Connections

```bash
# PostgreSQL
docker exec -it crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test

# TimescaleDB
docker exec -it crypto-bot-test-timescaledb psql -U cryptobot_test -d market_data_test

# Redis
docker exec -it crypto-bot-test-redis redis-cli
```

---

## Common Issues

| Symptom | Quick Fix |
|---------|-----------|
| "Port already in use" | `docker stop crypto-bot-test-postgres` |
| "Connection refused" | Wait 15 seconds for health checks |
| "Container exits" | `docker-compose -f docker-compose.test.yml down -v` then restart |
| Slow startup | Check system RAM/CPU, increase `start_period` if needed |

---

## Health Check Status

```bash
# Quick health check
docker inspect crypto-bot-test-postgres --format='{{.State.Health.Status}}'

# Expected: healthy

# Connection test
docker exec crypto-bot-test-postgres pg_isready -U cryptobot_test

# Expected: /var/run/postgresql:5432 - accepting connections
```

---

## Performance Benchmarks

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Startup time | <30s | 15s | ✅ |
| Health check pass | <20s | 10s | ✅ |
| Query latency (native) | <100ms | 10-30ms | ✅ |
| Memory usage | <1GB | ~203MB | ✅ |

---

## Test Database Specs

| Database | Port | Image | Memory | Purpose |
|----------|------|-------|--------|---------|
| PostgreSQL | 5434 | postgres:15-alpine | 79MB | General tests |
| TimescaleDB | 5435 | timescale/timescaledb | 118MB | Time-series tests |
| Redis | 6380 | redis:7-alpine | 5MB | Cache/queue tests |

---

## Configuration Files

- **docker-compose.test.yml** - Container definitions
- **scripts/test-db-start.sh** - Startup script
- **scripts/verify-test-db.sh** - Verification script
- **docs/testing/TEST_DATABASE_SETUP.md** - Full documentation

---

## Troubleshooting One-Liners

```bash
# Reset everything
docker-compose -f docker-compose.test.yml down -v && ./scripts/test-db-start.sh

# Check logs
docker logs crypto-bot-test-postgres --tail 50

# Test connection from Python
python -c "import psycopg2; psycopg2.connect('postgresql://cryptobot_test:test_password_123@localhost:5434/cryptobot_test')"

# Monitor resource usage
docker stats crypto-bot-test-postgres --no-stream
```

---

**Full Documentation:** [TEST_DATABASE_SETUP.md](TEST_DATABASE_SETUP.md)
**Resolution Report:** [TEST_DB_HEALTH_CHECK_RESOLUTION.md](TEST_DB_HEALTH_CHECK_RESOLUTION.md)
