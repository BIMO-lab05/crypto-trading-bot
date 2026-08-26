# End-to-End Testing Guide

## Overview

This guide defines the end-to-end (E2E) testing strategy for the Crypto Trading Bot system. E2E tests validate complete workflows across all microservices, ensuring the system functions correctly as an integrated whole.

## Testing Goals

### Coverage Targets
- **Critical Trading Flows**: 100% coverage
- **User Workflows**: All major paths tested
- **Service Integration**: All service-to-service interactions
- **Error Handling**: Graceful degradation and recovery

### Performance Requirements
- Complete trading cycle: < 5 seconds
- Data pipeline latency: < 1 second
- API Gateway response: < 100ms
- System uptime: 99.9%

---

## Test Scenarios

### 1. Complete Trading Cycle (Critical Path)

**Workflow:**
```
1. Market Data → Technical Analysis → Trading Signal
2. Signal Aggregation → Risk Check → Order Generation
3. Order Execution → Position Tracking → Portfolio Update
4. Profit/Loss Calculation → Alert Generation
```

**Services Involved:**
- Market Data Service (8003)
- Technical Analysis Service (8004)
- Trading Engine (8005)
- Bybit Connector (8002)
- Portfolio Manager (8006)
- Notification Service (8010)
- API Gateway (8000)

**Test Cases:**
1. `test_full_buy_cycle_with_profit`
2. `test_full_sell_cycle_with_loss`
3. `test_trading_cycle_with_stop_loss_trigger`
4. `test_trading_cycle_with_take_profit_trigger`
5. `test_trading_cycle_risk_limit_rejection`

---

### 2. Data Pipeline Flow

**Workflow:**
```
1. Real-time price data from Bybit WebSocket
2. Store in TimescaleDB via Market Data Service
3. Cache in Redis for fast access
4. Trigger technical analysis calculations
5. Generate trading signals
6. Publish to RabbitMQ message bus
```

**Services Involved:**
- Bybit Connector (WebSocket)
- Market Data Service
- Redis Cache
- TimescaleDB
- Technical Analysis Service
- RabbitMQ Message Bus

**Test Cases:**
1. `test_realtime_data_ingestion_and_storage`
2. `test_data_cache_invalidation`
3. `test_data_pipeline_with_missing_data`
4. `test_historical_data_backfill`
5. `test_data_pipeline_performance_under_load`

---

### 3. Signal Generation and Aggregation

**Workflow:**
```
1. Fetch latest market data (OHLCV)
2. Calculate technical indicators (RSI, MACD, BB, EMA)
3. Generate individual indicator signals
4. Aggregate signals with confidence weighting
5. Apply trend filter and gatekeeper logic
6. Validate signal confidence threshold
7. Send final signal to Trading Engine
```

**Services Involved:**
- Market Data Service
- Technical Analysis Service
- Trading Engine (Signal Aggregator)

**Test Cases:**
1. `test_signal_generation_all_indicators_bullish`
2. `test_signal_generation_conflicting_indicators`
3. `test_signal_blocked_by_bearish_trend`
4. `test_signal_rejected_low_confidence`
5. `test_signal_aggregation_timeout_handling`

---

### 4. Risk Management Flow

**Workflow:**
```
1. Receive trading signal from aggregator
2. Check account balance and available margin
3. Calculate position size (max 10% of portfolio)
4. Validate daily P&L limits (max 5% loss)
5. Check max concurrent positions limit
6. Apply risk/reward ratio validation
7. Approve or reject trade
```

**Services Involved:**
- Trading Engine (Risk Manager)
- Portfolio Manager
- Trading Engine (Position Manager)

**Test Cases:**
1. `test_risk_check_blocks_oversized_position`
2. `test_risk_check_blocks_excessive_daily_loss`
3. `test_risk_check_allows_valid_trade`
4. `test_risk_check_emergency_stop_all_trading`
5. `test_risk_check_max_concurrent_positions`

---

### 5. Order Execution and Tracking

**Workflow:**
```
1. Generate order from approved signal
2. Send order to Bybit via Bybit Connector
3. Receive order confirmation and ID
4. Track order status (pending → filled)
5. Update position in Portfolio Manager
6. Calculate realized/unrealized P&L
7. Send notifications
```

