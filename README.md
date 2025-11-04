# 🤖 Crypto Trading Bot

An autonomous cryptocurrency trading system built with microservices architecture, featuring technical analysis, risk management, and real-time trading on Bybit exchange.

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code Coverage](https://img.shields.io/badge/Coverage-80%25-brightgreen.svg)](tests/)
[![Progress](https://img.shields.io/badge/Progress-75%25-blue.svg)](progress.md)

## 🎯 Features

- **Microservices Architecture**: 6 independent services for scalability
- **Technical Analysis**: RSI, MACD, Bollinger Bands, Moving Averages
- **Risk Management**: 2% max per trade, 5% daily loss limit, emergency stop
- **Real-time Data**: WebSocket streaming from Bybit
- **Paper Trading**: Safe testing mode with simulated capital
- **Time-Series Optimization**: TimescaleDB for efficient market data storage
- **Message-Driven**: RabbitMQ for reliable inter-service communication
- **Comprehensive Testing**: TDD approach with >80% coverage goal
- **Auto-Documentation**: OpenAPI/Swagger for all API endpoints

## 🏗️ Architecture

```
┌─────────────┐
│  Frontend   │  React Dashboard
└──────┬──────┘
       │
┌──────▼──────┐
│ API Gateway │  Authentication, Routing, Rate Limiting
└──────┬──────┘
       │
   ┌───┴───┬────────────┬──────────────┐
   │       │            │              │
┌──▼───┐ ┌─▼─────┐ ┌───▼────┐  ┌──────▼────┐
│Trade │ │Portfolio│Technical│  │   Market  │
│Engine│ │ Manager │Analysis │  │    Data   │
└──┬───┘ └────────┘ └───┬────┘  └─────┬─────┘
   │                     │             │
   └──────────┬──────────┴─────────────┘
              │
      ┌───────▼────────┐
      │ Bybit Connector│
      └───────┬────────┘
              │
      ┌───────▼────────┐
      │ Bybit Exchange │
      └────────────────┘
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| API Gateway | 8000 | Entry point, authentication, routing |
| Trading Engine | 8001 | Strategy execution, risk management |
| Bybit Connector | 8002 | Exchange API interface |
| Market Data | 8003 | Data collection and storage |
| Technical Analysis | 8004 | Indicators and signal generation |
| Portfolio Manager | 8005 | Balance and position tracking |

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Git
- Bybit Testnet account (get free API keys at https://testnet.bybit.com/)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd crypto-trading-bot
   ```

2. **Start infrastructure**
   ```bash
   cd infrastructure
   docker-compose up -d
   ```

   Verify services are running:
   ```bash
   docker-compose ps
   # All services should show "Up"
   ```

3. **Configure Bybit Connector**
   ```bash
   cd ../services/bybit-connector
   cp .env.example .env
   nano .env  # Add your Bybit testnet API keys
   ```

4. **Start Bybit Connector**
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --port 8002 --reload
   ```

5. **Start Market Data Service** (in new terminal)
   ```bash
   cd services/market-data-service
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --port 8003 --reload
   ```

6. **Test the Pipeline**
   ```bash
   # In new terminal
   python3 scripts/test_pipeline.py
   ```

7. **Access API Documentation**
   - Bybit Connector: http://localhost:8002/docs
   - Market Data Service: http://localhost:8003/docs

📖 **Detailed testing guide**: See [TESTING_GUIDE.md](TESTING_GUIDE.md)

## 📋 Environment Configuration

Key environment variables (see `.env.example` for complete list):

```bash
# Bybit API (GET FROM TESTNET!)
BYBIT_API_KEY=your_testnet_api_key
BYBIT_API_SECRET=your_testnet_api_secret
BYBIT_TESTNET=true

# Trading Mode
TRADING_MODE=PAPER  # Start with paper trading

# Risk Management
MAX_RISK_PER_TRADE=0.02  # 2% max
MAX_DAILY_LOSS=0.05      # 5% daily limit

# Trading Pairs
TRADING_PAIRS=BTCUSDT,ETHUSDT
```

## 🔐 Getting Bybit API Keys

### Testnet (Recommended for Development)

1. Go to https://testnet.bybit.com/
2. Sign up for testnet account
3. Navigate to API Management
4. Create API key with permissions:
   - ✅ Read
   - ✅ Trade
   - ✅ Wallet
5. Copy API Key and Secret to `.env`

**⚠️ IMPORTANT**: Never use production API keys during development!

## 🧪 Testing

### Run All Tests
```bash
pytest tests/ -v --cov=services --cov-report=html
```

### Test Coverage
```bash
# View coverage report
open htmlcov/index.html
```

### Test Specific Service
```bash
cd services/bybit-connector
pytest tests/ -v
```

## 📊 Management Interfaces

- **RabbitMQ Management**: http://localhost:15672
  - User: `cryptobot` (from .env)
  - Password: from `RABBITMQ_PASSWORD`

- **API Documentation** (when services running):
  - API Gateway: http://localhost:8000/docs
  - Bybit Connector: http://localhost:8002/docs
  - Market Data: http://localhost:8003/docs
  - Technical Analysis: http://localhost:8004/docs
  - Trading Engine: http://localhost:8001/docs
  - Portfolio Manager: http://localhost:8005/docs

## 📁 Project Structure

```
crypto-trading-bot/
├── services/               # Microservices
│   ├── api-gateway/
│   ├── bybit-connector/
│   ├── market-data-service/
│   ├── portfolio-manager/
│   ├── technical-analysis/
│   └── trading-engine/
├── frontend/              # React dashboard
├── infrastructure/        # Docker, K8s configs
│   ├── docker-compose.yml
│   └── scripts/
├── shared/                # Shared utilities
│   ├── contracts/
│   └── utils/
├── tests/                 # Integration tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docs/                  # Documentation
│   ├── architecture/
│   ├── api/
│   └── development/
├── .env.example           # Environment template
├── .gitignore
├── progress.md            # Development tracking
└── README.md
```

## 📚 Documentation

### 🚀 Getting Started (Start Here!)
- **[START_HERE.md](START_HERE.md)** - 15-minute guide to get you testing!
- **[QUICKSTART.md](QUICKSTART.md)** - Rapid setup instructions
- **[CHEATSHEET.md](CHEATSHEET.md)** - Command reference for daily use

### 🧪 Testing & Verification
- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** - Comprehensive testing manual
- **[TEST_RESULTS.md](TEST_RESULTS.md)** - Current status and verification

### 📊 Development Tracking
- **[progress.md](progress.md)** - Detailed development progress
- **[SESSION_SUMMARY.md](SESSION_SUMMARY.md)** - Latest session accomplishments

### 🏗️ Architecture & Design
- [System Architecture](docs/architecture/SYSTEM_OVERVIEW.md)
- [Service Contracts](docs/architecture/SERVICE_CONTRACTS.md)
- [Setup Guide](docs/development/SETUP.md)
- [Testing Strategy](docs/development/TESTING.md)

## 🛠️ Development Workflow

1. **Follow TDD**: Write tests before implementation
2. **Run tests**: `pytest tests/ -v`
3. **Format code**: `black . && isort .`
4. **Type checking**: `mypy .`
5. **Commit**: `git commit -m "feat(service): description"`
6. **Update progress**: Update `progress.md` after each session

## ⚠️ Risk Management Rules

- **Never risk >2% per trade**
- **Stop trading if daily loss >5%**
- **Start with paper trading mode**
- **Test on testnet for minimum 2 weeks**
- **Manual approval required for trades >$10k**
- **Emergency stop button always accessible**

## 🔒 Security Best Practices

- ✅ API keys in environment variables only
- ✅ Never commit `.env` file
- ✅ Use testnet for development
- ✅ Enable 2FA on Bybit account
- ✅ Whitelist IP addresses (production)
- ✅ Regular security audits
- ✅ All trades logged for compliance

## 📈 Performance Targets

- Order execution: < 100ms latency
- API response time: < 50ms (p99)
- Data processing: > 1000 msgs/sec
- System uptime: 99.9%
- Test coverage: > 80%

## 🎯 Roadmap

### Phase 1: MVP (Weeks 1-4) - 🟡 In Progress (75% Complete)
- [x] Project infrastructure
- [x] Documentation structure
- [x] Bybit Connector (95% - Testing Ready)
- [x] Market Data Service (95% - Testing Ready)
- [ ] Technical Analysis
- [ ] Trading Engine
- [ ] Paper Trading Mode

### Phase 2: Enhanced (Weeks 5-8)
- [ ] Frontend Dashboard
- [ ] Multiple Strategies
- [ ] Advanced Indicators
- [ ] Alert System
- [ ] Performance Analytics

### Phase 3: AI Features (Weeks 9-12)
- [ ] ML Price Prediction
- [ ] Sentiment Analysis
- [ ] Auto-optimization
- [ ] Backtesting Framework

## 🐛 Troubleshooting

### Docker services won't start
```bash
docker-compose down
docker-compose up -d --build
docker-compose logs -f
```

### Port already in use
```bash
lsof -i :8000  # Find process
kill -9 <PID>  # Kill process
```

### Database connection failed
```bash
docker exec -it crypto-bot-postgres pg_isready
# Check credentials in .env
```

### Python package installation issues
```bash
pip install --upgrade pip
pip cache purge
pip install -r requirements.txt --force-reinstall
```

## 🤝 Contributing

1. Follow TDD principles
2. Maintain >80% test coverage
3. Update documentation
4. Follow commit conventions
5. Update `progress.md`

## 📝 License

MIT License - See [LICENSE](LICENSE) file

## ⚡ Current Status

**Development Phase**: Infrastructure Complete, Services Ready for Testing
**Progress**: 75% Complete (2/6 services implemented, testing infrastructure ready)
**Infrastructure**: ✅ All systems healthy (PostgreSQL, TimescaleDB, Redis, RabbitMQ)
**Next Milestone**: Pipeline Testing with Bybit Testnet API → Technical Analysis Service

📊 **Quick Links**:
- 🚀 **[START_HERE.md](START_HERE.md)** - Begin testing in 15 minutes!
- 📖 **[SESSION_SUMMARY.md](SESSION_SUMMARY.md)** - Latest accomplishments
- 📊 **[progress.md](progress.md)** - Detailed development tracking
- 🧪 **[TEST_RESULTS.md](TEST_RESULTS.md)** - Infrastructure verification

## 📞 Support

- Documentation: [docs/](docs/)
- Issues: GitHub Issues
- Progress Tracking: [progress.md](progress.md)

---

**⚠️ DISCLAIMER**: This software is for educational purposes. Cryptocurrency trading carries risk. Never invest more than you can afford to lose. Always test thoroughly on testnet before using real funds. The authors are not responsible for any financial losses.

**🔴 IMPORTANT**: Start with `TRADING_MODE=PAPER` and `BYBIT_TESTNET=true`. Test for minimum 2 weeks before considering live trading.

---

**Last Updated**: 2025-10-30
**Version**: 0.1.0-alpha
**Status**: 🟡 Development
