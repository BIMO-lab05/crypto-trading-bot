# Service Contracts - API Specifications

## Overview

This document defines the API contracts between microservices in the Crypto Trading Bot system. All services follow RESTful conventions and return JSON responses.

## Common Patterns

### Response Format

All API responses follow this structure:

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "timestamp": "2025-10-30T12:00:00Z"
}
```

Error response:
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": { ... }
  },
  "timestamp": "2025-10-30T12:00:00Z"
}
```

### Health Check Endpoints

Every service implements:
- `GET /health` - Basic health check
- `GET /ready` - Readiness probe (checks dependencies)

---

## 1. API Gateway (Port 8000)

### Authentication
```
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET /api/v1/auth/me
```

### Proxy Routes
Routes requests to appropriate microservices based on path prefix.

---

## 2. Trading Engine (Port 8001)

### Strategies

#### List Strategies
```
GET /api/v1/strategies

Response:
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "name": "Simple Moving Average",
      "description": "SMA crossover strategy",
      "parameters": {
        "short_period": 10,
        "long_period": 50
      },
      "is_active": false,
      "created_at": "2025-10-30T12:00:00Z"
    }
  ]
}
```

#### Get Strategy
```
GET /api/v1/strategies/{strategy_id}
```

#### Create Strategy
```
POST /api/v1/strategies

Request:
{
  "name": "My Strategy",
  "description": "Custom strategy",
  "parameters": { ... }
}
```

#### Activate/Deactivate Strategy
```
PUT /api/v1/strategies/{strategy_id}/activate
PUT /api/v1/strategies/{strategy_id}/deactivate
```

### Trades

#### List Trades
```
GET /api/v1/trades?symbol=BTCUSDT&limit=100&offset=0

Response:
{
  "success": true,
  "data": {
    "trades": [
      {
        "id": "uuid",
        "strategy_id": "uuid",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 0.001,
        "price": 50000.0,
        "status": "FILLED",
        "order_id": "bybit-order-123",
        "executed_at": "2025-10-30T12:05:00Z",
        "created_at": "2025-10-30T12:00:00Z"
      }
    ],
    "total": 150,
    "limit": 100,
    "offset": 0
  }
}
```

#### Get Trade
```
GET /api/v1/trades/{trade_id}
```

### Risk Management

#### Get Risk Parameters
```
GET /api/v1/risk/parameters

Response:
{
  "success": true,
  "data": {
    "max_risk_per_trade": 0.02,
    "max_daily_loss": 0.05,
    "max_position_size": 0.1,
    "stop_loss_percentage": 0.03,
    "emergency_stop_active": false
  }
}
```

#### Update Risk Parameters
```
PUT /api/v1/risk/parameters

Request:
{
  "max_risk_per_trade": 0.015,
  "stop_loss_percentage": 0.02
}
```

#### Emergency Stop
```
POST /api/v1/risk/emergency-stop
POST /api/v1/risk/resume
```

---

## 3. Bybit Connector (Port 8002)

### Account

#### Get Balance
```
GET /api/v1/account/balance

Response:
{
  "success": true,
  "data": {
    "balances": [
      {
        "asset": "USDT",
        "free": 10000.0,
        "locked": 500.0,
        "total": 10500.0
      },
      {
        "asset": "BTC",
        "free": 0.5,
        "locked": 0.0,
        "total": 0.5
      }
    ],
    "updated_at": "2025-10-30T12:00:00Z"
  }
}
```

#### Get Positions
```
GET /api/v1/account/positions

Response:
{
  "success": true,
  "data": {
    "positions": [
      {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "entry_price": 48000.0,
        "mark_price": 50000.0,
        "unrealized_pnl": 200.0,
        "leverage": 1
      }
    ]
  }
}
```

### Orders

#### Place Order
```
POST /api/v1/orders

Request:
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "order_type": "LIMIT",
  "quantity": 0.001,
  "price": 50000.0,
  "time_in_force": "GTC"
}

Response:
{
  "success": true,
  "data": {
    "order_id": "bybit-123456",
    "symbol": "BTCUSDT",
    "status": "NEW",
    "created_at": "2025-10-30T12:00:00Z"
  }
}
```

#### Get Order Status
```
GET /api/v1/orders/{order_id}
```

#### Cancel Order
```
DELETE /api/v1/orders/{order_id}
```

#### Get Active Orders
```
GET /api/v1/orders/active?symbol=BTCUSDT
```

---

## 4. Market Data Service (Port 8003)

### Candles (OHLCV)

#### Get Historical Candles
```
GET /api/v1/candles/{symbol}?interval=1h&start=2025-10-29T00:00:00Z&end=2025-10-30T00:00:00Z&limit=100

Response:
{
  "success": true,
  "data": {
    "candles": [
      {
        "time": "2025-10-30T00:00:00Z",
        "open": 50000.0,
        "high": 50500.0,
        "low": 49800.0,
        "close": 50200.0,
        "volume": 125.5
      }
    ],
    "symbol": "BTCUSDT",
    "interval": "1h"
  }
}
```

