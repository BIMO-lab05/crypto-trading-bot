# Development Environment Setup

## Prerequisites

### Required Software
- **Python 3.12** or higher
- **Docker** and **Docker Compose**
- **Git**
- **Node.js 18+** (for frontend development)
- **PostgreSQL client** (optional, for database access)

### System Requirements
- **OS**: Linux, macOS, or Windows (with WSL2)
- **RAM**: Minimum 8GB, recommended 16GB
- **Disk Space**: 20GB free space
- **Network**: Stable internet connection for API calls

---

## Quick Start

### 1. Clone the Repository

```bash
# Navigate to your workspace
cd /path/to/workspace

# Repository should already exist
cd crypto-trading-bot

# Verify structure
ls -la
```

### 2. Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file with your settings
nano .env  # or use your preferred editor
```

Required environment variables:
```bash
# Bybit API Configuration
BYBIT_API_KEY=your_testnet_api_key
BYBIT_API_SECRET=your_testnet_api_secret
BYBIT_TESTNET=true

# Database Configuration
POSTGRES_USER=cryptobot
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=cryptobot

# TimescaleDB Configuration
TIMESCALE_USER=cryptobot
TIMESCALE_PASSWORD=your_secure_password
TIMESCALE_DB=market_data

# Redis Configuration
REDIS_PASSWORD=your_secure_password

# RabbitMQ Configuration
RABBITMQ_USER=cryptobot
RABBITMQ_PASSWORD=your_secure_password
RABBITMQ_VHOST=cryptobot

# Application Configuration
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

### 3. Start Infrastructure Services

```bash
# Navigate to infrastructure directory
cd infrastructure

# Start all services (PostgreSQL, TimescaleDB, Redis, RabbitMQ)
docker-compose up -d

# Verify all services are running
docker-compose ps

# Expected output:
# crypto-bot-postgres      running
# crypto-bot-timescaledb   running
# crypto-bot-redis         running
# crypto-bot-rabbitmq      running

# Check logs
docker-compose logs -f
```

### 4. Setup Python Virtual Environment

Each service has its own virtual environment:

```bash
# Example for bybit-connector service
cd ../services/bybit-connector

# Create virtual environment
python3.12 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate   # Windows

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Verify installation
python --version
pip list
```

### 5. Initialize Databases

Databases are automatically initialized via Docker Compose init scripts, but you can verify:

```bash
# Connect to PostgreSQL
docker exec -it crypto-bot-postgres psql -U cryptobot -d cryptobot

# Verify tables
\dt trading_engine.*
\dt portfolio.*
\dt audit.*

# Exit
\q

# Connect to TimescaleDB
docker exec -it crypto-bot-timescaledb psql -U cryptobot -d market_data

# Verify hypertables
\d market_data.candles
SELECT * FROM timescaledb_information.hypertables;

# Exit
\q
```

### 6. Run Tests

```bash
# From service directory (with venv activated)
cd services/bybit-connector

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# View coverage report
# Open htmlcov/index.html in browser
```

### 7. Start a Service

```bash
# Example: Start bybit-connector service
cd services/bybit-connector
source venv/bin/activate

# Run with uvicorn (development mode with auto-reload)
uvicorn main:app --reload --host 0.0.0.0 --port 8002

# Service should be available at http://localhost:8002
# API docs at http://localhost:8002/docs
```

---

## Service-by-Service Setup

### Bybit Connector (Port 8002)

```bash
cd services/bybit-connector
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export BYBIT_API_KEY=your_key
export BYBIT_API_SECRET=your_secret
export BYBIT_TESTNET=true

# Run tests
pytest tests/ -v

# Start service
uvicorn main:app --reload --port 8002
```

### Market Data Service (Port 8003)

```bash
cd services/market-data-service
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start service
uvicorn main:app --reload --port 8003
```

### Technical Analysis Service (Port 8004)

```bash
cd services/technical-analysis
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install TA-Lib (system dependency)
# Linux:
sudo apt-get install ta-lib
# Mac:
brew install ta-lib

pip install TA-Lib

# Start service
uvicorn main:app --reload --port 8004
```

