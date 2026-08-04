# Test Infrastructure Quality Checklist

Quick reference guide for evaluating and improving test coverage across the crypto trading bot.

---

## Service Health Summary

### Traffic Light Status

| Service | Coverage | Test Count | Org. | Fixtures | Issues | Status |
|---------|----------|-----------|------|----------|--------|--------|
| api-gateway | 80%+ | 11 | Excellent | Strong | Large files | YELLOW |
| bybit-connector | 80%+ | 11 | Good | Strong | Coverage push | YELLOW |
| market-data | 75-80% | 18 | Very Good | Good | Test duplication | YELLOW |
| portfolio-manager | 75-80% | 15 | Good | MISSING | 2x push files | RED |
| technical-analysis | 80%+ | 19 | Excellent | Good | Large handlers | YELLOW |
| trading-engine | 80%+ | 29 | BEST | Strong | None | GREEN |
| notification-service | 70-75% | 4 | Fair | MISSING | Minimal tests | RED |
| ml-prediction | <70% | 18 | Poor | MISSING | 8x push files | RED |
| sentiment-analysis | 70-75% | 5 | Fair | MISSING | Large push file | RED |
| risk-metrics | 75-80% | 12 | Good | Good | 2x push files | YELLOW |

**Status Legend**: GREEN (Good) | YELLOW (Needs Improvement) | RED (Critical)

---

## Critical Issues by Service

### RED FLAG SERVICES

#### ML Prediction Service - URGENT
```
Coverage Status: Likely <70% without push files
Test Files: 18 (8 explicitly for coverage)
Conftest: MISSING
E2E Tests: None
Critical Issues:
  - test_easy_wins_80.py: 60 lines (trivial tests)
  - test_80_percent_push_supplement.py: Coverage-driven
  - test_one_more_percent.py: Admits coverage gaming
  - test_reach_80_percent.py: Coverage gaming
  - 8+ files with coverage goals in names

Action: AUDIT ALL TESTS, REMOVE TRIVIAL ONES, ADD MEANINGFUL TESTS
Timeline: 1-2 sprints
```

#### Portfolio Manager - CRITICAL
```
Coverage Status: 75-80% with 2 push files
Test Files: 15 (2 for coverage)
Conftest: MISSING
E2E Tests: None
Critical Issues:
  - test_80_percent_push.py: 22 KB coverage push
  - test_push_to_80.py: Another coverage push
  - No conftest.py for fixture management
  - Likely 70-75% without push files

Action: CREATE CONFTEST, AUDIT PUSH FILES, ADD INTEGRATION TESTS
Timeline: 1-2 sprints
```

#### Notification Service - CRITICAL
```
Coverage Status: 70-75% minimum (artificial 80%)
Test Files: 4 (1 is 27 KB coverage push)
Conftest: MISSING
E2E Tests: None
Critical Issues:
  - Only 4 test files for a core service
  - 27 KB coverage push file
  - No conftest infrastructure
  - Likely <60% organic coverage

Action: EXPAND TO 10+ TEST FILES, CREATE CONFTEST, ADD E2E TESTS
Timeline: 2 sprints
```

#### Sentiment Analysis Service - CRITICAL
```
Coverage Status: 70-75% minimum (artificial 80%)
Test Files: 5 (1 is 35 KB coverage push)
Conftest: MISSING
E2E Tests: None
Critical Issues:
  - Only 5 test files for a core service
  - 35 KB coverage push file
  - No conftest infrastructure
  - Likely <60% organic coverage

Action: EXPAND TO 12+ TEST FILES, CREATE CONFTEST, ADD INTEGRATION TESTS
Timeline: 2 sprints
```

---

## Conftest.py Implementation Checklist

### Services Missing conftest.py
- [ ] portfolio-manager/tests/conftest.py
- [ ] notification-service/tests/conftest.py
- [ ] ml-prediction-service/tests/conftest.py
- [ ] sentiment-analysis-service/tests/conftest.py

### conftest.py Template

```python
"""
[Service Name] - pytest Configuration and Fixtures
Purpose: Shared test fixtures and configuration
"""

import pytest
import os
from typing import AsyncGenerator, Generator
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"

from app.main import app
from app.config import Settings, get_settings


@pytest.fixture
def test_settings() -> Settings:
    """Provide test settings instance"""
    return Settings(
        environment="test",
        debug=False,
        # Add service-specific settings
    )


@pytest.fixture
async def mock_service_dependency() -> AsyncGenerator[Mock, None]:
    """Mock external service dependency"""
    mock = AsyncMock()
    # Configure mock methods
    yield mock


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """FastAPI test client with mocked dependencies"""
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def disable_external_calls():
    """Disable external API calls in tests"""
    # Override dependencies to use mocks
    yield
```

---

## Integration Test Structure Checklist

### Create for All Services (Currently: trading-engine only)

