# Testing Strategy - Crypto Trading Bot
## Comprehensive Test Coverage Plan

**Date Created:** 2025-11-21
**Target Coverage:** 80%+ across all services
**Testing Framework:** pytest with coverage.py

---

## Executive Summary

This document outlines the comprehensive testing strategy to achieve 80%+ test coverage across all 10 backend services. Our multi-layered approach ensures production readiness through unit, integration, and end-to-end testing.

### Current Coverage Status (Baseline - Nov 20, 2025)

| Service | Test Files | Coverage | Status | Priority |
|---------|-----------|----------|---------|----------|
| api-gateway | 4 | 50% | LOW | HIGH |
| bybit-connector | 5 | 66% | MEDIUM | HIGH |
| market-data-service | 12 | 48% | LOW | HIGH |
| portfolio-manager | 2 | 37% | LOW | CRITICAL |
| technical-analysis | 11 | 61% | MEDIUM | MEDIUM |
| trading-engine | 38 | N/A | ERROR | CRITICAL |
| notification-service | 0 | 0% | NO_TESTS | MEDIUM |
| ml-prediction-service | 4 | N/A | ERROR | MEDIUM |
| sentiment-analysis-service | 4 | N/A | ERROR | MEDIUM |
| risk-metrics-service | 6 | 69% | MEDIUM | MEDIUM |

**Summary:**
- Services with Tests: 9/10
- Services with 80%+ Coverage: 0/10
- Services Needing Tests: 1/10
- Services with Errors: 3/10

---

## Testing Pyramid Strategy

```
                 ╱╲
                ╱  ╲
               ╱ E2E ╲          10% - End-to-End Tests
              ╱--------╲
             ╱          ╲
            ╱Integration╲        30% - Integration Tests
           ╱--------------╲
          ╱                ╲
         ╱   Unit Tests     ╲    60% - Unit Tests
        ╱____________________╲
```

### 1. Unit Tests (60% of total tests)
**Purpose:** Test individual functions, classes, and methods in isolation

**Coverage Goals:**
- All business logic functions: 100%
- All validation logic: 100%
- All calculation methods: 100%
- Error handling paths: 90%+
- Edge cases: 80%+

**Tools:**
- pytest
- pytest-mock
- pytest-cov
- faker (test data generation)

**Example Structure:**
```python
# tests/unit/test_calculator.py
class TestRiskCalculator:
    def test_calculate_position_size_valid_input(self):
        """Test position size calculation with valid parameters"""
        pass

    def test_calculate_position_size_zero_capital_raises_error(self):
        """Test error handling for zero capital"""
        pass

    def test_calculate_position_size_exceeds_max_returns_max(self):
        """Test max position size enforcement"""
        pass
```

### 2. Integration Tests (30% of total tests)
**Purpose:** Test interaction between components and external services

**Coverage Goals:**
- Database operations: 100%
- RabbitMQ messaging: 100%
- Service-to-service communication: 90%+
- API endpoint flows: 90%+

**Tools:**
- pytest-asyncio
- Testcontainers (Docker containers for tests)
- httpx (async HTTP client)
- aio-pika (RabbitMQ testing)

**Example Structure:**
```python
# tests/integration/test_market_data_flow.py
class TestMarketDataFlow:
    @pytest.mark.asyncio
    async def test_fetch_store_retrieve_flow(self):
        """Test complete flow: fetch from Bybit -> store in DB -> retrieve"""
        pass
```

### 3. End-to-End Tests (10% of total tests)
**Purpose:** Test complete user workflows across multiple services

**Coverage Goals:**
- Critical trading flows: 100%
- Portfolio management flows: 100%
- Risk management workflows: 90%+

**Tools:**
- pytest
- docker-compose (test environment)
- Custom E2E framework

**Example Structure:**
```python
# tests/e2e/test_trading_workflow.py
class TestCompleteTradingWorkflow:
    @pytest.mark.e2e
    async def test_signal_to_execution_flow(self):
        """Test: Signal generation -> Risk check -> Order execution -> Portfolio update"""
        pass
```

---

## Service-Specific Test Plans

### 1. API Gateway (Current: 50% → Target: 85%)

