# Technical Analysis Service

## Overview

The Technical Analysis Service provides REST API endpoints for calculating technical indicators and generating trading signals. It analyzes market data fetched from the Market Data Service and returns actionable signals with confidence scores.

## Architecture

```
┌─────────────────────┐
│  Trading Engine     │
│  (Port: 8004)       │
└──────────┬──────────┘
           │
           ↓ GET /api/v1/indicators/*
┌─────────────────────────────────────┐
│  Technical Analysis Service         │
│  Port: 8004                         │
│  • RSI Calculator                   │
│  • MACD Calculator                  │
│  • Bollinger Bands Calculator       │
│  • Moving Averages (SMA/EMA)        │
└──────────┬──────────────────────────┘
           │
           ↓ GET /api/v1/klines/*
┌─────────────────────┐
│  Market Data Service│
│  Port: 8003         │
└─────────────────────┘
```

## Technical Indicators

### 1. RSI (Relative Strength Index)

**Purpose**: Momentum oscillator measuring speed and magnitude of price changes

**Interpretation**:
- **RSI > 70**: Overbought (potential SELL)
- **RSI < 30**: Oversold (potential BUY)
- **RSI 40-60**: Neutral (HOLD)

**Parameters**:
- `period`: Calculation period (default: 14)
- `interval`: Candlestick interval (default: "60" = 1 hour)
- `limit`: Number of candles (default: 200)

**Endpoint**: `GET /api/v1/indicators/rsi/{symbol}`

**Example Request**:
```bash
curl "http://localhost:8004/api/v1/indicators/rsi/BTCUSDT?interval=60&period=14"
```

**Example Response**:
```json
{
  "symbol": "BTCUSDT",
  "interval": "60",
  "timestamp": 1730332800000,
  "rsi": 43.74,
  "signal": "HOLD",
  "confidence": 0.69,
  "parameters": {
    "period": 14
  }
}
```

### 2. MACD (Moving Average Convergence Divergence)

**Purpose**: Trend-following momentum indicator showing relationship between two EMAs

**Interpretation**:
- **MACD crosses above Signal**: Bullish (BUY)
- **MACD crosses below Signal**: Bearish (SELL)
- **Histogram**: Difference magnitude

**Parameters**:
- `fast`: Fast EMA period (default: 12)
- `slow`: Slow EMA period (default: 26)
- `signal`: Signal line period (default: 9)
- `interval`: Candlestick interval (default: "60")
- `limit`: Number of candles (default: 200)

**Endpoint**: `GET /api/v1/indicators/macd/{symbol}`

**Example Request**:
```bash
curl "http://localhost:8004/api/v1/indicators/macd/BTCUSDT?interval=60&fast=12&slow=26&signal=9"
```

**Example Response**:
```json
{
  "symbol": "BTCUSDT",
  "interval": "60",
  "timestamp": 1730332800000,
  "macd_line": 428.08,
  "signal_line": 43171.64,
  "histogram": -42743.55,
  "signal": "SELL",
  "confidence": 1.0,
  "parameters": {
    "fast": 12,
    "slow": 26,
    "signal": 9
  }
}
```

### 3. Bollinger Bands

**Purpose**: Volatility indicator using standard deviation bands

**Interpretation**:
- **Price at/below lower band**: Oversold (BUY)
- **Price at/above upper band**: Overbought (SELL)
- **Price in middle**: Neutral (HOLD)

**Parameters**:
- `period`: SMA period (default: 20)
- `std_dev`: Standard deviations (default: 2.0)
- `interval`: Candlestick interval (default: "60")
- `limit`: Number of candles (default: 200)

**Endpoint**: `GET /api/v1/indicators/bollinger/{symbol}`

**Example Request**:
```bash
curl "http://localhost:8004/api/v1/indicators/bollinger/BTCUSDT?interval=60&period=20&std_dev=2.0"
```

