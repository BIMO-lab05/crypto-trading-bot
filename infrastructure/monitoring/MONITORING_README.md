# Crypto Trading Bot - Monitoring Configuration

## Overview

This directory contains comprehensive Prometheus and Grafana monitoring configuration for the crypto trading bot staging environment.

## Directory Structure

```
infrastructure/monitoring/
├── alertmanager/
│   ├── alertmanager.yml         # AlertManager main configuration
│   └── templates/               # Notification templates
│       └── email.tmpl          # Email notification template
├── grafana/
│   ├── dashboards/              # Grafana dashboard JSON files
│   │   ├── trading-performance-dashboard.json    # Trading metrics & equity
│   │   ├── risk-metrics-dashboard.json           # Risk & portfolio analysis
│   │   ├── execution-quality-dashboard.json      # Order execution metrics
│   │   ├── multi-exchange-dashboard.json         # Exchange health & arbitrage
│   │   └── system-health-staging-dashboard.json  # Infrastructure health
│   └── provisioning/
│       ├── dashboards/          # Dashboard provisioning config
│       └── datasources/         # Datasource provisioning config
├── prometheus/
│   ├── prometheus-ha.yml        # Main Prometheus configuration
│   ├── recording-rules.yml      # Pre-computed metrics
│   ├── alerts/                  # Alert rule files
│   │   ├── trading-alerts.yaml  # Trading-specific alerts
│   │   ├── exchange-alerts.yaml # Exchange connectivity alerts
│   │   └── system-alerts.yaml   # Infrastructure alerts
│   └── targets/
│       └── services.json        # Static target discovery
├── kubernetes/monitoring/
│   └── servicemonitors/         # Kubernetes ServiceMonitor CRDs
│       ├── trading-services.yaml
│       └── infrastructure-services.yaml
├── deploy-monitoring.sh         # Deployment automation script
└── MONITORING_README.md         # This file
```

## Grafana Dashboards

### 1. Trading Performance Dashboard
**UID:** `trading-performance-staging`

Displays core trading metrics:
- Total equity and equity curve over time
- Daily/weekly P&L visualization
- Win rate, profit factor, Sharpe/Sortino ratios
- Current and maximum drawdown
- Trade statistics by symbol
- Open positions count

### 2. Risk Management Dashboard
**UID:** `risk-metrics-dashboard`

Portfolio risk analysis:
- P&L tracking with thresholds
- Position allocation pie chart
- Position size vs limits (bar chart)
- Correlation analysis
- VaR (95% and 99%) with limits
- Drawdown analysis
- Active risk alerts table

### 3. Execution Quality Dashboard
**UID:** `execution-quality-staging`

Order execution metrics:
- Execution latency (P50, P95, P99)
- Fill rates by exchange
- Slippage analysis by symbol
- Order type distribution
- Maker vs taker ratio
- TWAP/VWAP execution quality
- Smart router decisions

### 4. Multi-Exchange Dashboard
**UID:** `multi-exchange-staging`

Multi-exchange monitoring:
- WebSocket connection status per exchange
- API latency and error rates
- Price comparison across exchanges
- Price spread detection
- Arbitrage opportunities tracking
- API rate limit usage
- Failover event history

### 5. System Health Dashboard
**UID:** `system-health-staging`

Infrastructure monitoring:
- Pod CPU/memory usage
- HPA scaling events and replica counts
- Request rates and response latency
- PostgreSQL connection pool
- Redis cache hit rates
- RabbitMQ queue depths
- Error rates by service

## Alert Rules

### Trading Alerts (trading-alerts.yaml)

| Alert | Severity | Condition | Description |
|-------|----------|-----------|-------------|
| DrawdownWarning10Percent | warning | Drawdown >= 10% | Portfolio drawdown exceeds 10% |
| DrawdownWarning15Percent | warning | Drawdown >= 15% | Elevated risk warning |
| DrawdownCritical20Percent | critical | Drawdown >= 20% | Critical - halt trading |
| PositionSizeExceedsLimit | warning | Position > 5% of portfolio | Single position too large |
| PositionSizeCritical | critical | Position > 10% of portfolio | Critical risk violation |
| CircuitBreakerTriggered | critical | Circuit breaker = 1 | Trading halted |
| DailyLossLimitExceeded | critical | Daily loss > 5% | Daily loss limit breached |
| TradingEngineDown | critical | up == 0 for 15s | Trading engine unavailable |
| WinRateBelow40Percent | warning | Win rate < 40% for 6h | Strategy underperforming |

### Exchange Alerts (exchange-alerts.yaml)

| Alert | Severity | Condition | Description |
|-------|----------|-----------|-------------|
| BybitWebSocketDisconnected | critical | WS connected == 0 for 15s | No real-time data |
| WebSocketReconnectRateHigh | warning | > 3 reconnects in 5m | Connection instability |
| APIRateLimitApproaching | warning | Remaining < 100 | Approaching rate limit |
| APIRateLimitCritical | critical | Remaining < 20 | Rate limit nearly exhausted |
| MarketDataStale | warning | No update for > 30s | Stale price data |
| MarketDataCriticallyStale | critical | No update for > 60s | Critical data freshness issue |
| PrimaryExchangeFailover | warning | Failover active | Using backup exchange |

### System Alerts (system-alerts.yaml)