**Missing Coverage:**
- [ ] WebSocket connection handling (WebSocketManager class)
- [ ] WebSocket broadcast functionality
- [ ] Authentication middleware edge cases
- [ ] ML prediction endpoints
- [ ] Sentiment analysis endpoints
- [ ] Error responses for all endpoints
- [ ] Rate limiting behavior

**New Test Files Needed:**
```
tests/
├── test_websocket_manager.py       # WebSocket functionality
├── test_auth_middleware.py         # Authentication edge cases
├── test_ml_endpoints.py            # ML prediction routes
├── test_sentiment_endpoints.py     # Sentiment analysis routes
├── test_error_handling.py          # Comprehensive error scenarios
└── test_rate_limiting.py           # Rate limit enforcement
```

**Priority Tests:**
1. WebSocket connection lifecycle
2. Enhanced trading signal aggregation
3. ML prediction endpoint validation
4. Authentication token validation
5. CORS configuration

### 2. Bybit Connector (Current: 66% → Target: 85%)

**Missing Coverage:**
- [ ] Circuit breaker failure scenarios
- [ ] WebSocket reconnection logic
- [ ] Order execution error handling
- [ ] Rate limit handling
- [ ] Connection timeout scenarios
- [ ] Order status polling

**New Test Files Needed:**
```
tests/
├── test_circuit_breaker.py         # Circuit breaker patterns
├── test_websocket_handler.py       # WebSocket edge cases
├── test_order_execution.py         # Order execution flows
├── test_rate_limiting.py           # Rate limit handling
└── test_error_scenarios.py         # Comprehensive errors
```

**Priority Tests:**
1. Circuit breaker open/close/half-open states
2. WebSocket reconnection after disconnect
3. Order rejection handling
4. API key validation
5. Network timeout handling

### 3. Market Data Service (Current: 48% → Target: 85%)

**Missing Coverage:**
- [ ] Data fetcher error handling
- [ ] Cache invalidation logic
- [ ] Database connection pooling
- [ ] Scheduler task execution
- [ ] Data quality validation
- [ ] Historical data backfill

**New Test Files Needed:**
```
tests/
├── unit/
│   ├── test_data_validator.py      # Data quality checks
│   ├── test_cache_manager.py       # Cache operations
│   └── test_scheduler.py           # Scheduled tasks
├── integration/
│   ├── test_database_operations.py # Full DB workflow
│   └── test_data_pipeline.py       # Fetch -> Store -> Retrieve
```

**Priority Tests:**
1. Data validation (missing values, outliers)
2. Cache hit/miss scenarios
3. Database transaction handling
4. Scheduler task failures
5. Historical data integrity

### 4. Portfolio Manager (Current: 37% → Target: 85%) **CRITICAL**

**Missing Coverage:**
- [ ] Transaction processing logic
- [ ] Position tracking updates
- [ ] P&L calculations
- [ ] Balance validation
- [ ] Concurrency handling
- [ ] Transaction rollback scenarios

**New Test Files Needed:**
```
tests/
├── unit/
│   ├── test_portfolio_calculator.py    # P&L calculations
│   ├── test_position_manager.py        # Position tracking
│   ├── test_transaction_validator.py   # Transaction validation
│   └── test_balance_manager.py         # Balance operations
├── integration/
│   ├── test_transaction_flow.py        # Complete transaction flow
│   ├── test_concurrent_operations.py   # Concurrency tests
│   └── test_database_consistency.py    # Data integrity
```

**Priority Tests:**
1. P&L calculation accuracy
2. Concurrent transaction handling
3. Balance insufficient scenarios
4. Transaction rollback on errors
5. Position update consistency

### 5. Technical Analysis (Current: 61% → Target: 85%)

**Missing Coverage:**
- [ ] Indicator calculation edge cases
- [ ] Signal generation logic
- [ ] Multi-timeframe analysis
- [ ] Indicator aggregation
- [ ] Historical indicator calculations

**New Test Files Needed:**
```
tests/
├── unit/
│   ├── test_rsi_calculator.py          # RSI edge cases
│   ├── test_macd_calculator.py         # MACD edge cases
│   ├── test_bollinger_bands.py         # Bollinger calculations
│   ├── test_signal_aggregator.py       # Signal logic
│   └── test_multi_timeframe.py         # MTF analysis
```

**Priority Tests:**
1. RSI with insufficient data
2. MACD crossover detection
3. Bollinger band breakout logic
4. Signal confidence calculation
5. Multi-timeframe alignment

