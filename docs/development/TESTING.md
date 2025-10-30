# Testing Strategy

## Overview

This project follows **Test-Driven Development (TDD)** principles. Write tests **before** implementing features.

### Testing Goals
- **Unit Test Coverage**: >80%
- **Integration Test Coverage**: All service interactions
- **End-to-End Tests**: Critical user flows
- **Performance Tests**: API response times < 100ms

---

## Testing Stack

### Unit & Integration Testing
- **pytest**: Test framework
- **pytest-asyncio**: Async test support
- **pytest-cov**: Coverage reporting
- **pytest-mock**: Mocking support
- **httpx**: HTTP client for testing FastAPI

### Performance Testing
- **locust**: Load testing
- **pytest-benchmark**: Performance benchmarking

### Test Fixtures
- **Factory Boy**: Test data generation
- **Faker**: Fake data generation

---

## Test Structure

### Directory Layout
```
tests/
├── unit/                      # Unit tests (isolated)
│   ├── test_bybit_connector.py
│   ├── test_trading_engine.py
│   └── test_technical_analysis.py
├── integration/               # Integration tests (service interactions)
│   ├── test_trade_flow.py
│   ├── test_data_pipeline.py
│   └── test_message_queue.py
├── e2e/                       # End-to-end tests
│   └── test_full_trading_cycle.py
├── performance/               # Performance tests
│   └── test_api_latency.py
├── fixtures/                  # Shared test fixtures
│   ├── __init__.py
│   ├── database.py
│   └── mock_data.py
└── conftest.py                # Pytest configuration
```

### Naming Conventions

```python
# Test file naming
test_[module_name].py

# Test class naming
class Test[ClassName]:
    pass

# Test method naming
def test_[method]_[scenario]_[expected_result](self):
    """Test that [method] with [scenario] returns [expected result]"""
    pass
```

**Examples**:
```python
def test_place_order_valid_params_returns_order_id():
    """Test that placing order with valid parameters returns order ID"""
    pass

def test_calculate_rsi_insufficient_data_raises_error():
    """Test that RSI calculation with insufficient data raises ValueError"""
    pass

def test_execute_strategy_risk_exceeded_skips_trade():
    """Test that strategy execution skips trade when risk limit exceeded"""
    pass
```

---

## Unit Testing

### Example: Testing Bybit Connector

```python
# tests/unit/test_bybit_connector.py

import pytest
from unittest.mock import Mock, patch
from services.bybit_connector.client import BybitClient

class TestBybitClient:
    """Unit tests for BybitClient"""

    @pytest.fixture
    def client(self):
        """Create BybitClient instance for testing"""
        return BybitClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

    def test_init_valid_credentials_creates_client(self):
        """Test that initialization with valid credentials creates client"""
        client = BybitClient("key", "secret", testnet=True)
        assert client is not None
        assert client.testnet is True

    def test_init_missing_api_key_raises_error(self):
        """Test that initialization without API key raises ValueError"""
        with pytest.raises(ValueError, match="API key required"):
            BybitClient(api_key=None, api_secret="secret")

    @patch('services.bybit_connector.client.pybit.HTTP')
    def test_place_order_valid_params_returns_order(self, mock_http, client):
        """Test that placing order with valid parameters returns order"""
        # Arrange
        mock_response = {
            "ret_code": 0,
            "result": {
                "order_id": "123456",
                "symbol": "BTCUSDT",
                "status": "New"
            }
        }
        mock_http.return_value.place_active_order.return_value = mock_response

        # Act
        result = client.place_order(
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            qty=0.001,
            price=50000
        )

        # Assert
        assert result["order_id"] == "123456"
        assert result["symbol"] == "BTCUSDT"

    @patch('services.bybit_connector.client.pybit.HTTP')
    def test_place_order_api_error_raises_exception(self, mock_http, client):
        """Test that API error during order placement raises exception"""
        # Arrange
        mock_http.return_value.place_active_order.side_effect = Exception("API Error")

        # Act & Assert
        with pytest.raises(Exception, match="API Error"):
            client.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Limit",
                qty=0.001,
                price=50000
            )

    def test_validate_symbol_valid_symbol_returns_true(self, client):
        """Test that validate_symbol returns True for valid symbol"""
        assert client.validate_symbol("BTCUSDT") is True

    def test_validate_symbol_invalid_symbol_returns_false(self, client):
        """Test that validate_symbol returns False for invalid symbol"""
        assert client.validate_symbol("INVALID") is False
```

---

## Integration Testing

### Example: Testing Trade Flow

```python
# tests/integration/test_trade_flow.py

import pytest
from httpx import AsyncClient
from services.trading_engine.main import app as trading_app
from services.bybit_connector.main import app as bybit_app

@pytest.mark.asyncio
class TestTradeFlow:
    """Integration tests for complete trade flow"""

    async def test_execute_trade_signal_to_order(self):
        """Test complete flow from signal to order execution"""
        # Start with technical analysis signal
        signal = {
            "symbol": "BTCUSDT",
            "action": "BUY",
            "confidence": 0.8
        }

        # Trading engine receives signal
        async with AsyncClient(app=trading_app, base_url="http://test") as client:
            response = await client.post("/api/v1/signals", json=signal)
            assert response.status_code == 200
            trade_id = response.json()["data"]["trade_id"]

        # Verify order sent to Bybit connector
        async with AsyncClient(app=bybit_app, base_url="http://test") as client:
            response = await client.get(f"/api/v1/orders/{trade_id}")
            assert response.status_code == 200
            assert response.json()["data"]["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_risk_management_blocks_excessive_trade(self):
        """Test that risk management blocks trade exceeding limits"""
        # Create trade that exceeds risk limit
        trade = {
            "symbol": "BTCUSDT",
            "quantity": 100,  # Exceeds max position size
            "price": 50000
        }

        async with AsyncClient(app=trading_app, base_url="http://test") as client:
            response = await client.post("/api/v1/trades", json=trade)
            assert response.status_code == 400
            assert "risk limit exceeded" in response.json()["error"]["message"].lower()
```

