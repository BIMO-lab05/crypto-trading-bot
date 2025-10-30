# System Overview - Crypto Trading Bot

## Architecture

This document provides a high-level overview of the Crypto Trading Bot system architecture.

### Design Philosophy

The system follows a **microservices architecture** with the following principles:
- **Service Independence**: Each service can be developed, deployed, and scaled independently
- **Event-Driven Communication**: Services communicate via message queues (RabbitMQ)
- **Data Isolation**: Each service has its own data storage concerns
- **Fault Tolerance**: Circuit breakers and health checks prevent cascading failures
- **Security First**: API keys isolated, all communications logged for audit

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                        │
│                    Real-time Dashboard & Controls                │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/WebSocket
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway                               │
│              Routes requests, Authentication, Rate Limiting      │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Trading    │    │  Portfolio   │    │  Technical   │
│   Engine     │    │   Manager    │    │  Analysis    │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                    │
       │        RabbitMQ Message Bus            │
       └───────────────────┼────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│    Bybit     │    │ Market Data  │    │  PostgreSQL  │
│  Connector   │    │   Service    │    │  TimescaleDB │
└──────┬───────┘    └──────┬───────┘    └──────────────┘
       │                   │
       ▼                   ▼
┌─────────────────────────────────┐
│       Bybit Exchange API        │
│    (Testnet & Production)       │
└─────────────────────────────────┘
```

### Service Descriptions

#### 1. API Gateway
- **Purpose**: Single entry point for all client requests
- **Responsibilities**:
  - Route requests to appropriate microservices
  - Authentication and authorization
  - Rate limiting and throttling
  - Request/response transformation
- **Technology**: FastAPI, Redis (session storage)
- **Port**: 8000

#### 2. Trading Engine
- **Purpose**: Core trading logic and strategy execution
- **Responsibilities**:
  - Execute trading strategies
  - Risk management (max 2% per trade, 5% daily loss limit)
  - Order generation and validation
  - Emergency stop-loss handling
- **Technology**: Python 3.12, FastAPI
- **Port**: 8001

#### 3. Bybit Connector
- **Purpose**: Interface with Bybit exchange API
- **Responsibilities**:
  - Place, modify, cancel orders
  - Query account balances and positions
  - WebSocket real-time updates
  - Circuit breaker for API failures
- **Technology**: Python 3.12, pybit library, WebSockets
- **Port**: 8002

#### 4. Market Data Service
- **Purpose**: Collect and store market data
- **Responsibilities**:
  - Fetch historical OHLCV data
  - Real-time price streaming via WebSocket
  - Store data in TimescaleDB
  - Provide data query API
- **Technology**: Python 3.12, TimescaleDB, Redis
- **Port**: 8003

#### 5. Technical Analysis Service
- **Purpose**: Calculate technical indicators and generate signals
- **Responsibilities**:
  - RSI, MACD, Bollinger Bands, EMA, SMA calculations
  - Support/resistance level detection
  - Signal generation with confidence scores
  - Caching for performance
- **Technology**: Python 3.12, pandas, numpy, TA-Lib
- **Port**: 8004

#### 6. Portfolio Manager
- **Purpose**: Track balances, positions, and P&L
- **Responsibilities**:
  - Real-time balance tracking
  - Position management (entry/exit tracking)
  - Profit & Loss calculation
  - Portfolio performance metrics
- **Technology**: Python 3.12, PostgreSQL
- **Port**: 8005

### Data Flow

#### Trading Flow
1. **Market Data** → Market Data Service collects real-time prices
2. **Analysis** → Technical Analysis Service calculates indicators
3. **Signal Generation** → Technical Analysis publishes signals to message queue
4. **Strategy Execution** → Trading Engine receives signals, evaluates risk
5. **Order Placement** → Trading Engine sends order to Bybit Connector
6. **Execution** → Bybit Connector places order on exchange
7. **Confirmation** → Order status updates flow back through the system
8. **Portfolio Update** → Portfolio Manager updates balances and positions

### Message Queue Topics

```
market.data.{symbol}        - Real-time price updates
analysis.signal.{symbol}    - Technical analysis signals
trade.execute               - Order execution commands
trade.result                - Execution results
portfolio.update            - Balance/position changes
alert.critical              - System alerts
```

### Data Storage

#### PostgreSQL
- Trading strategies configuration
- Trade history and audit logs
- System events and logs
- User management

#### TimescaleDB
- OHLCV candle data (time-series optimized)
- Tick data (real-time trades)
- Order book snapshots
- Technical indicator cache

#### Redis
- Real-time price cache
- Session management
- Rate limiting counters
- Temporary calculation cache

### Deployment

#### Development
- Docker Compose for local development
- All services run on localhost with different ports
- Test databases with sample data

#### Production (Future)
- Kubernetes cluster
- Auto-scaling based on load
- High availability with replicas
- Monitoring with Prometheus/Grafana

### Security Considerations

1. **API Key Management**: Stored in environment variables, never in code
2. **Network Isolation**: Services communicate only via defined interfaces
3. **Audit Logging**: All trades and API calls logged for compliance
4. **Rate Limiting**: Prevent abuse and API quota exhaustion
5. **Data Encryption**: Sensitive data encrypted at rest

### Performance Requirements

- **Order Execution Latency**: < 100ms
- **Data Processing Throughput**: > 1000 messages/sec
- **API Response Time**: < 50ms (p99)
- **System Uptime**: 99.9%

### Scalability Strategy

1. **Horizontal Scaling**: Add more service instances
2. **Database Sharding**: Partition data by symbol/timeframe
3. **Caching**: Redis for frequently accessed data
4. **Message Queue**: RabbitMQ handles async communication
5. **Load Balancing**: Distribute requests across instances

---

**Last Updated**: 2025-10-30
**Version**: 1.0
**Status**: Initial Design
