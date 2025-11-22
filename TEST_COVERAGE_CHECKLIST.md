# Test Coverage Enhancement - Action Checklist
**Task:** Achieve 80%+ test coverage across all 10 services
**Current Status:** 0/10 services at 80%+
**Target:** 10/10 services at 80%+

---

## Quick Status Dashboard

```
Service                          Tests   Coverage   Status
────────────────────────────────────────────────────────────────
technical-analysis               11      61%        ⚠️ MEDIUM
risk-metrics-service             7       69%        ⚠️ MEDIUM
bybit-connector                  6       66%        ⚠️ MEDIUM
api-gateway                      5       50%        ❌ LOW
market-data-service              13      48%        ❌ LOW
portfolio-manager                2       37%        ❌ LOW
trading-engine                   42      ERROR      ❌ BROKEN
ml-prediction-service            4       ERROR      ❌ BROKEN
sentiment-analysis-service       4       ERROR      ❌ BROKEN
notification-service             0       0%         ❌ NO TESTS
────────────────────────────────────────────────────────────────
Services at 80%+: 0/10 (0%)
Average Coverage: 49%
```

---

## Phase 1: Critical Fixes (Week 1)

### ✅ Completed

- [x] **SQZMOM Indicator Tests** (Technical Analysis)
  - [x] Fixed True Range calculation test
  - [x] Fixed performance timeout test
  - [x] 27/27 tests passing
  - File: `services/technical-analysis/tests/test_squeeze_momentum.py`

- [x] **Coverage Analysis Infrastructure**
  - [x] Created quick_coverage.py script
  - [x] Created comprehensive analysis script
  - [x] Generated detailed coverage reports

### ⚠️ In Progress

- [ ] **SQZMOM API Tests** (Technical Analysis) - 53% done
  - [x] Created test file with 17 test cases
  - [ ] Fix 8 failing tests (mocking issues)
  - [ ] Add conftest.py for proper fixtures
  - File: `services/technical-analysis/tests/test_sqzmom_api.py`
  - **Estimated:** 2-3 hours

- [ ] **Integration Tests** (Technical Analysis)
  - [ ] Fix 5 failing tests in test_multi_indicator_pipeline.py
  - [ ] test_all_indicators_with_bullish_data
  - [ ] test_all_indicators_with_bearish_data
  - [ ] test_volume_confirms_breakout_signal
  - [ ] test_complete_analysis_pipeline
  - [ ] test_multi_indicator_pipeline_performance
  - **Estimated:** 2 hours

### ❌ To Do - Critical Priority

- [ ] **Trading Engine - Fix Test Execution**
  ```bash
  cd services/trading-engine
  pip install respx  # Missing dependency
  pytest tests/ --cov=app --cov-report=html -v
  ```
  - Issue: ModuleNotFoundError: No module named 'respx'
  - Expected: 690 tests should run
  - **Estimated:** 30 minutes

- [ ] **Portfolio Manager - Comprehensive Tests**
  ```bash
  cd services/portfolio-manager
  # Create comprehensive test suite
  pytest tests/ --cov=app --cov-report=html
  ```
  - Current: 37% coverage (LOWEST)
  - Target: 80%+ coverage
  - Tests needed:
    - [ ] Position tracking tests
    - [ ] P&L calculation tests
    - [ ] Balance management tests
    - [ ] Order management tests
    - [ ] Multi-position scenarios
    - [ ] Edge cases (margin calls, liquidation)
  - **Estimated:** 6-8 hours

---

## Phase 2: Gateway & Data Services (Week 2)

### API Gateway (50% → 80%)
- [ ] **Comprehensive Endpoint Tests**
  - [ ] Test all route handlers
  - [ ] Test service proxy logic
  - [ ] Test authentication middleware
  - [ ] Test rate limiting
  - [ ] Test CORS handling
  - [ ] Test error responses
  - **Estimated:** 4-5 hours

### Market Data Service (48% → 80%)
- [ ] **Database Integration Tests**
  - [ ] TimescaleDB connection tests
  - [ ] Data insertion tests
  - [ ] Query performance tests
- [ ] **Caching Layer Tests**
  - [ ] Redis connection tests
  - [ ] Cache hit/miss tests
  - [ ] Cache invalidation tests
