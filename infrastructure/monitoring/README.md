# Monitoring Infrastructure

**Observability stack (Prometheus + Grafana + alerting) for the Crypto Trading Bot.**

> Merged from `MONITORING_README.md`, `MONITORING_SETUP_GUIDE.md`, `QUICK_REFERENCE.md`, `README_ALERTING.md`, and `ALERTING_QUICK_REFERENCE.md` on 2026-07-30. Those five files are superseded by this README.

> **Read this first (2026-07-30):**
> - **Canonical compose file is `docker-compose.unified.yml` at the repo root.** Older monitoring docs referenced split files (`docker-compose.yml` + `docker-compose.monitoring.yml`); the plain `docker-compose.yml` is incomplete (missing DBs) — do not use it. Prometheus (`:9090`) and Grafana (host port `:3001`) are part of the unified stack.
> - **Kubernetes/Helm monitoring content** (ServiceMonitors, `deploy-monitoring.sh`, Prometheus Operator) is retained below but **out of scope for v1.x** — current posture is docker-compose-only per `.planning/REQUIREMENTS.md`.
> - **Grafana credentials:** see `.env` (`GRAFANA_USER` / `GF_SECURITY_ADMIN_PASSWORD`); **rotate the default**. Superseded docs printed the default admin credentials in plaintext — treat those defaults as burned and rotate on any environment where they were ever used.
> - **Living operator guides** now live in `docs/operations/`: [`MONITORING_GUIDE.md`](../../docs/operations/MONITORING_GUIDE.md), [`ALERTING_GUIDE.md`](../../docs/operations/ALERTING_GUIDE.md), [`ALERT_RUNBOOKS.md`](../../docs/operations/ALERT_RUNBOOKS.md). This README documents what is in *this* directory and the day-to-day commands.
> - **Tier-1 cron monitor:** `scripts/monitoring/` is the separate lightweight cron-based health monitor (15-min cadence, notify-only, no autonomous remediation) — see `scripts/monitoring/README.md` and ADR-026 (`wiki/decisions/ADR-026-monitoring-disposition.md`).

---

## Table of Contents