**Example Response**:
```json
{
  "symbol": "BTCUSDT",
  "interval": "60",
  "timestamp": 1730332800000,
  "upper_band": 2037627.19,
  "middle_band": 1898586.49,
  "lower_band": 1759545.78,
  "current_price": 1759541.40,
  "signal": "BUY",
  "confidence": 0.4,
  "parameters": {
    "period": 20,
    "std_dev": 2.0
  }
}
```

### 4. SMA (Simple Moving Average)

**Purpose**: Average price over a period

**Interpretation**:
- **Price > SMA**: Bullish trend (BUY)
- **Price < SMA**: Bearish trend (SELL)
- **Distance from SMA**: Determines confidence

**Parameters**:
- `period`: Number of periods (default: 20)
- `interval`: Candlestick interval (default: "60")
- `limit`: Number of candles (default: 200)

**Endpoint**: `GET /api/v1/indicators/sma/{symbol}`

**Example Request**:
```bash
curl "http://localhost:8004/api/v1/indicators/sma/BTCUSDT?interval=60&period=20"
```

**Example Response**:
```json
{
  "symbol": "BTCUSDT",
  "interval": "60",
  "timestamp": 1730332800000,
  "ma_type": "SMA",
  "value": 1898586.49,
  "current_price": 1759541.40,
  "signal": "SELL",
  "confidence": 1.0,
  "parameters": {
    "period": 20
  }
}
```

### 5. EMA (Exponential Moving Average)

**Purpose**: Weighted moving average giving more importance to recent prices

**Interpretation**:
- **Price > EMA**: Bullish trend (BUY)
- **Price < EMA**: Bearish trend (SELL)
- More responsive than SMA

**Parameters**:
- `period`: Number of periods (default: 20)
- `interval`: Candlestick interval (default: "60")
- `limit`: Number of candles (default: 200)

**Endpoint**: `GET /api/v1/indicators/ema/{symbol}`

**Example Request**:
```bash
curl "http://localhost:8004/api/v1/indicators/ema/BTCUSDT?interval=60&period=20"
```

**Example Response**:
```json
{
  "symbol": "BTCUSDT",
  "interval": "60",
  "timestamp": 1730332800000,
  "ma_type": "EMA",
  "value": 1825889.47,
  "current_price": 1759541.40,
  "signal": "SELL",
  "confidence": 0.73,
  "parameters": {
    "period": 20
  }
}
```

## Signal Types

All indicators return one of these signals:

- **BUY**: Bullish signal suggesting buying opportunity
- **SELL**: Bearish signal suggesting selling opportunity
- **HOLD**: Neutral signal, no action recommended
- **NEUTRAL**: Insufficient data or unclear signal

## Confidence Scoring

Each signal includes a confidence score (0.0 - 1.0):

- **0.9 - 1.0**: Very high confidence (strong signal)
- **0.7 - 0.8**: High confidence
- **0.5 - 0.6**: Moderate confidence
- **0.3 - 0.4**: Low confidence
- **0.1 - 0.2**: Very low confidence (weak signal)

Confidence is calculated based on:
- Distance from threshold values
- Volatility conditions
- Indicator-specific factors

## Health Endpoints

### Health Check
```bash
curl http://localhost:8004/health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "technical-analysis",
  "market_data_connection": true,
  "timestamp": 1730332800000
}
```

### Readiness Check
```bash
curl http://localhost:8004/ready
```

**Response**:
```json
{
  "status": "ready",
  "service": "technical-analysis",
  "dependencies": {
    "market_data_service": true
  },
  "timestamp": 1730332800000
}
```

## Installation & Setup

### Prerequisites
- Python 3.12+
- Market Data Service running on port 8003
- Virtual environment (recommended)

### Install Dependencies
```bash
cd services/technical-analysis
pip install -r requirements.txt
```

### Environment Configuration

