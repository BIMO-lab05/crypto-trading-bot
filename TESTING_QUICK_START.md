# Testing Quick Start Guide
## Run Tests and Check Coverage - Fast Reference

**Date:** 2025-11-21
**Purpose:** Quick commands to run tests and analyze coverage

---

## Quick Commands

### Run All Tests (Fast Check)
```bash
# Quick coverage analysis for all services
python quick_coverage.py

# Output shows: Service | Test Files | Coverage | Status
```

### Run Tests for Specific Service
```bash
# Portfolio Manager
cd services/portfolio-manager
pytest tests/ --cov=app --cov-report=term -v

# Notification Service
cd services/notification-service
pytest tests/ --cov=app --cov-report=term -v

# API Gateway
cd services/api-gateway
pytest tests/ --cov=app --cov-report=term -v
```

### Generate HTML Coverage Report
```bash
# For single service
cd services/portfolio-manager
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html

# For all services
pytest services/*/tests/ --cov=services --cov-report=html
open htmlcov/index.html
```

### Run Tests with Verbose Output
```bash
# Show test names and results
pytest tests/ -v

# Show test names and print statements
pytest tests/ -vv -s

# Stop on first failure
pytest tests/ -x
```

---

## New Tests Created (November 21, 2025)

### 1. Portfolio Manager - Transaction Tests
**File:** `/mnt/d/Bimo_max/crypto-trading-bot/services/portfolio-manager/tests/test_transaction_manager.py`

**Coverage:** 60+ test cases

**Test Classes:**
- `TestTransactionExecution` - Buy/sell transaction logic
- `TestTransactionHistory` - History tracking and retrieval
- `TestTransactionValidation` - Input validation
- `TestRebalancingRecommendations` - Portfolio rebalancing
- `TestConcurrentTransactions` - Concurrent operation handling

**Run Tests:**
```bash
cd services/portfolio-manager
pytest tests/test_transaction_manager.py -v
```

### 2. Notification Service - Complete Test Suite
**Files:**
- `/mnt/d/Bimo_max/crypto-trading-bot/services/notification-service/tests/conftest.py`
- `/mnt/d/Bimo_max/crypto-trading-bot/services/notification-service/tests/test_main.py`

**Coverage:** 90+ test cases

**Test Classes:**
- `TestHealthEndpoint` - Health check functionality
- `TestConfigurationEndpoint` - Configuration retrieval
- `TestTradeNotificationEndpoint` - Trade alerts
- `TestProfitLossNotificationEndpoint` - P&L notifications
- `TestDailyLimitNotificationEndpoint` - Daily limit alerts
- `TestErrorNotificationEndpoint` - Error notifications
- `TestStartupNotificationEndpoint` - Startup messages
- `TestDailySummaryNotificationEndpoint` - Daily summaries
- `TestNotificationTestEndpoint` - Testing functionality
- `TestCORSConfiguration` - CORS middleware
- `TestErrorHandling` - Error scenarios

**Run Tests:**
```bash
cd services/notification-service
pytest tests/test_main.py -v
```

---

## Coverage Analysis

### Check Coverage for Specific Service
```bash
cd services/<service-name>

# Terminal output only
pytest tests/ --cov=app --cov-report=term

# Show missing lines
pytest tests/ --cov=app --cov-report=term-missing

# Generate HTML report
pytest tests/ --cov=app --cov-report=html
```

### Check Overall System Coverage
```bash
# From project root
pytest services/*/tests/ --cov=services --cov-report=term

# With detailed HTML report
pytest services/*/tests/ --cov=services --cov-report=html
```

### Enforce Minimum Coverage
```bash
# Fail if coverage below 80%
pytest tests/ --cov=app --cov-fail-under=80
```

---

## Current Coverage Status

| Service | Test Files | Coverage | Tests Added | Status |
|---------|-----------|----------|-------------|---------|
| api-gateway | 4 | 50% | 0 | 🔴 IN PROGRESS |
| bybit-connector | 5 | 66% | 0 | 🟡 PLANNED |
| market-data-service | 12 | 48% | 0 | 🔴 PLANNED |
| portfolio-manager | 6 | 37% → 60%+ | 1 file (60+ tests) | 🟢 IMPROVING |
| technical-analysis | 11 | 61% | 0 | 🟡 PLANNED |
| trading-engine | 38 | ERROR | 0 | 🔴 FIX NEEDED |
| notification-service | 2 | 0% → 85%+ | 2 files (90+ tests) | 🟢 COMPLETE |
| ml-prediction-service | 4 | ERROR | 0 | 🔴 FIX NEEDED |
| sentiment-analysis-service | 4 | ERROR | 0 | 🔴 FIX NEEDED |
| risk-metrics-service | 6 | 69% | 0 | 🟡 PLANNED |

