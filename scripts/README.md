# Crypto Trading Bot - Operational Scripts

**Version:** 1.0.0
**Last Updated:** 2025-11-14

---

## Overview

This directory contains operational scripts for managing, monitoring, and validating the crypto trading bot system. These scripts automate common operational tasks and provide comprehensive system monitoring.

**Available Scripts:**
- `startup.sh` - Automated system startup with orchestration
- `health_check.sh` - Comprehensive health validation
- `validate_risk_limits.py` - Risk management rule validation
- `monitor.py` - Continuous system monitoring with alerting

---

## Quick Reference

### First Time Setup
```bash
# 1. Start the entire system
./scripts/startup.sh

# 2. Validate risk management
python3 scripts/validate_risk_limits.py --verbose

# 3. Start continuous monitoring
python3 scripts/monitor.py --interval 60
```

### Daily Operations
```bash
# Quick restart (skip rebuild)
./scripts/startup.sh --skip-build

# Health check
./scripts/health_check.sh --verbose

# Monitor (1 minute intervals)
python3 scripts/monitor.py --interval 60
```

---

## Script Details

### 1. startup.sh - System Startup Orchestration

**Purpose:** Automated startup of all services with proper ordering and validation.

**Usage:**
```bash
./scripts/startup.sh [OPTIONS]
```

**Options:**
- `--skip-build` - Skip Docker image rebuild (faster restart)
- `--verbose` - Show detailed output
- `--help` - Show help message

**What It Does:**

1. **Pre-flight Checks** (10-15 seconds)
   - Verifies Docker and docker-compose installed
   - Checks Docker daemon running
   - Validates project structure

2. **Stop Existing Containers** (5-10 seconds)
   - Gracefully stops any running containers
   - Cleans up networks

3. **Build Docker Images** (5-10 minutes first time, skippable)
   - Builds all service images
   - Can skip with `--skip-build` for faster restart

4. **Start Infrastructure** (30-60 seconds)
   - Starts TimescaleDB, Redis, RabbitMQ
   - Waits for each to be ready

5. **Start Core Services** (30-60 seconds)
   - Starts bybit-connector, market-data, technical-analysis
   - Validates health endpoints

6. **Start AI/ML Services** (30-60 seconds)
   - Starts ml-prediction, sentiment-analysis, risk-metrics
   - Loads ML models

7. **Start Business Logic** (30-60 seconds)
   - Starts portfolio-manager, trading-engine
   - Initializes trading state

8. **Start Support Services** (30-60 seconds)
   - Starts notification-service, api-gateway
   - Configures routing

9. **Initialize Paper Trading** (5-10 seconds)
   - Sets up $10,000 initial balance
   - Configures paper trading mode

10. **Run Health Checks** (30-60 seconds)
    - Validates all 10 services healthy
    - Shows comprehensive system status

**Exit Codes:**
- `0` - All systems operational
- `1` - Some services degraded
- `2` - Critical failures

**Example Output:**
```
╔═══════════════════════════════════════════════════════════╗
║  Crypto Trading Bot - System Startup                     ║
║  2025-11-14 10:30:45                                      ║
╚═══════════════════════════════════════════════════════════╝

[10:30:45] STEP: [1/10] Running pre-flight checks...
[10:30:46] SUCCESS: Pre-flight checks passed
[10:30:46] STEP: [2/10] Stopping existing containers...
[10:30:50] SUCCESS: Stopped existing containers
...
[10:35:20] SUCCESS: All health checks passed

═══════════════════════════════════════════════════════════
Startup Summary
═══════════════════════════════════════════════════════════

Total startup time: 4m 35s

✓ System Status: ALL SYSTEMS OPERATIONAL

All 10 microservices are running and healthy.

Next Steps:
  1. Open dashboard:
     cd dashboard && python3 -m http.server 8080
     Access: http://localhost:8080
  ...
```

**Typical Startup Times:**
- First time (with build): **7-12 minutes**
- Restart (--skip-build): **3-5 minutes**
- Fast restart (warm cache): **2-3 minutes**

---

### 2. health_check.sh - Comprehensive Health Validation

**Purpose:** One-time comprehensive validation of all system components.

**Usage:**
```bash
./scripts/health_check.sh [OPTIONS]
```

