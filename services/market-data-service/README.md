# Market Data Service

**Version:** 2.0.0
**Port:** 8002

## Overview

The Market Data Service is a microservice responsible for collecting, storing, and serving cryptocurrency market data from Bybit exchange. It provides real-time and historical candlestick (kline) data, ticker information, and automated data collection through scheduled jobs.

Refactored November 2025 from a single 868-line module into 9 focused modules (Strangler Fig incremental migration), fully backward compatible.

## Architecture

### 4-Layer Clean Architecture

```
┌─────────────────────────────────────────┐
│         HTTP Layer (main.py)            │  FastAPI routes, middleware
├─────────────────────────────────────────┤
│      Handlers Layer (handlers/)         │  Request validation, orchestration
├─────────────────────────────────────────┤
│  Business Logic (repository/, fetcher)  │  Data operations, external APIs
├─────────────────────────────────────────┤
│     Infrastructure (database/, cache)   │  PostgreSQL, Redis, TimescaleDB
└─────────────────────────────────────────┘
```

```
app/
├── main.py                     # Pure routing layer
├── handlers/                   # HTTP request handlers
│   ├── health.py              # Health & metrics endpoints
│   ├── collection.py          # Data collection endpoints
│   ├── query.py               # Data query endpoints
│   └── scheduler.py           # Scheduler control endpoints
├── utils/                      # Extracted utilities
│   ├── logging_config.py      # Structured logging with secret masking
│   ├── metrics.py             # Prometheus metrics & middleware
│   └── request_models.py      # Pydantic validation models
├── repository.py              # Data access layer
├── database.py                # Database connection management
├── fetcher.py                 # External API client
├── scheduler.py               # APScheduler job management
└── config.py                  # Configuration management
```

### Design Principles

- **Single Responsibility:** Each module has one clear purpose
- **Dependency Injection:** FastAPI `Depends` for loose coupling
- **Separation of Concerns:** HTTP ↔ Business Logic ↔ Data Access
- **Testability:** All layers independently testable

## Module Descriptions

### `/app/handlers/`

**Purpose:** HTTP request handling and orchestration

#### `health.py`
- Health check endpoint (`/health`)
- Readiness check with Bybit Connector validation (`/ready`)
- Prometheus metrics exposition (`/metrics`)

#### `collection.py`
- Kline data collection (`POST /api/v1/collect/kline/{symbol}`)
- Ticker data collection (`POST /api/v1/collect/ticker/{symbol}`)
- Bulk collection for multiple symbols (`POST /api/v1/collect/bulk`)
- Symbol validation and error handling

#### `query.py`
- Kline data retrieval with filtering (`GET /api/v1/klines/{symbol}`)
- Latest ticker with 3-tier caching (`GET /api/v1/ticker/{symbol}`)
- Latest kline with Redis caching (`GET /api/v1/latest/{symbol}`)

#### `scheduler.py`
- Scheduler status endpoint (`GET /api/v1/scheduler/status`)
- Manual scheduler control (`POST /api/v1/scheduler/start|stop`)
- Trigger manual collection (`POST /api/v1/scheduler/collect`)

### `/app/utils/`

**Purpose:** Reusable utilities and cross-cutting concerns

#### `logging_config.py`
- Structured JSON logging with `python-json-logger`
- **Secret Masking:** Automatically masks API keys, passwords, tokens, connection strings (10+ regex patterns)
- Configures root logger and suppresses noisy libraries

#### `metrics.py`
- **Prometheus Metrics:**
  - `http_requests_total` - HTTP request counter
  - `http_request_duration_seconds` - Request latency histogram
  - `http_requests_active` - Active requests gauge
  - `data_collection_total` - Data collection attempts
  - `data_records_stored_total` - Records stored counter
  - `bybit_connector_calls_total` - External API calls
  - `database_operations_total` - Database operations
- `PrometheusMiddleware` - Automatic request tracking

#### `request_models.py`
- `IntervalEnum` - Valid candlestick intervals
- `CollectKlineRequest` - Kline collection validation
- `BulkCollectRequest` - Bulk collection validation