### Real-time Data

#### Get Latest Price
```
GET /api/v1/price/{symbol}

Response:
{
  "success": true,
  "data": {
    "symbol": "BTCUSDT",
    "price": 50200.0,
    "timestamp": "2025-10-30T12:00:00Z"
  }
}
```

#### Get 24h Statistics
```
GET /api/v1/ticker/{symbol}

Response:
{
  "success": true,
  "data": {
    "symbol": "BTCUSDT",
    "last_price": 50200.0,
    "price_change": 1200.0,
    "price_change_percent": 2.45,
    "high_24h": 51000.0,
    "low_24h": 48500.0,
    "volume_24h": 15000.0
  }
}
```

---

## 5. Technical Analysis Service (Port 8004)

### Indicators

#### Calculate RSI
```
GET /api/v1/indicators/rsi/{symbol}?interval=1h&period=14

Response:
{
  "success": true,
  "data": {
    "symbol": "BTCUSDT",
    "indicator": "RSI",
    "period": 14,
    "value": 65.5,
    "timestamp": "2025-10-30T12:00:00Z"
  }
}
```

#### Calculate MACD
```
GET /api/v1/indicators/macd/{symbol}?interval=1h&fast=12&slow=26&signal=9

Response:
{
  "success": true,
  "data": {
    "symbol": "BTCUSDT",
    "indicator": "MACD",
    "macd": 125.5,
    "signal": 120.0,
    "histogram": 5.5,
    "timestamp": "2025-10-30T12:00:00Z"
  }
}
```

#### Calculate Bollinger Bands
```
GET /api/v1/indicators/bollinger/{symbol}?interval=1h&period=20&std=2

Response:
{
  "success": true,
  "data": {
    "symbol": "BTCUSDT",
    "indicator": "BOLLINGER_BANDS",
    "upper": 51000.0,
    "middle": 50000.0,
    "lower": 49000.0,
    "timestamp": "2025-10-30T12:00:00Z"
  }
}
```

### Signals

#### Get Trading Signals
```
GET /api/v1/signals/{symbol}?strategy=all

Response:
{
  "success": true,
  "data": {
    "symbol": "BTCUSDT",
    "signals": [
      {
        "type": "RSI_OVERSOLD",
        "action": "BUY",
        "confidence": 0.75,
        "details": {
          "rsi_value": 28.5,
          "threshold": 30
        }
      }
    ],
    "timestamp": "2025-10-30T12:00:00Z"
  }
}
```

---

## 6. Portfolio Manager (Port 8005)

### Portfolio

#### Get Portfolio Summary
```
GET /api/v1/portfolio/summary

Response:
{
  "success": true,
  "data": {
    "total_value_usdt": 10500.0,
    "available_balance": 10000.0,
    "locked_balance": 500.0,
    "unrealized_pnl": 200.0,
    "realized_pnl": 150.0,
    "total_pnl": 350.0,
    "positions_count": 2
  }
}
```

#### Get Positions
```
GET /api/v1/portfolio/positions?status=OPEN

Response:
{
  "success": true,
  "data": {
    "positions": [
      {
        "id": "uuid",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "entry_price": 48000.0,
        "current_price": 50000.0,
        "unrealized_pnl": 200.0,
        "opened_at": "2025-10-29T10:00:00Z"
      }
    ]
  }
}
```

#### Get Performance Metrics
```
GET /api/v1/portfolio/performance?period=30d

Response:
{
  "success": true,
  "data": {
    "total_trades": 45,
    "winning_trades": 28,
    "losing_trades": 17,
    "win_rate": 0.622,
    "average_profit": 50.0,
    "average_loss": -25.0,
    "profit_factor": 2.0,
    "sharpe_ratio": 1.5,
    "max_drawdown": 0.08
  }
}
```

---

## Message Queue Contracts

### Topic: `market.data.{symbol}`
```json
{
  "symbol": "BTCUSDT",
  "price": 50200.0,
  "volume": 1.5,
  "timestamp": "2025-10-30T12:00:00Z"
}
```

### Topic: `analysis.signal.{symbol}`
```json
{
  "symbol": "BTCUSDT",
  "signal_type": "RSI_OVERSOLD",
  "action": "BUY",
  "confidence": 0.75,
  "timestamp": "2025-10-30T12:00:00Z"
}
```

### Topic: `trade.execute`
```json
{
  "trade_id": "uuid",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "order_type": "LIMIT",
  "quantity": 0.001,
  "price": 50000.0
}
```

### Topic: `trade.result`
```json
{
  "trade_id": "uuid",
  "order_id": "bybit-123456",
  "status": "FILLED",
  "executed_price": 50000.0,
  "executed_quantity": 0.001,
  "timestamp": "2025-10-30T12:00:00Z"
}
```

---

**Last Updated**: 2025-10-30
**Version**: 1.0
