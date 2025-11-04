# API Gateway Service

## Overview

The API Gateway is the **unified entry point** for the Crypto Trading Bot system. It provides a single, consistent API interface that routes requests to all backend microservices, handles cross-cutting concerns like CORS and error handling, and aggregates data from multiple services.

## Features

### 🎯 Core Capabilities
- **Unified API**: Single entry point for all services
- **Request Routing**: Intelligent routing to 5 backend services
- **Health Aggregation**: Monitor all services from one endpoint
- **Error Handling**: Consistent error responses across all routes
- **CORS Support**: Cross-origin requests enabled
- **Service Discovery**: Automatic backend service health checking

### 🔌 Backend Services Integration
- **Bybit Connector** (Port 8002) - Exchange API
- **Market Data** (Port 8003) - Real-time & historical data
- **Technical Analysis** (Port 8004) - Indicators & signals
- **Trading Engine** (Port 8005) - Trading decisions & execution
- **Portfolio Manager** (Port 8006) - Portfolio tracking & performance

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              API Gateway (Port 8000)                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │   Request    │  │   Service    │  │   Error     │  │
│  │   Router     │  │    Proxy     │  │  Handler    │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────────┘  │
│         │                  │                            │
│         └──────────────────┼────────────────────────────┘
│                            │
└────────────────────────────┼────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
  ┌────────────┐      ┌────────────┐     ┌────────────┐
  │  Market    │      │  Trading   │     │ Portfolio  │
  │   Data     │      │  Engine    │     │  Manager   │
  │  (8003)    │      │  (8005)    │     │  (8006)    │
  └────────────┘      └────────────┘     └────────────┘
         │                   │
         ▼                   ▼
  ┌────────────┐      ┌────────────┐
  │  Bybit     │      │ Technical  │
  │ Connector  │      │ Analysis   │
  │  (8002)    │      │  (8004)    │
  └────────────┘      └────────────┘
```

## API Endpoints

### Health & Status

#### GET /health
Gateway health with all backend services status

```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "api-gateway",
  "version": "1.0.0",
  "timestamp": 1730332800000,
  "backend_services": {
    "bybit_connector": true,
    "market_data": true,
    "technical_analysis": true,
    "trading_engine": true,
    "portfolio_manager": true
  }
}
```

#### GET /
API Gateway information and available endpoints

```bash
curl http://localhost:8000/
```

---

### Market Data Routes

#### GET /api/market/ticker/{symbol}
Get real-time ticker data

```bash
curl "http://localhost:8000/api/market/ticker/BTCUSDT"
```

#### GET /api/market/kline/{symbol}
Get candlestick/kline data

```bash
curl "http://localhost:8000/api/market/kline/BTCUSDT?interval=60&limit=100"
```

**Parameters**:
- `interval`: Time interval (1, 5, 15, 30, 60, 240, D, W, M)
- `limit`: Number of candles (default: 100)

---

### Technical Analysis Routes

#### GET /api/analysis/rsi/{symbol}
Get RSI indicator

```bash
curl "http://localhost:8000/api/analysis/rsi/BTCUSDT?interval=60&period=14"
```

#### GET /api/analysis/macd/{symbol}
Get MACD indicator

```bash
curl "http://localhost:8000/api/analysis/macd/BTCUSDT?interval=60"
```

#### GET /api/analysis/all/{symbol}
Get all technical indicators

```bash
curl "http://localhost:8000/api/analysis/all/BTCUSDT?interval=60"
```

---

### Trading Engine Routes

#### GET /api/trading/signals/{symbol}
Get aggregated trading signal

```bash
curl "http://localhost:8000/api/trading/signals/BTCUSDT?interval=60"
```

**Response**:
```json
{
  "success": true,
  "signal": {
    "symbol": "BTCUSDT",
    "action": "BUY",
    "confidence": 0.75,
    "aggregated_score": 0.68,
    "consensus_count": 4
  }
}
```

#### POST /api/trading/signals/{symbol}/analyze
Analyze signal and optionally execute

```bash
curl -X POST "http://localhost:8000/api/trading/signals/BTCUSDT/analyze?execute=true"
```

#### GET /api/trading/positions
Get trading positions

```bash
curl "http://localhost:8000/api/trading/positions?status=open"
```

---

### Portfolio Manager Routes

#### GET /api/portfolio
Get portfolio details

```bash
curl "http://localhost:8000/api/portfolio?portfolio_id=default"
```

**Response**:
```json
{
  "success": true,
  "portfolio": {
    "portfolio_id": "default",
    "cash_balance": "5000.00",
    "total_value": "10000.00",
    "total_pnl": "200.00",
    "holdings": [...]
  }
}
```

#### GET /api/portfolio/balance
Get portfolio balance

```bash
curl "http://localhost:8000/api/portfolio/balance"
```

#### GET /api/portfolio/holdings
Get all holdings

```bash
curl "http://localhost:8000/api/portfolio/holdings"
```

#### GET /api/portfolio/performance
Get performance metrics

```bash
curl "http://localhost:8000/api/portfolio/performance"
```

#### POST /api/portfolio/buy
Execute buy transaction

```bash
curl -X POST "http://localhost:8000/api/portfolio/buy?symbol=BTCUSDT&quantity=0.1&price=67000"
```

#### POST /api/portfolio/sell
Execute sell transaction

```bash
curl -X POST "http://localhost:8000/api/portfolio/sell?symbol=BTCUSDT&quantity=0.05&price=68000"
```

---

### Aggregation Endpoints

#### GET /api/dashboard/{symbol}
Get aggregated dashboard data from multiple services

```bash
curl "http://localhost:8000/api/dashboard/BTCUSDT?interval=60"
```

**Response**: Combined data from Market Data, Trading Engine, and Portfolio Manager

---

## Configuration

### Environment Variables

Create `.env` file:

```env
# Service Configuration
SERVICE_NAME=api-gateway
SERVICE_PORT=8000
LOG_LEVEL=INFO