Create `.env` file:
```env
# Service Configuration
SERVICE_NAME=technical-analysis
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8004
DEBUG=true
LOG_LEVEL=INFO

# Market Data Service
MARKET_DATA_URL=http://localhost:8003

# Indicator Defaults
DEFAULT_RSI_PERIOD=14
DEFAULT_MACD_FAST=12
DEFAULT_MACD_SLOW=26
DEFAULT_MACD_SIGNAL=9
DEFAULT_BB_PERIOD=20
DEFAULT_BB_STD_DEV=2.0
DEFAULT_MA_PERIOD=20
```

### Run Service

**Development Mode**:
```bash
python app/main.py
```

**Production Mode**:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8004 --workers 4
```

**With Docker** (if docker-compose is configured):
```bash
docker-compose up technical-analysis
```

## API Documentation

Once running, access interactive API docs:

- **Swagger UI**: http://localhost:8004/docs
- **ReDoc**: http://localhost:8004/redoc
- **OpenAPI JSON**: http://localhost:8004/openapi.json

## Project Structure

```
technical-analysis/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration settings
│   ├── models.py               # Pydantic models
│   ├── fetcher.py              # Market data fetcher
│   └── indicators/
│       ├── __init__.py
│       ├── rsi.py              # RSI calculator
│       ├── macd.py             # MACD calculator
│       ├── bollinger_bands.py  # Bollinger Bands calculator
│       └── moving_averages.py  # SMA/EMA calculators
├── logs/
│   └── service.log             # Application logs
├── tests/                      # Unit tests (TODO)
├── .env                        # Environment variables
├── requirements.txt            # Python dependencies
├── PROGRESS.md                 # Development progress
└── README.md                   # This file
```

## Dependencies

Core packages:
- **fastapi**: Web framework
- **uvicorn**: ASGI server
- **pydantic**: Data validation
- **pydantic-settings**: Settings management
- **httpx**: Async HTTP client
- **pandas**: Data analysis
- **numpy**: Numerical computing

## Example: Multiple Indicators Analysis

Fetch all indicators for comprehensive analysis:

```bash
#!/bin/bash
SYMBOL="BTCUSDT"
INTERVAL="60"

echo "=== RSI ==="
curl -s "http://localhost:8004/api/v1/indicators/rsi/$SYMBOL?interval=$INTERVAL" | jq

echo -e "\n=== MACD ==="
curl -s "http://localhost:8004/api/v1/indicators/macd/$SYMBOL?interval=$INTERVAL" | jq

echo -e "\n=== Bollinger Bands ==="
curl -s "http://localhost:8004/api/v1/indicators/bollinger/$SYMBOL?interval=$INTERVAL" | jq

echo -e "\n=== SMA ==="
curl -s "http://localhost:8004/api/v1/indicators/sma/$SYMBOL?interval=$INTERVAL" | jq

echo -e "\n=== EMA ==="
curl -s "http://localhost:8004/api/v1/indicators/ema/$SYMBOL?interval=$INTERVAL" | jq
```

## Integration with Trading Engine

The Trading Engine will consume these indicators to make trading decisions:

```python
import httpx

async def analyze_symbol(symbol: str, interval: str = "60"):
    """Fetch all indicators for a symbol"""
    base_url = "http://localhost:8004/api/v1/indicators"

    async with httpx.AsyncClient() as client:
        # Fetch all indicators in parallel
        rsi_task = client.get(f"{base_url}/rsi/{symbol}?interval={interval}")
        macd_task = client.get(f"{base_url}/macd/{symbol}?interval={interval}")
        bb_task = client.get(f"{base_url}/bollinger/{symbol}?interval={interval}")
        sma_task = client.get(f"{base_url}/sma/{symbol}?interval={interval}")
        ema_task = client.get(f"{base_url}/ema/{symbol}?interval={interval}")

        responses = await asyncio.gather(
            rsi_task, macd_task, bb_task, sma_task, ema_task
        )

        return {
            "rsi": responses[0].json(),
            "macd": responses[1].json(),
            "bollinger": responses[2].json(),
            "sma": responses[3].json(),
            "ema": responses[4].json()
        }

