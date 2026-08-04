# Testing Commands Quick Reference

## Health Check All Services

```bash
# Quick health check all services
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  echo "Port $port: $(curl -s http://localhost:$port/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("status", "ERROR"))')"
done
```

## Test Individual Services

```bash
# API Gateway
cd /mnt/d/Bimo_max/crypto-trading-bot/services/api-gateway
python3 -m pytest tests/ -v --tb=short

# Trading Engine
cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine
python3 -m pytest tests/unit/ -v --tb=short

# Technical Analysis
cd /mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis
python3 -m pytest tests/unit/ -v --tb=short

# Market Data Service
cd /mnt/d/Bimo_max/crypto-trading-bot/services/market-data-service
python3 -m pytest tests/ -v --tb=short

# Portfolio Manager
cd /mnt/d/Bimo_max/crypto-trading-bot/services/portfolio-manager
python3 -m pytest tests/ -v --tb=short

# Risk Metrics
cd /mnt/d/Bimo_max/crypto-trading-bot/services/risk-metrics-service
python3 -m pytest tests/ -v --tb=short

# E2E Tests
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 -m pytest tests/e2e/ -v --tb=short
```

## Test Specific API Endpoints

### Market Data
```bash
# Get ticker data
curl "http://localhost:8000/api/market/ticker/BTCUSDT" | python3 -m json.tool

# Get kline data
curl "http://localhost:8000/api/market/kline/BTCUSDT?interval=1h&limit=5" | python3 -m json.tool

# Direct Market Data Service
curl "http://localhost:8002/api/v1/ticker/BTCUSDT" | python3 -m json.tool
curl "http://localhost:8002/api/v1/klines/BTCUSDT?interval=1h&limit=5" | python3 -m json.tool
```

### Trading Signals
```bash
# Get trading signal
curl "http://localhost:8000/api/trading/signals/BTCUSDT" | python3 -m json.tool

# Analyze and trade
curl -X POST "http://localhost:8000/api/trading/signals/BTCUSDT/analyze" | python3 -m json.tool

# Get positions
curl "http://localhost:8000/api/trading/positions" | python3 -m json.tool
```

### Portfolio
```bash
# Get portfolio summary
curl "http://localhost:8000/api/portfolio" | python3 -m json.tool

# Get balance
curl "http://localhost:8000/api/portfolio/balance" | python3 -m json.tool

# Get holdings
curl "http://localhost:8000/api/portfolio/holdings" | python3 -m json.tool

# Get performance metrics
curl "http://localhost:8000/api/portfolio/performance" | python3 -m json.tool
```

### Risk Metrics
```bash
# Get risk scorecard
curl "http://localhost:8000/api/risk/scorecard" | python3 -m json.tool

# Get capital metrics
curl "http://localhost:8000/api/risk/capital" | python3 -m json.tool

# Get exposure metrics
curl "http://localhost:8000/api/risk/exposure" | python3 -m json.tool

# Get VaR metrics
curl "http://localhost:8000/api/risk/var" | python3 -m json.tool
```

### Dashboard
```bash
# Get aggregated dashboard data
curl "http://localhost:8000/api/dashboard/BTCUSDT" | python3 -m json.tool
```

## Data Collection Commands

```bash
# Check scheduler status
curl "http://localhost:8002/api/v1/scheduler/status" | python3 -m json.tool

# Start scheduler
curl -X POST "http://localhost:8002/api/v1/scheduler/start" | python3 -m json.tool

# Stop scheduler
curl -X POST "http://localhost:8002/api/v1/scheduler/stop" | python3 -m json.tool

# Trigger manual collection
curl -X POST "http://localhost:8002/api/v1/scheduler/collect" | python3 -m json.tool
```

## Technical Analysis Direct Endpoints

```bash
# Get RSI
curl "http://localhost:8004/api/v1/indicators/rsi/BTCUSDT?interval=1h&period=14" | python3 -m json.tool

# Get MACD
curl "http://localhost:8004/api/v1/indicators/macd/BTCUSDT?interval=1h" | python3 -m json.tool

# Get Bollinger Bands
curl "http://localhost:8004/api/v1/indicators/bollinger/BTCUSDT?interval=1h" | python3 -m json.tool

# Get all indicators signal
curl "http://localhost:8004/api/v1/indicators/signal/BTCUSDT?interval=1h" | python3 -m json.tool
```

## Run Tests with Coverage

```bash
# API Gateway with coverage
cd /mnt/d/Bimo_max/crypto-trading-bot/services/api-gateway
python3 -m pytest tests/ --cov=app --cov-report=html --cov-report=term

# Trading Engine with coverage
cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine
python3 -m pytest tests/unit/ --cov=app --cov-report=html --cov-report=term

# Technical Analysis with coverage
cd /mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis
python3 -m pytest tests/unit/ --cov=app --cov-report=html --cov-report=term
```

## Run Specific Test Files

```bash
# Test specific file
python3 -m pytest tests/test_main.py -v

# Test specific class
python3 -m pytest tests/test_main.py::TestMarketDataRoutes -v

# Test specific function
python3 -m pytest tests/test_main.py::TestMarketDataRoutes::test_get_ticker_success -v
```

## Watch Tests (Auto-rerun on Changes)

```bash
# Install pytest-watch
pip install pytest-watch

# Watch and auto-run tests
cd /mnt/d/Bimo_max/crypto-trading-bot/services/api-gateway
ptw tests/ -- -v --tb=short
```

## Database Inspection