**Services Involved:**
- Trading Engine (Order Generator)
- Bybit Connector
- Portfolio Manager
- Notification Service

**Test Cases:**
1. `test_order_execution_successful_fill`
2. `test_order_execution_partial_fill`
3. `test_order_execution_rejection_by_exchange`
4. `test_order_execution_timeout_handling`
5. `test_order_execution_network_failure_recovery`

---

### 6. ML Prediction Integration (Phase 3)

**Workflow:**
```
1. Fetch historical price data
2. Train ML model (LSTM/GRU)
3. Generate price predictions
4. Combine with technical indicators
5. Enhanced signal generation
6. Execute trade with ML-augmented signals
```

**Services Involved:**
- ML Prediction Service (8007)
- Market Data Service
- Technical Analysis Service
- Trading Engine

**Test Cases:**
1. `test_ml_prediction_model_training`
2. `test_ml_prediction_inference`
3. `test_ml_prediction_integration_with_signals`
4. `test_ml_prediction_fallback_on_failure`
5. `test_ml_prediction_performance_impact`

---

### 7. Sentiment Analysis Integration (Phase 3)

**Workflow:**
```
1. Fetch social media sentiment (Twitter, Reddit)
2. Analyze sentiment (positive/negative/neutral)
3. Calculate sentiment score
4. Combine with technical + ML signals
5. Adjust confidence based on sentiment
6. Execute trade
```

**Services Involved:**
- Sentiment Analysis Service (8008)
- Technical Analysis Service
- ML Prediction Service
- Trading Engine

**Test Cases:**
1. `test_sentiment_analysis_positive_sentiment`
2. `test_sentiment_analysis_negative_sentiment`
3. `test_sentiment_analysis_neutral_sentiment`
4. `test_sentiment_integration_with_signals`
5. `test_sentiment_analysis_fallback_on_api_failure`

---

### 8. Frontend Dashboard Interaction

**Workflow:**
```
1. User opens dashboard (React frontend)
2. Frontend requests data via API Gateway
3. Display real-time portfolio balance
4. Display active positions
5. Display recent trade history
6. User clicks emergency stop button
7. System halts all trading
```

**Services Involved:**
- Frontend (React, Port 5173)
- API Gateway (8000)
- Portfolio Manager
- Trading Engine
- All backend services

**Test Cases:**
1. `test_dashboard_loads_portfolio_data`
2. `test_dashboard_displays_realtime_updates`
3. `test_dashboard_emergency_stop_functionality`
4. `test_dashboard_handles_service_unavailability`
5. `test_dashboard_websocket_reconnection`

---

### 9. Multi-Service Failure Scenarios

**Workflow:**
```
1. Simulate failure of Technical Analysis Service
2. Trading Engine should fallback to last known signals
3. Continue monitoring for service recovery
4. Resume normal operation when service returns
```

**Services Involved:**
- All services (resilience testing)

**Test Cases:**
1. `test_system_continues_with_ta_service_down`
2. `test_system_continues_with_market_data_down`
3. `test_system_halts_safely_with_bybit_connector_down`
4. `test_system_recovers_after_database_outage`
5. `test_circuit_breaker_prevents_cascade_failures`

---

### 10. Performance and Scalability

**Workflow:**
```
1. Generate high volume of trading signals
2. Process concurrent trades across multiple symbols
3. Handle burst traffic to API Gateway
4. Maintain response time SLAs
5. Monitor resource usage
```

**Services Involved:**
- All services (system-wide load testing)

**Test Cases:**
1. `test_system_handles_100_concurrent_signals`
2. `test_api_gateway_throughput_1000_rps`
3. `test_database_connection_pool_under_load`
4. `test_message_queue_handles_burst_traffic`
5. `test_system_resource_usage_within_limits`

---

## Test Implementation

### Directory Structure

```
tests/e2e/
├── __init__.py
├── conftest.py                      # E2E test fixtures
├── test_trading_cycle.py            # Scenario 1
├── test_data_pipeline.py            # Scenario 2
├── test_signal_generation.py        # Scenario 3
├── test_risk_management.py          # Scenario 4
├── test_order_execution.py          # Scenario 5
├── test_ml_integration.py           # Scenario 6
├── test_sentiment_integration.py    # Scenario 7
├── test_frontend_interaction.py     # Scenario 8
├── test_failure_scenarios.py        # Scenario 9
├── test_performance.py              # Scenario 10
├── fixtures/
│   ├── __init__.py
│   ├── services.py                  # Service client fixtures
│   ├── mock_data.py                 # Mock market data
│   └── test_config.py               # Test configuration
└── utils/
    ├── __init__.py
    ├── service_manager.py           # Start/stop services
    ├── wait_for_health.py           # Health check utilities
    └── assertions.py                # Custom assertions
```

