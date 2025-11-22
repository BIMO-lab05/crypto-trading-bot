# End-to-End Tests

This directory contains end-to-end tests for the Crypto Trading Bot system.

## Directory Structure

```
e2e/
├── conftest.py              # Pytest fixtures and configuration
├── fixtures/                # Test data and fixtures
│   ├── __init__.py
│   └── mock_data.py        # Mock data generators
├── utils/                   # Testing utilities
│   ├── __init__.py
│   ├── wait_for_health.py  # Health check utilities
│   └── assertions.py       # Custom assertions
├── test_trading_cycle.py   # Trading cycle E2E tests
├── test_data_pipeline.py   # Data pipeline E2E tests
├── test_signal_generation.py  # Signal generation E2E tests
├── test_risk_management.py # Risk management E2E tests
├── test_order_execution.py # Order execution E2E tests
├── test_failure_scenarios.py # Failure scenarios and resilience E2E tests
├── test_performance_scalability.py # Performance and scalability E2E tests
└── README.md               # This file
```

## Prerequisites

1. **Services Running**: Ensure all required services are running
   ```bash
   # Start all services
   docker-compose up -d

   # Or use the startup script
   ./scripts/start_all_services.sh
   ```

2. **Install Dependencies**:
   ```bash
   pip install pytest pytest-asyncio httpx
   ```

## Running Tests

### Run All E2E Tests
```bash
# From project root
pytest tests/e2e/ -v

# With detailed output
pytest tests/e2e/ -v -s

# With coverage
pytest tests/e2e/ --cov=services
```

### Run Specific Test File
```bash
pytest tests/e2e/test_trading_cycle.py -v
```

### Run Specific Test
```bash
pytest tests/e2e/test_trading_cycle.py::test_full_buy_cycle_with_profit -v
```

### Run by Marker
```bash
# Run only smoke tests (critical path)
pytest tests/e2e/ -m smoke

# Run only slow tests
pytest tests/e2e/ -m slow

# Exclude slow tests
pytest tests/e2e/ -m "not slow"
```

## Available Fixtures

### Service Clients
- `market_data_client` - Market Data Service client
- `trading_engine_client` - Trading Engine client
- `portfolio_client` - Portfolio Manager client
- `technical_analysis_client` - Technical Analysis client
- `api_gateway_client` - API Gateway client

### Test Data
- `bullish_market_data` - Bullish candlestick data
- `bearish_market_data` - Bearish candlestick data
- `initial_portfolio` - Initial portfolio state
- `bullish_indicators` - Bullish technical indicators
- `bearish_indicators` - Bearish technical indicators

### Example Usage

```python
import pytest
from tests.e2e.utils.assertions import (
    assert_trade_executed,
    assert_position_opened,
    assert_pnl_positive
)

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_profitable_trade(
    market_data_client,
    trading_engine_client,
    portfolio_client,
    bullish_market_data
):
    \"\"\"Test a complete profitable trading cycle.\"\"\"

    # Setup: Get initial balance
    initial_balance = await portfolio_client.get_balance()

    # Step 1: Inject bullish market data
    await market_data_client.inject_candles(
        symbol="BTCUSDT",
        candles=bullish_market_data,
        interval="60"
    )

    # Step 2: Wait for signal and position
    await asyncio.sleep(5)

    # Step 3: Verify position opened
    positions = await portfolio_client.get_positions()
    assert_position_opened(positions, "BTCUSDT", "BUY")

    # Step 4: Verify profit
    final_balance = await portfolio_client.get_balance()
    pnl = final_balance - initial_balance
    assert_pnl_positive(pnl)
```

## Utilities

### Health Checks
```python
from tests.e2e.utils.wait_for_health import (
    wait_for_service_health,
    wait_for_all_services,
    poll_until
)

# Wait for a service
await wait_for_service_health("trading-engine", timeout=60)

# Wait for multiple services
results = await wait_for_all_services(
    services=["trading-engine", "market-data"],
    timeout=120
)

# Poll until condition is met
async def check_trade_complete():
    trades = await portfolio_client.get_trade_history()
    return len(trades) > 0

success = await poll_until(check_trade_complete, timeout=30)
```

