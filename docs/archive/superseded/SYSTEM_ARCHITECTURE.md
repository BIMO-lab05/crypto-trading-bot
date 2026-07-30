# System Architecture - Crypto Trading Bot

**Enterprise-Grade Microservices Architecture**
**Version:** 2.0.0
**Last Updated:** 2025-11-14

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CRYPTO TRADING BOT SYSTEM                        │
│                   10 Microservices + Infrastructure                 │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                          USER INTERFACES                             │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────┐         ┌────────────────────┐             │
│  │   Dashboard UI     │         │   CLI Scripts      │             │
│  │  (Port 8080)       │         │   (35+ utilities)  │             │
│  │                    │         │                    │             │
│  │  - Real-time data  │         │  - Daily ops       │             │
│  │  - Service status  │         │  - Maintenance     │             │
│  │  - Trading view    │         │  - Emergency       │             │
│  └────────┬───────────┘         └─────────┬──────────┘             │
│           │                               │                         │
│           └───────────────┬───────────────┘                         │
│                           ↓                                         │
└───────────────────────────────────────────────────────────────────┬─┘
                            │                                         │
┌───────────────────────────┴────────────────────────────────────────▼─┐
│                       API LAYER                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │               API Gateway (Port 8000)                       │    │
│  │  • Request routing                                          │    │
│  │  • Load balancing                                           │    │
│  │  • Rate limiting                                            │    │
│  │  • Authentication                                           │    │
│  └────────────────────────┬───────────────────────────────────┘    │
│                           │                                         │
└───────────────────────────┴─────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ↓                   ↓                   ↓
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   External    │   │    Trading    │   │  Monitoring   │
│   Services    │   │   Services    │   │   Services    │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## Microservices Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CORE TRADING SERVICES                            │
└─────────────────────────────────────────────────────────────────────┘

        ┌────────────────────────────────────────────┐
        │    Bybit Connector (Port 8001)             │
        │  ┌──────────────────────────────────┐      │
        │  │  • REST API client               │      │
        │  │  • WebSocket connections         │      │
        │  │  • Order execution               │      │
        │  │  • Account management            │      │
        │  └──────────────────────────────────┘      │
        └────────────┬───────────────────────────────┘
                     │
        ┌────────────┴───────────────────────────────┐
        │                                            │
        ↓                                            ↓
┌────────────────┐                          ┌────────────────┐
│  Market Data   │                          │ Trading Engine │
│  (Port 8002)   │                          │  (Port 8005)   │
│                │                          │                │
│ • Price feeds  │◄─────────────────────────┤ • Strategy     │
│ • Orderbook    │                          │ • Signals      │
│ • Trades       │                          │ • Risk mgmt    │
│ • Klines       │                          │ • Execution    │
└────────┬───────┘                          └───────┬────────┘
         │                                          │
         │                                          │
         ↓                                          ↓
┌─────────────────┐                        ┌──────────────────┐
│Technical Analysis│                        │Portfolio Manager │
│  (Port 8004)    │                        │   (Port 8003)    │
│                 │                        │                  │
│ • RSI           │                        │ • Balance        │
│ • MACD          │                        │ • Positions      │
│ • Bollinger     │                        │ • P&L tracking   │
│ • EMA/SMA       │                        │ • Performance    │
└─────────────────┘                        └──────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    AI/ML SERVICES                                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐              ┌──────────────────────┐
│  ML Prediction      │              │ Sentiment Analysis   │
│   (Port 8007)       │              │    (Port 8008)       │
│                     │              │                      │
│ • LSTM models       │              │ • News analysis      │
│ • Price prediction  │              │ • Social media       │
│ • Pattern recog.    │              │ • Market sentiment   │
│ • Model training    │              │ • Fear & Greed Index │
└─────────────────────┘              └──────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                 MONITORING & SUPPORT SERVICES                       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐              ┌──────────────────────┐
│ Notification Svc    │              │  Risk Metrics        │
│   (Port 8006)       │              │   (Port 8009)        │
│                     │              │                      │
│ • Telegram alerts   │              │ • Sharpe ratio       │
│ • Email notifs      │              │ • Max drawdown       │
│ • Trade alerts      │              │ • VaR                │
│ • System alerts     │              │ • Volatility         │
└─────────────────────┘              └──────────────────────┘
```

---

## Infrastructure Layer

```
┌─────────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE SERVICES                          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐    ┌─────────────────────┐    ┌──────────────┐
│   TimescaleDB       │    │      Redis          │    │  RabbitMQ    │
│  (PostgreSQL)       │    │                     │    │              │
│                     │    │                     │    │              │
│ • Time-series data  │    │ • Caching           │    │ • Async msgs │
│ • Market history    │    │ • Session store     │    │ • Events     │
│ • Trading records   │    │ • Rate limiting     │    │ • Job queue  │
│ • Analytics         │    │ • Pub/Sub           │    │ • Tasks      │
└─────────────────────┘    └─────────────────────┘    └──────────────┘
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     TRADING DECISION FLOW                           │
└─────────────────────────────────────────────────────────────────────┘