### Example E2E Test Template

```python
# tests/e2e/test_trading_cycle.py

import pytest
import asyncio
import httpx
from decimal import Decimal

# Host-run tests read the declared account size — never write a literal
from shared.account import PAPER_INITIAL_BALANCE

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_buy_cycle_with_profit(
    services,
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    \"\"\"
    Test complete buy-to-sell cycle resulting in profit.

    Steps:
    1. Inject bullish market data
    2. Wait for signal generation
    3. Verify order execution
    4. Simulate price increase
    5. Trigger take-profit
    6. Verify profit in portfolio
    \"\"\"
    symbol = "BTCUSDT"
    initial_balance = Decimal(str(PAPER_INITIAL_BALANCE))

    # Step 1: Setup initial portfolio
    await portfolio_client.set_balance(initial_balance)

    # Step 2: Inject bullish market data
    await market_data_client.inject_price_data(
        symbol=symbol,
        prices=[100, 101, 102, 103, 104, 105],  # Uptrend
        interval="60"
    )

    # Step 3: Wait for signal generation and order execution
    await asyncio.sleep(5)  # Allow time for signal processing

    # Step 4: Verify position was opened
    positions = await portfolio_client.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == symbol
    assert positions[0]["side"] == "BUY"
    entry_price = Decimal(positions[0]["entry_price"])

    # Step 5: Simulate price increase (take profit trigger)
    target_price = entry_price * Decimal("1.10")  # 10% profit
    await market_data_client.inject_price_data(
        symbol=symbol,
        prices=[float(target_price)],
        interval="60"
    )

    # Step 6: Wait for take-profit execution
    await asyncio.sleep(5)

    # Step 7: Verify position closed and profit realized
    positions = await portfolio_client.get_positions()
    assert len(positions) == 0  # Position should be closed

    final_balance = await portfolio_client.get_balance()
    assert final_balance > initial_balance  # Profit was made

    # Step 8: Verify trade history
    history = await portfolio_client.get_trade_history()
    assert len(history) == 2  # Buy and sell orders
    assert history[0]["side"] == "BUY"
    assert history[1]["side"] == "SELL"
    assert history[1]["pnl"] > 0  # Profitable trade
```

### Pytest Fixtures for E2E

```python
# tests/e2e/conftest.py

import pytest
import asyncio
import httpx
from typing import Dict, AsyncGenerator

@pytest.fixture(scope="session")
async def services():
    \"\"\"Start all required services for E2E testing.\"\"\"
    from tests.e2e.utils.service_manager import ServiceManager

    manager = ServiceManager()

    # Start services in dependency order
    await manager.start_service("market-data-service", port=8003)
    await manager.start_service("technical-analysis", port=8004)
    await manager.start_service("trading-engine", port=8005)
    await manager.start_service("portfolio-manager", port=8006)
    await manager.start_service("bybit-connector", port=8002)
    await manager.start_service("api-gateway", port=8000)

    # Wait for all services to be healthy
    await manager.wait_for_all_healthy(timeout=60)

    yield manager

    # Cleanup: stop all services
    await manager.stop_all_services()

@pytest.fixture
async def market_data_client(services):
    \"\"\"HTTP client for Market Data Service.\"\"\"
    async with httpx.AsyncClient(base_url="http://localhost:8003") as client:
        yield MarketDataClient(client)

@pytest.fixture
async def trading_engine_client(services):
    \"\"\"HTTP client for Trading Engine.\"\"\"
    async with httpx.AsyncClient(base_url="http://localhost:8005") as client:
        yield TradingEngineClient(client)

@pytest.fixture
async def portfolio_client(services):
    \"\"\"HTTP client for Portfolio Manager.\"\"\"
    async with httpx.AsyncClient(base_url="http://localhost:8006") as client:
        yield PortfolioClient(client)

@pytest.fixture(autouse=True)
async def cleanup_state(services):
    \"\"\"Clean up state between tests.\"\"\"
    # Reset database state
    # Clear Redis cache
    # Reset RabbitMQ queues
    yield
    # Cleanup after test
```