# Aggregate signals
indicators = await analyze_symbol("BTCUSDT")

buy_signals = sum(1 for ind in indicators.values() if ind["signal"] == "BUY")
sell_signals = sum(1 for ind in indicators.values() if ind["signal"] == "SELL")

if buy_signals >= 3:
    print("Strong BUY consensus")
elif sell_signals >= 3:
    print("Strong SELL consensus")
else:
    print("Mixed signals, HOLD")
```

## Logging

Logs are written to `logs/service.log` with the following levels:

- **INFO**: General operational messages, signal generation
- **DEBUG**: Detailed calculation steps
- **WARNING**: Non-critical issues
- **ERROR**: Errors that need attention

Example log entries:
```
2025-10-30 23:11:23 - app.indicators.rsi - INFO - RSI Calculator initialized with period=14
2025-10-30 23:11:23 - app.indicators.rsi - INFO - RSI: 43.74 → HOLD (conf: 0.69)
2025-10-30 23:11:35 - app.indicators.macd - INFO - MACD 428.08 < Signal 43171.64 → SELL (hist: -42743.55, conf: 1.00)
```

## Performance Considerations

- **Data Caching**: Market data is fetched fresh for each request (no caching at this layer)
- **Calculation Speed**: Pandas/NumPy ensure fast calculations even with 1000+ candles
- **Response Time**: Typically <50ms for single indicator calculation
- **Concurrency**: FastAPI handles multiple concurrent requests efficiently

## Error Handling

Common errors and responses:

### 404 - No Data Available
```json
{
  "detail": "No data available for symbol"
}
```
**Cause**: Symbol not found or no market data

### 400 - Insufficient Data
```json
{
  "detail": "Insufficient data to calculate RSI"
}
```
**Cause**: Not enough historical candles for calculation

### 503 - Market Data Service Unavailable
Health check will show:
```json
{
  "status": "healthy",
  "market_data_connection": false
}
```

## Testing

### Manual Testing

Test all endpoints:
```bash
# Health check
curl http://localhost:8004/health

# Test each indicator
curl "http://localhost:8004/api/v1/indicators/rsi/BTCUSDT?interval=60"
curl "http://localhost:8004/api/v1/indicators/macd/BTCUSDT?interval=60"
curl "http://localhost:8004/api/v1/indicators/bollinger/BTCUSDT?interval=60"
curl "http://localhost:8004/api/v1/indicators/sma/BTCUSDT?interval=60"
curl "http://localhost:8004/api/v1/indicators/ema/BTCUSDT?interval=60"
```

### Unit Tests (TODO)

Run unit tests:
```bash
pytest tests/ -v --cov=app
```

## Troubleshooting

### Service won't start
1. Check Market Data Service is running: `curl http://localhost:8003/health`
2. Verify .env configuration
3. Check logs: `tail -f logs/service.log`

### Indicators return null/None
1. Ensure sufficient candle data (minimum periods required)
2. Check Market Data Service has data for symbol
3. Verify interval is valid

### Slow response times
1. Check Market Data Service response time
2. Reduce `limit` parameter if fetching too many candles
3. Monitor system resources

## Future Enhancements

- [ ] Additional indicators (Stochastic, ATR, Fibonacci)
- [ ] Indicator combination strategies
- [ ] Backtesting capabilities
- [ ] Signal strength aggregation endpoint
- [ ] WebSocket support for real-time signals
- [ ] Caching layer for frequently requested symbols
- [ ] Machine learning-based signal confidence adjustment

## License

Part of the Crypto Trading Bot project - see main project README for license information.

## Support

For issues or questions:
1. Check service logs: `logs/service.log`
2. Verify dependencies are running
3. Review API documentation: http://localhost:8004/docs
4. Check project documentation in `docs/` directory