1. DATA COLLECTION
   ┌──────────────┐
   │  Bybit API   │
   │  (External)  │
   └──────┬───────┘
          │
          ↓
   ┌──────────────────┐
   │ Market Data Svc  │ ─────► Store in TimescaleDB
   └──────┬───────────┘
          │
          ↓

2. ANALYSIS
   ┌────────────────────────────────────┐
   │   Technical Analysis Service       │
   │   • Calculates indicators          │
   │   • Identifies patterns            │
   │   • Generates signals              │
   └────────┬───────────────────────────┘
            │
            ├─────► ML Prediction Service
            │       • LSTM price forecast
            │       • Pattern recognition
            │
            └─────► Sentiment Analysis
                    • News sentiment
                    • Social signals

3. SIGNAL GENERATION
   ┌─────────────────┐
   │ Trading Engine  │
   │                 │
   │ Combines:       │
   │ • TA signals    │◄────┐
   │ • ML predictions│     │
   │ • Sentiment     │     │ All signals aggregated
   │ • Risk limits   │     │
   └────────┬────────┘     │
            │              │
            ↓              │
   ┌──────────────────┐   │
   │  Risk Metrics    ├───┘
   │  Validation      │
   └────────┬─────────┘
            │
            ↓

4. DECISION
   ┌─────────────────────┐
   │  Risk Manager       │
   │  • Position size    │
   │  • Stop-loss calc   │
   │  • Circuit breaker  │
   └─────────┬───────────┘
             │
             ↓

5. EXECUTION
   ┌─────────────────────┐
   │  Trade if:          │
   │  • Signal strong    │
   │  • Risk acceptable  │
   │  • Limits OK        │
   └─────────┬───────────┘
             │
             ↓
   ┌─────────────────────┐
   │  Bybit Connector    │
   │  • Execute order    │
   │  • Confirm fill     │
   └─────────┬───────────┘
             │
             ↓

6. TRACKING
   ┌─────────────────────┐
   │ Portfolio Manager   │
   │ • Update balance    │
   │ • Track position    │
   │ • Calculate P&L     │
   └─────────┬───────────┘
             │
             ↓
   ┌─────────────────────┐
   │ Notification Svc    │
   │ • Alert user        │
   │ • Log trade         │
   └─────────────────────┘
```

---

## Risk Management Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                   RISK MANAGEMENT LAYERS                            │
└─────────────────────────────────────────────────────────────────────┘

                    ┌──────────────┐
                    │ Trade Signal │
                    └──────┬───────┘
                           │
                           ↓
        ┌──────────────────────────────────────┐
        │     Layer 1: Pre-Trade Validation     │
        │  ┌────────────────────────────────┐   │
        │  │ • Max risk per trade (2%)      │   │
        │  │ • Position size calculation    │   │
        │  │ • Account balance check        │   │
        │  └────────────┬───────────────────┘   │
        └───────────────┼───────────────────────┘
                        │ PASS
                        ↓
        ┌──────────────────────────────────────┐
        │    Layer 2: Portfolio Limits          │
        │  ┌────────────────────────────────┐   │
        │  │ • Max positions (5 concurrent) │   │
        │  │ • Diversification check        │   │
        │  │ • Correlation analysis         │   │
        │  └────────────┬───────────────────┘   │
        └───────────────┼───────────────────────┘
                        │ PASS
                        ↓
        ┌──────────────────────────────────────┐
        │    Layer 3: Daily Loss Limit          │
        │  ┌────────────────────────────────┐   │
        │  │ • Daily P&L tracking           │   │
        │  │ • Stop if loss > 5%            │   │
        │  │ • Reset at midnight            │   │
        │  └────────────┬───────────────────┘   │
        └───────────────┼───────────────────────┘
                        │ PASS
                        ↓
        ┌──────────────────────────────────────┐
        │   Layer 4: Circuit Breaker            │
        │  ┌────────────────────────────────┐   │
        │  │ • Max drawdown (10%)           │   │
        │  │ • Emergency halt               │   │
        │  │ • Manual override required     │   │
        │  └────────────┬───────────────────┘   │
        └───────────────┼───────────────────────┘
                        │ PASS
                        ↓
                ┌────────────────┐
                │ Execute Trade  │
                └────────────────┘
```