- [ ] **WebSocket Tests**
  - [ ] Connection establishment
  - [ ] Data streaming
  - [ ] Reconnection logic
  - **Estimated:** 5-6 hours

### Bybit Connector (66% → 80%)
- [ ] **WebSocket Tests**
  - [ ] Connection failure handling
  - [ ] Reconnection logic
  - [ ] Message parsing
- [ ] **REST Client Tests**
  - [ ] Rate limiting
  - [ ] Error recovery
  - [ ] Authentication failures
- [ ] **Order Execution Tests**
  - [ ] Success scenarios
  - [ ] Error scenarios
  - [ ] Timeout handling
  - **Estimated:** 3-4 hours

---

## Phase 3: ML & Supporting Services (Week 3)

### Risk Metrics Service (69% → 80%)
- [ ] **Edge Case Tests**
  - [ ] Extreme market conditions
  - [ ] Boundary value tests
  - [ ] Error injection tests
- [ ] **Performance Tests**
  - [ ] High-frequency updates
  - [ ] Stress testing
  - **Estimated:** 2-3 hours

### ML Prediction Service (ERROR → 80%)
- [ ] **Fix Test Execution**
  - [ ] Diagnose import errors
  - [ ] Install missing dependencies
  - [ ] Verify tests run
- [ ] **Model Tests**
  - [ ] Model training tests
  - [ ] Prediction accuracy tests
  - [ ] Feature engineering tests
- [ ] **API Tests**
  - [ ] Prediction endpoint tests
  - [ ] Model management tests
  - **Estimated:** 4-5 hours

### Sentiment Analysis Service (ERROR → 80%)
- [ ] **Fix Test Execution**
  - [ ] Diagnose import errors
  - [ ] Install missing dependencies
  - [ ] Verify tests run
- [ ] **NLP Pipeline Tests**
  - [ ] Text processing tests
  - [ ] Sentiment scoring tests
  - [ ] Data source integration tests
- [ ] **API Tests**
  - [ ] Sentiment endpoint tests
  - [ ] Bulk analysis tests
  - **Estimated:** 4-5 hours

### Notification Service (0% → 80%)
- [ ] **Create Test Infrastructure**
  - [ ] Create tests/ directory
  - [ ] Create conftest.py
  - [ ] Setup test fixtures
- [ ] **Notification Tests**
  - [ ] Email notification tests
  - [ ] Telegram notification tests
  - [ ] Alert priority tests
  - [ ] Rate limiting tests
- [ ] **API Tests**
  - [ ] Send notification endpoint
  - [ ] Notification history endpoint
  - **Estimated:** 4-5 hours

---

## Service-by-Service Checklist

### ✅ Technical Analysis (61% → 75%+)

**Completed:**
- [x] SQZMOM unit tests (27/27 passing)
- [x] Existing indicator tests (RSI, MACD, BB, SMA, EMA, Stochastic, ATR)

**To Do:**
- [ ] Fix SQZMOM API tests (8 failing)
- [ ] Fix integration tests (5 failing)
- [ ] Add tests for advanced indicators
- [ ] Add multi-timeframe tests
- [ ] Add aggregated signal tests
- **Files:**
  - `tests/test_sqzmom_api.py` (fix)
  - `tests/integration/test_multi_indicator_pipeline.py` (fix)
  - `tests/test_advanced.py` (create)
  - `tests/test_aggregation.py` (create)

### ❌ Trading Engine (ERROR → 80%)

**Issue:** Missing `respx` dependency prevents test execution

**Fix:**
```bash
cd services/trading-engine
pip install respx
pytest tests/ --cov=app --cov-report=html
```

**Verify:**
- [ ] 690 tests collected and run
- [ ] Measure actual coverage
- [ ] Fix any failing tests
- [ ] Add missing tests if coverage < 80%

**Expected Results:**
- Should have good coverage (42 test files!)
- May just need dependency fixes

### ❌ Portfolio Manager (37% → 80%)

**Critical:** Handles money - needs comprehensive testing

**Create Tests For:**
- [ ] Position Management
  - [ ] Open position
  - [ ] Close position
  - [ ] Update position
  - [ ] Multiple positions
- [ ] P&L Calculation
  - [ ] Realized P&L
  - [ ] Unrealized P&L
  - [ ] Total equity
  - [ ] ROI calculation
