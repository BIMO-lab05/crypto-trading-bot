# Test Database Setup Guide

## Overview

Comprehensive test database infrastructure for the crypto trading bot microservices.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Database Strategy                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Unit Tests (Fast)                                           │
│  ├─ In-memory data structures                                │
│  ├─ Mocked dependencies                                      │
│  └─ No database required                                     │
│                                                               │
│  Integration Tests (Medium)                                  │
│  ├─ Docker PostgreSQL (port 5434)                           │
│  ├─ Transaction rollback for isolation                       │
│  └─ Shared schema, isolated data                            │
│                                                               │
│  E2E Tests (Slow)                                            │
│  ├─ Full service stack                                       │
│  ├─ TimescaleDB for market data (port 5435)                 │
│  └─ Redis for caching (port 6380)                           │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Database Instances

| Database | Port | Purpose | Data Persistence |
|----------|------|---------|------------------|
| PostgreSQL | 5434 | Trading engine, portfolio management | tmpfs (in-memory) |
| TimescaleDB | 5435 | Market data, candles, time-series | tmpfs (in-memory) |
| Redis | 6380 | Caching, session management | In-memory |

**Benefits:**
- Separate ports prevent conflicts with production databases
- tmpfs storage = 5-10x faster than disk
- No data persistence = fresh state for each test run
- Isolation = tests don't interfere with each other

---

## Quick Start

### 1. Start Test Databases

```bash
# From project root
./scripts/test-db-start.sh
```

Wait for health checks to pass (automatic, ~10 seconds).

### 2. Run Tests

```bash
# Single service
cd services/trading-engine
pytest tests/

# All services
pytest services/*/tests/

# With coverage
pytest services/trading-engine/tests/ --cov=app --cov-report=html
```

### 3. Stop Test Databases

```bash
./scripts/test-db-stop.sh
```

---

## Detailed Usage

### Starting Test Databases

```bash
# Start all test databases
./scripts/test-db-start.sh

# Check status
docker-compose -f docker-compose.test.yml ps

# View logs
docker-compose -f docker-compose.test.yml logs -f
```

### Running Tests

```bash
# Run all tests (unit + integration)
pytest services/trading-engine/tests/ -v

# Run only unit tests (fast, no database)
pytest services/trading-engine/tests/ -v -m "unit"

# Run only integration tests (with database)
pytest services/trading-engine/tests/ -v -m "integration"

# Run specific test file
pytest services/trading-engine/tests/test_positions.py -v

# Run specific test
pytest services/trading-engine/tests/test_positions.py::test_create_position -v

# With detailed output
pytest services/trading-engine/tests/ -vvs

# Stop on first failure
pytest services/trading-engine/tests/ -x

# Run in parallel (faster)
pytest services/trading-engine/tests/ -n auto
```

### Coverage Reports

```bash
# Terminal report
pytest services/trading-engine/tests/ --cov=app --cov-report=term-missing

# HTML report
pytest services/trading-engine/tests/ --cov=app --cov-report=html
open htmlcov/index.html

# Coverage target: >80%
```

### Cleaning Test Databases

```bash
# Stop and remove all test data
./scripts/test-db-clean.sh

# Removes:
# - All containers
# - All volumes
# - All networks
```

---

## Test Fixtures

### Available Fixtures

#### Database Session Fixtures

```python
@pytest.mark.integration
async def test_with_async_db(async_db_session):
    """Async database session with auto-rollback"""
    # Create test data
    position = Position(...)
    async_db_session.add(position)
    await async_db_session.commit()
    # Automatically rolled back after test

def test_with_sync_db(sync_db_session):
    """Synchronous database session"""
    result = sync_db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
```

#### Clean Database Fixture

```python
async def test_with_clean_tables(clean_database):
    """Guaranteed empty tables at test start"""
    # All tables truncated before test
    result = await clean_database.execute(
        text("SELECT COUNT(*) FROM positions")
    )
    assert result.scalar() == 0
```

#### Repository Fixtures

```python
async def test_position_repository(position_repository):
    """Position repository with mocked database"""
    position = await position_repository.create(...)
    assert position.position_id is not None
```

#### Test Data Fixtures

```python
async def test_with_portfolio(test_portfolio):
    """Pre-created test portfolio"""
    assert test_portfolio.portfolio_id == "test_portfolio_001"
    assert test_portfolio.cash_balance == Decimal("10000.00")

async def test_with_position(test_position):
    """Pre-created test position"""
    assert test_position.symbol == "BTCUSDT"
    assert test_position.status == "OPEN"
```

#### Helper Fixtures

