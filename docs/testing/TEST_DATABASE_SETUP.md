# Test Database Setup and Troubleshooting Guide

**Version:** 2.1
**Last Updated:** 2026-07-30
**Status:** Production-Ready - Optimized Health Checks

---

## Overview

This document provides comprehensive setup instructions and troubleshooting for the test database infrastructure used in integration testing.

### Test Database Stack

| Service | Image | Port | Purpose | Health Check Time |
|---------|-------|------|---------|------------------|
| PostgreSQL | postgres:15-alpine | 5434 | General test database | ~15 seconds |
| TimescaleDB | timescale/timescaledb:latest-pg15 | 5435 | Time-series test data | ~15 seconds |
| Redis | redis:7-alpine | 6380 | Cache & message queue | ~10 seconds |

---

## Quick reference

> Merged from `docs/testing/TEST_DB_QUICK_REFERENCE.md` on 2026-07-30.

**Status:** ✅ OPERATIONAL | **Startup Time:** 15s | **Success Rate:** 91%

### Quick commands

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

### Connection strings

```python
# PostgreSQL (:5434)
POSTGRES_URL = "postgresql://cryptobot_test:test_password_123@localhost:5434/cryptobot_test"

# TimescaleDB (:5435)
TIMESCALEDB_URL = "postgresql://cryptobot_test:test_password_123@localhost:5435/market_data_test"

# Redis (:6380)
REDIS_URL = "redis://localhost:6380/0"
```

### Manual connections

```bash
# PostgreSQL
docker exec -it crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test

# TimescaleDB
docker exec -it crypto-bot-test-timescaledb psql -U cryptobot_test -d market_data_test

# Redis
docker exec -it crypto-bot-test-redis redis-cli
```

### Common issues (quick fixes)

| Symptom | Quick Fix |
|---------|-----------|
| "Port already in use" | `docker stop crypto-bot-test-postgres` |
| "Connection refused" | Wait 15 seconds for health checks |
| "Container exits" | `docker-compose -f docker-compose.test.yml down -v` then restart |
| Slow startup | Check system RAM/CPU, increase `start_period` if needed |

### Health check status

```bash
# Quick health check
docker inspect crypto-bot-test-postgres --format='{{.State.Health.Status}}'
# Expected: healthy

# Connection test
docker exec crypto-bot-test-postgres pg_isready -U cryptobot_test
# Expected: /var/run/postgresql:5432 - accepting connections
```

### Performance at a glance

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Startup time | <30s | 15s | ✅ |
| Health check pass | <20s | 10s | ✅ |
| Query latency (native) | <100ms | 10-30ms | ✅ |
| Memory usage | <1GB | ~203MB | ✅ |

### Test database specs

| Database | Port | Image | Memory | Purpose |
|----------|------|-------|--------|---------|
| PostgreSQL | 5434 | postgres:15-alpine | 79MB | General tests |
| TimescaleDB | 5435 | timescale/timescaledb | 118MB | Time-series tests |
| Redis | 6380 | redis:7-alpine | 5MB | Cache/queue tests |

### Configuration files

- **docker-compose.test.yml** - Container definitions
- **scripts/test-db-start.sh** - Startup script
- **scripts/test-db-stop.sh** - Stop script
- **scripts/verify-test-db.sh** - Verification script (24 automated tests)

### Troubleshooting one-liners

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

**Health-check resolution history:** see `docs/archive/infrastructure-2025/TEST_DB_HEALTH_CHECK_RESOLUTION.md` (moved to archive in the 2026-07-30 docs restructure; the quick reference previously linked it at `docs/testing/`).

---

## Quick Start

### 1. Start Test Databases

```bash
# From project root
./scripts/test-db-start.sh
```

**Expected Output:**
```
==========================================
Starting Test Database Infrastructure
==========================================
Starting test database containers...
 Container crypto-bot-test-postgres  Started
 Container crypto-bot-test-timescaledb  Started
 Container crypto-bot-test-redis  Started

Waiting for databases to be ready...

Checking database health...
✓ crypto-bot-test-postgres is healthy
✓ crypto-bot-test-timescaledb is healthy
✓ crypto-bot-test-redis is healthy

==========================================
Test Database Infrastructure Ready
==========================================
```

### 2. Verify Connectivity

```bash
# PostgreSQL
docker exec crypto-bot-test-postgres pg_isready -U cryptobot_test -d cryptobot_test

# TimescaleDB
docker exec crypto-bot-test-timescaledb pg_isready -U cryptobot_test -d market_data_test

# Redis
docker exec crypto-bot-test-redis redis-cli ping
```