- [ ] Balance Management
  - [ ] Deposit
  - [ ] Withdrawal
  - [ ] Balance updates from trades
  - [ ] Margin requirements
- [ ] Order Management
  - [ ] Create order
  - [ ] Cancel order
  - [ ] Order history
  - [ ] Order status tracking
- [ ] Edge Cases
  - [ ] Margin call scenarios
  - [ ] Liquidation scenarios
  - [ ] Negative balance protection
  - [ ] Concurrent trade handling

**Files to Create:**
- `tests/test_position_manager.py`
- `tests/test_pnl_calculator.py`
- `tests/test_balance_manager.py`
- `tests/test_order_manager.py`
- `tests/test_edge_cases.py`

### ⚠️ API Gateway (50% → 80%)

**Create Tests For:**
- [ ] Route Handlers
  - [ ] All GET endpoints
  - [ ] All POST endpoints
  - [ ] All PUT/DELETE endpoints
- [ ] Service Proxy
  - [ ] Successful proxying
  - [ ] Service unavailable handling
  - [ ] Timeout handling
  - [ ] Retry logic
- [ ] Middleware
  - [ ] Authentication
  - [ ] Rate limiting
  - [ ] CORS
  - [ ] Request validation
- [ ] Error Handling
  - [ ] 404 errors
  - [ ] 500 errors
  - [ ] Validation errors
  - [ ] Service errors

**Files:**
- `tests/test_routes.py` (expand)
- `tests/test_proxy.py` (create)
- `tests/test_middleware.py` (create)
- `tests/test_errors.py` (create)

### ⚠️ Market Data Service (48% → 80%)

**Create Tests For:**
- [ ] Data Fetching
  - [ ] Kline fetching
  - [ ] Orderbook fetching
  - [ ] Ticker fetching
  - [ ] Historical data
- [ ] Database
  - [ ] TimescaleDB insert
  - [ ] TimescaleDB query
  - [ ] Data aggregation
  - [ ] Connection pooling
- [ ] Caching
  - [ ] Redis get/set
  - [ ] Cache invalidation
  - [ ] Cache warming
- [ ] WebSocket
  - [ ] Connection
  - [ ] Subscription
  - [ ] Data streaming
  - [ ] Reconnection

**Files:**
- `tests/test_fetcher.py` (expand)
- `tests/test_database.py` (create)
- `tests/test_cache.py` (create)
- `tests/test_websocket.py` (create)

### ⚠️ Bybit Connector (66% → 80%)

**Create Tests For:**
- [ ] REST Client
  - [ ] Authentication
  - [ ] Rate limiting
  - [ ] Error handling
  - [ ] Timeout handling
- [ ] WebSocket
  - [ ] Connection
  - [ ] Subscription
  - [ ] Message parsing
  - [ ] Reconnection
- [ ] Order Management
  - [ ] Place order
  - [ ] Cancel order
  - [ ] Get order status
  - [ ] Get positions
- [ ] Error Scenarios
  - [ ] Network errors
  - [ ] API errors
  - [ ] Invalid parameters

**Files:**
- `tests/test_rest_client.py` (expand)
- `tests/test_websocket.py` (expand)
- `tests/test_orders.py` (create)

### ⚠️ Risk Metrics Service (69% → 80%)

**Create Tests For:**
- [ ] Risk Calculations
  - [ ] VaR calculation
  - [ ] Sharpe ratio
  - [ ] Max drawdown
  - [ ] Win rate
- [ ] Edge Cases
  - [ ] Extreme volatility
  - [ ] Zero trades
  - [ ] Negative returns
  - [ ] Large position sizes
- [ ] Performance
  - [ ] High-frequency updates
  - [ ] Large datasets
  - [ ] Concurrent calculations

**Files:**
- `tests/test_risk_calculations.py` (expand)
- `tests/test_edge_cases.py` (create)
- `tests/test_performance.py` (expand)

### ❌ ML Prediction Service (ERROR → 80%)

**Fix First:**
```bash
cd services/ml-prediction-service
pytest tests/ -v  # See what errors appear
pip install [missing packages]
```

**Then Create Tests For:**
- [ ] Model Training
- [ ] Predictions
- [ ] Feature Engineering
- [ ] Model Evaluation
- [ ] API Endpoints