```python
async def test_with_query_helper(db_query_helper):
    """Execute raw SQL queries"""
    result = await db_query_helper(
        "SELECT COUNT(*) FROM positions WHERE symbol = :symbol",
        {"symbol": "BTCUSDT"}
    )
    count = result.scalar()

def test_decimal_comparison(assert_decimal_equal):
    """Assert Decimal equality with tolerance"""
    assert_decimal_equal(
        Decimal("123.456789"),
        Decimal("123.456790"),
        tolerance=Decimal("0.000001")
    )

def test_performance(benchmark_timer):
    """Measure execution time"""
    with benchmark_timer() as timer:
        # Code to benchmark
        expensive_operation()

    timer.assert_faster_than(100)  # Assert < 100ms
```

---

## Writing Tests

### Test Structure

```python
"""
Test Module: test_positions.py
Tests position management functionality
"""

import pytest
from decimal import Decimal
from app.models import PositionCreate, PositionSide

# ==========================================
# UNIT TESTS (No database required)
# ==========================================

@pytest.mark.unit
def test_position_model_validation():
    """Test position model validation logic"""
    # Fast unit test using in-memory data
    position = PositionCreate(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000.00")
    )
    assert position.symbol == "BTCUSDT"


# ==========================================
# INTEGRATION TESTS (Database required)
# ==========================================

@pytest.mark.integration
async def test_create_position_in_database(
    db_session,
    test_portfolio,
    sample_position_data
):
    """Test creating position in database"""
    from database.models import Position

    # Create position
    position = Position(
        portfolio_id=test_portfolio.portfolio_id,
        **sample_position_data
    )
    db_session.add(position)
    await db_session.commit()
    await db_session.refresh(position)

    # Verify
    assert position.position_id is not None
    assert position.symbol == "BTCUSDT"


@pytest.mark.integration
async def test_position_repository(position_repository):
    """Test position repository operations"""
    # Create position
    position = await position_repository.create(
        portfolio_id="test_portfolio_001",
        symbol="ETHUSDT",
        side="LONG",
        quantity=Decimal("1.0"),
        entry_price=Decimal("3000.00")
    )

    # Verify
    assert position.position_id is not None

    # Retrieve
    retrieved = await position_repository.get(position.position_id)
    assert retrieved.symbol == "ETHUSDT"


# ==========================================
# PERFORMANCE TESTS
# ==========================================

@pytest.mark.slow
@pytest.mark.integration
async def test_bulk_position_creation_performance(
    db_session,
    test_portfolio,
    benchmark_timer
):
    """Test bulk position creation performance"""
    from database.models import Position

    positions = []
    for i in range(100):
        position = Position(
            portfolio_id=test_portfolio.portfolio_id,
            symbol=f"TEST{i}USDT",
            side="LONG",
            quantity=Decimal("1.0"),
            entry_price=Decimal("100.00")
        )
        positions.append(position)

    with benchmark_timer() as timer:
        db_session.add_all(positions)
        await db_session.commit()

    # Assert bulk insert is fast
    timer.assert_faster_than(1000)  # < 1 second for 100 rows
```

### Test Markers

```python
# Mark test types
@pytest.mark.unit          # Fast unit test
@pytest.mark.integration   # Database integration test
@pytest.mark.slow          # Slow-running test
@pytest.mark.benchmark     # Performance benchmark

# Run specific markers
pytest -m "unit"           # Only unit tests
pytest -m "integration"    # Only integration tests
pytest -m "not slow"       # Exclude slow tests
```

---

## Configuration

### Environment Variables

Test database configuration via environment variables:

```bash
# PostgreSQL Test Database
export TEST_DB_HOST=localhost
export TEST_DB_PORT=5434
export TEST_DB_NAME=cryptobot_test
export TEST_DB_USER=cryptobot_test
export TEST_DB_PASSWORD=test_password_123

# TimescaleDB Test Database
export TIMESCALE_TEST_DB_HOST=localhost
export TIMESCALE_TEST_DB_PORT=5435
export TIMESCALE_TEST_DB_NAME=market_data_test
export TIMESCALE_TEST_DB_USER=cryptobot_test
export TIMESCALE_TEST_DB_PASSWORD=test_password_123

# Redis Test Instance
export TEST_REDIS_HOST=localhost
export TEST_REDIS_PORT=6380
```

### Pytest Configuration

```ini
# pytest.ini
[pytest]
markers =
    unit: Fast unit tests (no database)
    integration: Integration tests (with database)
    slow: Slow-running tests
    benchmark: Performance benchmarks

# Default: run all except slow tests
addopts = -v -m "not slow"

# Async support
asyncio_mode = auto
```

---

## Performance Optimization

### Speed Comparison

| Test Type | Database | Avg Time | Isolation Method |
|-----------|----------|----------|------------------|
| Unit | None | 1-5 ms | N/A |
| Integration | PostgreSQL | 50-200 ms | Transaction rollback |
| E2E | Full stack | 1-5 seconds | Fresh containers |

### Optimization Tips