---

## Operational Automation

```
┌─────────────────────────────────────────────────────────────────────┐
│                 OPERATIONAL AUTOMATION LAYER                        │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     CRON SCHEDULER                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Daily Operations (Mon-Fri):                                    │
│  ├─ 09:00 → Daily Startup                                       │
│  ├─ 09:00-18:00 → Health Checks (every 30 min)                  │
│  ├─ 18:00 → Daily Shutdown                                      │
│  ├─ 20:00 → Daily Performance Report                            │
│  └─ 23:00 → Automated Backup                                    │
│                                                                  │
│  Weekly Operations (Sunday):                                    │
│  ├─ 03:00 → Log Cleanup                                         │
│  ├─ 04:00 → Database Maintenance                                │
│  └─ 20:00 → Weekly Performance Report                           │
│                                                                  │
│  Monthly Operations (1st of month):                             │
│  ├─ 05:00 → Full Database Optimization                          │
│  └─ 21:00 → Monthly Performance Report                          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    SYSTEMD SERVICES                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  crypto-bot-monitor.service:                                    │
│  ├─ Continuous monitoring (60s interval)                        │
│  ├─ Service health checks                                       │
│  ├─ Trading status monitoring                                   │
│  ├─ Portfolio tracking                                          │
│  ├─ Alert generation                                            │
│  └─ Auto-restart on failure                                     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    BACKUP SYSTEM                                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Automated Backups:                                             │
│  ├─ TimescaleDB (daily)                                         │
│  ├─ Redis snapshots (daily)                                     │
│  ├─ Configuration files (daily)                                 │
│  ├─ ML models (weekly)                                          │
│  └─ Logs (daily)                                                │
│                                                                  │
│  Retention Policy:                                              │
│  ├─ Daily backups: 30 days                                      │
│  ├─ Weekly backups: 90 days                                     │
│  └─ Monthly backups: 1 year                                     │
│                                                                  │
│  Disaster Recovery:                                             │
│  ├─ Full system recovery (automated)                            │
│  ├─ Selective restore (database, config, models)                │
│  ├─ Pre-restore backup (safety)                                 │
│  └─ Post-recovery validation                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Service Communication

```
┌─────────────────────────────────────────────────────────────────────┐
│                  SERVICE COMMUNICATION PATTERNS                     │
└─────────────────────────────────────────────────────────────────────┘

1. SYNCHRONOUS (REST API)
   ┌─────────────┐                  ┌─────────────┐
   │   Client    │ ──── HTTP ──────►│   Service   │
   │             │◄──── JSON ───────│             │
   └─────────────┘                  └─────────────┘

   Used for:
   • User commands
   • Service health checks
   • Data queries
   • Trade execution

2. ASYNCHRONOUS (Message Queue)
   ┌─────────────┐                  ┌─────────────┐
   │  Publisher  │ ─── Publish ────►│  RabbitMQ   │
   └─────────────┘                  └──────┬──────┘
                                          │
                                    Subscribe
                                          │
                                          ↓
                                   ┌─────────────┐
                                   │ Subscriber  │
                                   └─────────────┘

   Used for:
   • Market data updates
   • Trade notifications
   • System events
   • Background tasks

3. CACHING (Redis)
   ┌─────────────┐                  ┌─────────────┐
   │   Service   │ ──── Get/Set ───►│    Redis    │
   │             │◄──── Fast ───────│   (Cache)   │
   └─────────────┘                  └─────────────┘

   Used for:
   • Session data
   • Rate limiting
   • Recent market data
   • Temporary state

4. DATA PERSISTENCE (TimescaleDB)
   ┌─────────────┐                  ┌─────────────┐
   │   Service   │ ──── SQL ───────►│ TimescaleDB │
   │             │◄──── Rows ───────│  (Postgres) │
   └─────────────┘                  └─────────────┘

   Used for:
   • Market history
   • Trade records
   • User data
   • Analytics
```

---

## Scalability & High Availability

```
┌─────────────────────────────────────────────────────────────────────┐
│                  SCALABILITY ARCHITECTURE                           │
└─────────────────────────────────────────────────────────────────────┘