### ❌ Sentiment Analysis Service (ERROR → 80%)

**Fix First:**
```bash
cd services/sentiment-analysis-service
pytest tests/ -v  # See what errors appear
pip install [missing packages]
```

**Then Create Tests For:**
- [ ] Text Processing
- [ ] Sentiment Scoring
- [ ] Data Sources
- [ ] API Endpoints

### ❌ Notification Service (0% → 80%)

**Create From Scratch:**
```bash
cd services/notification-service
mkdir tests
touch tests/__init__.py
touch tests/conftest.py
touch tests/test_email.py
touch tests/test_telegram.py
touch tests/test_api.py
```

**Create Tests For:**
- [ ] Email Notifications
- [ ] Telegram Notifications
- [ ] Alert Priority
- [ ] Rate Limiting
- [ ] API Endpoints

---

## Testing Commands Reference

### Run All Tests for a Service
```bash
cd services/[service-name]
pytest tests/ --cov=app --cov-report=html --cov-report=term-missing -v
```

### Run Specific Test File
```bash
pytest tests/test_specific.py -v
```

### Run Specific Test
```bash
pytest tests/test_file.py::TestClass::test_method -v
```

### Run Tests with Coverage
```bash
pytest tests/ --cov=app --cov-report=html
```

### View Coverage Report
```bash
open htmlcov/index.html  # or firefox, chrome, etc.
```

### Quick Coverage Check (All Services)
```bash
python3 quick_coverage.py
```

---

## Progress Tracking

### Daily Checklist

**Morning:**
- [ ] Run `python3 quick_coverage.py` to check status
- [ ] Review previous day's progress
- [ ] Pick next task from checklist

**During Work:**
- [ ] Write tests
- [ ] Run tests frequently
- [ ] Check coverage incrementally
- [ ] Fix failing tests immediately

**End of Day:**
- [ ] Run full coverage analysis
- [ ] Update this checklist
- [ ] Commit changes
- [ ] Document progress

### Weekly Goals

**Week 1:**
- [ ] Trading Engine tests running
- [ ] Portfolio Manager at 80%+
- [ ] Technical Analysis at 75%+
- [ ] All SQZMOM tests passing

**Week 2:**
- [ ] API Gateway at 80%+
- [ ] Market Data Service at 80%+
- [ ] Bybit Connector at 80%+

**Week 3:**
- [ ] All remaining services at 80%+
- [ ] All tests passing
- [ ] CI/CD integration complete

---

## Success Criteria

### Service-Level
- [x] Test files exist
- [ ] Tests run successfully (no errors)
- [ ] Coverage ≥80%
- [ ] All tests passing
- [ ] Fast execution (<60s)

### Project-Level
- [ ] 10/10 services with tests
- [ ] 10/10 services at 80%+
- [ ] 0 test execution errors
- [ ] 0 test failures
- [ ] Automated CI/CD testing

---

## Estimated Time Investment

| Task | Estimated Hours |
|------|----------------|
| Fix Trading Engine | 0.5 |
| Complete SQZMOM API tests | 2-3 |
| Fix integration tests | 2 |
| Portfolio Manager tests | 6-8 |
| API Gateway tests | 4-5 |
| Market Data Service tests | 5-6 |
| Bybit Connector tests | 3-4 |
| Risk Metrics tests | 2-3 |
| ML Prediction tests | 4-5 |
| Sentiment Analysis tests | 4-5 |
| Notification Service tests | 4-5 |
| **TOTAL** | **37-48 hours** |

**Timeline:** 3 weeks with focused effort

---

## Next Immediate Actions

1. **Install missing dependency for Trading Engine:**
   ```bash
   cd services/trading-engine
   pip install respx
   pytest tests/ -v
   ```

2. **Fix SQZMOM API tests:**
   ```bash
   cd services/technical-analysis
   # Fix mocking in tests/test_sqzmom_api.py
   pytest tests/test_sqzmom_api.py -v
   ```

3. **Run coverage analysis:**
   ```bash
   python3 quick_coverage.py
   ```

4. **Start Portfolio Manager tests:**
   ```bash
   cd services/portfolio-manager
   # Create comprehensive test suite
   ```

---

**Last Updated:** November 20, 2025
**Status:** Phase 1 in progress
**Next Review:** Check progress after completing immediate actions
