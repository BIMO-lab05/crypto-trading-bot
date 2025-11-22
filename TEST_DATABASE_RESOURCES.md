# Test Database Resources - Quick Reference

## Status: ✅ OPERATIONAL

All test databases are running and verified.

---

## Quick Commands

```bash
# Start test databases
./scripts/test-db-start.sh

# Verify connectivity
python3 scripts/test-db-verify.py

# Run tests
cd services/trading-engine
pytest tests/ -v

# Stop test databases
./scripts/test-db-stop.sh

# Clean everything
./scripts/test-db-clean.sh
```

---

## Database Connections

### PostgreSQL (Trading Data)
```bash
Host:     localhost
Port:     5434
Database: cryptobot_test
User:     cryptobot_test
Password: test_password_123

# CLI access
docker exec -it crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test

# Python connection
postgresql+asyncpg://cryptobot_test:test_password_123@localhost:5434/cryptobot_test
```

### TimescaleDB (Market Data)
```bash
Host:     localhost
Port:     5435
Database: market_data_test
User:     cryptobot_test
Password: test_password_123

# CLI access
docker exec -it crypto-bot-test-timescaledb psql -U cryptobot_test -d market_data_test

# Python connection
postgresql+asyncpg://cryptobot_test:test_password_123@localhost:5435/market_data_test
```

### Redis (Caching)
```bash
Host:     localhost
Port:     6380
Database: 0

# CLI access
docker exec -it crypto-bot-test-redis redis-cli

# Python connection
redis://localhost:6380/0
```

---

## File Locations

### Configuration
- **docker-compose.test.yml** - Test database containers

### Scripts
- **scripts/test-db-start.sh** - Start databases
- **scripts/test-db-stop.sh** - Stop databases
- **scripts/test-db-clean.sh** - Clean all data
- **scripts/test-db-verify.py** - Verify connectivity

### Test Fixtures
- **shared/tests/fixtures/database.py** - Centralized database fixtures
- **services/trading-engine/tests/conftest.py** - Service-specific fixtures

### Tests
- **tests/test_database_infrastructure.py** - Infrastructure verification

### Documentation
- **TEST_DATABASE_SETUP.md** - Complete usage guide (3,500 lines)
- **TEST_DATABASE_IMPLEMENTATION_REPORT.md** - Implementation details
- **TEST_DATABASE_RESOURCES.md** - This file (quick reference)

---

## Environment Variables

```bash
# PostgreSQL
export TEST_DB_HOST=localhost
export TEST_DB_PORT=5434
export TEST_DB_NAME=cryptobot_test
export TEST_DB_USER=cryptobot_test
export TEST_DB_PASSWORD=test_password_123

# TimescaleDB
export TIMESCALE_TEST_DB_HOST=localhost
export TIMESCALE_TEST_DB_PORT=5435
export TIMESCALE_TEST_DB_NAME=market_data_test
export TIMESCALE_TEST_DB_USER=cryptobot_test
export TIMESCALE_TEST_DB_PASSWORD=test_password_123

# Redis
export TEST_REDIS_HOST=localhost
export TEST_REDIS_PORT=6380
```

---

## Test Fixtures Usage

### Import Fixtures

```python
import pytest
from decimal import Decimal

# Async database session with auto-rollback
async def test_with_database(async_db_session):
    """Test with database session"""
    # Your test code here
    # Changes automatically rolled back after test
    pass

# Test data fixtures
async def test_with_portfolio(test_portfolio):
    """Test with pre-created portfolio"""
    assert test_portfolio.cash_balance == Decimal("10000.00")

# Helper fixtures
async def test_with_helpers(db_query_helper, assert_decimal_equal):
    """Test with helper utilities"""
    result = await db_query_helper("SELECT COUNT(*) FROM positions")
    count = result.scalar()
    assert_decimal_equal(Decimal("123.45"), Decimal("123.45"))
```

### Available Fixtures

- **async_db_session** - Async database session (auto-rollback)
- **sync_db_session** - Sync database session (auto-rollback)
- **clean_database** - Session with truncated tables
- **test_portfolio** - Pre-created test portfolio
- **test_position** - Pre-created test position
- **db_query_helper** - Execute raw SQL queries
- **assert_decimal_equal** - Assert Decimal equality with tolerance
- **benchmark_timer** - Performance timing utility

---

## Common Test Patterns

### Integration Test

```python
@pytest.mark.integration
async def test_create_position(async_db_session):
    """Test creating position in database"""
    from database.models import Position
    from decimal import Decimal

    # Create position
    position = Position(
        portfolio_id="test_portfolio_001",
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000.00")
    )

    # Persist
    async_db_session.add(position)
    await async_db_session.commit()
    await async_db_session.refresh(position)

    # Verify
    assert position.position_id is not None
    assert position.symbol == "BTCUSDT"

    # Automatically rolled back after test!
```

### Unit Test (No Database)

```python
@pytest.mark.unit
def test_position_validation():
    """Test position model validation"""
    from app.models import PositionCreate, PositionSide
    from decimal import Decimal

    # Test in-memory validation
    position = PositionCreate(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000.00")
    )

    assert position.symbol == "BTCUSDT"
```

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Database startup | 10 seconds |
| Single test (with DB) | 50-200ms |
| Transaction rollback | ~5ms |
| 1000 bulk inserts | 1.3 seconds |
| Infrastructure tests | 8 passed in 1.78s |

**Optimizations:**
- tmpfs storage (5-10x faster than disk)
- Transaction rollback (instant cleanup)
- Connection pooling disabled for tests
- Parallel execution supported

---

## Troubleshooting

### Database Not Running

```bash
# Check status
docker-compose -f docker-compose.test.yml ps

# Start if not running
./scripts/test-db-start.sh

# Check logs if failing
docker logs crypto-bot-test-postgres
```

### Connection Refused

```bash
# Verify port is exposed
docker ps | grep test-postgres

# Should show: 0.0.0.0:5434->5432/tcp

# Test connectivity
python3 scripts/test-db-verify.py
```

### Tests Failing Intermittently

```python
# Use transaction rollback for isolation
async def test_isolated(async_db_session):
    # This ensures clean state
    pass

# Or explicitly clean database
async def test_clean(clean_database):
    # Tables truncated before test
    pass
```

---

## CI/CD Integration

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

      - name: Install dependencies
        run: |
          cd services/trading-engine
          pip install -r requirements.txt

      - name: Run tests
        run: |
          cd services/trading-engine
          pytest tests/ --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3

      - name: Stop test databases
        if: always()
        run: ./scripts/test-db-stop.sh
```

---

## Support

**Documentation:**
- TEST_DATABASE_SETUP.md - Complete usage guide
- TEST_DATABASE_IMPLEMENTATION_REPORT.md - Technical details

**Verification:**
```bash
python3 scripts/test-db-verify.py
python3 -m pytest tests/test_database_infrastructure.py -v
```

**Contact:**
Database Administrator for infrastructure issues

---

## Version Info

- **Created:** 2025-11-22
- **Status:** ✅ Operational
- **PostgreSQL:** 15.14
- **TimescaleDB:** 15.13
- **Redis:** 7.x
- **pytest:** 8.4.2
- **SQLAlchemy:** 2.0.x