**Options:**
- `--verbose` - Show detailed service information

**What It Checks:**

1. **Docker Containers** (Section 1/5)
   - All containers running
   - Container health status
   - Resource usage

2. **Microservices Health** (Section 2/5)
   - All 10 services responding
   - Health endpoint status
   - Response time validation

3. **Database Connectivity** (Section 3/5)
   - TimescaleDB ready and accessible
   - Redis ready and key count
   - RabbitMQ ready and queue status

4. **Data Collection Status** (Section 4/5)
   - Market data available
   - Recent candles for BTCUSDT
   - Data freshness check

5. **ML Models Status** (Section 5/5)
   - Models loaded for symbols
   - Prediction availability
   - Model confidence scores

**Exit Codes:**
- `0` - System healthy (all tests passed)
- `1` - System degraded (1-2 failures)
- `2` - System critical (3+ failures)

**Example Output:**
```
╔════════════════════════════════════════════════════════╗
║  Crypto Trading Bot - System Health Check             ║
║  2025-11-14 10:35:20                                   ║
╚════════════════════════════════════════════════════════╝

[1/5] Docker Containers
────────────────────────────────────────
✓ All containers running (13/13)

[2/5] Microservices Health
────────────────────────────────────────
✓ All microservices healthy (10/10)

[3/5] Database Connectivity
────────────────────────────────────────
✓ TimescaleDB is ready
✓ Redis is ready
✓ RabbitMQ is ready

[4/5] Data Collection Status
────────────────────────────────────────
✓ Market data available (50 candles for BTCUSDT)

[5/5] ML Models Status
────────────────────────────────────────
✓ ML models loaded (5/5 symbols)

════════════════════════════════════════════════════════
Summary
════════════════════════════════════════════════════════
✓ System Status: HEALTHY
  All 10 services are operational

Next steps:
  1. Open dashboard: cd dashboard && python3 -m http.server 8080
  2. View API docs: http://localhost:8005/docs
  3. Run E2E test: cd tests/integration && python3 test_e2e_trading_flow.py
```

**When to Use:**
- After system startup
- Before running tests
- After configuration changes
- When debugging issues
- Before going to production

---

### 3. validate_risk_limits.py - Risk Management Validation

**Purpose:** Validate all risk management rules and safety mechanisms.

**Usage:**
```bash
python3 scripts/validate_risk_limits.py [OPTIONS]
```

**Options:**
- `--verbose` - Show detailed test information

**What It Validates:**

1. **Service Connectivity** (Test 1/8)
   - Trading Engine accessible
   - Portfolio Manager accessible
   - Risk Metrics accessible

2. **Position Size Calculation** (Test 2/8)
   - 2% risk per trade enforced
   - Stop-loss percentage validation
   - Edge case handling

3. **Daily Loss Limit** (Test 3/8)
   - 5% daily loss limit enforced
   - Remaining allowance calculation
   - Trading halt when limit reached

4. **Circuit Breaker** (Test 4/8)
   - 10% drawdown activates breaker
   - System protection engaged
   - Trading halted automatically

5. **Stop-Loss Calculation** (Test 5/8)
   - ATR-based dynamic stop-loss
   - LONG and SHORT validation
   - Volatility-adjusted logic

6. **Maximum Positions** (Test 6/8)
   - 5 concurrent positions limit
   - Position diversity check
   - Available slots tracking

7. **Leverage Restrictions** (Test 7/8)
   - 1x leverage only (no margin)
   - Position size <= balance
   - No liquidation risk

8. **Emergency Stop Procedures** (Test 8/8)
   - Emergency stop endpoint exists
   - Close all positions endpoint
   - Notification system ready

**Exit Codes:**
- `0` - All risk rules validated (SAFE for trading)
- `1` - Some rules need attention (review before live)
- `2` - Critical issues (DO NOT trade)