## API Endpoints

### Health & Monitoring

| Endpoint | Method | Description | Rate Limit |
|----------|--------|-------------|------------|
| `/health` | GET | Service health status | 60/min |
| `/ready` | GET | Readiness check (validates Bybit Connector) | 60/min |
| `/metrics` | GET | Prometheus metrics | No limit |

### Data Collection (Requires API Key)

| Endpoint | Method | Description | Rate Limit |
|----------|--------|-------------|------------|
| `/api/v1/collect/kline/{symbol}` | POST | Collect historical klines | 20/min |
| `/api/v1/collect/ticker/{symbol}` | POST | Collect current ticker | 30/min |
| `/api/v1/collect/bulk` | POST | Bulk collection (max 10 symbols) | 5/min |

### Data Query (Public)

| Endpoint | Method | Description | Rate Limit |
|----------|--------|-------------|------------|
| `/api/v1/klines/{symbol}` | GET | Get klines with filtering | 60/min |
| `/api/v1/ticker/{symbol}` | GET | Get latest ticker (cached) | 60/min |
| `/api/v1/latest/{symbol}` | GET | Get latest kline (cached) | 60/min |

### Scheduler Control (Requires API Key)

| Endpoint | Method | Description | Rate Limit |
|----------|--------|-------------|------------|
| `/api/v1/scheduler/status` | GET | Get scheduler status | 30/min |
| `/api/v1/scheduler/start` | POST | Start scheduler | 10/min |
| `/api/v1/scheduler/stop` | POST | Stop scheduler | 10/min |
| `/api/v1/scheduler/collect` | POST | Trigger manual collection | 5/min |

## Testing

### Test Coverage

**Total Tests:** 150+ test cases

| Test Type | Location | Count | Coverage |
|-----------|----------|-------|----------|
| **Unit Tests** | `tests/unit/` | 85+ | Utils & Models |
| **Integration Tests** | `tests/integration/` | 67+ | Handlers & Flows |

Unit: `test_logging_config.py`, `test_metrics.py`, `test_request_models.py`.
Integration: `test_health_handlers.py`, `test_collection_handlers.py`, `test_query_handlers.py`.

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_metrics.py -v

# Run integration tests only
pytest tests/integration/ -v
```

## Configuration

### Environment Variables

```bash
# Service Configuration
SERVICE_NAME=market-data-service
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8002
DEBUG=false

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/crypto_bot
TIMESCALE_ENABLED=true

# Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379

# External Services (bybit-connector runs on port 8001)
BYBIT_CONNECTOR_URL=http://bybit-connector:8001

# Security
API_KEY=your-api-key-here

# Logging
LOG_LEVEL=INFO

# Scheduler
SCHEDULER_ENABLED=true
KLINE_COLLECTION_INTERVAL=300  # 5 minutes
TICKER_COLLECTION_INTERVAL=300 # 5 minutes

# Ingest Symbols (wider than the trading universe — trading-engine
# restricts positions to BTC/ETH/SOL/BNB/ADA as of 2026-05-03)
SYMBOLS_LIST=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT
```

## Development Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ with TimescaleDB extension
- Redis 6+
- Docker & Docker Compose

### Local Development

```bash
# 1. Navigate to service directory
cd services/market-data-service

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment
cp .env.example .env
# Edit .env with your configuration

# 5. Run database migrations
alembic upgrade head

# 6. Run the service
uvicorn app.main:app --reload --port 8002
```

### Docker Development

Use the canonical compose file `docker-compose.unified.yml` (plain `docker-compose.yml` is incomplete — missing the databases):

```bash
# Build and run
docker compose -f docker-compose.unified.yml up -d market-data-service

# View logs
docker compose -f docker-compose.unified.yml logs -f market-data-service

