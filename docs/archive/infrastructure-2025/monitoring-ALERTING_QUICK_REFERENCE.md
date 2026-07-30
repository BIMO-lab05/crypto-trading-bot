# Alerting System - Quick Reference Card

**Version:** 1.0 | **Date:** 2025-11-21

---

## Setup Commands (One-Time)

```bash
# Navigate to monitoring directory
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring

# Run interactive setup
./scripts/setup_alerting.sh

# OR manual setup:
cp telegram-bot/.env.example telegram-bot/.env
nano telegram-bot/.env  # Add credentials
docker-compose -f docker-compose.monitoring.yml up -d
```

---

## Quick Start

### 1. Create Telegram Bot
```
1. Open Telegram → Search @BotFather
2. Send: /newbot
3. Copy token → TELEGRAM_BOT_TOKEN
```

### 2. Get Gmail App Password
```
1. Enable 2FA in Google Account
2. Visit: https://myaccount.google.com/apppasswords
3. Create password for "Mail"
4. Copy → SMTP_PASSWORD
```

### 3. Test System
```bash
cd scripts
./test_alerts.sh all
```

---

## Essential URLs

| Service | URL | Purpose |
|---------|-----|---------|
| AlertManager | http://localhost:9093 | View/manage alerts |
| Prometheus Alerts | http://localhost:9090/alerts | Alert rules status |
| Telegram Bot Health | http://localhost:8007/health | Bot status |
| Grafana | http://localhost:3000 | Dashboards |

---

## Alert Severity Matrix

| Severity | Response Time | Channels | Repeat |
|----------|--------------|----------|--------|
| **CRITICAL** | 5-15 min | Email + Telegram | 1h |
| **WARNING** | 30-60 min | Email | 4-8h |
| **INFO** | 4-24 hours | Email (daily) | 24h |

---

## Critical Alerts (Top 6)

| Alert | Trigger | Impact |
|-------|---------|--------|
| TradingEngineDown | Down 30s | No trading |
| DailyLossExceeded | Loss > 5% | Financial risk |
| ServiceDown | Down 1m | Service offline |
| HighErrorRate | Errors > 5% | Degradation |
| DatabaseDown | Down 1m | System failure |
| RiskLimitViolation | Limit breach | Compliance |

---

## Common Commands

### Test Alerts
```bash
./test_alerts.sh all              # Test everything
./test_alerts.sh telegram         # Test Telegram only
./test_alerts.sh critical         # Test critical alert
```

### View Alerts
```bash
# Active alerts
curl http://localhost:9093/api/v1/alerts | jq

# Prometheus rules
curl http://localhost:9090/api/v1/rules | jq

# Telegram bot health
curl http://localhost:8007/health
```

### Manage Services
```bash
# Start all
docker-compose -f docker-compose.monitoring.yml up -d

# Restart AlertManager
docker restart crypto-bot-alertmanager

# Restart Telegram bot
docker restart crypto-bot-telegram-alerts

# View logs
docker logs crypto-bot-alertmanager
docker logs crypto-bot-telegram-alerts
```

### Reload Configuration
```bash
# Reload Prometheus (picks up new alert rules)
curl -X POST http://localhost:9090/-/reload

# Restart AlertManager (for config changes)
docker restart crypto-bot-alertmanager
```

---

## Troubleshooting Quick Fixes

### No Emails?
```bash
# 1. Check credentials
docker exec crypto-bot-alertmanager env | grep SMTP

# 2. View logs
docker logs crypto-bot-alertmanager | grep -i email

# 3. Verify app password (not regular password!)
```

### No Telegram?
```bash
# 1. Test bot
curl -X POST http://localhost:8007/test

# 2. Get chat ID
curl http://localhost:8007/get-chat-id

# 3. Check token
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
```

### Alerts Not Firing?
```bash
# 1. Check rule syntax
docker exec crypto-bot-prometheus promtool check rules \
  /etc/prometheus/rules/trading-alerts.yml

# 2. Reload Prometheus
curl -X POST http://localhost:9090/-/reload

# 3. Check metric exists
curl "http://localhost:9090/api/v1/query?query=up"
```

---

## Alert Investigation Steps