**Example Output:**
```
╔═══════════════════════════════════════════════════════════╗
║  Crypto Trading Bot - Risk Management Validation         ║
║  2025-11-14 10:40:00                                      ║
╚═══════════════════════════════════════════════════════════╝

[1/8] Service Connectivity
──────────────────────────────────────────────────
✓ Trading Engine accessible
✓ Portfolio Manager accessible
✓ Risk Metrics accessible

[2/8] Position Size Calculation (2% Risk Limit)
──────────────────────────────────────────────────
✓ Standard trade: $10K balance, 5% SL
✓ Tight stop: $5K balance, 2% SL
✓ Large account: $50K balance, 10% SL
...

═══════════════════════════════════════════════════════════
Risk Management Validation Summary
═══════════════════════════════════════════════════════════

Tests Run: 24
Passed: 24
Failed: 0
Warnings: 0

Pass Rate: 100.0%

✓ All Risk Management Rules VALIDATED

Risk controls are properly configured:
  • Position sizing: 2% risk per trade
  • Daily loss limit: 5% of portfolio
  • Circuit breaker: 10% drawdown
  • Stop-loss: ATR-based dynamic
  • Max positions: 5 concurrent
  • Leverage: 1x (no leverage)
  • Emergency stop: Available

System is SAFE for paper trading
```

**When to Use:**
- Before starting live trading
- After risk configuration changes
- As part of deployment checklist
- Regular compliance validation
- After system updates

---

### 4. monitor.py - Continuous System Monitoring

**Purpose:** Continuous health monitoring with automated alerting.

**Usage:**
```bash
python3 scripts/monitor.py [OPTIONS]
```

**Options:**
- `--interval SECONDS` - Monitoring interval (default: 60)
- `--alert-threshold N` - Alert after N consecutive failures (default: 3)

**What It Monitors:**

**Service Health:**
- All 10 microservices status
- Response time tracking
- Failure count per service
- Critical vs non-critical classification

**Trading Metrics:**
- Current portfolio balance
- Daily P&L ($ and %)
- Open position count
- Unrealized P&L

**Data Collection:**
- Recent candle availability
- Data freshness (age check)
- Collection status

**Alert Conditions:**
- Service down (3+ consecutive failures)
- Critical service down (immediate alert)
- Slow response time (>1000ms)
- Daily loss approaching 4% (before 5% limit)
- Position count at limit
- Stale data (>2 hours old)

**Features:**
- Color-coded real-time dashboard
- Alert cooldown (5 minutes) to prevent spam
- JSON metrics export to `/tmp/crypto_bot_metrics.json`
- Metrics history (last 100 data points)
- Graceful shutdown (Ctrl+C)

**Example Output:**
```
======================================================================
System Monitor - 2025-11-14 10:45:30
Uptime: 0:15:45
======================================================================

Services: 10/10 healthy - ALL OPERATIONAL

Trading Metrics:
  Balance: $10,250.50
  Daily P&L: $250.50 (2.51%)
  Open Positions: 2
  Unrealized P&L: $150.25

Data Collection:
  Recent candles: 10
  Data age: 3.5 minutes

======================================================================
Next check in 60 seconds (Ctrl+C to stop)
```

**Alert Examples:**
```
[2025-11-14 10:46:00] ALERT (WARNING): market-data is down (3 consecutive failures)
[2025-11-14 10:47:00] ALERT (CRITICAL): trading-engine is down! (1 consecutive failures)
[2025-11-14 11:00:00] ALERT (WARNING): Daily loss at -4.20% ($420.00) - approaching 5% limit!
[2025-11-14 11:15:00] ALERT (WARNING): market-data is slow: 1250ms response time
```

**Stop Monitoring:**
Press `Ctrl+C` for graceful shutdown.

**Integration:**
Metrics are exported to `/tmp/crypto_bot_metrics.json` for integration with:
- Prometheus (via file exporter)
- Grafana (for visualization)
- Datadog, New Relic, etc.
- Custom alerting systems

**When to Use:**
- During active trading
- For 24/7 monitoring
- Development/testing environments
- Pre-production validation
- Live production monitoring

---

## Common Workflows

### Workflow 1: Daily Startup

```bash
# Morning startup routine
cd /mnt/d/Bimo_max/crypto-trading-bot

# 1. Start system (skip build for faster start)
./scripts/startup.sh --skip-build

# 2. Wait for startup to complete (~3 minutes)

# 3. Validate health
./scripts/health_check.sh --verbose

# 4. Validate risk controls
python3 scripts/validate_risk_limits.py

# 5. Start monitoring (in background)
nohup python3 scripts/monitor.py --interval 60 > /tmp/monitor.log 2>&1 &

# 6. Open dashboard
cd dashboard
python3 -m http.server 8080 &

# 7. Access dashboard at http://localhost:8080
```