```bash
# Connect to PostgreSQL
docker exec -it postgres psql -U trading_user -d trading_db

# Inside psql:
# List tables
\dt

# Check kline data
SELECT COUNT(*) FROM klines WHERE symbol = 'BTCUSDT';
SELECT * FROM klines WHERE symbol = 'BTCUSDT' ORDER BY timestamp DESC LIMIT 5;

# Check ticker data
SELECT * FROM tickers WHERE symbol = 'BTCUSDT' ORDER BY timestamp DESC LIMIT 1;

# Check positions
SELECT * FROM positions;

# Check trades
SELECT * FROM trades ORDER BY executed_at DESC LIMIT 10;

# Exit psql
\q
```

## Service Logs

```bash
# View logs for specific service
docker-compose logs -f api-gateway
docker-compose logs -f market-data-service
docker-compose logs -f trading-engine
docker-compose logs -f technical-analysis
docker-compose logs -f portfolio-manager
docker-compose logs -f risk-metrics-service

# View all service logs
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100 market-data-service

# View logs since 10 minutes ago
docker-compose logs --since=10m market-data-service
```

## Performance Testing

```bash
# Simple load test with Apache Bench
ab -n 100 -c 10 http://localhost:8000/health

# Test ticker endpoint
ab -n 100 -c 10 http://localhost:8000/api/market/ticker/BTCUSDT

# Test trading signals endpoint
ab -n 50 -c 5 http://localhost:8000/api/trading/signals/BTCUSDT
```

## Debugging Commands

```bash
# Check if service is running
curl -I http://localhost:8000/health

# Check response time
time curl http://localhost:8000/api/market/ticker/BTCUSDT

# Verbose curl output
curl -v http://localhost:8000/health

# Check OpenAPI spec
curl http://localhost:8000/openapi.json | python3 -m json.tool

# List all available endpoints
curl http://localhost:8000/openapi.json | python3 -c "import sys, json; spec = json.load(sys.stdin); print('\\n'.join([f'{method.upper()} {path}' for path, methods in spec['paths'].items() for method in methods.keys()]))"
```

## Fix and Verify Commands

```bash
# Fix E2E tests import error
cd /mnt/d/Bimo_max/crypto-trading-bot
# Add "from typing import Optional" to tests/e2e/fixtures/mock_data.py
python3 -m pytest tests/e2e/ -v

# Verify all services are healthy
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  status=$(curl -s http://localhost:$port/health | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status", "ERROR"))' 2>/dev/null || echo "DOWN")
  echo "Port $port: $status"
done

# Quick test summary
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 -m pytest services/api-gateway/tests/ -v --tb=line -q
python3 -m pytest services/trading-engine/tests/unit/ -v --tb=line -q
python3 -m pytest services/technical-analysis/tests/unit/ -v --tb=line -q
```

## Continuous Testing Loop

```bash
# Run tests every 30 seconds
watch -n 30 'python3 -m pytest services/api-gateway/tests/ -v --tb=line'

# Or create a loop script
while true; do
  clear
  date
  python3 -m pytest services/api-gateway/tests/ -v --tb=short
  sleep 30
done
```

## Generate Test Report

```bash
# Generate HTML test report
cd /mnt/d/Bimo_max/crypto-trading-bot/services/api-gateway
python3 -m pytest tests/ --html=report.html --self-contained-html

# Generate JUnit XML report (for CI/CD)
python3 -m pytest tests/ --junitxml=report.xml

# Generate combined coverage report
python3 -m pytest tests/ --cov=app --cov-report=html --cov-report=xml
```

## Quick Validation Script

```bash
#!/bin/bash
# Save as: /mnt/d/Bimo_max/crypto-trading-bot/scripts/validate_system.sh

echo "=== Crypto Trading Bot System Validation ==="
echo ""

echo "1. Checking service health..."
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  status=$(curl -s http://localhost:$port/health 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status", "ERROR"))' 2>/dev/null || echo "DOWN")
  echo "  Port $port: $status"
done

echo ""
echo "2. Testing key endpoints..."
echo "  Ticker: $(curl -s http://localhost:8000/api/market/ticker/BTCUSDT | python3 -c 'import sys,json; print("OK" if json.load(sys.stdin).get("ticker") else "FAIL")' 2>/dev/null || echo "FAIL")"
echo "  Signals: $(curl -s http://localhost:8000/api/trading/signals/BTCUSDT | python3 -c 'import sys,json; print("OK" if json.load(sys.stdin).get("success") else "FAIL")' 2>/dev/null || echo "FAIL")"
echo "  Portfolio: $(curl -s http://localhost:8000/api/portfolio | python3 -c 'import sys,json; print("OK" if json.load(sys.stdin).get("success") else "FAIL")' 2>/dev/null || echo "FAIL")"

echo ""
echo "3. Running unit tests..."
cd /mnt/d/Bimo_max/crypto-trading-bot/services/api-gateway
python3 -m pytest tests/ -q --tb=no | tail -1

echo ""
echo "Validation complete!"
```

## Monitor Mode

```bash
# Terminal 1: Watch logs
docker-compose logs -f

# Terminal 2: Watch health
watch -n 5 'for port in 8000 8001 8002 8003 8004 8005; do curl -s http://localhost:$port/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Port $port: {d.get(\"status\", \"ERROR\")}\")"; done'

# Terminal 3: Run tests on change
ptw services/api-gateway/tests/ -- -v --tb=short
```

---

**Quick Reference Card**
- Health: `curl localhost:8000/health`
- Ticker: `curl localhost:8000/api/market/ticker/BTCUSDT`
- Signals: `curl localhost:8000/api/trading/signals/BTCUSDT`
- Tests: `python3 -m pytest tests/ -v`
- Logs: `docker-compose logs -f`