1. [What's In This Directory](#whats-in-this-directory)
2. [Setup](#setup)
3. [Dashboards](#dashboards)
4. [Alerting](#alerting)
5. [Key Metrics and PromQL](#key-metrics-and-promql)
6. [Quick Commands](#quick-commands)
7. [Emergency Procedures](#emergency-procedures)
8. [Troubleshooting](#troubleshooting)
9. [Maintenance, Backup, Performance](#maintenance-backup-performance)
10. [Security](#security)
11. [Checklists](#checklists)
12. [Related Documentation](#related-documentation)

---

## What's In This Directory

### Components

| Component | Purpose | Host Port | URL |
|-----------|---------|-----------|-----|
| **Prometheus** | Metrics collection and storage | 9090 | http://localhost:9090 |
| **Grafana** | Visualization and dashboards | 3001 | http://localhost:3001 |
| **AlertManager** | Alert routing and management | 9093 | http://localhost:9093 |
| **Telegram alert bot** | Telegram notification relay | 8080 (see note) | health endpoint on the bot container |
| **Loki** | Log aggregation | 3100 | http://localhost:3100 |
| **Promtail** | Log shipping agent | 9080 | - |
| **Node Exporter** | System metrics | 9100 | - |
| **cAdvisor** | Container metrics | 8080 | http://localhost:8080 |
| **Redis Exporter** | Redis metrics | 9121 | - |
| **Postgres Exporter** | Database metrics | 9187 | - |

> ⚠️ Port contradictions date-stamped 2026-07-30:
> - **Grafana**: docs from 2025-11 disagreed between `:3000` and `:3001`. The unified compose stack maps Grafana to host port **3001** (`:3000` is the frontend). K8s port-forwards in older guides used `3000:3000` (container port), which still works in a K8s context.
> - **Telegram alert bot**: the 2025-11-21 alerting docs said the bot's health endpoint was `http://localhost:8007/health` — but **8007 is ml-prediction-service's port** in the unified stack (the collision went unnoticed because ml-prediction sits behind the compose `ml` profile and is off by default). Verify the bot's actual host port mapping in `docker-compose.unified.yml` before relying on the `:8007` commands preserved below.
> - **cAdvisor `:8080`** may also collide with other local tooling; it was optional/commented-out in the compose overlay.

### Directory Layout

Two generations of this directory's layout were documented; both are preserved here because the directory has accumulated files from both. Verify against `ls` before editing configs.

**Compose-era layout** (2025-11-11 → 2025-11-21 docs):

```
infrastructure/monitoring/
├── prometheus.yml / prometheus/prometheus.yml   # Prometheus scrape config
├── prometheus/alerts.yml                        # Alert rule definitions
├── rules/
│   ├── phase3-alerts.yml            # Phase 3 (ML/sentiment/risk) alert rules
│   └── trading-alerts.yml           # 26 production alert rules
├── grafana-provisioning/ | grafana/provisioning/
│   ├── dashboards/                  # Dashboard provisioning config
│   └── datasources/                 # Datasource provisioning config
├── grafana/dashboards/              # Dashboard JSON files
├── alertmanager/
│   ├── alertmanager.yml             # Alert routing configuration
│   ├── .env                         # Email credentials (generated; NEVER commit)
│   └── templates/email.tmpl         # Email HTML template
├── telegram-bot/
│   ├── telegram_alerts.py           # Telegram bot application
│   ├── Dockerfile                   # Container build
│   ├── requirements.txt             # Python dependencies
│   └── .env                         # Bot credentials (generated; NEVER commit)
├── loki/loki-config.yml             # Log storage/retention (30 days)
├── promtail/promtail-config.yml     # Log collection config
├── scripts/
│   ├── setup_alerting.sh            # Interactive alerting setup wizard
│   └── test_alerts.sh               # Alert testing suite
└── README.md                        # This file
```

**Staging/K8s layout** (undated MONITORING_README.md — K8s out of scope for v1.x):

```
infrastructure/monitoring/
├── prometheus/
│   ├── prometheus-ha.yml            # HA Prometheus configuration
│   ├── recording-rules.yml          # Pre-computed metrics
│   ├── alerts/
│   │   ├── trading-alerts.yaml      # Trading-specific alerts
│   │   ├── exchange-alerts.yaml     # Exchange connectivity alerts
│   │   └── system-alerts.yaml       # Infrastructure alerts
│   └── targets/services.json        # Static target discovery
├── grafana/dashboards/              # 5 staging dashboard JSONs (see Dashboards)
├── kubernetes/monitoring/servicemonitors/
│   ├── trading-services.yaml
│   └── infrastructure-services.yaml
└── deploy-monitoring.sh             # K8s deployment automation script
```

Also in this directory (kept separate):

- **[`PROMETHEUS_INSTRUMENTATION_GUIDE.md`](./PROMETHEUS_INSTRUMENTATION_GUIDE.md)** — how to add Prometheus metrics to the ML Prediction, Sentiment Analysis, and Risk Metrics services (metric definitions, FastAPI instrumentation, best practices). Read it before adding or renaming any metric.

---

## Setup

### Prerequisites

```bash
# Ensure Docker and Docker Compose are installed
docker --version
docker compose version

# Ensure the crypto-bot-network exists (only needed if running components standalone)
docker network create crypto-bot-network 2>/dev/null || true
```

- All bot services running (ports 8000–8009)
- Host ports 3001 (Grafana) and 9090 (Prometheus) available

### Start the Stack (compose — canonical)

```bash
# From repo root — monitoring services are part of the unified stack
docker compose -f docker-compose.unified.yml up -d

# Check monitoring services are running
docker ps | grep -E "prometheus|grafana|alertmanager"

# View logs
docker logs crypto-bot-prometheus
docker logs crypto-bot-grafana
docker compose -f docker-compose.unified.yml logs -f prometheus grafana
```

> Historical note (date-stamped 2026-07-30): 2025-11 docs started monitoring via
> `docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d` and
> `docker-compose -f docker-compose.monitoring.yml up -d` (from this directory).
> The unified compose file is now canonical. If extended components (AlertManager,
> Loki/Promtail, exporters, the Telegram bot) are not present in
> `docker-compose.unified.yml`, they still live in the historical
> `docker-compose.monitoring.yml` overlay — check before assuming they are running.

### Instrumenting Services

Each microservice exports metrics at `GET /metrics`.

Add to each service's `requirements.txt`:

```
# Monitoring
prometheus-client==0.19.0
prometheus-fastapi-instrumentator==6.1.0
```

Quick example for any FastAPI service:

```python
# app/main.py
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Service Name")

# Enable Prometheus metrics
Instrumentator().instrument(app).expose(app)
```

Custom business metrics:

```python
from prometheus_client import Counter, Histogram

trades_counter = Counter('trades_executed_total', 'Total trades executed')
trade_latency = Histogram('trade_execution_duration_seconds', 'Trade execution time')
```

See [`PROMETHEUS_INSTRUMENTATION_GUIDE.md`](./PROMETHEUS_INSTRUMENTATION_GUIDE.md) for full per-service metric catalogs and best practices.

### Environment Variables

Create `.env` in `infrastructure/monitoring/` (or set in the repo-root `.env` consumed by the unified compose). **Never commit these files.**

```bash
# Grafana
GRAFANA_USER=admin
GRAFANA_PASSWORD=<strong-password>        # rotate the default!

# Database credentials (for exporters)
DB_USER=cryptobot
DB_PASSWORD=<db-password>
DB_NAME=cryptobot

# Redis
REDIS_PASSWORD=<redis-password>

# Alerting — required
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_CHAT_ID=<from /get-chat-id>
SMTP_USERNAME=your-email@gmail.com        # Gmail address
SMTP_PASSWORD=<16-char app password>      # App-Specific Password, NOT your Gmail password
ALERT_EMAIL=alerts@example.com            # Recipient
WEBHOOK_TOKEN=<secure-random-token>       # Generated by setup script

# Alerting — optional
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_WEBHOOK_URL_CRITICAL=https://hooks.slack.com/services/YOUR/CRITICAL/URL
SLACK_WEBHOOK_URL_DATABASE=https://hooks.slack.com/services/YOUR/DATABASE/URL
PAGERDUTY_SERVICE_KEY=<pagerduty-key>
```

### Prometheus Configuration

**File:** `prometheus.yml` (this directory).

Key settings:
- **Scrape interval**: 15 seconds (adjustable per service)
- **Evaluation interval**: 15 seconds for alert rules
- **Data retention**: 15 days per the 2025-11-11 setup guide; the 2025-11-16 stack doc used `--storage.tsdb.retention.time=30d`. Check the actual `command:` flags in compose — and see [Performance](#maintenance-backup-performance) for tuning.

Scrape targets — all microservices every 15s, plus exporters:

| Target | Port |
|---|---|
| api-gateway | 8000 |
| bybit-connector | 8001 |
| market-data-service | 8002 |
| portfolio-manager | 8003 |
| technical-analysis | 8004 |
| trading-engine | 8005 |
| notification-service | 8006 |
| ml-prediction-service | 8007 (behind `ml` profile; off by default) |
| sentiment-analysis-service | 8008 (behind `analytics` profile; off by default) |
| risk-metrics-service | 8009 |
| Node Exporter / cAdvisor | 9100 / 8080 |
| Postgres / Redis exporters | 9187 / 9121 |

> ⚠️ Corrected 2026-07-30: the 2025-11-16 doc listed trading-engine on 8001, TA on 8003, portfolio on 8004, bybit on 8005, risk on 8006 — that ordering was wrong relative to the running stack. The table above matches the unified compose / repo `CLAUDE.md`.

Reload configuration without restart:

```bash
# Send reload signal (picks up new alert rules too)
curl -X POST http://localhost:9090/-/reload

# Or restart the service
docker compose -f docker-compose.unified.yml restart prometheus
```

### Grafana Configuration

- **Datasources**: auto-provisioned (Prometheus for metrics; Loki for logs and AlertManager where the extended stack is running)
- **Dashboards**: auto-loaded from the provisioning directory
- **Admin credentials**: see `.env`; **rotate the default**

Change the admin password:

```bash
# Method 1: Environment variable (compose)
GF_SECURITY_ADMIN_PASSWORD=<new-password>

# Method 2: Grafana CLI
docker exec -it crypto-bot-grafana grafana-cli admin reset-admin-password <new-password>
```

### Alerting Setup (5 Minutes)

#### Step 1: Create Telegram Bot (2 minutes)

1. Open Telegram and search for **@BotFather**
2. Send command: `/newbot`
3. Follow prompts to create your bot
4. **Copy the token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`) → `TELEGRAM_BOT_TOKEN`

#### Step 2: Get Gmail App Password (2 minutes)

1. Go to your Google Account settings
2. Enable **2-Factor Authentication** if not already enabled
3. Visit: https://myaccount.google.com/apppasswords
4. Create an **App-Specific Password** for "Mail"
5. **Copy the 16-character password** → `SMTP_PASSWORD`

#### Step 3: Run Setup Script (1 minute)

```bash
cd infrastructure/monitoring
./scripts/setup_alerting.sh
```

The script will:
- Ask for your Telegram bot token
- Ask for your Gmail credentials
- Generate a secure webhook token
- Create configuration files (`telegram-bot/.env`, `alertmanager/.env`)
- Start all services
- Help you get your Telegram chat ID

Manual alternative:

```bash
cp telegram-bot/.env.example telegram-bot/.env
nano telegram-bot/.env  # Add credentials
docker compose -f docker-compose.unified.yml up -d
```

#### Step 4: Test Everything

```bash
cd scripts
./test_alerts.sh all
```

Check:
- Your email inbox (and spam folder)
- Your Telegram app for notifications
- AlertManager UI: http://localhost:9093

### Kubernetes / Staging Variant (out of scope for v1.x)

> Date-stamped 2026-07-30: the following K8s-based deployment (Prometheus Operator + ServiceMonitors) was documented for a staging cluster. K8s is out of scope for v1.x; retained for a future K8s target.

Prerequisites: Kubernetes cluster with Prometheus Operator installed; `kubectl` configured; `jq` installed.

```bash
# Deploy everything
./deploy-monitoring.sh

# Dry run (preview changes)
./deploy-monitoring.sh --dry-run

# Custom namespace
./deploy-monitoring.sh --namespace custom-staging --monitoring-namespace monitoring
```

Manual dashboard import:

```bash
kubectl port-forward -n monitoring svc/grafana 3000:3000
# Then: Dashboards > Import > upload JSON files from grafana/dashboards/
# Select the Prometheus datasource when prompted
```

K8s-specific troubleshooting:
- Prometheus not scraping: check ServiceMonitor labels match service labels; verify namespace selectors; check RBAC permissions for the Prometheus service account
- Verify: `kubectl get servicemonitors`

---

## Dashboards

### Access

1. **Grafana**: http://localhost:3001 — credentials: see `.env`; rotate the default
2. **Prometheus UI**: http://localhost:9090 — no authentication by default (add auth for production, see [Security](#security))
3. **AlertManager**: http://localhost:9093 — view and manage active alerts

Grafana navigation:

```
Home → Dashboards → Crypto Trading Bot → Phase 3 AI Services
```

### Core Dashboards (compose stack, 2025-11-16)

1. **System Overview** — overall system health and performance
2. **Trading Performance** — trading metrics, P&L, positions
3. **Database Performance** — database and Redis metrics

### Phase 3 AI Services Dashboard (2025-11-11)

18 panels in 6 rows covering the ML/sentiment/risk services:

- **Row 1: Service Overview** — request rates for all Phase 3 services; service latency (p95) gauges
- **Row 2: ML Prediction Quality** — prediction accuracy trends; model inference performance; cache hit rate gauge
- **Row 3: Sentiment Analysis** — current market sentiment gauge; news fetch success rate; API latency gauge; sentiment score trends
- **Row 4: News Processing** — news articles processed per minute; news processing rate trends
- **Row 5: Risk Metrics** — portfolio risk percentage; VaR trends; Sharpe ratio gauge; Sortino ratio gauge; average position size; win rate percentage
- **Row 6: System Health** — error rates for all services; CPU and memory usage

> Note (2026-07-30): ML predictions and sentiment analysis are **disabled by default** (`ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`; services behind compose `ml` / `analytics` profiles). Rows 2–4 of this dashboard will show "No Data" unless those profiles are up.

### Staging Dashboard Suite (5 dashboards, K8s-era)

| Dashboard | UID | Shows |
|---|---|---|
| **Trading Performance** | `trading-performance-staging` | Total equity and equity curve; daily/weekly P&L; win rate, profit factor, Sharpe/Sortino; current and max drawdown; trade statistics by symbol; open positions count |
| **Risk Management** | `risk-metrics-dashboard` | P&L tracking with thresholds; position allocation pie chart; position size vs limits; correlation analysis; VaR (95%/99%) with limits; drawdown analysis; active risk alerts table |
| **Execution Quality** | `execution-quality-staging` | Execution latency (P50/P95/P99); fill rates by exchange; slippage analysis by symbol; order type distribution; maker vs taker ratio; TWAP/VWAP execution quality; smart router decisions |
| **Multi-Exchange** | `multi-exchange-staging` | WebSocket connection status per exchange; API latency and error rates; price comparison across exchanges; spread detection; arbitrage opportunity tracking; API rate limit usage; failover event history |
| **System Health** | `system-health-staging` | Pod CPU/memory; HPA scaling events and replica counts; request rates and response latency; PostgreSQL connection pool; Redis cache hit rates; RabbitMQ queue depths; error rates by service |

### Custom Dashboards

1. In Grafana, click "Create" → "Dashboard"
2. Add panels with PromQL queries
3. Save dashboard
4. Export the JSON into `infrastructure/monitoring/` (grafana dashboards dir) for version control

### Log Exploration (Loki)

1. Go to Grafana → Explore
2. Select "Loki" datasource
3. Enter a LogQL query
4. View logs with filtering and highlighting

```logql
# All logs from trading engine
{job="trading-engine"}

# Errors across all services
{level="error"}

# Logs for specific request ID
{request_id="abc-123"}

# Trading actions
{job="trading-engine", action=~"BUY|SELL"}

# Slow requests (>1s)
{job="api-gateway"} | json | duration_ms > 1000
```

---

## Alerting

Full guide: [`docs/operations/ALERTING_GUIDE.md`](../../docs/operations/ALERTING_GUIDE.md). Per-alert investigation steps: [`docs/operations/ALERT_RUNBOOKS.md`](../../docs/operations/ALERT_RUNBOOKS.md).

The production alerting system (2025-11-21) provides:

- **26 comprehensive alert rules** (`rules/trading-alerts.yml`) covering all critical scenarios
- **Email notifications** with professional HTML templates (`alertmanager/templates/email.tmpl`)
- **Telegram bot** for real-time mobile notifications (`telegram-bot/`)
- **Smart alert routing** by severity and component, with grouping and inhibition to prevent alert fatigue
- **Testing suite** (`scripts/test_alerts.sh`) and **interactive setup** (`scripts/setup_alerting.sh`)

### Severity Matrix

| Severity | Response Time | Channels | Repeat |
|----------|--------------|----------|--------|
| **CRITICAL** | 5-15 min | Email + Telegram | 1h |
| **WARNING** | 30-60 min | Email | 4-8h |
| **INFO** | 4-24 hours | Email (daily digest) | 24h |

AlertManager routing (extended stack): critical → PagerDuty + Slack; trading → Telegram; database → Slack `#database`; warnings → Slack `#warnings`.

### Critical Alerts (Immediate Action Required)

| Alert | Triggers When | What It Means / Action |
|-------|--------------|------------------------|
| **TradingEngineDown** (a.k.a. TradingEngineStopped) | Service down 30s (15s in staging rules) | Trading has stopped — check service logs, restart if needed |
| **DailyLossExceeded** | Daily loss > 5% | Daily loss circuit-breaker territory — review trades, consider emergency stop |
| **ServiceDown** | Any service down for 1m | Service outage |
| **HighErrorRate** | Error rate > 5% for 5m | System degradation |
| **DatabaseDown** | Database unreachable for 1m | Complete system failure — check database health, restore |
| **RiskLimitViolation** | Risk limits breached | Compliance issue |

### Warning Alerts (Investigation Needed — Email only)

- High API Latency (> 1 second, P99, 5m) — check database connections, cache hit rate
- High Memory Usage (> 1 GB)
- Circuit Breaker Triggered
- Low Win Rate (< 40%)
- Bybit Rate Limit Hit
- High Database Connections (> 180 for 5m) — check for connection leaks, increase pool size
- Low Cache Hit Rate
- Slow Database Queries (avg > 1s) — review slow query log, optimize indexes
- High Unrealized Loss
- Position Size Exceeded
- High Drawdown
- Container Restarted
- High File Descriptor Usage
- Prometheus Target Down

### Info Alerts (Awareness — daily email digest)

- High CPU Usage
- Low Disk Space
- Deployment Completed
- Backup Completed
- No Trades Executed
- Low Sharpe Ratio

### Phase 3 Alert Rules (`rules/phase3-alerts.yml`, 2025-11-11)

| Alert | Condition | Duration | Action |
|-------|-----------|----------|--------|
| MLPredictionServiceDown | Service unreachable | 1 minute | Check service logs |
| HighPortfolioRisk | Risk >5% | 5 minutes | Review open positions |
| LowMLPredictionAccuracy | Accuracy <70% | 5 minutes | Retrain model |
| HighMLInferenceLatency | p95 >500ms | 5 minutes | Optimize model |

Also configured: high error rates (>0.1 errors/sec) per Phase 3 service.

### Staging Alert Rules (`prometheus/alerts/*.yaml`, K8s-era)

**Trading (`trading-alerts.yaml`):**

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

**Exchange (`exchange-alerts.yaml`):**

| Alert | Severity | Condition | Description |
|-------|----------|-----------|-------------|
| BybitWebSocketDisconnected | critical | WS connected == 0 for 15s | No real-time data |
| WebSocketReconnectRateHigh | warning | > 3 reconnects in 5m | Connection instability |
| APIRateLimitApproaching | warning | Remaining < 100 | Approaching rate limit |
| APIRateLimitCritical | critical | Remaining < 20 | Rate limit nearly exhausted |
| MarketDataStale | warning | No update for > 30s | Stale price data |
| MarketDataCriticallyStale | critical | No update for > 60s | Critical data freshness issue |
| PrimaryExchangeFailover | warning | Failover active | Using backup exchange |

**System (`system-alerts.yaml`):**

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

### Alert States

- **Inactive**: condition not met
- **Pending**: condition met, waiting for duration
- **Firing**: alert is active and triggering

View: Prometheus http://localhost:9090/alerts, or Grafana → Alerting → Alert Rules.

### How Notifications Look

**Email** — color-coded severity, summary/description, recommended action steps, links to runbooks and Grafana, alert start time and instance details:

```
Subject: [FIRING] TradingEngineDown - Crypto Bot

CRITICAL ALERT
Trading Engine is down

Summary: Trading Engine has been down for 30 seconds
Description: No trades can be executed

Recommended Actions:
1. Check service logs: docker logs crypto-bot-trading
2. Verify database connectivity
3. Check Bybit API status
4. Restart service if needed

View Dashboard →
View Runbook →
```

**Telegram** — real-time mobile notification with severity emoji, component, summary/description, action, and quick links to Grafana/AlertManager.

### Testing Alerts

```bash
cd infrastructure/monitoring/scripts

./test_alerts.sh all          # Test everything (telegram, critical/warning/info email,
                              # trading, database, resolution notification)
./test_alerts.sh telegram     # Test Telegram only
./test_alerts.sh critical     # Test critical alert
./test_alerts.sh trading      # Test trading-specific alert
./test_alerts.sh resolution   # Test alert resolution

# Send custom test alert manually
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "MyTestAlert",
      "severity": "warning"
    },
    "annotations": {
      "summary": "This is a test alert"
    }
  }]'

# Trigger a real alert by stopping a service, then check after 1-2 min
docker stop crypto-bot-ml-prediction
curl http://localhost:9090/api/v1/alerts | jq
docker start crypto-bot-ml-prediction
```

### Alert Investigation Workflow

**1. Acknowledge**

```bash
# View alert details
curl http://localhost:9093/api/v1/alerts | jq '.[] | select(.labels.alertname=="AlertName")'

# Silence alert for 2 hours
curl -X POST http://localhost:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name": "alertname", "value": "AlertName"}],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "endsAt": "'$(date -u -d '+2 hours' +%Y-%m-%dT%H:%M:%SZ)'",
    "createdBy": "admin",
    "comment": "Under investigation"
  }'
```

**2. Investigate**

```bash
# Check service logs
docker logs --tail 100 crypto-bot-{service}

# Check service status
docker ps | grep crypto-bot-{service}

# Check metrics
curl "http://localhost:9090/api/v1/query?query=up{job='service'}"
```

**3. Resolve**

```bash
# Restart service
docker restart crypto-bot-{service}

# Verify recovery
curl http://localhost:{port}/health
```

Then follow the per-alert runbook: [`docs/operations/ALERT_RUNBOOKS.md`](../../docs/operations/ALERT_RUNBOOKS.md).

### Alert Response Guide (Phase 3 services)

| Alert | Immediate Action | Investigation |
|-------|------------------|---------------|
| MLPredictionServiceDown | Check service status, restart if needed | Review logs for errors |
| HighPortfolioRisk | Review open positions, consider reducing exposure | Check risk calculations |
| LowMLPredictionAccuracy | Switch to backup model | Analyze prediction errors, retrain |
| HighMLInferenceLatency | Check system resources | Optimize model, add caching |
| LowNewsFetchSuccessRate | Check API keys and rate limits | Review external API status |

### On-Call Escalation

| Time | Level | Action |
|------|-------|--------|
| 0-15 min | L1 | On-call engineer investigates |
| 15-60 min | L2 | Escalate to senior engineer |
| 60+ min | L3 | Escalate to architect |

### Contacts

| Issue Type | Contact | Method |
|------------|---------|--------|
| Service Down | On-call Engineer | PagerDuty / Phone |
| High Risk Alert | Trading Team Lead | Slack #trading-alerts |
| ML Model Issues | ML Team | Slack #ml-models |
| Infrastructure | DevOps Team | Slack #devops |

*(Solo-founder reality check, 2026-07-30: the team/rotation structure above is aspirational boilerplate from 2025-11; the operator is a single person. The tier-1 cron monitor in `scripts/monitoring/` plus Telegram notification is the actual escalation path.)*

---

## Key Metrics and PromQL

### Trading Metrics

| Metric | Type | Description |
|--------|------|-------------|
| portfolio_equity_usd | gauge | Total portfolio value |
| portfolio_value_gauge | gauge | Portfolio value (legacy name) |
| portfolio_daily_pnl_usd | gauge | Daily profit/loss |
| portfolio_daily_pnl_percentage | gauge | Daily P&L % |
| portfolio_drawdown_percentage | gauge | Current drawdown % |
| trades_executed_total | counter | Total trades executed |
| trades_winning_total / winning_trades_total | counter | Winning trades count |
| trade_execution_duration_seconds | histogram | Execution latency |
| active_positions_count / active_positions_gauge | gauge | Open positions |
| daily_loss_percentage | gauge | Daily P&L (alerting rules) |
| win_rate | gauge | Win rate % |

### Risk Metrics

| Metric | Type | Description |
|--------|------|-------------|
| position_size_percentage | gauge | Position as % of portfolio |
| portfolio_risk_exposure | gauge | Total risk exposure |
| portfolio_risk_percentage | gauge | Portfolio risk % (alert >5%) |
| portfolio_var_95 / value_at_risk_95 | gauge | Value at Risk (95%) |
| portfolio_var_99 | gauge | Value at Risk (99%) |
| sharpe_ratio | gauge | Risk-adjusted returns (alert <1.0) |
| trading_circuit_breaker_state | gauge | 0=normal, 1=triggered |

### Exchange Metrics

| Metric | Type | Description |
|--------|------|-------------|
| bybit_websocket_connected | gauge | WebSocket status |
| bybit_api_rate_limit_remaining | gauge | API calls remaining |
| market_data_last_update_timestamp | gauge | Last price update |
| order_slippage_percentage | gauge | Order slippage % |

### ML / Sentiment Metrics (Phase 3)

| Metric | Type | Description | Alert Threshold |
|--------|------|-------------|----------------|
| `ml_prediction_accuracy` | Gauge | Prediction accuracy (0-1) | <0.70 |
| `ml_model_inference_seconds` | Histogram | Model inference time | p95 >0.5s |
| `ml_cache_hits_total` | Counter | Cache hits | Hit rate <70% |
| `ml_prediction_errors_total` | Counter | Total errors | >0.1/sec |
| `sentiment_score` | Gauge | Current sentiment (-1 to 1) | <-0.7 or >0.7 |
| `sentiment_news_fetch_success_total` | Counter | Successful news fetches | Success rate <90% |
| `sentiment_api_latency_seconds` | Histogram | External API latency | p95 >1.0s |
| `sentiment_analysis_errors_total` | Counter | Total errors | >0.1/sec |

### System Metrics

| Metric | Type | Description |
|--------|------|-------------|
| container_cpu_usage_seconds_total | counter | Container CPU |
| container_memory_usage_bytes | gauge | Container memory |
| pg_stat_activity_count / pg_stat_database_numbackends | gauge | DB connections |
| redis_memory_used_bytes | gauge | Redis memory |
| rabbitmq_queue_messages | gauge | Queue depth |
| process_resident_memory_bytes | gauge | Service memory usage |

### Essential PromQL Queries

```promql
# Service uptime
up{job=~"ml-prediction-service|sentiment-analysis-service|risk-metrics-service"}

# Request rate (req/sec)
rate(http_requests_total[5m])

# Request latency (P99)
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Service latency p95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Error rate (HTTP 5xx)
rate(http_requests_total{status_code=~"5.."}[5m])

# Generic error rate
rate(service_errors_total[5m])

# Trade execution latency (P99)
histogram_quantile(0.99, rate(trade_execution_duration_seconds_bucket[5m]))

# ML prediction accuracy
avg(ml_prediction_accuracy) * 100

# ML prediction rate
rate(ml_prediction_requests_total[5m])

# Current sentiment score
avg(sentiment_score)

# Portfolio risk
portfolio_risk_percentage

# Cache hit rate (application)
cache_hits_total / (cache_hits_total + cache_misses_total)

# Postgres cache hit ratio
pg_stat_database_blks_hit / (pg_stat_database_blks_hit + pg_stat_database_blks_read)

# Postgres query performance
rate(pg_stat_statements_mean_exec_time[5m])

# Postgres replication lag
pg_replication_lag_seconds

# Host CPU usage
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Host memory usage
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Host disk space available
(node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100

# Service memory (MB)
process_resident_memory_bytes / 1024 / 1024

# Currently firing alerts
ALERTS{alertstate="firing"}
```

### Critical Metric Thresholds

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| ML Accuracy | >80% | 70-80% | <70% |
| Inference Latency | <100ms | 100-500ms | >500ms |
| Cache Hit Rate | >85% | 70-85% | <70% |
| Sentiment API Latency | <500ms | 500-1000ms | >1000ms |
| News Fetch Success | >95% | 90-95% | <90% |
| Portfolio Risk | <3% | 3-5% | >5% |
| Drawdown | <5% | 5-10% | >10% |
| Win Rate | >55% | 50-55% | <50% |

---

## Quick Commands

### Quick Access URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana Dashboard | http://localhost:3001 | see `.env`; rotate the default |
| Prometheus UI | http://localhost:9090 | None (add auth for production) |
| AlertManager | http://localhost:9093 | None (add auth for production) |
| Prometheus Alerts | http://localhost:9090/alerts | None |
| ML Prediction Metrics | http://localhost:8007/metrics | None (requires `ml` profile up) |
| Sentiment Metrics | http://localhost:8008/metrics | None (requires `analytics` profile up) |
| Risk Metrics | http://localhost:8009/metrics | None |

### Stack Management

```bash
# Start / stop stack (from repo root)
docker compose -f docker-compose.unified.yml up -d
docker compose -f docker-compose.unified.yml down

# Restart monitoring services
docker compose -f docker-compose.unified.yml restart prometheus grafana

# Restart alerting components
docker restart crypto-bot-alertmanager
docker restart crypto-bot-telegram-alerts

# Check service health
docker compose -f docker-compose.unified.yml ps prometheus grafana

# View all monitoring containers
docker ps | grep -E "prometheus|grafana|alertmanager"

# View container logs
docker logs -f crypto-bot-prometheus
docker logs -f crypto-bot-grafana
docker logs -f crypto-bot-alertmanager
docker logs crypto-bot-telegram-alerts

# Execute commands in container
docker exec -it crypto-bot-prometheus sh
docker exec -it crypto-bot-grafana sh
```

### Status Checks

```bash
# Check if Prometheus is scraping
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Unhealthy targets only
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health!="up")'

# Test metrics endpoints
curl http://localhost:8007/metrics | grep ml_prediction
curl http://localhost:8008/metrics | grep sentiment
curl http://localhost:8009/metrics | grep risk

# Reload Prometheus config
curl -X POST http://localhost:9090/-/reload

# View active alerts (Prometheus)
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[]'

# View active alerts (AlertManager)
curl http://localhost:9093/api/v1/alerts | jq

# Firing alerts only
curl -s http://localhost:9093/api/v1/alerts | jq '.data[] | select(.state=="firing")'

# Prometheus rules
curl http://localhost:9090/api/v1/rules | jq

# Telegram bot health / chat ID / test  (verify actual bot port — see port note at top)
curl http://localhost:8007/health
curl http://localhost:8007/get-chat-id
curl -X POST http://localhost:8007/test
```

### Daily Operations

```bash
# Morning check: overnight alerts
curl http://localhost:9093/api/v1/alerts | jq '.[] | select(.status.state=="active")'

# Morning check: service health
docker compose -f docker-compose.unified.yml ps
```

### Maintenance Schedule

| Task | Frequency | Command / Where |
|------|-----------|-----------------|
| Check dashboards | Daily | Open Grafana, review dashboards |
| Review alerts | Daily | Prometheus alerts page / AlertManager |
| Check Prometheus targets | Daily | `curl -s localhost:9090/api/v1/targets \| jq ...` |
| Check disk space | Weekly | `df -h` and check Prometheus volume |
| Backup metrics | Weekly | Run backup script (see Backup) |
| Review alert frequency / false positives | Weekly | `ALERTS{alertstate="firing"}` + Grafana |
| Review dashboard usage | Weekly | Grafana → Server Admin → Stats |
| Update alert rules | As needed | Edit rules, then `curl -X POST localhost:9090/-/reload` |
| Update services | Monthly | `docker compose pull` and restart |
| Tune thresholds | Monthly | Based on actual metrics |
| Review retention | Monthly | Adjust if storage is an issue |
| Update runbooks | Quarterly | `docs/operations/ALERT_RUNBOOKS.md` |
| Track MTTA/MTTR | Ongoing | Mean Time To Acknowledge / Resolve |

---

## Emergency Procedures

> Canonical emergency stop (2026-07-30): `touch safety/EMERGENCY_STOP` (kill-switch file) or `POST /api/portfolio/emergency-stop` (admin-guarded). See repo root `RUNBOOK.md`. The commands below are the older container-level fallbacks.

### Stop All Trading (Risk Too High)

```bash
# Check current risk
curl http://localhost:8009/api/portfolio/risk | jq

# Preferred: kill-switch file
touch safety/EMERGENCY_STOP

# Fallback: stop the trading-engine container
docker stop crypto-bot-trading-engine

# Review positions (portfolio-manager, port 8003)
curl http://localhost:8003/api/positions | jq
```

> Note: the 2025-11 quick reference used `docker stop crypto-bot-trading` — verify the actual container name with `docker ps | grep trading`.

### Rollback to Previous ML Model

```bash
docker exec crypto-bot-ml-prediction \
  cp /app/models/backup/model.h5 /app/models/active/model.h5

docker restart crypto-bot-ml-prediction
```

### Clear Cache (Performance Issues)

```bash
# Redis cache clear (if used)
docker exec crypto-bot-redis redis-cli FLUSHALL

# Restart services
docker compose -f docker-compose.unified.yml restart ml-prediction sentiment-analysis
```

### Destroy Monitoring Data (DESTRUCTIVE!)

```bash
# Removes monitoring containers AND their volumes
docker compose -f docker-compose.unified.yml down -v   # affects ALL stack volumes — be sure
```

---

## Troubleshooting

### Prometheus Not Scraping Metrics

**Symptom**: no data in Grafana, targets show as "DOWN" in Prometheus.

```bash
# 1. Check if services are running
docker ps | grep -E "ml-prediction|sentiment|risk-metrics"

# 2. Verify services expose /metrics
curl http://localhost:8000/metrics
curl http://localhost:8007/metrics
curl http://localhost:8008/metrics
curl http://localhost:8009/metrics

# 3. Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq

# 4. Check Prometheus logs
docker logs crypto-bot-prometheus

# 5. Verify network connectivity from inside the Prometheus container
docker exec crypto-bot-prometheus wget -O- http://api-gateway:8000/metrics
```

### Grafana Shows "No Data" / Dashboards Not Loading

```bash
# Verify Prometheus datasource is configured (Configuration → Data Sources; test connection)
curl http://localhost:3001/api/datasources

# Check metrics exist in Prometheus: run `up{job="ml-prediction-service"}` at :9090

# Verify metric names match dashboard queries (Edit panel → View query)

# Check the time range covers when services were running (try "Last 6 hours")

# Check dashboard provisioning
docker exec crypto-bot-grafana ls -la /var/lib/grafana/dashboards/

# Reset admin password if locked out
docker exec crypto-bot-grafana grafana-cli admin reset-admin-password <new-password>

# Reload Grafana
docker restart crypto-bot-grafana
```

### Alerts Not Firing

```bash
# 1. Validate alert rule syntax
docker exec crypto-bot-prometheus promtool check rules \
  /etc/prometheus/rules/trading-alerts.yml

# 2. Reload Prometheus (rules changes need reload)
curl -X POST http://localhost:9090/-/reload

# 3. Check the metric exists
curl "http://localhost:9090/api/v1/query?query=up{job='trading-engine'}"

# 4. View alert status
curl http://localhost:9090/api/v1/alerts | jq

# 5. Check AlertManager config
docker exec crypto-bot-alertmanager amtool check-config /etc/alertmanager/alertmanager.yml

# 6. Test alert routing
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"TestAlert","severity":"warning"}}]'
```

### No Emails Received

Possible causes: regular Gmail password used instead of App-Specific Password; 2FA not enabled; emails in spam; wrong SMTP credentials.

```bash
# 1. Check credentials are loaded
docker exec crypto-bot-alertmanager env | grep SMTP

# 2. Check AlertManager logs
docker logs crypto-bot-alertmanager | grep -i email

# 3. Verify you're using a 16-character App-Specific Password
#    (generate at https://myaccount.google.com/apppasswords)

# 4. Test AlertManager health
curl http://alertmanager:9093/-/healthy
```

### No Telegram Notifications

Possible causes: wrong bot token; wrong chat ID; bot not started; webhook token mismatch.

```bash
# 1. Test bot token directly
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"

# 2. Get your chat ID / test the relay (verify bot port — see port note at top)
curl http://localhost:8007/get-chat-id
curl -X POST http://localhost:8007/test

# 3. Check bot logs and that it's running
docker logs crypto-bot-telegram-alerts
docker ps | grep telegram
```

### Loki Not Receiving Logs

```bash
# Check Promtail status
docker logs crypto-bot-promtail

# Verify log files exist
docker exec crypto-bot-promtail ls -la /services/*/logs/

# Test Loki query
curl -G 'http://localhost:3100/loki/api/v1/query' --data-urlencode 'query={job="trading-engine"}'
```

### Metrics Not Updating (stuck at old values)

```bash
# 1. Check service is recording metrics
grep -r "prometheus" services/ml-prediction-service/app/

# 2. Watch the metrics endpoint for changes
watch -n 1 "curl -s http://localhost:8007/metrics | grep ml_prediction"

# 3. Check for exceptions in service logs
docker logs crypto-bot-ml-prediction | grep -i error
docker logs crypto-bot-ml-prediction | tail -50
```

### High Memory Usage (Prometheus/Grafana)

```bash
# Check container stats
docker stats crypto-bot-prometheus crypto-bot-grafana
```

1. Reduce Prometheus retention (compose `command:` flag): `--storage.tsdb.retention.time=7d`
2. Reduce scrape frequency in `prometheus.yml`: `scrape_interval: 30s`
3. Reduce metric cardinality — avoid high-cardinality labels (user IDs, timestamps); limit unique label combinations
4. Restart if needed: `docker compose -f docker-compose.unified.yml restart prometheus`

### Service Down

```bash
docker ps -a | grep crypto-bot
docker restart crypto-bot-ml-prediction
```

---

## Maintenance, Backup, Performance

### Backup

```bash
# Backup Prometheus data
docker run --rm -v crypto-bot-prometheus-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/prometheus-backup-$(date +%Y%m%d).tar.gz /data

# Restore Prometheus data
docker run --rm -v crypto-bot-prometheus-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/prometheus-backup.tar.gz -C /

# Backup AlertManager data
docker run --rm -v alertmanager-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/alertmanager-backup.tar.gz /data

# Backup Grafana dashboards via CLI
docker exec crypto-bot-grafana grafana-cli admin export-dashboard > grafana-backup.json

# Export a dashboard via API
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:3001/api/dashboards/uid/crypto-bot-phase3 > dashboard-backup.json

# Import a dashboard via API
curl -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d @dashboard-backup.json \
  http://localhost:3001/api/dashboards/db
```

> Note: volume names differ between compose generations (`prometheus-data` vs `crypto-bot-prometheus-data`). Check `docker volume ls` for the actual names.

### Performance Tuning

**Prometheus:**

- Adjust scrape interval in `prometheus.yml`
- Configure retention: `--storage.tsdb.retention.time=30d` (or `7d`/`15d` if storage-bound)
- Limit storage size: `--storage.tsdb.retention.size=10GB`
- Block durations: `--storage.tsdb.min-block-duration=2h`, `--storage.tsdb.max-block-duration=2h`
- Enable remote write for long-term storage
- Use recording rules (`prometheus/recording-rules.yml`) for frequently used queries

**Grafana:**

- Enable caching; limit dashboard refresh rate; optimize queries via recording rules
- Use an external DB instead of SQLite for heavy use:

```yaml
# compose environment:
- GF_DATABASE_TYPE=postgres
- GF_DATABASE_HOST=postgres:5432
- GF_DATABASE_NAME=grafana
```

**Loki:**

- Adjust retention period in `loki-config.yml` (default 30 days)
- Configure compression; use appropriate index period

**Metric cardinality (in service code):**

```python
# Bad: High cardinality
request_counter.labels(user_id=user.id).inc()

# Good: Low cardinality
request_counter.labels(user_type=user.type).inc()
```

---

## Security

1. **Change default passwords** — Grafana admin credentials: see `.env`; rotate the default:
   ```bash
   docker exec crypto-bot-grafana grafana-cli admin reset-admin-password <new-strong-password>
   # or set GF_SECURITY_ADMIN_PASSWORD in the compose environment
   ```

2. **Enable HTTPS** — reverse proxy (nginx/Traefik) with Let's Encrypt, or direct Grafana TLS:
   ```yaml
   environment:
     - GF_SERVER_PROTOCOL=https
     - GF_SERVER_CERT_FILE=/etc/grafana/grafana.crt
     - GF_SERVER_CERT_KEY=/etc/grafana/grafana.key
   volumes:
     - ./certs/grafana.crt:/etc/grafana/grafana.crt
     - ./certs/grafana.key:/etc/grafana/grafana.key
   ```

3. **Restrict network access** — bind to localhost only:
   ```yaml
   ports:
     - "127.0.0.1:3001:3000"  # Only localhost can access Grafana
   ```
   Or isolate with Docker networks:
   ```yaml
   networks:
     monitoring:
       internal: true  # No external access
     crypto-bot-network:
       external: true
   ```

4. **Enable authentication**
   - Grafana: built-in auth or LDAP/OAuth
   - Prometheus: reverse proxy with basic auth, e.g.:
     ```yaml
     nginx-prometheus:
       image: nginx:alpine
       volumes:
         - ./nginx-prometheus.conf:/etc/nginx/nginx.conf
         - ./htpasswd:/etc/nginx/.htpasswd
       ports:
         - "9090:80"
     ```
   - AlertManager: basic auth or OAuth2 proxy

5. **Credential files** — `telegram-bot/.env` and `alertmanager/.env` contain live secrets; never commit them to git (repo `.gitignore` covers `.env`).

---

## Checklists

### Production Monitoring Checklist

- [ ] Change Grafana admin password (rotate the default; see `.env`)
- [ ] Enable Prometheus authentication
- [ ] Configure HTTPS for Grafana
- [ ] Set up Alertmanager with Slack/email
- [ ] Configure alert rules for all critical metrics
- [ ] Set up automated backups
- [ ] Document runbooks for common alerts (`docs/operations/ALERT_RUNBOOKS.md`)
- [ ] Test disaster recovery procedures
- [ ] Configure log aggregation (Loki)
- [ ] Set up metric-based autoscaling (K8s only — out of scope for v1.x)
- [ ] Create operational dashboards for on-call
- [ ] Configure retention policies based on storage

### Alerting Deployment Checklist

- [ ] Telegram bot created and tested
- [ ] Gmail App-Specific Password configured
- [ ] All test alerts pass (`./scripts/test_alerts.sh all`)
- [ ] Email notifications received (check inbox/spam)
- [ ] Telegram notifications received
- [ ] Alert thresholds reviewed and tuned
- [ ] Runbooks accessible (`docs/operations/ALERT_RUNBOOKS.md`)
- [ ] Escalation procedures documented
- [ ] On-call rotation configured (if using PagerDuty)

### Post-Deployment Verification

- [ ] Prometheus targets are UP (`/targets` page)
- [ ] Alert rules are loaded (`/rules` page)
- [ ] Grafana datasource is working
- [ ] Dashboards are imported/provisioned
- [ ] Test alert fires and routes correctly
- [ ] Notification channels are configured
- [ ] (K8s only) ServiceMonitors are created (`kubectl get servicemonitors`)

### Alerting Testing Checklist

- [ ] Telegram bot responds: `./test_alerts.sh telegram`
- [ ] Email received: check inbox/spam
- [ ] Critical alerts work: `./test_alerts.sh critical`
- [ ] Trading alerts work: `./test_alerts.sh trading`
- [ ] Resolution works: `./test_alerts.sh resolution`
- [ ] All tests pass: `./test_alerts.sh all`

---

## Related Documentation

### Living operator guides (canonical, in `docs/operations/`)

| Guide | Purpose |
|---|---|
| [`docs/operations/MONITORING_GUIDE.md`](../../docs/operations/MONITORING_GUIDE.md) | Full metrics catalog, dashboards, alerting rules, best practices |
| [`docs/operations/ALERTING_GUIDE.md`](../../docs/operations/ALERTING_GUIDE.md) | Complete alerting system documentation and configuration |
| [`docs/operations/ALERT_RUNBOOKS.md`](../../docs/operations/ALERT_RUNBOOKS.md) | Per-alert investigation and resolution procedures |
| [`docs/operations/RUNBOOK.md`](../../docs/operations/RUNBOOK.md) | General operations runbook |

### In this directory

- [`PROMETHEUS_INSTRUMENTATION_GUIDE.md`](./PROMETHEUS_INSTRUMENTATION_GUIDE.md) — adding Prometheus metrics to services (kept as a separate document)

### Elsewhere in the repo

- `scripts/monitoring/` — **Tier-1 cron health monitor** (15-min cadence; curl health checks, Prometheus alert scrape, price-divergence check, notification cadence check; notify-only). See `scripts/monitoring/README.md` and ADR-026 (`wiki/decisions/ADR-026-monitoring-disposition.md`) — the autonomous tier-2 escalation path was deliberately deleted 2026-05-13.
- `docker-compose.unified.yml` (repo root) — canonical compose file including Prometheus and Grafana.

### External resources

- [Prometheus Documentation](https://prometheus.io/docs/) · [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Documentation](https://grafana.com/docs/) · [Grafana Community Forum](https://community.grafana.com/)
- [Loki Documentation](https://grafana.com/docs/loki/)
- [AlertManager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/) · [AlertManager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Prometheus Alerting Docs](https://prometheus.io/docs/alerting/latest/overview/)
- [Prometheus Operator](https://prometheus-operator.dev/) (K8s-era)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [Prometheus Slack](https://slack.prometheus.io/)

---

**Last consolidated:** 2026-07-30 (sources dated 2025-11-11 → 2025-11-21)