# Rebuild after code changes
docker compose -f docker-compose.unified.yml build market-data-service
docker compose -f docker-compose.unified.yml up -d market-data-service
```

## Automated Data Collection

The service runs three automated collection jobs (see `SCHEDULER_SETUP.md` for full setup and customization):

1. **Kline Collection** (every 5 minutes) — candlestick data for configured symbols
2. **Ticker Collection** (every 5 minutes) — real-time ticker data, same symbols
3. **Hourly Full Collection** (every hour at :00) — comprehensive refresh

```bash
# Check scheduler status
curl http://localhost:8002/api/v1/scheduler/status

# View Prometheus metrics
curl http://localhost:8002/metrics

# Check service health
curl http://localhost:8002/health
```

## Caching Strategy

### 3-Tier Caching Architecture

```
Request → Redis Cache (5-60s TTL)
    ↓ (cache miss)
Database (PostgreSQL/TimescaleDB)
    ↓ (data miss)
Live Fetch (Bybit Connector)
    ↓
Store in DB → Cache → Return
```

**TTL Configuration:**
- Tickers: 5 seconds (high volatility)
- Latest Klines: 60 seconds (less volatile)

> Operational note (2026-07): in practice TimescaleDB acts as the working cache (Redis observed empty in testing). If prices look stuck, force-refresh with `POST /api/v1/collect/ticker/{symbol}` or wait up to 5 min for the scheduler.

## Monitoring & Observability

Metrics at `http://localhost:8002/metrics`: request rates/latencies, active connections, collection success/failure, database operations, external API calls.

```bash
# Liveness probe
curl http://localhost:8002/health

# Readiness probe (checks Bybit Connector)
curl http://localhost:8002/ready
```

## Security Features

- **Secret Masking:** logs automatically mask API keys, passwords, tokens (Bearer, JWT), authorization headers, DB connection strings, sensitive query params
- **Rate Limiting:** per-endpoint limits using `slowapi`, keyed by client IP
- **API Key Authentication:** protected endpoints require `X-API-Key` header:
  ```bash
  curl -H "X-API-Key: your-key" http://localhost:8002/api/v1/collect/kline/BTCUSDT
  ```

## Troubleshooting

**Service won't start:**
```bash
docker logs crypto-bot-market-data-service
docker exec crypto-bot-market-data-service python -c "from app.database import init_database; import asyncio; asyncio.run(init_database())"
```

**Scheduler not running:**
```bash
curl http://localhost:8002/api/v1/scheduler/status
curl -X POST -H "X-API-Key: your-key" http://localhost:8002/api/v1/scheduler/start
```

**No data collected:**
```bash
curl http://localhost:8002/ready
curl http://localhost:8002/metrics | grep collection_total
```

## API Examples

```bash
# Collect 7 days of 1-hour klines for BTCUSDT
curl -X POST -H "X-API-Key: your-key" \
  "http://localhost:8002/api/v1/collect/kline/BTCUSDT?interval=60&days=7"

# Get latest 100 klines
curl "http://localhost:8002/api/v1/klines/BTCUSDT?interval=60&limit=100"

# Get klines in time range
curl "http://localhost:8002/api/v1/klines/BTCUSDT?start_time=1700000000000&end_time=1700100000000"

# Get latest ticker (with caching)
curl "http://localhost:8002/api/v1/ticker/BTCUSDT"
```

## Deployment

Zero-downtime deployment supported (all endpoints backward compatible):

```bash
docker compose -f docker-compose.unified.yml build market-data-service
docker compose -f docker-compose.unified.yml up -d market-data-service
docker compose -f docker-compose.unified.yml exec market-data-service curl http://localhost:8002/health
```

## Additional Documentation

- **API Documentation:** http://localhost:8002/docs (Swagger UI)
- **Scheduler Setup & Customization:** `SCHEDULER_SETUP.md`

## Contributing

When modifying this service:

1. Maintain single responsibility per module
2. Add tests for new functionality (unit + integration)
3. Update this README if adding/changing endpoints
4. Follow existing code patterns and naming conventions
5. Ensure all tests pass: `pytest`
6. Update Prometheus metrics for new operations

## License

Part of the Crypto Trading Bot project.