```
services/[service-name]/tests/
├── integration/
│   ├── conftest.py              # Integration-specific fixtures
│   ├── test_api_endpoints.py    # API endpoint tests
│   ├── test_database_integration.py
│   ├── test_service_communication.py
│   ├── test_message_queue.py    # If applicable
│   └── test_e2e_workflow.py     # End-to-end flow
├── unit/
│   ├── test_module1.py
│   └── test_module2.py
└── conftest.py                  # Root fixtures
```

---

## Coverage Push File Detection

### How to Identify Coverage Push Files
```
Files with these characteristics:
- Names: test_*_push.py, test_*_boost.py, test_*_80*.py
- Size: Unusually large (25+ KB) relative to actual functionality
- Content: Many simple assertions, repeating test patterns
- Comments: Reference coverage goals or "easy wins"
- Test counts: >100 tests in a single file

Examples Found:
✗ ml-prediction-service/test_easy_wins_80.py (60 lines, trivial)
✗ ml-prediction-service/test_80_percent_push_supplement.py
✗ portfolio-manager/test_80_percent_push.py (22 KB)
✗ portfolio-manager/test_push_to_80.py
✗ notification-service/test_80_coverage_push.py (27 KB)
✗ sentiment-analysis-service/test_80_coverage_push.py (35 KB)
✗ api-gateway/test_gateway_80_coverage.py (24.5 KB)
```

---

## Test Quality Assessment Questions

### For Each Service, Answer:

1. **Test Organization**
   - [ ] Tests organized by concern (unit/integration/e2e)?
   - [ ] Conftest.py provides shared fixtures?
   - [ ] Clear separation between test types?
   - [ ] Test files focused on single concern?

2. **Coverage Quality**
   - [ ] Coverage includes meaningful assertions?
   - [ ] Tests check both happy path and error cases?
   - [ ] Edge cases tested (None, empty, negative)?
   - [ ] Async error conditions tested?

3. **Integration Testing**
   - [ ] Service-to-service communication tested?
   - [ ] Database persistence validated?
   - [ ] Message queue integration tested?
   - [ ] API contracts verified?

4. **End-to-End Testing**
   - [ ] Complete user workflows tested?
   - [ ] Multi-service scenarios covered?
   - [ ] Failure scenarios tested?
   - [ ] Recovery paths validated?

5. **Mock Quality**
   - [ ] Mocks match production behavior?
   - [ ] Mock setup documented?
   - [ ] Async mocks properly configured?
   - [ ] Real integration tests exist?

6. **Test Maintenance**
   - [ ] Tests are deterministic (no flakiness)?
   - [ ] Clear test names describe behavior?
   - [ ] Proper cleanup after each test?
   - [ ] No test interdependencies?

---

## Implementation Priority Matrix

### Phase 1: Critical Fixes (Weeks 1-2)
- [ ] Create missing conftest.py (4 services)
- [ ] Audit coverage push files in ml-prediction
- [ ] Remove trivial tests
- [ ] Document test quality standards

### Phase 2: Coverage Expansion (Weeks 3-4)
- [ ] Expand notification service (4 → 10+ tests)
- [ ] Expand sentiment analysis (5 → 15+ tests)
- [ ] Add integration tests to all services

### Phase 3: Integration & E2E (Weeks 5-6)
- [ ] Create integration test subdirectories
- [ ] Add service-to-service tests
- [ ] Expand E2E testing beyond trading-engine
- [ ] Implement contract testing

### Phase 4: Quality Assurance (Week 7+)
- [ ] Implement mutation testing
- [ ] Add performance benchmarks
- [ ] Set up flaky test detection
- [ ] Create test quality dashboard

---

## Test Execution Commands

### Run All Tests with Coverage
```bash
pytest services/*/tests --cov=services --cov-report=html --cov-report=term-missing
```

### Run Service-Specific Tests
```bash
pytest services/[service-name]/tests --cov=services/[service-name]
```

### Run Integration Tests Only
```bash
pytest -m integration
```

### Run With Markers
```bash
pytest -m "not slow"           # Skip slow tests
pytest -m "unit"               # Unit tests only
pytest -m "integration"        # Integration tests only
pytest -m "e2e"                # E2E tests only
```

### Run Specific Test File
```bash
pytest services/[service]/tests/test_[module].py -v
```

### Run With Coverage and HTML Report
```bash
pytest --cov=services --cov-report=html
# Then open htmlcov/index.html
```

---

## Test File Size Guidelines

### Recommended Sizes
```
Small test file:      <1 KB   - Single unit test
Medium test file:     1-15 KB - Feature test suite
Large test file:      15-25 KB - Component test suite
Critical file:        >25 KB  - May need splitting

Current Issues:
test_phase3_endpoints.py       43 KB  - SPLIT NEEDED
test_80_coverage_push.py       35 KB  - AUDIT & SPLIT
test_comprehensive_80.py       35 KB  - REORGANIZE
test_optimization_handler.py   30 KB  - CONSOLIDATE

Action: Files >25 KB should be reviewed for splitting
```