1. **Use transaction rollback** instead of truncating tables
2. **tmpfs storage** keeps data in RAM (5-10x faster)
3. **Disable connection pooling** for tests (NullPool)
4. **Run tests in parallel**: `pytest -n auto`
5. **Mark slow tests**: Exclude with `-m "not slow"`

### Parallel Testing

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run in parallel
pytest services/trading-engine/tests/ -n auto

# Specify worker count
pytest services/trading-engine/tests/ -n 4
```

---

## Troubleshooting

### Database Connection Errors

```
Error: connection to server at "localhost" (127.0.0.1), port 5434 failed
```

**Solution:**
```bash
# Check if test databases are running
docker-compose -f docker-compose.test.yml ps

# Start test databases
./scripts/test-db-start.sh

# Check health
docker ps | grep test
```

### Port Already in Use

```
Error: Bind for 0.0.0.0:5434 failed: port is already allocated
```

**Solution:**
```bash
# Find process using port
lsof -i :5434

# Kill existing container
docker stop crypto-bot-test-postgres

# Or clean everything
./scripts/test-db-clean.sh
./scripts/test-db-start.sh
```

### Tests Failing Intermittently

**Cause:** Test isolation issues (tests affecting each other)

**Solution:**
```python
# Use transaction rollback fixtures
async def test_isolated(async_db_session):
    # Changes automatically rolled back
    pass

# Or explicitly clean database
async def test_clean(clean_database):
    # Tables truncated before test
    pass
```

### Slow Test Performance

```bash
# Profile tests to find slow ones
pytest services/trading-engine/tests/ --durations=10

# Mark slow tests
@pytest.mark.slow
async def test_expensive_operation():
    pass

# Exclude slow tests
pytest -m "not slow"
```

### Import Errors

```
Error: No module named 'database'
```

**Solution:**
```python
# Add to conftest.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
```

---

## CI/CD Integration

### GitHub Actions

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
          pip install -r requirements-test.txt

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

## Best Practices

### 1. Test Isolation

```python
# ✓ Good: Use transaction rollback
async def test_create_user(async_db_session):
    user = User(name="test")
    async_db_session.add(user)
    await async_db_session.commit()
    # Automatically rolled back

# ✗ Bad: Manual cleanup (error-prone)
async def test_create_user_bad(db_session):
    user = User(name="test")
    db_session.add(user)
    db_session.commit()
    db_session.delete(user)  # Might not run if test fails
```

### 2. Test Data Management

```python
# ✓ Good: Use fixtures for test data
@pytest.fixture
async def sample_portfolio(db_session):
    portfolio = Portfolio(...)
    db_session.add(portfolio)
    await db_session.commit()
    return portfolio

# ✗ Bad: Create data in each test (duplicated)
async def test_something(db_session):
    portfolio = Portfolio(...)  # Repeated in every test
```

### 3. Async/Await Consistency

```python
# ✓ Good: Consistent async usage
@pytest.mark.integration
async def test_async_operation(async_db_session):
    result = await async_db_session.execute(...)
    await async_db_session.commit()

# ✗ Bad: Mixing sync/async incorrectly
def test_mixed(db_session):
    result = await db_session.execute(...)  # Error!
```

### 4. Clear Test Names

```python
# ✓ Good: Descriptive names
def test_create_position_with_valid_data_succeeds():
    pass

def test_create_position_with_negative_quantity_raises_validation_error():
    pass

# ✗ Bad: Vague names
def test_position_1():
    pass
```

---

## Coverage Goals

| Component | Target Coverage | Current |
|-----------|----------------|---------|
| Trading Engine | 80% | TBD |
| Portfolio Manager | 80% | TBD |
| Market Data Service | 75% | TBD |
| Technical Analysis | 80% | TBD |
| API Gateway | 70% | TBD |

### Checking Coverage

```bash
# Generate coverage report
pytest services/trading-engine/tests/ --cov=app --cov-report=term-missing

# View in browser
pytest services/trading-engine/tests/ --cov=app --cov-report=html
open htmlcov/index.html

# Coverage badge
pytest services/trading-engine/tests/ --cov=app --cov-report=term | grep TOTAL
```

---

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [SQLAlchemy testing guide](https://docs.sqlalchemy.org/en/latest/core/testing.html)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Docker Compose](https://docs.docker.com/compose/)

---

## Summary

**Test Database Strategy:**
- Docker-based PostgreSQL and TimescaleDB on separate ports
- Transaction rollback for test isolation
- tmpfs storage for maximum performance
- Shared fixtures for consistency across services

**Performance:**
- Unit tests: <5ms (no database)
- Integration tests: 50-200ms (with database)
- Full test suite: <2 minutes

**Usage:**
```bash
./scripts/test-db-start.sh
pytest services/trading-engine/tests/ --cov=app
./scripts/test-db-stop.sh
```

---

**Version:** 1.0
**Last Updated:** 2025-11-22
**Maintained by:** DBA Team
