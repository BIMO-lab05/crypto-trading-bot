# Database Integration Tests

## Overview

Comprehensive database persistence tests for the Trading Engine service. These tests verify that all database operations work correctly with real PostgreSQL database.

## Test Coverage

### Position Persistence Tests (`TestPositionPersistence`)
- ✅ Create position persists to database
- ✅ Update position price persists
- ✅ Close position persists
- ✅ Get position by ID
- ✅ Get open positions filtered by portfolio
- ✅ Concurrent position updates
- ✅ Position with null optional fields

**Coverage:** 7 test cases

### Trade Persistence Tests (`TestTradePersistence`)
- ✅ Log trade persists to database
- ✅ Trade foreign key constraints enforced
- ✅ Multiple trades for same position

**Coverage:** 3 test cases

### Portfolio Persistence Tests (`TestPortfolioPersistence`)
- ✅ Create portfolio persists
- ✅ Get existing portfolio (no duplication)
- ✅ Update portfolio balance persists
- ✅ Portfolio transaction isolation

**Coverage:** 4 test cases

### Database Rollback Tests (`TestDatabaseRollback`)
- ✅ Position creation rollback on error
- ✅ Trade logging rollback on error

**Coverage:** 2 test cases

### Database Performance Tests (`TestDatabasePerformance`)
- ✅ Bulk position creation performance (100 positions < 2s)
- ✅ Query performance with large dataset (1000 positions < 200ms)
- ✅ Database index usage verification

**Coverage:** 3 test cases

### Data Integrity Tests (`TestDataIntegrity`)
- ✅ Position quantity constraint (no negative)
- ✅ Position side constraint (LONG/SHORT only)
- ✅ Portfolio foreign key cascade delete

**Coverage:** 3 test cases

**Total:** 22 comprehensive test cases

## Prerequisites

### 1. PostgreSQL Database Running

```bash
# Start PostgreSQL via Docker Compose (from project root)
docker-compose up -d postgres

# Verify PostgreSQL is running
docker ps | grep postgres
```

### 2. Test Database Setup

```bash
# Connect to PostgreSQL
docker exec -it crypto-bot-postgres psql -U cryptobot -d postgres

# Create test database (if not exists)
CREATE DATABASE cryptobot_test;

# Verify
\l cryptobot_test

# Exit
\q
```

### 3. Environment Configuration

Ensure `.env.test` file exists with test database credentials:

```bash
# services/trading-engine/.env.test
TEST_DB_HOST=localhost
TEST_DB_PORT=5432
TEST_DB_NAME=cryptobot_test
TEST_DB_USER=cryptobot
TEST_DB_PASSWORD=cryptobot_dev_password
```

### 4. Python Dependencies

```bash
# From trading-engine directory
pip install -r requirements.txt

# Verify pytest-asyncio is installed
pip list | grep pytest-asyncio
```

## Running Tests

### Run All Integration Tests

```bash
# From trading-engine directory
pytest tests/integration/test_database_persistence.py -v

# Or with marker
pytest -m integration -v
```

### Run Specific Test Class

```bash
# Test position persistence only
pytest tests/integration/test_database_persistence.py::TestPositionPersistence -v

# Test performance only
pytest tests/integration/test_database_persistence.py::TestDatabasePerformance -v
```

### Run Specific Test Case

```bash
pytest tests/integration/test_database_persistence.py::TestPositionPersistence::test_create_position_persists_to_db -v
```

### Run with Coverage Report