### 6. Trading Engine (Current: ERROR → Target: 85%) **CRITICAL**

**Missing Coverage:**
- [ ] Strategy execution logic
- [ ] Risk checks before orders
- [ ] Order management
- [ ] Signal processing
- [ ] Position sizing

**New Test Files Needed:**
```
tests/
├── unit/
│   ├── test_strategy_executor.py       # Strategy logic
│   ├── test_risk_validator.py          # Risk checks
│   ├── test_order_manager.py           # Order handling
│   ├── test_position_sizer.py          # Position sizing
│   └── test_signal_processor.py        # Signal processing
├── integration/
│   ├── test_trading_workflow.py        # Complete trading flow
│   └── test_strategy_execution.py      # Strategy tests
```

**Priority Tests:**
1. Risk validation before trade
2. Position sizing calculation
3. Order submission logic
4. Strategy signal processing
5. Error recovery

### 7. Notification Service (Current: 0% → Target: 85%) **NEW**

**Missing Coverage:**
- [ ] Email notification sending
- [ ] Telegram message delivery
- [ ] Alert priority handling
- [ ] Notification templating
- [ ] Rate limiting notifications

**New Test Files Needed:**
```
tests/
├── test_config.py                  # Configuration
├── test_email_sender.py            # Email functionality
├── test_telegram_sender.py         # Telegram bot
├── test_alert_manager.py           # Alert handling
├── test_template_engine.py         # Template rendering
└── test_rate_limiter.py            # Notification rate limiting
```

**Priority Tests:**
1. Email SMTP connection
2. Telegram bot API calls
3. Alert priority filtering
4. Template rendering
5. Rate limit enforcement

### 8. ML Prediction Service (Current: ERROR → Target: 80%)

**Missing Coverage:**
- [ ] Model loading/initialization
- [ ] Prediction generation
- [ ] Model training workflow
- [ ] Feature engineering
- [ ] Model evaluation

**New Test Files Needed:**
```
tests/
├── unit/
│   ├── test_feature_engineer.py        # Feature creation
│   ├── test_model_manager.py           # Model lifecycle
│   ├── test_predictor.py               # Prediction logic
│   └── test_model_evaluator.py         # Model metrics
├── integration/
│   └── test_prediction_pipeline.py     # Full pipeline
```

**Priority Tests:**
1. Model initialization
2. Prediction with valid input
3. Feature engineering accuracy
4. Model retraining trigger
5. Prediction confidence scores

### 9. Sentiment Analysis Service (Current: ERROR → Target: 80%)

**Missing Coverage:**
- [ ] News fetching
- [ ] Sentiment scoring
- [ ] Social media analysis
- [ ] Sentiment aggregation
- [ ] Historical sentiment tracking

**New Test Files Needed:**
```
tests/
├── unit/
│   ├── test_news_fetcher.py            # News API
│   ├── test_sentiment_analyzer.py      # Sentiment logic
│   ├── test_social_analyzer.py         # Social media
│   └── test_aggregator.py              # Score aggregation
└── integration/
    └── test_sentiment_pipeline.py      # Full pipeline
```

**Priority Tests:**
1. News API integration
2. Sentiment scoring accuracy
3. Social media data parsing
4. Aggregation weighting
5. Historical tracking

### 10. Risk Metrics Service (Current: 69% → Target: 85%)

**Missing Coverage:**
- [ ] VaR calculation edge cases
- [ ] Sharpe ratio calculation
- [ ] Drawdown tracking
- [ ] Risk alerts triggering
- [ ] Circuit breaker logic

**New Test Files Needed:**
```
tests/
├── unit/
│   ├── test_var_calculator.py          # VaR calculations
│   ├── test_sharpe_calculator.py       # Sharpe ratio
│   ├── test_drawdown_tracker.py        # Drawdown logic
│   ├── test_alert_generator.py         # Alert creation
│   └── test_circuit_breaker.py         # Circuit breaker
```

**Priority Tests:**
1. VaR with different confidence levels
2. Sharpe ratio calculation
3. Maximum drawdown detection
4. Alert threshold triggers
5. Circuit breaker activation

---

## Test Data Management

### Fixtures Strategy