HORIZONTAL SCALING
┌────────────────────────────────────────────────────────┐
│                  Load Balancer                         │
└────────┬──────────────┬──────────────┬────────────────┘
         │              │              │
         ↓              ↓              ↓
  ┌───────────┐  ┌───────────┐  ┌───────────┐
  │ Service 1 │  │ Service 2 │  │ Service 3 │  (Multiple instances)
  └───────────┘  └───────────┘  └───────────┘

VERTICAL SCALING
┌────────────────────────────────────────────────────────┐
│  Service Resources:                                    │
│  ├─ CPU: 2-4 cores per service                         │
│  ├─ RAM: 512MB - 2GB per service                       │
│  ├─ Disk: SSD for database (fast I/O)                  │
│  └─ Network: Low latency connection                    │
└────────────────────────────────────────────────────────┘

HIGH AVAILABILITY
┌────────────────────────────────────────────────────────┐
│  • Database replication (primary + replicas)           │
│  • Redis sentinel (failover)                           │
│  • Service health monitoring                           │
│  • Auto-restart on failure                             │
│  • Circuit breakers                                    │
│  • Graceful degradation                                │
└────────────────────────────────────────────────────────┘
```

---

## Security Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                                  │
└─────────────────────────────────────────────────────────────────────┘

1. NETWORK SECURITY
   ┌─────────────────────────────────────┐
   │ • Firewall rules                    │
   │ • Port restrictions                 │
   │ • TLS/SSL for external APIs         │
   │ • Internal network isolation        │
   └─────────────────────────────────────┘

2. API SECURITY
   ┌─────────────────────────────────────┐
   │ • API key authentication            │
   │ • Rate limiting                     │
   │ • Request validation                │
   │ • CORS policies                     │
   └─────────────────────────────────────┘

3. DATA SECURITY
   ┌─────────────────────────────────────┐
   │ • Encrypted API keys (env vars)     │
   │ • Database encryption at rest       │
   │ • Secure credential storage         │
   │ • No hardcoded secrets              │
   └─────────────────────────────────────┘

4. OPERATIONAL SECURITY
   ┌─────────────────────────────────────┐
   │ • Risk management enforcement       │
   │ • Circuit breakers                  │
   │ • Emergency stop procedures         │
   │ • Audit logging                     │
   └─────────────────────────────────────┘
```

---

## Monitoring & Observability

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MONITORING STACK                                 │
└─────────────────────────────────────────────────────────────────────┘

APPLICATION MONITORING
┌────────────────────────────────────────────────────────┐
│  • Service health checks (10 services)                 │
│  • Response time tracking                              │
│  • Error rate monitoring                               │
│  • Resource usage (CPU, RAM, Disk)                     │
└────────────────────────────────────────────────────────┘

BUSINESS METRICS
┌────────────────────────────────────────────────────────┐
│  • Trading performance (P&L, win rate)                 │
│  • Portfolio metrics (balance, positions)              │
│  • Risk metrics (Sharpe, drawdown, VaR)                │
│  • Trade execution metrics                             │
└────────────────────────────────────────────────────────┘

ALERTING
┌────────────────────────────────────────────────────────┐
│  • Service failures → Telegram/Email                   │
│  • Trading losses → Immediate alerts                   │
│  • Risk limit breaches → Emergency notifications       │
│  • System issues → Admin alerts                        │
└────────────────────────────────────────────────────────┘