### Custom Assertions
```python
from tests.e2e.utils.assertions import *

# Assert trade was executed
assert_trade_executed(trade_history, "BTCUSDT", "BUY")

# Assert position opened
assert_position_opened(positions, "BTCUSDT", "BUY", min_quantity=Decimal("0.01"))

# Assert position closed
assert_position_closed(positions, "BTCUSDT")

# Assert P&L positive
assert_pnl_positive(pnl, min_profit=Decimal("10.00"))

# Assert risk check passed
assert_risk_check_passed(risk_response)

# Assert service healthy
assert_service_healthy(health_response, "Trading Engine")

# Assert response time
assert_response_time(elapsed_time, max_time=1.0, operation="Signal Aggregation")
```

### Mock Data Generators
```python
from tests.e2e.fixtures.mock_data import *

# Generate market data
bullish_candles = generate_bullish_candles(start_price=100.0, num_candles=50)
bearish_candles = generate_bearish_candles(start_price=100.0, num_candles=50)
sideways_candles = generate_sideways_candles(base_price=100.0, num_candles=50)

# Generate trade data
trade = generate_trade_data("BTCUSDT", "BUY", 0.01, 100.0, pnl=5.0)

# Generate portfolio data
portfolio = generate_portfolio_data(balance=10000.0, positions=[])

# Generate indicators
indicators = generate_indicator_data(
    rsi=25.0,
    macd=1.5,
    bb_position=15.0,
    trend_filter="BULLISH"
)

# Create complete scenarios
profitable_scenario = create_profitable_trade_scenario()
losing_scenario = create_losing_trade_scenario()
```

## Test Markers

- `@pytest.mark.e2e` - End-to-end test
- `@pytest.mark.smoke` - Smoke test (critical path)
- `@pytest.mark.slow` - Slow running test (>10s)
- `@pytest.mark.integration` - Integration test

## Debugging

### View Service Logs
```bash
# Tail all logs
docker-compose logs -f

# View specific service
docker-compose logs trading-engine -f
```

### Check Service Health
```bash
# Use the health check utility
python tests/e2e/utils/wait_for_health.py trading-engine

# Check all services
python tests/e2e/utils/wait_for_health.py
```

### Run Tests with Debug Output
```bash
# Show all print statements
pytest tests/e2e/ -v -s

# Show detailed logs
pytest tests/e2e/ --log-cli-level=DEBUG

# Stop on first failure
pytest tests/e2e/ -x

# Drop into debugger on failure
pytest tests/e2e/ --pdb
```

## Best Practices

1. **Use Fixtures**: Leverage pytest fixtures for reusable setup
2. **Clean State**: Tests should not depend on each other
3. **Descriptive Names**: Use clear, descriptive test names
4. **Document Steps**: Add comments explaining test steps
5. **Custom Assertions**: Use domain-specific assertions
6. **Realistic Data**: Use realistic mock data
7. **Timeouts**: Always use timeouts for async operations
8. **Error Messages**: Provide clear error messages

## Troubleshooting

### Services Not Healthy
```bash
# Check if services are running
docker-compose ps

# Check service logs
docker-compose logs --tail=100 trading-engine

# Restart services
docker-compose restart
```

### Tests Timing Out
- Increase timeout in `wait_for_service_health`
- Check service logs for errors
- Verify network connectivity
- Check resource usage (CPU/memory)

### Tests Failing Intermittently
- Increase wait times between steps
- Use `poll_until` instead of fixed waits
- Check for race conditions
- Verify cleanup between tests

## Contributing

When adding new E2E tests:

1. **Create Test File**: Add `test_*.py` file in this directory
2. **Use Fixtures**: Utilize existing fixtures from `conftest.py`
3. **Add Markers**: Tag tests appropriately (`@pytest.mark.e2e`, etc.)
4. **Document**: Add docstrings explaining what the test validates
5. **Clean Up**: Ensure tests clean up after themselves

## Related Documentation

- [E2E Testing Guide](../../docs/development/E2E_TESTING_GUIDE.md)
- [Testing Strategy](../../docs/development/TESTING.md)
- [System Architecture](../../docs/architecture/SYSTEM_OVERVIEW.md)