### 1. Acknowledge
```bash
# View alert details
curl http://localhost:9093/api/v1/alerts | jq '.[] | select(.labels.alertname=="AlertName")'

# Silence alert (2 hours)
curl -X POST http://localhost:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{"matchers":[{"name":"alertname","value":"AlertName"}],"endsAt":"'$(date -u -d '+2 hours' +%Y-%m-%dT%H:%M:%SZ)'"}'
```

### 2. Investigate
```bash
# Check service logs
docker logs --tail 100 crypto-bot-{service}

# Check service status
docker ps | grep crypto-bot-{service}

# Check metrics
curl "http://localhost:9090/api/v1/query?query=up{job='service'}"
```

### 3. Resolve
```bash
# Restart service
docker restart crypto-bot-{service}

# Verify recovery
curl http://localhost:{port}/health
```

---

## File Locations

```
infrastructure/monitoring/
├── alertmanager/
│   ├── alertmanager.yml          # Main config
│   └── templates/email.tmpl      # Email template
├── telegram-bot/
│   ├── telegram_alerts.py        # Bot code
│   └── .env                      # Bot config
├── rules/
│   └── trading-alerts.yml        # 26 alert rules
└── scripts/
    ├── setup_alerting.sh         # Setup wizard
    └── test_alerts.sh            # Test suite

docs/operations/
├── ALERTING_GUIDE.md             # Full guide
└── ALERT_RUNBOOKS.md             # Investigation steps
```

---

## Environment Variables

### Required
```bash
TELEGRAM_BOT_TOKEN=123456789:ABC...  # From @BotFather
TELEGRAM_CHAT_ID=987654321           # From /get-chat-id
SMTP_USERNAME=your-email@gmail.com   # Gmail address
SMTP_PASSWORD=app-password           # 16-char app password
ALERT_EMAIL=alerts@domain.com        # Recipient
WEBHOOK_TOKEN=secure-random-token    # Generate with setup script
```

### Optional
```bash
SLACK_WEBHOOK_URL=https://...        # Slack integration
PAGERDUTY_SERVICE_KEY=key            # PagerDuty integration
```

---

## Key Metrics to Monitor

### Trading
```promql
daily_loss_percentage              # Daily P&L
win_rate                           # Win rate %
active_positions                   # Open positions
trade_executions_total             # Total trades
```

### System
```promql
up{job="service"}                  # Service health
http_requests_total                # Request count
http_request_duration_seconds      # Latency
process_resident_memory_bytes      # Memory usage
```

### Database
```promql
pg_stat_database_numbackends       # Connections
pg_stat_database_blks_hit          # Cache hits
```

---

## On-Call Escalation

| Time | Level | Action |
|------|-------|--------|
| 0-15 min | L1 | On-call engineer investigates |
| 15-60 min | L2 | Escalate to senior engineer |
| 60+ min | L3 | Escalate to architect |

---

## Contact Information

- **Alerts Email:** alerts@cryptobot.com
- **On-Call:** See PagerDuty rotation
- **Documentation:** /docs/operations/ALERTING_GUIDE.md
- **Runbooks:** /docs/operations/ALERT_RUNBOOKS.md

---

## Testing Checklist

- [ ] Telegram bot responds: `./test_alerts.sh telegram`
- [ ] Email received: Check inbox/spam
- [ ] Critical alerts work: `./test_alerts.sh critical`
- [ ] Trading alerts work: `./test_alerts.sh trading`
- [ ] Resolution works: `./test_alerts.sh resolution`
- [ ] All tests pass: `./test_alerts.sh all`

---

## Daily Operations

### Morning Check
```bash
# View overnight alerts
curl http://localhost:9093/api/v1/alerts | jq '.[] | select(.status.state=="active")'

# Check service health
docker-compose -f docker-compose.monitoring.yml ps
```

### Weekly Review
```bash
# Alert frequency
curl http://localhost:9090/api/v1/query \
  --data-urlencode 'query=ALERTS{alertstate="firing"}'

# False positive rate
# Review in Grafana dashboard
```

---

**Print this page and keep it handy for quick reference!**

**Last Updated:** 2025-11-21 | **Version:** 1.0