**Shared Fixtures (`conftest.py`):**
```python
# tests/conftest.py
import pytest
from faker import Faker

@pytest.fixture
def faker():
    return Faker()

@pytest.fixture
def sample_market_data():
    """Sample OHLCV data for testing"""
    return [
        {
            "timestamp": 1700000000000,
            "open": 45000.0,
            "high": 45500.0,
            "low": 44800.0,
            "close": 45200.0,
            "volume": 1000.0
        }
    ]

@pytest.fixture
def sample_portfolio():
    """Sample portfolio data"""
    return {
        "portfolio_id": "test-001",
        "balance": 100000.0,
        "positions": [],
        "equity": 100000.0
    }
```

### Database Test Data

**Strategy:**
- Use transactions for test isolation
- Clean up after each test
- Use factories for complex objects

```python
@pytest.fixture
async def db_session():
    """Provide database session with rollback"""
    async with async_session() as session:
        yield session
        await session.rollback()
```

---

## Continuous Integration Setup

### GitHub Actions Workflow

```yaml
name: Test Coverage

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: timescale/timescaledb:latest-pg14
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s

      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s

      rabbitmq:
        image: rabbitmq:3-management-alpine
        options: >-
          --health-cmd "rabbitmq-diagnostics -q ping"
          --health-interval 10s

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio

      - name: Run tests with coverage
        run: |
          pytest --cov=services --cov-report=xml --cov-report=term

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: true
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest-coverage
        name: pytest-coverage
        entry: pytest
        args: [--cov=services, --cov-fail-under=80]
        language: system
        pass_filenames: false
        always_run: true
```

---

## Coverage Reporting

### Generate HTML Reports

```bash
# Run tests with coverage
pytest --cov=services --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html
```

### Coverage Badges

Generate badges for README:
```bash
# Install coverage-badge
pip install coverage-badge

# Generate badge
coverage-badge -o coverage.svg -f
```

### Coverage Metrics Dashboard

```python
# scripts/coverage_dashboard.py
"""
Generate coverage dashboard with detailed metrics per service
"""
import coverage
import json

def generate_dashboard():
    cov = coverage.Coverage()
    cov.load()

    report = {
        "total_coverage": cov.report(),
        "services": {}
    }

    for service in SERVICES:
        service_cov = cov.get_data().measured_files()
        service_report = {
            "lines": len(service_cov),
            "covered": cov.analysis(service_cov)[1],
            "missing": cov.analysis(service_cov)[2],
            "percentage": (covered / lines * 100) if lines > 0 else 0
        }
        report["services"][service] = service_report

    return report
```

---

## Testing Best Practices

### 1. Test Naming Convention

```python
def test_<function_name>_<scenario>_<expected_result>():
    """
    Clear description of what is being tested
    """
    pass

# Examples:
def test_calculate_rsi_with_valid_data_returns_correct_value():
    pass

def test_place_order_with_insufficient_balance_raises_error():
    pass
```

### 2. Arrange-Act-Assert Pattern

```python
def test_example():
    # Arrange: Set up test data and dependencies
    portfolio = Portfolio(balance=10000)
    order = Order(symbol="BTCUSDT", quantity=1.0)

    # Act: Execute the function being tested
    result = portfolio.can_place_order(order)

    # Assert: Verify expected outcome
    assert result is True
```

### 3. Mock External Dependencies

```python
@pytest.mark.asyncio
async def test_fetch_market_data(mock_bybit_client):
    """Test market data fetching with mocked Bybit API"""
    # Mock the external API call
    mock_bybit_client.get_ticker.return_value = {
        "symbol": "BTCUSDT",
        "last_price": "45000"
    }

    # Test the service
    data_service = MarketDataService(mock_bybit_client)
    result = await data_service.fetch_ticker("BTCUSDT")

    assert result["symbol"] == "BTCUSDT"
    assert result["last_price"] == "45000"
```

### 4. Test Parametrization

```python
@pytest.mark.parametrize("rsi_value,expected_signal", [
    (20, "BUY"),      # Oversold
    (50, "NEUTRAL"),  # Neutral
    (80, "SELL"),     # Overbought
])
def test_rsi_signal_generation(rsi_value, expected_signal):
    """Test RSI signal generation for different values"""
    signal = generate_rsi_signal(rsi_value)
    assert signal == expected_signal
```