### 3. Run Tests

```bash
# Run all tests
pytest

# Run specific service tests
cd services/trading-engine && pytest tests/

# Run with coverage
pytest --cov=services --cov-report=html
```

### 4. Stop Test Databases

```bash
./scripts/test-db-stop.sh

# Or manually with cleanup
docker-compose -f docker-compose.test.yml down -v
```

---

## Configuration Details

### Health Check Configuration

#### PostgreSQL & TimescaleDB
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U cryptobot_test -d cryptobot_test"]
  interval: 5s        # Check every 5 seconds
  timeout: 5s         # Command must complete in 5 seconds
  retries: 5          # Allow 5 failures before marking unhealthy
  start_period: 10s   # Grace period for initial startup
```

**Explanation:**
- `start_period: 10s` - During first 10 seconds, failed health checks don't count against retries
- `interval: 5s` - After start_period, checks run every 5 seconds
- `retries: 5` - Maximum 25 seconds (5 retries × 5s) to become healthy after start_period
- Total time to healthy: ~15 seconds for fresh container

#### Redis
```yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 5s
  timeout: 3s
  retries: 5
  start_period: 5s    # Redis starts faster than PostgreSQL
```

### Performance Optimizations

#### 1. tmpfs Storage (In-Memory)
```yaml
tmpfs:
  - /var/lib/postgresql/data:rw,noexec,nosuid,size=512m
```

**Benefits:**
- 5-10x faster I/O than disk
- No disk wear from test data
- Automatic cleanup on container stop
- Ideal for ephemeral test environments

**Trade-offs:**
- Limited to 512MB per database
- Data lost when container stops
- Requires sufficient RAM

#### 2. Optimized PostgreSQL Settings
```yaml
command:
  - postgres
  - -c
  - shared_buffers=256MB
  - -c
  - max_connections=100
```

**Tuning Rationale:**
- `shared_buffers=256MB` - Match 50% of tmpfs size for optimal caching
- `max_connections=100` - Support concurrent test execution

---

## Troubleshooting Guide

### Issue 1: Health Check Timeout

**Symptom:**
```
✗ crypto-bot-test-postgres failed to become healthy
```

**Diagnosis:**
```bash
# Check container status
docker ps -a --filter "name=crypto-bot-test"

# Check health check logs
docker inspect crypto-bot-test-postgres --format='{{range .State.Health.Log}}{{.Start}} - {{.ExitCode}} - {{.Output}}{{"\n"}}{{end}}'

# Check container logs
docker logs crypto-bot-test-postgres --tail 50
```

**Common Causes:**

#### A. Container Not Starting
```bash
# Check for error messages
docker logs crypto-bot-test-postgres

# Look for:
# - "FATAL: database system is starting up"
# - "FATAL: role 'postgres' does not exist"
# - Permission errors
```

**Fix:**
```bash
# Remove volumes and restart fresh
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml up -d
```

#### B. Health Check Command Wrong
```yaml
# WRONG - using default postgres user
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U postgres"]

# CORRECT - using configured test user
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U cryptobot_test -d cryptobot_test"]
```

#### C. Too Aggressive Timing
```yaml
# OLD - might timeout on slow systems
healthcheck:
  interval: 2s
  timeout: 2s
  retries: 10
  # Missing start_period!

# OPTIMIZED - works reliably
healthcheck:
  interval: 5s
  timeout: 5s
  retries: 5
  start_period: 10s
```

### Issue 2: Port Already in Use

**Symptom:**
```
Error starting userland proxy: listen tcp4 0.0.0.0:5434: bind: address already in use
```

**Diagnosis:**
```bash
# Find what's using the port
lsof -i :5434
# Or on Linux
netstat -tulpn | grep 5434
```

**Fix:**

**Option A: Stop Conflicting Service**
```bash
# If it's a production database
docker stop crypto-bot-postgres

# If it's another test instance
docker stop crypto-bot-test-postgres
```

**Option B: Change Test Port**
```yaml
# In docker-compose.test.yml
ports:
  - "15434:5432"  # Use different host port
```

### Issue 3: Database Connection Refused

**Symptom:**
```python
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Diagnosis:**
```bash
# Check container is running
docker ps --filter "name=crypto-bot-test-postgres"

# Check port mapping
docker port crypto-bot-test-postgres

# Test connection from host
docker exec crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test -c "SELECT 1;"
```

**Common Causes:**

#### A. Container Not Healthy
```bash
# Wait for health check
sleep 15
docker ps --format "table {{.Names}}\t{{.Status}}"
```