# Backend Service URLs
BYBIT_CONNECTOR_URL=http://localhost:8002
MARKET_DATA_URL=http://localhost:8003
TECHNICAL_ANALYSIS_URL=http://localhost:8004
TRADING_ENGINE_URL=http://localhost:8005
PORTFOLIO_MANAGER_URL=http://localhost:8006

# Security
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS
CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]
```

---

## Installation & Deployment

### Prerequisites
- Python 3.12+
- All 5 backend services running

### Install Dependencies

```bash
cd services/api-gateway
pip install -r requirements.txt
```

### Start Service

```bash
# Set PYTHONPATH
export PYTHONPATH=/path/to/api-gateway

# Run with uvicorn
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or with reload for development:

```bash
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Usage Examples

### Complete Trading Flow via Gateway

```bash
# 1. Check system health
curl http://localhost:8000/health

# 2. Get market data
curl "http://localhost:8000/api/market/ticker/BTCUSDT"

# 3. Get trading signal
curl "http://localhost:8000/api/trading/signals/BTCUSDT?interval=60"

# 4. Check portfolio
curl "http://localhost:8000/api/portfolio"

# 5. Execute buy (if signal is good)
curl -X POST "http://localhost:8000/api/portfolio/buy?symbol=BTCUSDT&quantity=0.1&price=67000"

# 6. Check updated portfolio
curl "http://localhost:8000/api/portfolio/holdings"

# 7. Get performance metrics
curl "http://localhost:8000/api/portfolio/performance"
```

### Python Client Example

```python
import httpx
import asyncio

class TradingBotClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()

    async def get_signal(self, symbol: str, interval: str = "60"):
        """Get trading signal"""
        response = await self.client.get(
            f"{self.base_url}/api/trading/signals/{symbol}",
            params={"interval": interval}
        )
        return response.json()

    async def get_portfolio(self):
        """Get portfolio state"""
        response = await self.client.get(f"{self.base_url}/api/portfolio")
        return response.json()

    async def buy_asset(self, symbol: str, quantity: float, price: float):
        """Execute buy transaction"""
        response = await self.client.post(
            f"{self.base_url}/api/portfolio/buy",
            params={"symbol": symbol, "quantity": quantity, "price": price}
        )
        return response.json()

    async def close(self):
        await self.client.aclose()

# Usage
async def main():
    client = TradingBotClient()

    # Get signal
    signal = await client.get_signal("BTCUSDT")
    print(f"Signal: {signal['signal']['action']}")

    # Check portfolio
    portfolio = await client.get_portfolio()
    print(f"Balance: ${portfolio['portfolio']['cash_balance']}")

    # Buy if signal is strong
    if signal['signal']['action'] == 'BUY' and signal['signal']['confidence'] > 0.7:
        result = await client.buy_asset("BTCUSDT", 0.1, 67000)
        print(f"Transaction: {result['message']}")

    await client.close()

asyncio.run(main())
```

---

## Error Handling

The API Gateway provides consistent error responses:

### Service Unavailable (503)
```json
{
  "detail": "Service market-data unavailable"
}
```

### Timeout (504)
```json
{
  "detail": "Timeout connecting to trading-engine"
}
```

### Not Found (404)
```json
{
  "detail": "Service 'unknown-service' not found"
}
```

---

## Performance

- **Response Time**: <100ms (excluding backend service time)
- **Concurrent Requests**: Supports high concurrency with async/await
- **Timeout**: 30 seconds per backend request
- **Health Check**: <5 seconds for all services

---

## Monitoring

### Logs

Service logs are written to `logs/service.log`:

```bash
tail -f logs/service.log
```

### Health Monitoring

Monitor all services with a single endpoint:

```bash
watch -n 5 'curl -s http://localhost:8000/health | python3 -m json.tool'
```

---

## Security Considerations

### Current Implementation
- ✅ CORS enabled for specified origins
- ✅ Request timeout protection
- ✅ Error message sanitization
- ⚠️ Authentication: Not yet implemented
- ⚠️ Rate limiting: Not yet implemented

### Before Production
1. Implement JWT authentication
2. Add rate limiting per user/IP
3. Enable HTTPS/TLS
4. Add API key management
5. Implement request logging
6. Add input validation
7. Enable security headers

---

## Future Enhancements

- [ ] JWT authentication & authorization
- [ ] Rate limiting per user
- [ ] Response caching (Redis)
- [ ] Request/response logging
- [ ] API versioning
- [ ] WebSocket support for real-time updates
- [ ] GraphQL endpoint
- [ ] API usage analytics
- [ ] Request replay protection
- [ ] Circuit breaker pattern

---

## Troubleshooting

### Gateway Won't Start
1. Check if port 8000 is available: `lsof -i :8000`
2. Verify Python path: `export PYTHONPATH=.`
3. Check logs: `tail logs/service.log`

### Backend Service Unavailable
1. Check service health: `curl http://localhost:800X/health`
2. Verify service URLs in `.env`
3. Check network connectivity

### Slow Response Times
1. Check backend service response times
2. Review timeout settings
3. Monitor service logs for errors

---

## License

Part of the Crypto Trading Bot project.

## Support

For issues or questions:
1. Check logs: `logs/service.log`
2. Verify all backend services are running
3. Review API documentation: http://localhost:8000/docs
4. Check service health: http://localhost:8000/health