| Alert | Severity | Condition | Description |
|-------|----------|-----------|-------------|
| PodHighCPUUsage | warning | CPU > 80% for 10m | Pod CPU pressure |
| PodCriticalCPUUsage | critical | CPU > 95% for 5m | CPU saturation |
| PodHighMemoryUsage | warning | Memory > 85% for 10m | Memory pressure |
| ContainerOOMKilled | critical | OOM kill detected | Out of memory |
| HPAAtMaxReplicas | warning | At max for 15m | Cannot scale further |
| PostgreSQLDown | critical | pg_up == 0 | Database unavailable |
| RedisDown | critical | redis_up == 0 | Cache unavailable |
| RabbitMQDown | critical | rabbitmq_up == 0 | Message broker unavailable |
| TradingQueueDepthCritical | critical | Queue > 1000 for 2m | Order backlog |

## Deployment

### Prerequisites

1. Kubernetes cluster with Prometheus Operator installed
2. kubectl configured with cluster access
3. jq installed (for verification)

### Deploy All Monitoring

```bash
# Deploy everything
./deploy-monitoring.sh

# Dry run (preview changes)
./deploy-monitoring.sh --dry-run

# Custom namespace
./deploy-monitoring.sh --namespace custom-staging --monitoring-namespace monitoring
```

### Manual Dashboard Import

1. Access Grafana:
   ```bash
   kubectl port-forward -n monitoring svc/grafana 3000:3000
   ```

2. Navigate to Dashboards > Import

3. Upload JSON files from `grafana/dashboards/`

4. Select Prometheus datasource when prompted

### Testing Alerts

```bash
# Test alert firing
./scripts/test_alerts.sh

# Manually trigger test alert
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    },
    "annotations": {
      "summary": "Test alert"
    }
  }]'
```

## Notification Channels

Configure the following environment variables for alerts:

```bash
# Email notifications
export SMTP_USERNAME=alerts@example.com
export SMTP_PASSWORD=your-password
export ALERT_EMAIL=team@example.com

# Telegram notifications
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_CHAT_ID=your-chat-id
export WEBHOOK_TOKEN=secure-token

# Slack (optional)
export SLACK_WEBHOOK_URL_CRITICAL=https://hooks.slack.com/...
export SLACK_WEBHOOK_URL_DATABASE=https://hooks.slack.com/...

# PagerDuty (optional)
export PAGERDUTY_SERVICE_KEY=your-service-key
```

## Key Metrics

### Trading Metrics

| Metric | Type | Description |
|--------|------|-------------|
| portfolio_equity_usd | gauge | Total portfolio value |
| portfolio_daily_pnl_usd | gauge | Daily profit/loss |
| portfolio_daily_pnl_percentage | gauge | Daily P&L % |
| portfolio_drawdown_percentage | gauge | Current drawdown % |
| trades_executed_total | counter | Total trades executed |
| trades_winning_total | counter | Winning trades count |
| trade_execution_duration_seconds | histogram | Execution latency |
| active_positions_count | gauge | Open positions |

### Risk Metrics

| Metric | Type | Description |
|--------|------|-------------|
| position_size_percentage | gauge | Position as % of portfolio |
| portfolio_risk_exposure | gauge | Total risk exposure |
| portfolio_var_95 | gauge | Value at Risk (95%) |
| portfolio_var_99 | gauge | Value at Risk (99%) |
| trading_circuit_breaker_state | gauge | 0=normal, 1=triggered |

### Exchange Metrics

| Metric | Type | Description |
|--------|------|-------------|
| bybit_websocket_connected | gauge | WebSocket status |
| bybit_api_rate_limit_remaining | gauge | API calls remaining |
| market_data_last_update_timestamp | gauge | Last price update |
| order_slippage_percentage | gauge | Order slippage % |

### System Metrics

| Metric | Type | Description |
|--------|------|-------------|
| container_cpu_usage_seconds_total | counter | Container CPU |
| container_memory_usage_bytes | gauge | Container memory |
| pg_stat_activity_count | gauge | DB connections |
| redis_memory_used_bytes | gauge | Redis memory |
| rabbitmq_queue_messages | gauge | Queue depth |

## Verification Checklist

After deployment, verify:

- [ ] Prometheus targets are UP (`/targets` page)
- [ ] ServiceMonitors are created (`kubectl get servicemonitors`)
- [ ] Alert rules are loaded (`/rules` page)
- [ ] Grafana datasource is working
- [ ] All 5 dashboards are imported
- [ ] Test alert fires and routes correctly
- [ ] Notification channels are configured

## Troubleshooting

### Prometheus not scraping targets

1. Check ServiceMonitor labels match service labels
2. Verify namespace selectors are correct
3. Check RBAC permissions for Prometheus service account

### Grafana dashboards not loading

1. Verify Prometheus datasource is configured
2. Check dashboard JSON syntax
3. Ensure metrics exist in Prometheus

### Alerts not firing

1. Check Prometheus rules are loaded: `/api/v1/rules`
2. Verify expression in Prometheus UI
3. Check AlertManager routing configuration

### AlertManager not sending notifications

1. Test AlertManager connectivity: `curl http://alertmanager:9093/-/healthy`
2. Check AlertManager logs for errors
3. Verify SMTP/webhook credentials

## Support

For issues or questions, check:
- Prometheus Operator docs: https://prometheus-operator.dev/
- Grafana docs: https://grafana.com/docs/
- AlertManager docs: https://prometheus.io/docs/alerting/