---

## End-to-End Testing

```python
# tests/e2e/test_full_trading_cycle.py

import pytest
import asyncio

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_trading_cycle():
    """
    Test complete trading cycle from market data to position closure

    Flow:
    1. Market data arrives
    2. Technical analysis calculates indicators
    3. Signal generated
    4. Trading engine evaluates signal
    5. Order placed on exchange
    6. Position tracked
    7. Position closed based on exit signal
    """
    # This test requires all services running
    # Use docker-compose test environment

    # Step 1: Simulate market data
    # Step 2: Wait for analysis
    # Step 3: Verify signal generation
    # Step 4: Verify trade execution
    # Step 5: Verify portfolio update
    # Step 6: Simulate exit condition
    # Step 7: Verify position closure

    pass  # Implement when services are ready
```

---

## Test Fixtures

### Database Fixtures

```python
# tests/fixtures/database.py

import pytest
import asyncpg
from typing import AsyncGenerator

@pytest.fixture(scope="session")
async def db_pool() -> AsyncGenerator:
    """Create database connection pool for testing"""
    pool = await asyncpg.create_pool(
        host="localhost",
        port=5432,
        user="cryptobot",
        password="test_password",
        database="cryptobot_test"
    )
    yield pool
    await pool.close()

@pytest.fixture(autouse=True)
async def clean_database(db_pool):
    """Clean database before each test"""
    async with db_pool.acquire() as conn:
        await conn.execute("TRUNCATE trading_engine.trades CASCADE")
        await conn.execute("TRUNCATE portfolio.positions CASCADE")
        await conn.execute("TRUNCATE portfolio.balances CASCADE")
    yield
```

### Mock Data Fixtures

```python
# tests/fixtures/mock_data.py

import pytest
from datetime import datetime, timedelta

@pytest.fixture
def sample_candles():
    """Generate sample OHLCV candle data"""
    candles = []
    base_time = datetime.now()

    for i in range(100):
        candles.append({
            "time": base_time - timedelta(hours=i),
            "open": 50000 + i * 10,
            "high": 50100 + i * 10,
            "low": 49900 + i * 10,
            "close": 50000 + i * 10,
            "volume": 100.0
        })

    return candles

@pytest.fixture
def sample_order():
    """Generate sample order data"""
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 0.001,
        "price": 50000.0
    }
```

---

## Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/unit/test_bybit_connector.py -v
```

### Run Specific Test
```bash
pytest tests/unit/test_bybit_connector.py::TestBybitClient::test_place_order_valid_params_returns_order -v
```

### Run with Coverage
```bash
pytest tests/ --cov=services --cov-report=html --cov-report=term
```

### Run Only Unit Tests
```bash
pytest tests/unit/ -v
```

### Run Only Integration Tests
```bash
pytest tests/integration/ -v
```

### Run with Markers
```bash
# Run only async tests
pytest -m asyncio

# Run only e2e tests
pytest -m e2e

# Skip slow tests
pytest -m "not slow"
```

---

## Coverage Requirements

### Minimum Coverage Thresholds

```ini
# pytest.ini or setup.cfg
[coverage:run]
source = services
omit =
    */tests/*
    */venv/*
    */__pycache__/*

[coverage:report]
fail_under = 80
show_missing = True
```

### Generate Coverage Report
```bash
pytest --cov=services --cov-report=html

# Open report
open htmlcov/index.html  # Mac
xdg-open htmlcov/index.html  # Linux
```

---

## Continuous Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install pytest pytest-cov pytest-asyncio
          pip install -r requirements.txt

      - name: Run tests
        run: |
          pytest tests/ --cov=services --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Best Practices

### 1. Test Independence
- Each test should be independent
- Use fixtures for setup/teardown
- Don't rely on test execution order

### 2. Clear Assertions
```python
# Good
assert response.status_code == 200
assert result["order_id"] is not None

# Bad
assert response  # What are we checking?
```

### 3. Test One Thing
```python
# Good
def test_calculate_rsi_returns_correct_value():
    result = calculate_rsi(data)
    assert result == 65.5

# Bad - testing multiple things
def test_indicators():
    rsi = calculate_rsi(data)
    macd = calculate_macd(data)
    assert rsi == 65.5
    assert macd == 10.0
```

### 4. Use Descriptive Names
```python
# Good
def test_place_order_insufficient_balance_raises_error()

# Bad
def test_order()
```

### 5. Mock External Dependencies
```python
# Mock Bybit API calls
@patch('bybit_connector.client.HTTP')
def test_get_balance(mock_http):
    mock_http.return_value.get_wallet_balance.return_value = {...}
```

---

## Performance Testing

### Load Testing with Locust

```python
# tests/performance/locustfile.py

from locust import HttpUser, task, between

class TradingBotUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def get_balance(self):
        self.client.get("/api/v1/account/balance")

    @task(3)  # 3x weight
    def get_price(self):
        self.client.get("/api/v1/price/BTCUSDT")
```

Run load test:
```bash
locust -f tests/performance/locustfile.py --host=http://localhost:8000
```

---

**Last Updated**: 2025-10-30
**Version**: 1.0