---

## Test Fixture Best Practices

### Do's
- [ ] Use conftest.py for shared fixtures
- [ ] Use @pytest.fixture(autouse=True) for common setup
- [ ] Name fixtures descriptively (mock_service, test_client, etc.)
- [ ] Use fixture scope appropriately (function, module, session)
- [ ] Document fixture behavior and dependencies
- [ ] Clean up resources in teardown

### Don'ts
- [ ] Don't put all fixtures in individual test files
- [ ] Don't create complex fixture interdependencies
- [ ] Don't use fixtures for logic that belongs in tests
- [ ] Don't mock everything (use real objects when possible)
- [ ] Don't forget to clean up async resources
- [ ] Don't hide test setup in fixtures

---

## Mock Strategy Guidelines

### When to Use Mocks
```python
✓ External APIs (Bybit, database)
✓ Network calls
✓ File system operations
✓ Time-based operations
✓ Complex dependencies with side effects
```

### When to Use Real Objects
```python
✓ Simple data models (Pydantic models)
✓ Calculation logic
✓ String manipulation
✓ Configuration objects
✓ Test-local operations
```

### Integration Test Pattern
```python
# Use testcontainers for real dependencies
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

@pytest.fixture
def postgres():
    with PostgresContainer("postgres:15") as postgres:
        yield postgres.get_connection_url()

@pytest.fixture
def redis():
    with RedisContainer() as redis:
        yield redis.get_connection_url()
```

---

## Mutation Testing Quick Start

### Install Mutmut
```bash
pip install mutmut
```

### Run Mutation Tests
```bash
mutmut run --tests-dir=services/[service-name]/tests
```

### Generate HTML Report
```bash
mutmut html
```

### What Mutation Tests Check
- Does removing a line cause test failure?
- Does changing comparison operators cause failure?
- Does removing assertions cause failure?
- Are dead code paths covered?

---

## Performance Benchmarks

### Test Execution Time Targets
```
Unit Tests:       <100 ms per test (total <5 min)
Integration Tests: <500 ms per test (total <5 min)
E2E Tests:        <2 sec per test (total <5 min)
All Tests:        <15 minutes total
```

### Current Status: UNKNOWN
**Action**: Run `pytest -v --durations=10` to identify slow tests

---

## CI/CD Integration

### GitHub Actions Configuration
```yaml
- name: Run Tests
  run: |
    pytest services/*/tests \
      --cov=services \
      --cov-report=xml \
      --cov-report=html \
      --cov-fail-under=80 \
      -v

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

---

## Quality Metrics Dashboard

### Track These Metrics
- [ ] Overall coverage percentage (target: 85%)
- [ ] Coverage by service (target: 80% each)
- [ ] Integration test percentage (target: 30%)
- [ ] E2E test percentage (target: 10%)
- [ ] Flaky test count (target: 0)
- [ ] Test execution time (target: <15 min)
- [ ] Mutation kill rate (target: 90%)

### Reporting Tools
- Coverage.py
- pytest-html
- pytest-benchmark
- Mutmut
- TestcontainersOrchestra

---

## Immediate Action Items (Next Sprint)

### Critical
- [ ] Create conftest.py for 4 missing services
- [ ] Audit ml-prediction test_easy_wins_80.py
- [ ] Document test quality standards
- [ ] Identify all coverage push files

### High Priority
- [ ] Create integration test directory template
- [ ] Expand notification service test suite
- [ ] Expand sentiment analysis test suite
- [ ] Implement mutation testing

### Medium Priority
- [ ] Add E2E tests to other services
- [ ] Consolidate large test files (>25 KB)
- [ ] Create test data factories
- [ ] Add performance benchmarks

---

## Resources & References

### Documentation
- Pytest: https://docs.pytest.org/
- Coverage.py: https://coverage.readthedocs.io/
- TestContainers: https://testcontainers.com/
- Mutmut: https://mutmut.readthedocs.io/

### Test Patterns
- Given-When-Then pattern (used in bybit-connector)
- Arrange-Act-Assert pattern
- Test fixture factories
- Mocking patterns

### Tools to Implement
- pytest-xdist: Parallel test execution
- pytest-mock: Improved mocking
- pytest-asyncio: Async test support
- pytest-cov: Coverage reporting
- pytest-benchmark: Performance tests
- pytest-timeout: Test timeouts
- mutmut: Mutation testing

---

## Sign-Off Checklist

Before declaring service test infrastructure complete:

- [ ] All tests pass consistently
- [ ] Coverage >= 80% without push files
- [ ] Conftest.py exists with shared fixtures
- [ ] Integration tests exist (unit/integration/e2e)
- [ ] No trivial or redundant tests
- [ ] E2E workflow tested
- [ ] Test names clearly describe behavior
- [ ] Fixtures documented
- [ ] No flaky tests
- [ ] Test execution < 15 minutes

---

*Last Updated*: November 25, 2025
*Next Review*: December 2025