---

## Running E2E Tests

### Prerequisites

```bash
# 1. Ensure all services are built
docker-compose build

# 2. Start required infrastructure
docker-compose up -d postgres redis rabbitmq timescaledb

# 3. Install E2E test dependencies
pip install -r tests/e2e/requirements.txt
```

### Execute E2E Tests

```bash
# Run all E2E tests
pytest tests/e2e/ -v -s

# Run specific scenario
pytest tests/e2e/test_trading_cycle.py -v

# Run with coverage
pytest tests/e2e/ --cov=services --cov-report=html

# Run in parallel (faster)
pytest tests/e2e/ -n 4

# Run with detailed logging
pytest tests/e2e/ --log-cli-level=DEBUG
```

### Continuous Integration

```yaml
# .github/workflows/e2e-tests.yml

name: E2E Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432

      redis:
        image: redis:7
        ports:
          - 6379:6379

      rabbitmq:
        image: rabbitmq:3-management
        ports:
          - 5672:5672
          - 15672:15672

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r tests/e2e/requirements.txt

      - name: Run E2E tests
        run: pytest tests/e2e/ -v --cov=services

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Debugging E2E Tests

### View Service Logs

```bash
# Tail all service logs
docker-compose logs -f

# View specific service
docker-compose logs trading-engine

# View last 100 lines
docker-compose logs --tail=100 trading-engine
```

### Interactive Debugging

```python
# Add breakpoint in test
import pytest

@pytest.mark.e2e
async def test_something():
    # Test code...

    import pdb; pdb.set_trace()  # Debugger will pause here

    # Continue test...
```

### Check Service Health

```bash
# Health check script
for port in 8000 8002 8003 8004 8005 8006; do
    echo "=== Port $port ==="
    curl -s http://localhost:$port/health | jq
done
```

---

## Best Practices

### DO ✅

- **Test realistic scenarios** that users will actually encounter
- **Use production-like data** for testing
- **Test both happy paths and failure scenarios**
- **Clean up state** between tests
- **Make tests idempotent** (can run multiple times safely)
- **Use timeouts** to prevent hanging tests
- **Mock external APIs** (Bybit testnet, social media)
- **Parallelize independent tests** for speed
- **Log detailed information** for debugging
- **Monitor test execution time** and optimize slow tests

### DON'T ❌

- **Depend on external APIs** that can fail
- **Use production credentials** in tests
- **Share state** between tests
- **Make tests too complex** (split into smaller tests)
- **Ignore flaky tests** (fix or remove them)
- **Test implementation details** (test behavior)
- **Use sleep for synchronization** (poll for conditions instead)
- **Hardcode timeouts** (make them configurable)

---

## Success Criteria

### E2E Test Suite Completion Checklist

- [ ] All 10 test scenarios implemented
- [ ] Minimum 5 test cases per scenario
- [ ] All critical paths covered
- [ ] Failure scenarios tested
- [ ] Performance benchmarks established
- [ ] CI/CD pipeline integrated
- [ ] Documentation complete
- [ ] Test execution time < 10 minutes
- [ ] No flaky tests (>95% reliability)
- [ ] Code coverage > 70% (E2E perspective)

---

## Next Steps

After completing E2E testing:

1. **Production Deployment Preparation**
   - Staging environment validation
   - Production deployment playbook
   - Rollback procedures

2. **Monitoring and Alerting**
   - Set up Prometheus + Grafana
   - Configure alerts for critical failures
   - Create dashboards

3. **Security Hardening**
   - Penetration testing
   - Dependency vulnerability scanning
   - API rate limiting validation

4. **Performance Optimization**
   - Identify bottlenecks
   - Optimize database queries
   - Scale horizontally

---

## Related Documentation

- [Testing Strategy](./TESTING.md)
- [System Architecture](../architecture/SYSTEM_OVERVIEW.md)
- [Service Contracts](../architecture/SERVICE_CONTRACTS.md)
- [Deployment Guide](../DEPLOYMENT.md)

---

**Version:** 1.0
**Last Updated:** 2025-11-11
**Owner:** Trading Bot Dev Team