### 5. Test Error Scenarios

```python
def test_error_scenarios():
    """Test various error conditions"""
    # Test with None
    with pytest.raises(ValueError):
        calculate_position_size(None, 1000)

    # Test with negative value
    with pytest.raises(ValueError):
        calculate_position_size(-100, 1000)

    # Test with zero
    with pytest.raises(ZeroDivisionError):
        calculate_position_size(0, 1000)
```

---

## Implementation Timeline

### Week 1: Foundation (Nov 21-27)
- [ ] Set up testing infrastructure
- [ ] Create shared fixtures and utilities
- [ ] Fix existing test errors (3 services)
- [ ] Implement notification service tests (0% → 80%)

### Week 2: Critical Services (Nov 28 - Dec 4)
- [ ] Portfolio Manager: 37% → 85%
- [ ] Trading Engine: ERROR → 85%
- [ ] Market Data Service: 48% → 85%

### Week 3: Core Services (Dec 5-11)
- [ ] API Gateway: 50% → 85%
- [ ] Bybit Connector: 66% → 85%
- [ ] Technical Analysis: 61% → 85%

### Week 4: AI Services (Dec 12-18)
- [ ] ML Prediction Service: ERROR → 80%
- [ ] Sentiment Analysis: ERROR → 80%
- [ ] Risk Metrics: 69% → 85%

### Week 5: Integration & E2E (Dec 19-25)
- [ ] Integration tests for all services
- [ ] End-to-end trading workflows
- [ ] Performance tests
- [ ] Documentation updates

---

## Success Metrics

### Coverage Targets

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Overall Coverage | ~50% | 80%+ | 🔴 |
| Unit Test Coverage | ~40% | 85%+ | 🔴 |
| Integration Coverage | ~20% | 75%+ | 🔴 |
| Critical Path Coverage | ~60% | 100% | 🟡 |
| Error Handling Coverage | ~30% | 90%+ | 🔴 |

### Quality Metrics

- **Test Reliability:** <1% flaky test rate
- **Test Performance:** Full suite runs in <10 minutes
- **Build Success Rate:** >95% on CI
- **Code Review Coverage:** 100% of tests reviewed
- **Documentation:** All tests documented

---

## Tools and Commands

### Quick Coverage Check
```bash
# Fast coverage analysis
python quick_coverage.py

# Detailed coverage report
./run_coverage_analysis.sh
```

### Run Tests for Specific Service
```bash
# Run tests for one service
cd services/api-gateway
pytest tests/ --cov=app --cov-report=term

# Run specific test file
pytest tests/test_main.py -v

# Run tests with markers
pytest -m unit  # Only unit tests
pytest -m integration  # Only integration tests
pytest -m e2e  # Only E2E tests
```

### Debug Failed Tests
```bash
# Run with verbose output
pytest tests/ -vv

# Stop on first failure
pytest tests/ -x

# Show print statements
pytest tests/ -s

# Run specific test
pytest tests/test_main.py::TestHealthEndpoint::test_health_check
```

### Coverage Commands
```bash
# Generate HTML coverage report
pytest --cov=services --cov-report=html

# Show missing lines
pytest --cov=services --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=services --cov-fail-under=80
```

---

## Maintenance and Updates

### Weekly Reviews
- Review coverage metrics every Monday
- Identify new untested code
- Update test plans based on new features
- Review and fix flaky tests

### Monthly Audits
- Deep dive into coverage gaps
- Review test execution time
- Optimize slow tests
- Update documentation

### Quarterly Goals
- Q1 2026: Achieve 80%+ coverage across all services
- Q2 2026: Maintain 85%+ coverage
- Q3 2026: Implement mutation testing
- Q4 2026: Achieve 90%+ coverage

---

## Conclusion

This comprehensive testing strategy ensures production-grade quality for the crypto trading bot. By following the testing pyramid, implementing thorough unit, integration, and E2E tests, and maintaining high coverage standards, we create a robust, reliable, and maintainable system.

**Key Success Factors:**
1. Consistent test writing discipline
2. Regular coverage monitoring
3. Fast feedback loops
4. Comprehensive error testing
5. Continuous improvement mindset

---

**Document Version:** 1.0
**Last Updated:** 2025-11-21
**Next Review:** 2025-12-21
**Owner:** Testing Guardian Agent