LOGGING
┌────────────────────────────────────────────────────────┐
│  • Application logs (/tmp/*.log)                       │
│  • Docker logs (docker-compose logs)                   │
│  • Monitoring logs (monitor_YYYYMMDD.log)              │
│  • Audit trail (all trades logged)                     │
└────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Backend Services
```
┌────────────────────────────────────────────────────────┐
│  Language:        Python 3.8+                          │
│  Framework:       FastAPI                              │
│  Async:           asyncio, aiohttp                     │
│  Data:            pandas, numpy                        │
│  ML:              TensorFlow/Keras (LSTM)              │
│  Testing:         pytest                               │
└────────────────────────────────────────────────────────┘
```

### Frontend
```
┌────────────────────────────────────────────────────────┐
│  UI:              Vanilla JavaScript                   │
│  Styling:         CSS3                                 │
│  Real-time:       WebSocket / Polling                  │
│  Charts:          Chart.js / Custom                    │
└────────────────────────────────────────────────────────┘
```

### Infrastructure
```
┌────────────────────────────────────────────────────────┐
│  Database:        TimescaleDB (PostgreSQL)             │
│  Cache:           Redis 6+                             │
│  Message Queue:   RabbitMQ                             │
│  Containerization: Docker + Docker Compose             │
│  Orchestration:   Docker Compose (single host)         │
│                   Kubernetes ready (multi-host)        │
└────────────────────────────────────────────────────────┘
```

### Operational Tools
```
┌────────────────────────────────────────────────────────┐
│  Scripting:       Bash (35+ scripts)                   │
│  Scheduling:      Cron + Systemd                       │
│  Backup:          pg_dump, tar, gzip                   │
│  Monitoring:      Custom Python scripts                │
└────────────────────────────────────────────────────────┘
```

---

## Deployment Topologies

### Single Server Deployment (Current)
```
┌────────────────────────────────────────────────────────┐
│                   Single Host                          │
│                                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │           Docker Compose                     │    │
│  │  ┌────────────────────────────────────┐      │    │
│  │  │  All Services + Infrastructure     │      │    │
│  │  │  • 10 Microservices                │      │    │
│  │  │  • TimescaleDB                     │      │    │
│  │  │  • Redis                           │      │    │
│  │  │  • RabbitMQ                        │      │    │
│  │  └────────────────────────────────────┘      │    │
│  └──────────────────────────────────────────────┘    │
│                                                        │
│  Advantages:                                           │
│  ✓ Simple setup                                        │
│  ✓ Low cost                                            │
│  ✓ Easy to manage                                      │
│                                                        │
│  Suitable for:                                         │
│  • Development                                         │
│  • Testing                                             │
│  • Small-scale production                              │
└────────────────────────────────────────────────────────┘
```

### Multi-Server Deployment (Production)
```
┌────────────────────────────────────────────────────────┐
│              Kubernetes Cluster                        │
│                                                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐      │
│  │   Node 1   │  │   Node 2   │  │   Node 3   │      │
│  │  Services  │  │  Services  │  │   Infra    │      │
│  └────────────┘  └────────────┘  └────────────┘      │
│                                                        │
│  Features:                                             │
│  ✓ High availability                                   │
│  ✓ Auto-scaling                                        │
│  ✓ Load balancing                                      │
│  ✓ Zero-downtime updates                               │
│                                                        │
│  Suitable for:                                         │
│  • Large-scale production                              │
│  • High-frequency trading                              │
│  • Mission-critical operations                         │
└────────────────────────────────────────────────────────┘
```

---

## Performance Characteristics

### Throughput
```
┌────────────────────────────────────────────────────────┐
│  Market Data:     1000+ messages/second                │
│  API Requests:    100+ requests/second                 │
│  Trade Execution: <100ms latency                       │
│  Database Writes: 500+ inserts/second                  │
└────────────────────────────────────────────────────────┘
```

### Latency
```
┌────────────────────────────────────────────────────────┐
│  API Response:    <50ms (p99)                          │
│  Order Execution: <100ms (exchange dependent)          │
│  Dashboard Update: <500ms                              │
│  Health Check:    <10ms                                │
└────────────────────────────────────────────────────────┘
```

### Resource Usage (per service)
```
┌────────────────────────────────────────────────────────┐
│  CPU:             0.1-0.5 cores (idle-active)          │
│  RAM:             256MB-1GB (depending on service)     │
│  Disk I/O:        Low (except database)                │
│  Network:         Low-Medium                           │
└────────────────────────────────────────────────────────┘
```

---

## Future Architecture Enhancements

### Planned Improvements
```
1. Multi-Exchange Support
   ├─ Binance connector
   ├─ Coinbase connector
   └─ Unified order router

2. Advanced ML Models
   ├─ Transformer models
   ├─ Reinforcement learning
   └─ Ensemble methods

3. Real-time Analytics
   ├─ Apache Kafka integration
   ├─ Stream processing
   └─ Real-time dashboards

4. Geographic Distribution
   ├─ Multi-region deployment
   ├─ Edge computing
   └─ Low-latency execution

5. Advanced Risk Management
   ├─ Portfolio optimization
   ├─ Multi-asset strategies
   └─ Dynamic hedging
```

---

**Version:** 2.0.0
**Last Updated:** 2025-11-14
**Status:** Production-Ready (Paper Trading)

---

For implementation details, see:
- `GETTING_STARTED.md` - Setup guide
- `SCRIPTS_INDEX.md` - Operational scripts
- `TRADING_ENGINE_CAPABILITIES.md` - API documentation
- `DEPLOYMENT_RUNBOOK.md` - Production deployment
