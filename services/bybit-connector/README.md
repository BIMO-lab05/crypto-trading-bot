# Bybit Connector Service

Microservice for interfacing with Bybit exchange API.

## Features

- ✅ REST API client with authentication
- ✅ Circuit breaker pattern for resilience
- ✅ Exponential backoff retry logic
- ✅ Comprehensive error handling
- ✅ FastAPI REST endpoints
- ✅ Account management (balance, positions)
- ✅ Order management (place, cancel, query)
- ✅ Market data (ticker, kline, orderbook)

## Setup

1. **Create virtual environment**
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Bybit testnet API keys
   ```

4. **Run tests**
   ```bash
   pytest tests/ -v
   ```

5. **Start service**
   ```bash
   uvicorn app.main:app --reload --port 8001
   ```

## API Documentation

Once running, visit: http://localhost:8001/docs

## Endpoints

- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /api/v1/account/balance` - Get wallet balance
- `GET /api/v1/account/positions` - Get positions
- `POST /api/v1/order/place` - Place order
- `POST /api/v1/order/cancel` - Cancel order
- `GET /api/v1/order/open` - Get open orders
- `GET /api/v1/market/ticker` - Get ticker data
- `GET /api/v1/market/kline` - Get candlestick data

## Testing

```bash
# Run all tests
pytest tests/ -v --cov=app

# Run specific test file
pytest tests/test_bybit_client.py -v

# Generate coverage report
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

## Architecture

```
app/
├── __init__.py
├── main.py                 # FastAPI application
├── config.py              # Configuration management
├── exceptions.py          # Custom exceptions
├── auth.py                # Authentication & signatures
├── bybit_rest_client.py   # REST API client
└── circuit_breaker.py     # Circuit breaker pattern
```

## Circuit Breaker

The service implements circuit breaker pattern:
- Opens after 5 consecutive failures
- Stays open for 60 seconds
- Moves to half-open to test recovery
- Closes on successful request

Check status: `GET /api/v1/status/circuit-breaker`
Reset: `POST /api/v1/status/circuit-breaker/reset`