### Workflow 2: Troubleshooting

```bash
# Issue detected - investigate

# 1. Check current health
./scripts/health_check.sh --verbose

# 2. If services down, check logs
docker-compose logs -f [service-name]

# 3. Restart specific service
docker-compose restart [service-name]

# 4. If still failing, rebuild
docker-compose build [service-name]
docker-compose up -d [service-name]

# 5. Re-validate
./scripts/health_check.sh --verbose

# 6. Check risk controls still valid
python3 scripts/validate_risk_limits.py
```

### Workflow 3: Configuration Changes

```bash
# After modifying configuration

# 1. Stop current system
docker-compose down

# 2. Rebuild affected services
docker-compose build [service-name]

# 3. Full startup with validation
./scripts/startup.sh

# 4. Validate risk controls (critical!)
python3 scripts/validate_risk_limits.py --verbose

# 5. Run integration tests
cd tests/integration
python3 test_e2e_trading_flow.py

# 6. Resume monitoring
python3 scripts/monitor.py --interval 60
```

### Workflow 4: Pre-Production Checklist

```bash
# Before going to production

# 1. Clean restart
docker-compose down -v
./scripts/startup.sh

# 2. Comprehensive health check
./scripts/health_check.sh --verbose
# EXIT CODE MUST BE 0

# 3. Risk validation
python3 scripts/validate_risk_limits.py --verbose
# EXIT CODE MUST BE 0

# 4. Integration tests
cd tests/integration
python3 test_e2e_trading_flow.py
# PASS RATE MUST BE >80%

# 5. Monitor for 1 hour
python3 scripts/monitor.py --interval 60
# NO CRITICAL ALERTS

# 6. Review documentation
cat docs/DEPLOYMENT_RUNBOOK.md
# FOLLOW PRODUCTION CHECKLIST

# Only then: Enable live trading
```

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: System Validation

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Start System
        run: |
          ./scripts/startup.sh --verbose
        timeout-minutes: 15

      - name: Health Check
        run: |
          ./scripts/health_check.sh --verbose
          if [ $? -ne 0 ]; then
            echo "Health check failed"
            docker-compose logs
            exit 1
          fi

      - name: Risk Validation
        run: |
          python3 scripts/validate_risk_limits.py --verbose
          if [ $? -ne 0 ]; then
            echo "Risk validation failed"
            exit 1
          fi

      - name: Integration Tests
        run: |
          cd tests/integration
          python3 test_e2e_trading_flow.py
          if [ $? -ne 0 ]; then
            echo "Integration tests failed"
            exit 1
          fi

      - name: Cleanup
        if: always()
        run: docker-compose down -v