**Summary:**
- **Tests Added Today:** 150+ new test cases
- **New Test Files:** 3 files
- **Services Improved:** 2 services (Portfolio Manager, Notification Service)
- **Services Needing Attention:** 3 services (Trading Engine, ML Prediction, Sentiment Analysis)

---

## Testing Best Practices

### 1. Test Naming
```python
# Good: Descriptive and clear
def test_execute_buy_transaction_sufficient_balance_succeeds():
    pass

# Bad: Vague
def test_buy():
    pass
```

### 2. Arrange-Act-Assert Pattern
```python
def test_example():
    # Arrange: Setup test data
    portfolio = Portfolio(balance=10000)

    # Act: Execute the function
    result = portfolio.can_afford(5000)

    # Assert: Verify outcome
    assert result is True
```

### 3. Use Fixtures
```python
@pytest.fixture
def sample_portfolio():
    return Portfolio(balance=10000, assets=[])

def test_with_fixture(sample_portfolio):
    assert sample_portfolio.balance == 10000
```

### 4. Mock External Dependencies
```python
@pytest.mark.asyncio
async def test_api_call(mock_http_client):
    mock_http_client.get.return_value = {"status": "success"}

    service = MyService(mock_http_client)
    result = await service.fetch_data()

    assert result["status"] == "success"
```

---

## Troubleshooting

### Test Errors

**Import Errors:**
```bash
# Check Python path
python -c "import sys; print('\n'.join(sys.path))"

# Install dependencies
pip install -r requirements.txt
```

**Module Not Found:**
```bash
# Add service to Python path
export PYTHONPATH="${PYTHONPATH}:/path/to/service"

# Or install in editable mode
cd services/<service-name>
pip install -e .
```

**Async Test Errors:**
```bash
# Install pytest-asyncio
pip install pytest-asyncio

# Mark async tests
@pytest.mark.asyncio
async def test_async_function():
    pass
```

### Coverage Errors

**Coverage Not Working:**
```bash
# Install coverage tools
pip install pytest-cov coverage

# Verify installation
pytest --version
coverage --version
```

**Coverage Shows 0%:**
```bash
# Check coverage source paths
pytest tests/ --cov=app --cov-report=term -v

# Verify test discovery
pytest --collect-only
```

---

## Next Steps

### Immediate Actions (This Week)
1. **Fix Test Errors** - Trading Engine, ML Prediction, Sentiment Analysis
2. **Complete Portfolio Manager** - Add 5 more test files
3. **Test API Gateway WebSocket** - Create WebSocket test suite
4. **Validate Market Data** - Create data validation tests

### Short-term Goals (Next 2 Weeks)
1. Bring all services to 80%+ coverage
2. Create integration test suite
3. Set up CI/CD pipeline with coverage checks
4. Generate coverage badges

### Long-term Goals (1-2 Months)
1. Maintain 85%+ coverage across all services
2. Implement end-to-end test scenarios
3. Add performance testing
4. Create mutation testing framework

---

## Documentation Links

- **Full Testing Strategy:** `/mnt/d/Bimo_max/crypto-trading-bot/docs/TESTING_STRATEGY.md`
- **Coverage Report:** `/mnt/d/Bimo_max/crypto-trading-bot/TEST_COVERAGE_IMPROVEMENT_REPORT.md`
- **Test Files:**
  - Portfolio Manager: `services/portfolio-manager/tests/test_transaction_manager.py`
  - Notification Service: `services/notification-service/tests/test_main.py`

---

## Quick Reference Card

```
╔══════════════════════════════════════════════════════════════╗
║                    TESTING QUICK REFERENCE                    ║
╠══════════════════════════════════════════════════════════════╣
║ Run all tests:         python quick_coverage.py              ║
║ Single service:        cd services/<name> && pytest tests/   ║
║ With coverage:         pytest tests/ --cov=app               ║
║ HTML report:           pytest tests/ --cov=app --cov-report=html ║
║ Verbose:               pytest tests/ -v                       ║
║ Stop on failure:       pytest tests/ -x                       ║
║ Show prints:           pytest tests/ -s                       ║
║ Specific test:         pytest tests/test_file.py::test_name  ║
╠══════════════════════════════════════════════════════════════╣
║ Coverage target:       80%+ for all services                 ║
║ Test files added:      3 files, 150+ tests                   ║
║ Services improved:     Portfolio Manager, Notification       ║
║ Services need fix:     Trading Engine, ML, Sentiment         ║
╚══════════════════════════════════════════════════════════════╝
```

---

**Last Updated:** 2025-11-21 23:30 UTC
**Next Update:** Check TEST_COVERAGE_IMPROVEMENT_REPORT.md for weekly updates
**Questions:** Refer to TESTING_STRATEGY.md for detailed information