#### B. Wrong Connection Parameters
```python
# WRONG
DATABASE_URL = "postgresql://postgres:password@localhost:5432/postgres"

# CORRECT for test database
DATABASE_URL = "postgresql://cryptobot_test:test_password_123@localhost:5434/cryptobot_test"
```

#### C. Network Issues
```bash
# Check if container is on correct network
docker network inspect crypto-bot-test-network

# Test from another container
docker run --rm --network crypto-bot-test-network postgres:15-alpine \
  psql -h crypto-bot-test-postgres -U cryptobot_test -d cryptobot_test -c "SELECT version();"
```

### Issue 4: Container Exits Immediately

**Symptom:**
```bash
docker ps -a --filter "name=crypto-bot-test-postgres"
# Shows "Exited (1) 2 seconds ago"
```

**Diagnosis:**
```bash
# Check exit code and logs
docker inspect crypto-bot-test-postgres --format='{{.State.ExitCode}}'
docker logs crypto-bot-test-postgres
```

**Common Causes:**

#### A. tmpfs Permission Issues
```yaml
# If SELinux is enabled, may need different tmpfs options
tmpfs:
  - /var/lib/postgresql/data:rw,noexec,nosuid,size=512m,mode=0700
```

#### B. Invalid Configuration
```yaml
# Check for typos in command
command:
  - postgres
  - -c
  - shared_buffers=256MB  # Not: shared_buffer (singular)
```

### Issue 5: Slow Health Check Performance

**Symptom:**
```
Waiting for databases to be ready... (takes >30 seconds)
```

**Diagnosis:**
```bash
# Time the health check
time docker exec crypto-bot-test-postgres pg_isready -U cryptobot_test -d cryptobot_test

# Check system resources
docker stats crypto-bot-test-postgres --no-stream
```

**Optimization:**

#### A. Increase tmpfs Size (if enough RAM)
```yaml
tmpfs:
  - /var/lib/postgresql/data:rw,noexec,nosuid,size=1024m  # 1GB
```

#### B. Adjust PostgreSQL Memory Settings
```yaml
command:
  - postgres
  - -c
  - shared_buffers=512MB  # Increase if you have RAM
  - -c
  - effective_cache_size=1GB
```

### Issue 6: Data Persistence Between Tests

**Symptom:**
```
Test fails due to data from previous test run
```

**Diagnosis:**
```bash
# Check if volumes exist
docker volume ls | grep crypto-bot-test

# Check tmpfs is being used
docker inspect crypto-bot-test-postgres --format='{{.HostConfig.Tmpfs}}'
```

**Fix:**
```bash
# Ensure using tmpfs (data is ephemeral)
# In docker-compose.test.yml, verify:
tmpfs:
  - /var/lib/postgresql/data:rw,noexec,nosuid,size=512m

# NOT using volumes:
# volumes:  # <- Should NOT exist for test databases
#   - postgres_data:/var/lib/postgresql/data
```

**Clean Slate:**
```bash
# Force fresh start
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml up -d
```

---

## Performance Benchmarks

### Startup Times (Measured on WSL2, 16GB RAM)

| Operation | Time | Notes |
|-----------|------|-------|
| Fresh container creation | ~3 seconds | Network + image pull |
| Database initialization | ~5 seconds | Creating database files |
| First health check pass | ~15 seconds | Total time to healthy |
| Subsequent startups | ~10 seconds | If images cached |
| Shutdown | ~2 seconds | Graceful stop |

### Query Performance (tmpfs vs disk)

| Operation | tmpfs | SSD | HDD |
|-----------|-------|-----|-----|
| INSERT 1000 rows | 45ms | 230ms | 890ms |
| SELECT with index | 12ms | 18ms | 95ms |
| Full table scan | 89ms | 320ms | 1250ms |

**Conclusion:** tmpfs provides 5-10x performance improvement for test workloads.

---

## Database Credentials

### PostgreSQL Test Database
```
Host:     localhost
Port:     5434
Database: cryptobot_test
User:     cryptobot_test
Password: test_password_123
```

**Connection String:**
```
postgresql://cryptobot_test:test_password_123@localhost:5434/cryptobot_test
```

### TimescaleDB Test Database
```
Host:     localhost
Port:     5435
Database: market_data_test
User:     cryptobot_test
Password: test_password_123
```

**Connection String:**
```
postgresql://cryptobot_test:test_password_123@localhost:5435/market_data_test
```

### Redis Test Instance
```
Host:     localhost
Port:     6380
Password: (none)
```

**Connection String:**
```
redis://localhost:6380/0
```

---

## Advanced Usage

### Manual Database Management