```

### Jenkins Pipeline Example

```groovy
pipeline {
    agent any

    stages {
        stage('Startup') {
            steps {
                sh './scripts/startup.sh --verbose'
            }
        }

        stage('Validation') {
            parallel {
                stage('Health Check') {
                    steps {
                        sh './scripts/health_check.sh --verbose'
                    }
                }
                stage('Risk Validation') {
                    steps {
                        sh 'python3 scripts/validate_risk_limits.py --verbose'
                    }
                }
            }
        }

        stage('Integration Tests') {
            steps {
                dir('tests/integration') {
                    sh 'python3 test_e2e_trading_flow.py'
                }
            }
        }

        stage('Monitor') {
            steps {
                sh 'timeout 300 python3 scripts/monitor.py --interval 30 || true'
            }
        }
    }

    post {
        always {
            sh 'docker-compose down -v'
        }
    }
}
```

---

## Monitoring Metrics Export

The `monitor.py` script exports metrics to `/tmp/crypto_bot_metrics.json`:

```json
{
  "timestamp": "2025-11-14T10:45:30.123456",
  "uptime_seconds": 945,
  "services": {
    "api-gateway": {
      "healthy": true,
      "response_time_ms": 25.3,
      "status_code": 200
    },
    "trading-engine": {
      "healthy": true,
      "response_time_ms": 32.1,
      "status_code": 200
    }
    ...
  },
  "trading": {
    "current_balance": 10250.50,
    "daily_pnl": 250.50,
    "daily_pnl_pct": 2.51,
    "open_positions": 2,
    "unrealized_pnl": 150.25
  },
  "alerts_sent": 3
}
```

This can be consumed by external monitoring tools.

---

## Troubleshooting

### Script Won't Execute

**Problem:** `Permission denied` when running scripts

**Solution:**
```bash
# Make scripts executable
chmod +x scripts/*.sh
chmod +x scripts/*.py

# Or run with explicit interpreter
bash scripts/startup.sh
python3 scripts/monitor.py
```

### Docker Not Running

**Problem:** `Cannot connect to the Docker daemon`

**Solution:**
```bash
# Start Docker daemon
sudo systemctl start docker  # Linux
# Or start Docker Desktop (Windows/Mac)

# Verify Docker running
docker info
```

### Services Won't Start

**Problem:** Services fail health checks

**Solution:**
```bash
# 1. Check Docker resources
docker system df
docker stats --no-stream

# 2. View service logs
docker-compose logs [service-name]

# 3. Try clean restart
docker-compose down -v
./scripts/startup.sh

# 4. If still failing, rebuild
docker-compose build --no-cache
./scripts/startup.sh
```

### Port Conflicts

**Problem:** `Port is already allocated`

**Solution:**
```bash
# Find process using port
lsof -i :8000  # Linux/Mac
netstat -ano | findstr :8000  # Windows

# Kill process or change port in docker-compose.yml
```

### Health Check Times Out

**Problem:** Health check script hangs

**Solution:**
```bash
# Check specific service manually
curl http://localhost:8000/health

# View service logs
docker-compose logs -f api-gateway

# Restart unhealthy service
docker-compose restart api-gateway
```

---

## Best Practices

### 1. Always Validate After Changes
```bash
# After ANY configuration change:
python3 scripts/validate_risk_limits.py --verbose
```

### 2. Monitor During Active Trading
```bash
# Run continuous monitoring when bot is trading
python3 scripts/monitor.py --interval 60
```

### 3. Regular Health Checks
```bash
# Schedule health checks (crontab example)
0 */6 * * * /path/to/scripts/health_check.sh >> /var/log/crypto-bot-health.log 2>&1
```

### 4. Keep Logs
```bash
# Redirect script output to logs
./scripts/startup.sh --verbose 2>&1 | tee /var/log/crypto-bot-startup.log
```

### 5. Use --verbose for Debugging
```bash
# Always use --verbose when troubleshooting
./scripts/health_check.sh --verbose
python3 scripts/validate_risk_limits.py --verbose
```

---

## Script Dependencies

All scripts require:
- **Bash:** 4.0+ (for startup.sh, health_check.sh)
- **Python:** 3.8+ (for validate_risk_limits.py, monitor.py)
- **Docker:** 20.10+
- **docker-compose:** 1.29+
- **curl:** For HTTP requests
- **jq:** For JSON parsing (optional but recommended)

Python packages:
```bash
pip install httpx asyncio  # For Python scripts
```

---

## Related Documentation

- [System Status](../SYSTEM_STATUS_COMPLETE.md) - Complete system assessment
- [Trading Engine Capabilities](../docs/TRADING_ENGINE_CAPABILITIES.md) - API reference
- [Deployment Runbook](../docs/DEPLOYMENT_RUNBOOK.md) - Operations guide
- [Health Check Guide](../dashboard/README.md#troubleshooting) - Dashboard troubleshooting

---

## Support

**Issues:**
- Check service logs: `docker-compose logs [service-name]`
- Review documentation in `docs/` directory
- Run verbose mode for debugging

**Emergency:**
- Emergency stop: `curl -X POST http://localhost:8005/api/v1/emergency/stop`
- Close all positions: `curl -X POST http://localhost:8005/api/v1/emergency/close-all`
- Stop all services: `docker-compose down`

---

## Version History

**v1.0.0 (2025-11-14)**
- Initial release
- startup.sh - Automated orchestration
- health_check.sh - Health validation
- validate_risk_limits.py - Risk validation
- monitor.py - Continuous monitoring

---

**Maintained By:** Crypto Trading Bot Development Team
**Last Updated:** 2025-11-14
**Script Location:** `/mnt/d/Bimo_max/crypto-trading-bot/scripts/`
