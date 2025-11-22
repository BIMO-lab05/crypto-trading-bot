# Integration Tests - Quick Start Guide

## Prerequisites (5 minutes)

### 1. Install Dependencies
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine
pip install respx==0.20.0  # New dependency for HTTP mocking
# or
pip install -r requirements.txt
```

### 2. Start PostgreSQL
```bash
# From project root
docker-compose up -d postgres

# Verify
docker ps | grep postgres
```

### 3. Verify Database Connection
```bash
# Test connection
docker exec -it crypto-bot-postgres psql -U cryptobot -d trading_engine -c "SELECT 1;"
```

## Running Tests

### Quick Test Run (Recommended First Try)
```bash
# Run just one test to verify everything works
pytest tests/integration/test_trading_flow.py::TestCompleteTradingFlows::test_complete_buy_flow -v -s
```

### Run All Integration Tests
```bash
pytest tests/integration/test_trading_flow.py -v
```

### Run with Visual Progress
```bash
pytest tests/integration/test_trading_flow.py -v -s
```

### Run Specific Test Class
```bash
# Test only risk management
pytest tests/integration/test_trading_flow.py::TestRiskManagementIntegration -v

# Test only database consistency
pytest tests/integration/test_trading_flow.py::TestDatabaseConsistency -v

# Test only complete flows
pytest tests/integration/test_trading_flow.py::TestCompleteTradingFlows -v
```

### Run with Coverage Report
```bash
pytest tests/integration/test_trading_flow.py --cov=app --cov-report=html

# View report
python -m http.server 8080 -d htmlcov/
# Open browser to http://localhost:8080
```

## Expected Output

### Successful Test Run
```
============================= test session starts ==============================
collected 25 items

tests/integration/test_trading_flow.py::TestCompleteTradingFlows::test_complete_buy_flow PASSED                 [  4%]
tests/integration/test_trading_flow.py::TestCompleteTradingFlows::test_complete_sell_flow PASSED                [  8%]
tests/integration/test_trading_flow.py::TestCompleteTradingFlows::test_profitable_trade_complete_cycle PASSED   [ 12%]
tests/integration/test_trading_flow.py::TestRiskManagementIntegration::test_insufficient_balance_blocks_trade PASSED [ 16%]
...
======================== 25 passed in 12.34s ===============================
```

## Common Issues

### Issue: ModuleNotFoundError
```
ModuleNotFoundError: No module named 'app'
```
**Fix:** Run from trading-engine directory
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine
pytest tests/integration/test_trading_flow.py -v
```

### Issue: Database Connection Error
```
asyncpg.exceptions.InvalidCatalogNameError: database "trading_engine" does not exist
```
**Fix:** Create database
```bash
docker exec -it crypto-bot-postgres psql -U cryptobot -d postgres -c "CREATE DATABASE trading_engine;"
```

### Issue: respx Not Found
```
ModuleNotFoundError: No module named 'respx'
```
**Fix:** Install respx
```bash
pip install respx==0.20.0
```

### Issue: Import Error on Fixtures
```
fixture 'trading_system' not found
```
**Fix:** Ensure conftest.py is in same directory
```bash
ls tests/integration/conftest.py  # Should exist
```

## Test Timing

Expected execution times:
- Single test: ~0.5s
- Test class (3-4 tests): ~2-3s
- All tests (25 tests): ~10-15s

If tests are slower:
- Check database connection latency
- Ensure PostgreSQL has resources
- Consider running fewer tests in parallel

## Debugging Failed Tests

### View Test Output
```bash
# Show print statements and logs
pytest tests/integration/test_trading_flow.py -v -s

# Show even more detail
pytest tests/integration/test_trading_flow.py -vv -s
```

### Run Single Failing Test
```bash
pytest tests/integration/test_trading_flow.py::TestCompleteTradingFlows::test_complete_buy_flow -v -s
```

### Debug with pdb
```bash
# Add breakpoint in test code
import pdb; pdb.set_trace()

# Run test
pytest tests/integration/test_trading_flow.py::TestCompleteTradingFlows::test_complete_buy_flow -s
```

## Environment Variables

Optional environment variables for testing:

```bash
# Database configuration
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5433
export POSTGRES_DB=trading_engine
export POSTGRES_USER=cryptobot
export POSTGRES_PASSWORD=your_password

# Service URLs (mocked by default)
export TECHNICAL_ANALYSIS_URL=http://localhost:8004
export BYBIT_CONNECTOR_URL=http://localhost:8001

# Run tests
pytest tests/integration/test_trading_flow.py -v
```

## CI/CD Integration

### GitHub Actions Snippet
```yaml
- name: Run Integration Tests
  run: |
    cd services/trading-engine
    pip install -r requirements.txt
    pytest tests/integration/test_trading_flow.py -v --cov=app --cov-report=xml
```

### Docker Command
```bash
docker exec trading-engine pytest tests/integration/test_trading_flow.py -v
```

## Next Steps

1. ✅ Run quick test to verify setup
2. ✅ Run all tests to ensure full functionality
3. ✅ Check coverage report
4. ✅ Review any failed tests
5. ✅ Integrate into CI/CD pipeline

## Help

For detailed information, see:
- `INTEGRATION_TEST_REPORT.md` - Full implementation details
- `README.md` - Comprehensive test documentation
- `test_trading_flow.py` - Test code with inline comments
- `conftest.py` - Fixture documentation
- `helpers.py` - Utility function documentation

---

**Quick Commands Reference:**

```bash
# Basic run
pytest tests/integration/test_trading_flow.py -v

# With coverage
pytest tests/integration/test_trading_flow.py --cov=app --cov-report=html

# Single test
pytest tests/integration/test_trading_flow.py::TestCompleteTradingFlows::test_complete_buy_flow -v

# Debug mode
pytest tests/integration/test_trading_flow.py -v -s

# Specific class
pytest tests/integration/test_trading_flow.py::TestRiskManagementIntegration -v
```
