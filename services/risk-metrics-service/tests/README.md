# Risk & Metrics Service - Test Suite

Comprehensive test suite for the Risk & Metrics Service covering unit tests, integration tests, and API validation.

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Shared fixtures and test utilities
├── test_risk_engine.py      # Unit tests for risk calculation engine
├── test_auth.py             # Unit tests for authentication
├── test_api.py              # Integration tests for API endpoints
└── README.md                # This file
```

## Test Coverage

### Risk Engine Tests (`test_risk_engine.py`)
- **Capital Metrics**: Tests for capital allocation and utilization calculations
- **Exposure Metrics**: Tests for portfolio exposure and concentration analysis
- **Drawdown Metrics**: Tests for drawdown tracking and recovery calculations
- **Performance Metrics**: Tests for Sharpe ratio, Sortino ratio, and other performance indicators
- **VaR Calculation**: Tests for Value at Risk calculations with different confidence levels
- **Risk Scoring**: Tests for overall risk score calculation and risk level classification
- **Alert Generation**: Tests for risk alert triggers and notifications
- **Circuit Breaker**: Tests for trading halt logic and safety mechanisms

### Authentication Tests (`test_auth.py`)
- Valid API key authentication
- Invalid API key rejection
- Missing API key handling
- Case sensitivity validation
- Whitespace handling
- Partial key match rejection

### API Integration Tests (`test_api.py`)
- Health and status endpoints
- Risk metrics endpoints (capital, exposure, drawdown, VaR)
- Risk scorecard comprehensive endpoint
- Performance metrics endpoints
- Alert endpoints
- Circuit breaker endpoints
- Configuration management endpoints
- Error handling and edge cases
- CORS and security configurations
- Performance and load tests

## Running Tests

### Install Test Dependencies

First, ensure all testing dependencies are installed:

```bash
pip install -r requirements.txt
```

### Run All Tests

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_risk_engine.py

# Run specific test class
pytest tests/test_risk_engine.py::TestRiskEngineCapitalMetrics

# Run specific test
pytest tests/test_risk_engine.py::TestRiskEngineCapitalMetrics::test_calculate_capital_metrics_with_positions
```

### Run Tests by Marker

Tests are organized with pytest markers for selective execution:

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only risk calculation tests
pytest -m risk

# Run only authentication tests
pytest -m auth

# Run only performance tests
pytest -m performance

# Exclude slow tests
pytest -m "not slow"
```

### Generate Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=app --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Test Fixtures

### Key Fixtures (from conftest.py)

- **test_client**: FastAPI TestClient for making HTTP requests
- **admin_headers**: Valid authentication headers for admin endpoints
- **invalid_admin_headers**: Invalid headers for testing unauthorized access
- **mock_portfolio_data**: Realistic portfolio data for testing
- **mock_portfolio_data_concentrated**: Portfolio with concentrated positions
- **mock_empty_portfolio**: Empty portfolio for edge case testing
- **sample_returns**: Historical returns data for performance metrics
- **sample_historical_values**: Time-series portfolio values for drawdown calculations
- **risk_engine**: Fresh RiskEngine instance for each test
- **sample_trades**: Trade history for performance analysis
- **capital_metrics_sample**: Pre-calculated capital metrics
- **exposure_metrics_sample**: Pre-calculated exposure metrics
- **drawdown_metrics_sample**: Pre-calculated drawdown metrics
- **performance_metrics_sample**: Pre-calculated performance metrics
- **var_metrics_sample**: Pre-calculated VaR metrics

## Test Configuration

Test behavior is controlled by `pytest.ini`:

```ini
[pytest]
# Test discovery
python_files = test_*.py *_test.py
python_classes = Test* *Test
python_functions = test_*

# Options
addopts = -v --strict-markers --cov=app --cov-report=term-missing

# Markers
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow-running tests
    auth: Authentication tests
    risk: Risk calculation tests
    performance: Performance metric tests
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          pytest --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## Mocking External Dependencies

Tests use mocking to avoid external dependencies:

```python
# Mock portfolio manager service
@patch("app.main.fetch_portfolio_data")
async def test_get_capital_metrics(mock_fetch, test_client, mock_portfolio_data):
    mock_fetch.return_value = mock_portfolio_data
    response = test_client.get("/risk/capital")
    assert response.status_code == 200
```

## Test Data

### Sample Portfolio Data

```python
{
    "portfolio": {
        "total_value": 10000.0,
        "available_balance": 5000.0,
        "holdings": [
            {
                "symbol": "BTCUSDT",
                "quantity": 0.5,
                "current_price": 45000.0,
                "market_value": 22500.0
            }
        ]
    }
}
```

## Coverage Goals

- **Overall Coverage**: > 80%
- **Critical Modules**:
  - risk_engine.py: > 90%
  - auth.py: 100%
  - main.py endpoints: > 85%

## Debugging Tests

### Run with Debugging

```bash
# Run with pytest debugger
pytest --pdb

# Run with print statements visible
pytest -s

# Run with detailed output
pytest -vv

# Run last failed tests only
pytest --lf

# Run tests in parallel (faster)
pytest -n auto
```

### Common Issues

1. **Import Errors**: Ensure you're in the project root directory
2. **Fixture Not Found**: Check conftest.py is in tests/ directory
3. **Mock Not Working**: Verify correct import path in @patch decorator
4. **Async Test Fails**: Ensure pytest-asyncio is installed

## Best Practices

1. **Test Isolation**: Each test should be independent
2. **Clear Naming**: Use descriptive test names that explain what is being tested
3. **Arrange-Act-Assert**: Structure tests with clear setup, execution, and validation
4. **Mock External Services**: Don't make real API calls in tests
5. **Test Edge Cases**: Include tests for error conditions and boundary values
6. **Keep Tests Fast**: Unit tests should run in milliseconds
7. **Maintain Fixtures**: Keep shared test data in conftest.py

## Contributing

When adding new features:

1. Write tests first (TDD approach)
2. Ensure all tests pass before committing
3. Maintain > 80% code coverage
4. Add appropriate pytest markers
5. Update this README if adding new test categories

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)
