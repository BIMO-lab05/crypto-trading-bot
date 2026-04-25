# Statistical Arbitrage Paper Trading - Monitoring Guide

**Purpose:** Comprehensive monitoring setup for Statistical Arbitrage paper trading
**Author:** DevOps Automation Agent
**Date:** 2025-12-11
**Version:** 1.0

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Monitoring Checklist](#monitoring-checklist)
3. [Scripts Reference](#scripts-reference)
4. [Key Metrics](#key-metrics)
5. [Alert Configuration](#alert-configuration)
6. [Grafana Dashboard](#grafana-dashboard)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Run Health Check
```bash
# Quick health check of all services
cd /mnt/d/Bimo_max/crypto-trading-bot
./health_check.sh

# Continuous health monitoring
./health_check.sh --watch

# JSON output for automation
./health_check.sh --json
```

### 2. Monitor Paper Trading
```bash
# Single snapshot of paper trading status
./monitor_paper_trading.sh

# Continuous monitoring (refreshes every 30 seconds)
./monitor_paper_trading.sh --continuous

# Custom refresh interval (60 seconds)
./monitor_paper_trading.sh -c -i 60

# JSON output for external tools
./monitor_paper_trading.sh --json
```

### 3. Check Statistical Arbitrage Status
```bash
# API endpoint check
curl http://localhost:8005/api/v1/statistical-arbitrage/status | python3 -m json.tool

# Performance metrics
curl http://localhost:8005/api/v1/statistical-arbitrage/performance | python3 -m json.tool
```

---

## Monitoring Checklist

### Daily Monitoring Tasks

- [ ] **System Health**
  - [ ] All services running (check health_check.sh output)
  - [ ] No critical errors in logs
  - [ ] API connections healthy

- [ ] **Strategy Performance**
  - [ ] Signals generated per hour
  - [ ] Virtual orders placed
  - [ ] P&L tracking
  - [ ] Win rate monitoring

- [ ] **Risk Metrics**
  - [ ] Max drawdown < 10%
  - [ ] ROI within acceptable range
  - [ ] No unusual trading patterns

### Key Metrics to Watch

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Signals per hour | > 1 | < 1/hour for 30 min |
| Win rate | > 50% | < 40% |
| ROI | > 0% | < -5% |
| Max drawdown | < 5% | > 10% |
| Service uptime | 100% | < 99% |
| API latency | < 100ms | > 500ms |

---

## Scripts Reference

### health_check.sh

**Location:** `/mnt/d/Bimo_max/crypto-trading-bot/health_check.sh`

**Purpose:** Monitor health status of all microservices and infrastructure

**Usage:**
```bash
./health_check.sh [OPTIONS]

Options:
  --json    Output in JSON format
  --watch   Continuous monitoring mode
  -h        Show help
```

**Sample Output:**
```
============================================================================
  CRYPTO TRADING BOT - HEALTH CHECK
  Time: 2025-12-11 01:52:03
============================================================================

=== SERVICE HEALTH ===

SERVICE              STATUS       CONTAINER
------------------------------------------------------------------------
api-gateway          HEALTHY      Up 2 hours (healthy)
bybit-connector      HEALTHY      Up 5 hours (healthy)
trading-engine       HEALTHY      Up 2 hours (healthy)

=== STATISTICAL ARBITRAGE STATUS ===

Manager Status: active
Capital: $10,000.00
Total Trades: 5
Win Rate: 60.0%
```

### monitor_paper_trading.sh

**Location:** `/mnt/d/Bimo_max/crypto-trading-bot/monitor_paper_trading.sh`

**Purpose:** Real-time monitoring of Statistical Arbitrage paper trading

**Usage:**
```bash
./monitor_paper_trading.sh [OPTIONS]

Options:
  -c, --continuous    Continuous monitoring mode
  -i, --interval N    Refresh interval (default: 30 seconds)
  -j, --json          JSON output
  --no-logs           Hide activity logs
  --log-lines N       Number of log lines (default: 15)
  -h, --help          Show help
```

**What it monitors:**
- Manager status and capital allocation
- Active strategies (pairs, funding, triangular)
- Signal generation and execution
- Service connectivity
- Recent errors and activity

---

## Key Metrics

### Manager Metrics

| Metric Name | Description | Prometheus Key |
|-------------|-------------|----------------|
| Total Capital | Total capital in stat arb | `stat_arb_total_capital` |
| Allocated Capital | Currently deployed capital | `stat_arb_allocated_capital` |
| Total Profit | Cumulative P&L | `stat_arb_total_profit` |
| ROI % | Return on investment | `stat_arb_roi_percent` |
| Win Rate | Percentage of winning trades | `stat_arb_win_rate` |
| Total Trades | Number of trades executed | `stat_arb_total_trades` |

### Strategy Metrics

| Metric Name | Description | Prometheus Key |
|-------------|-------------|----------------|
| Strategy Count | Active strategies by type | `stat_arb_strategy_count{strategy_type="..."}` |
| Strategy Profit | P&L by strategy | `stat_arb_strategy_profit{strategy_id="..."}` |
| Pairs Z-Score | Current Z-score | `stat_arb_pairs_zscore{strategy_id="..."}` |
| Funding Rate | Current funding rate | `stat_arb_funding_rate{symbol="..."}` |

### Signal Metrics

| Metric Name | Description | Prometheus Key |
|-------------|-------------|----------------|
| Signals Generated | Count of signals | `stat_arb_signals_generated{strategy_type="..."}` |
| Signals Executed | Signals that became trades | `stat_arb_signals_executed{strategy_type="..."}` |
| Signals Rejected | Signals below threshold | `stat_arb_signals_rejected{strategy_type="...", reason="..."}` |

---

## Alert Configuration

### Alert Rules Location
`/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/rules/stat_arb_alerts.yml`

### Critical Alerts (Immediate Action Required)

| Alert | Condition | Action |
|-------|-----------|--------|
| StatArbMaxDrawdownCritical | Max drawdown > 10% | Pause trading immediately |
| StatArbNegativeROI | ROI < -5% for 5min | Review strategies |
| StatArbServiceDown | Trading engine unavailable | Restart service |

### Warning Alerts (Monitor Closely)

| Alert | Condition | Action |
|-------|-----------|--------|
| StatArbLowWinRate | Win rate < 40% | Evaluate strategy params |
| StatArbNoSignals | No signals for 1 hour | Check data feeds |
| StatArbPairsNotCointegrated | Cointegration lost | Recalibrate pair |
| StatArbExtremeZScore | Z-score > 3 | Check for stop-loss |

### Info Alerts (Tracking)

| Alert | Condition | Purpose |
|-------|-----------|---------|
| StatArbProfitableTrade | Profit increase | Track successful trades |
| StatArbROIMilestone | ROI > 5% | Celebrate progress |
| StatArbTriangularOpportunity | Opportunity > 0.5% | Track arb opportunities |

---

## Grafana Dashboard

### Dashboard Location
`/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/grafana/stat_arb_dashboard.json`

### Panels Overview

1. **Portfolio Overview Row**
   - Total Capital (gauge)
   - Allocated Capital (gauge)
   - Total P&L (stat with trend)
   - ROI % (stat with threshold colors)
   - Win Rate (gauge)
   - Total Trades (counter)

2. **Performance Over Time Row**
   - P&L Over Time (time series)
   - ROI % Over Time (time series)

3. **Strategy Breakdown Row**
   - Active Strategies by Type (pie chart)
   - P&L by Strategy (bar chart)

4. **Pairs Trading Metrics Row**
   - Z-Score by Pair (time series with thresholds)
   - Spread by Pair (time series)

5. **Funding Rate Arbitrage Row**
   - Funding Rates (time series)
   - Annualized Yield % (bar chart)

6. **Signal Activity Row**
   - Signals Generated per Minute (stacked bars)
   - Signal Execution Status (executed vs rejected)

### Importing the Dashboard

1. Access Grafana at `http://localhost:3000`
2. Go to Dashboards > Import
3. Upload the JSON file or paste the content
4. Select Prometheus as the data source
5. Click Import

---

## Troubleshooting

### Common Issues

#### 1. Manager Not Initialized
```bash
# Check status
curl http://localhost:8005/api/v1/statistical-arbitrage/status

# Initialize with default settings
curl -X POST "http://localhost:8005/api/v1/statistical-arbitrage/initialize?total_capital=10000"
```

#### 2. No Signals Being Generated
```bash
# Check if strategies are added
curl http://localhost:8005/api/v1/statistical-arbitrage/status | jq '.manager_status.strategies'

# Add a pairs strategy
curl -X POST "http://localhost:8005/api/v1/statistical-arbitrage/pairs/add?symbol_x=BTCUSDT&symbol_y=ETHUSDT"
```

#### 3. Service Connectivity Issues
```bash
# Check all service health
./health_check.sh

# Check Docker containers
docker ps | grep crypto-bot

# View service logs
docker logs crypto-bot-trading --tail 100
```

#### 4. Metrics Not Appearing in Prometheus
```bash
# Check metrics endpoint
curl http://localhost:8001/metrics | grep stat_arb

# Verify Prometheus is scraping
curl http://localhost:9090/api/v1/targets
```

### Log Locations

| Service | Container Logs | File Logs |
|---------|---------------|-----------|
| Trading Engine | `docker logs crypto-bot-trading` | `/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine/logs/` |
| Paper Trading Monitor | N/A | `/mnt/d/Bimo_max/crypto-trading-bot/logs/paper_trading/` |

### Getting Help

1. Check the service logs first
2. Run health check script
3. Review recent changes in git
4. Check Docker container status
5. Verify API endpoints are responding

---

## Recommended Monitoring Schedule

| Frequency | Task | Script/Tool |
|-----------|------|-------------|
| Continuous | Service health | `./health_check.sh --watch` |
| Every 30s | Paper trading status | `./monitor_paper_trading.sh -c` |
| Hourly | Performance review | Grafana Dashboard |
| Daily | Log analysis | Docker logs review |
| Weekly | Strategy performance | Performance endpoint |

---

## Files Reference

| File | Purpose | Location |
|------|---------|----------|
| health_check.sh | System health monitoring | `/mnt/d/Bimo_max/crypto-trading-bot/health_check.sh` |
| monitor_paper_trading.sh | Paper trading monitor | `/mnt/d/Bimo_max/crypto-trading-bot/monitor_paper_trading.sh` |
| stat_arb_metrics.py | Prometheus metrics module | `/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine/app/monitoring/stat_arb_metrics.py` |
| stat_arb_alerts.yml | Prometheus alert rules | `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/rules/stat_arb_alerts.yml` |
| stat_arb_dashboard.json | Grafana dashboard | `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/grafana/stat_arb_dashboard.json` |

---

*Document generated by DevOps Automation Agent - 2025-12-11*