```bash
# Generate coverage report
pytest tests/integration/test_database_persistence.py \
    --cov=app.repositories \
    --cov-report=term \
    --cov-report=html \
    -v

# View HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Run Performance Tests Only

```bash
# Performance tests are marked as 'slow'
pytest tests/integration/test_database_persistence.py -m slow -v
```

### Skip Performance Tests

```bash
# Run all except slow tests
pytest tests/integration/test_database_persistence.py -m "not slow" -v
```

### Run with SQL Query Debugging

```bash
# Set DB_ECHO=true to see all SQL queries
DB_ECHO=true pytest tests/integration/test_database_persistence.py -v -s
```

## Test Database Cleanup

Tests use **automatic cleanup** via fixtures:

- `setup_test_database` (session-scoped): Creates schema before all tests, drops after
- `clean_database` (function-scoped): Truncates tables before each test
- Transaction rollback: Each test runs in a transaction that's rolled back

No manual cleanup needed!

## Troubleshooting

### Error: Database Connection Failed

```
asyncpg.exceptions.InvalidCatalogNameError: database "cryptobot_test" does not exist
```

**Solution:** Create test database manually:

```bash
docker exec -it crypto-bot-postgres psql -U cryptobot -d postgres -c "CREATE DATABASE cryptobot_test;"
```

### Error: Permission Denied

```
asyncpg.exceptions.InsufficientPrivilegeError
```

**Solution:** Grant privileges:

```bash
docker exec -it crypto-bot-postgres psql -U cryptobot -d postgres
GRANT ALL PRIVILEGES ON DATABASE cryptobot_test TO cryptobot;
```

### Error: Tables Don't Exist

```
asyncpg.exceptions.UndefinedTableError: relation "positions" does not exist
```

**Solution:** Tests create tables automatically via `setup_test_database` fixture. If issue persists, check database models in `/shared/database/models.py`.

### Error: Foreign Key Violation

```
asyncpg.exceptions.ForeignKeyViolationError
```

**Solution:** This is expected in constraint tests. Check that test is using `pytest.raises()` to catch these errors.

### Tests Running Slowly

**Solution:**
1. Use connection pooling (already configured)
2. Run performance tests separately: `pytest -m slow`
3. Increase pool size in `.env.test`: `DB_POOL_SIZE=20`

## Test Execution Time

Expected execution times:

- **Fast tests** (17 tests): ~5-10 seconds
- **Slow tests** (3 tests): ~5-15 seconds
- **All tests** (22 tests): ~10-25 seconds

Performance benchmarks:
- Bulk create 100 positions: < 2 seconds
- Query 1000 positions: < 200ms

## Database Schema Verification

Tests verify the following tables exist and have correct schema:

- `portfolios` - Portfolio accounts
- `positions` - Trading positions
- `trades` - Trade execution records
- `portfolio_snapshots` - Portfolio state history

Schema is defined in: `/shared/database/models.py`

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Database Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: cryptobot_test
          POSTGRES_USER: cryptobot
          POSTGRES_PASSWORD: cryptobot_dev_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          cd services/trading-engine
          pip install -r requirements.txt

      - name: Run database tests
        env:
          TEST_DB_HOST: localhost
          TEST_DB_PORT: 5432
          TEST_DB_NAME: cryptobot_test
          TEST_DB_USER: cryptobot
          TEST_DB_PASSWORD: cryptobot_dev_password
        run: |
          cd services/trading-engine
          pytest tests/integration/test_database_persistence.py \
            --cov=app.repositories \
            --cov-report=xml \
            -v

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Coverage Goals

- **Target:** >95% coverage for `app.repositories`
- **Current:** Run coverage report to check

```bash
pytest tests/integration/test_database_persistence.py --cov=app.repositories --cov-report=term
```

## Next Steps

1. **Run the tests:** `pytest tests/integration/test_database_persistence.py -v`
2. **Check coverage:** Add `--cov` flag
3. **Review failures:** Fix any database schema issues
4. **Extend tests:** Add more edge cases as needed

## Contributing

When adding new database operations:

1. Add test case to appropriate test class
2. Follow naming convention: `test_<operation>_<scenario>_<expected>`
3. Use fixtures for test data
4. Verify both success and failure cases
5. Check database state directly (not just via repositories)
6. Add documentation to this README

## Questions?

Check the project documentation:
- Database schema: `/shared/database/models.py`
- Repository implementation: `/services/trading-engine/app/repositories.py`
- Main project docs: `/docs/`