#### Connect to PostgreSQL
```bash
# From host
docker exec -it crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test

# Interactive SQL session
docker exec -it crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test <<EOF
CREATE TABLE test_table (id SERIAL PRIMARY KEY, name TEXT);
INSERT INTO test_table (name) VALUES ('test');
SELECT * FROM test_table;
EOF
```

#### Connect to TimescaleDB
```bash
docker exec -it crypto-bot-test-timescaledb psql -U cryptobot_test -d market_data_test
```

#### Connect to Redis
```bash
docker exec -it crypto-bot-test-redis redis-cli

# Example commands
> PING
> SET test_key "test_value"
> GET test_key
> KEYS *
```

### Run SQL Scripts
```bash
# Execute migration scripts
docker exec -i crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test < migrations/001_initial.sql

# From stdin
cat <<'SQL' | docker exec -i crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    side VARCHAR(10),
    quantity DECIMAL(18,8),
    created_at TIMESTAMP DEFAULT NOW()
);
SQL
```

### Debugging Health Checks

#### Watch Health Status in Real-Time
```bash
# Monitor health check changes
watch -n 1 'docker inspect crypto-bot-test-postgres --format="{{.State.Health.Status}}"'
```

#### Manual Health Check Simulation
```bash
# Run same command as health check
docker exec crypto-bot-test-postgres pg_isready -U cryptobot_test -d cryptobot_test

# Expected output:
# /var/run/postgresql:5432 - accepting connections
```

### Performance Monitoring
```bash
# Container resource usage
docker stats crypto-bot-test-postgres --no-stream

# PostgreSQL query stats
docker exec crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test -c "
  SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time
  FROM pg_stat_statements
  ORDER BY total_exec_time DESC
  LIMIT 10;
"
```

---

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Start test databases
        run: ./scripts/test-db-start.sh

      - name: Wait for databases
        run: sleep 15

      - name: Run tests
        run: pytest --cov=services

      - name: Stop test databases
        if: always()
        run: ./scripts/test-db-stop.sh
```

### GitLab CI Example
```yaml
test:
  image: python:3.12
  services:
    - postgres:15-alpine
    - redis:7-alpine

  variables:
    POSTGRES_DB: cryptobot_test
    POSTGRES_USER: cryptobot_test
    POSTGRES_PASSWORD: test_password_123

  script:
    - pip install -r requirements.txt
    - pytest --cov=services
```

---

## Maintenance

### Regular Cleanup
```bash
# Remove all test containers and networks
docker-compose -f docker-compose.test.yml down -v --remove-orphans

# Clean up orphaned volumes
docker volume prune -f

# Clean up unused images
docker image prune -f
```

### Upgrade Database Versions
```yaml
# In docker-compose.test.yml
test-postgres:
  image: postgres:16-alpine  # Updated from 15-alpine
```

**After upgrading:**
```bash
# Pull new images
docker-compose -f docker-compose.test.yml pull

# Recreate containers
docker-compose -f docker-compose.test.yml up -d --force-recreate
```

---

## Frequently Asked Questions

### Q: Why use separate databases for tests?

**A:** Isolation ensures:
- Tests don't affect production data
- Parallel test execution
- Reproducible test environments
- Safe testing of destructive operations

### Q: Why tmpfs instead of regular volumes?

**A:** Benefits:
- 5-10x faster I/O
- No disk wear
- Automatic cleanup
- Ideal for ephemeral test data

### Q: Can I use these databases for development?

**A:** Not recommended. Use separate development databases:
- Test databases are ephemeral (data lost on stop)
- Different ports to avoid conflicts
- Optimized for speed, not durability

### Q: How much RAM does tmpfs use?

**A:** Current configuration:
- PostgreSQL: up to 512MB
- TimescaleDB: up to 512MB
- Redis: up to 128MB
- Total: ~1.2GB maximum

### Q: What if health checks still fail?

**A:** Try these steps:
1. Increase `start_period` to 20s
2. Check system resources (RAM, CPU)
3. Review container logs for errors
4. Test on different machine/environment
5. Report issue with logs to maintainers

---

## Related Documentation

- [Testing Strategy](TESTING.md)
- [Service Integration Tests](../tests/integration/README.md)
- [Database Schema](DATABASE_SCHEMA.md)
- [Development Setup](DEVELOPMENT_SETUP.md)

---

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review container logs: `docker logs crypto-bot-test-postgres`
3. Check GitHub issues
4. Contact database administrator team

**Last verified working:** 2025-11-22
**Docker Compose version:** 2.21.0+
**Docker version:** 20.10.0+