### Trading Engine (Port 8001)

```bash
cd services/trading-engine
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start service
uvicorn main:app --reload --port 8001
```

### Portfolio Manager (Port 8005)

```bash
cd services/portfolio-manager
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start service
uvicorn main:app --reload --port 8005
```

### API Gateway (Port 8000)

```bash
cd services/api-gateway
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start service
uvicorn main:app --reload --port 8000
```

---

## Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Frontend should be available at http://localhost:3000
```

---

## Accessing Services

### Management Interfaces

- **RabbitMQ Management**: http://localhost:15672
  - Username: `cryptobot` (from .env)
  - Password: `your_password` (from .env)

- **PgAdmin** (optional, with `--profile dev`):
  ```bash
  docker-compose --profile dev up -d
  ```
  - URL: http://localhost:5050
  - Email: `admin@cryptobot.local`
  - Password: `admin`

### API Documentation

Each service provides interactive API documentation:

- API Gateway: http://localhost:8000/docs
- Trading Engine: http://localhost:8001/docs
- Bybit Connector: http://localhost:8002/docs
- Market Data: http://localhost:8003/docs
- Technical Analysis: http://localhost:8004/docs
- Portfolio Manager: http://localhost:8005/docs

---

## Development Workflow

### 1. Make Changes
Edit code in your preferred IDE (VSCode, PyCharm, etc.)

### 2. Run Tests
```bash
# Run tests before committing
pytest tests/ -v --cov=.
```

### 3. Code Quality Checks
```bash
# Format code
black .
isort .

# Type checking
mypy .

# Linting
flake8 .
```

### 4. Commit Changes
```bash
git add .
git commit -m "feat(service): description of change"
```

---

## Troubleshooting

### Docker Services Not Starting

```bash
# Check Docker status
docker info

# Check container logs
docker-compose logs service-name

# Restart services
docker-compose restart

# Rebuild if needed
docker-compose down
docker-compose up -d --build
```

### Port Already in Use

```bash
# Find process using port
lsof -i :8000  # Replace with your port

# Kill process
kill -9 <PID>

# Or change port in service startup command
uvicorn main:app --reload --port 8010
```

### Database Connection Issues

```bash
# Verify database is running
docker exec -it crypto-bot-postgres pg_isready

# Check connection from Python
python -c "import psycopg2; conn = psycopg2.connect('postgresql://cryptobot:password@localhost:5432/cryptobot'); print('Connected')"
```

### Python Package Installation Issues

```bash
# Update pip
pip install --upgrade pip setuptools wheel

# Clear pip cache
pip cache purge

# Reinstall requirements
pip install -r requirements.txt --force-reinstall
```

---

## IDE Configuration

### VSCode

Recommended extensions:
- Python
- Pylance
- Docker
- GitLens
- REST Client

`.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true
}
```

### PyCharm

1. Open project
2. Settings → Project → Python Interpreter
3. Add interpreter → Existing environment
4. Select `venv/bin/python`

---

## Getting Bybit API Keys

### Testnet (Development)
1. Go to https://testnet.bybit.com/
2. Sign up for a testnet account
3. Navigate to API Management
4. Create new API key
5. Save key and secret (keep secure!)
6. Enable required permissions:
   - Read
   - Trade
   - Wallet

### Production (DO NOT USE YET)
Only use production after thorough testing:
1. Go to https://www.bybit.com/
2. Complete KYC verification
3. Enable 2FA
4. Create API key with restricted permissions
5. Whitelist IP addresses

---

## Next Steps

After setup is complete:
1. ✅ Verify all services are running
2. ✅ Run test suite to ensure everything works
3. ✅ Review architecture documentation
4. ✅ Start with bybit-connector service implementation
5. ✅ Follow TDD approach: write tests first

---

**Need Help?**
- Check [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
- Review service logs: `docker-compose logs -f`
- Run health checks: `curl http://localhost:8000/health`

**Last Updated**: 2025-10-30
