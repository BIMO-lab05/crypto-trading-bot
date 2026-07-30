# Production-Grade Alerting System - Setup Complete

**Date:** 2025-11-21
**Status:** Ready for Deployment
**Version:** 1.0

---

## What Was Configured

A complete production-grade alerting system with email and Telegram notifications for the Crypto Trading Bot monitoring infrastructure.

### Components Delivered

1. **Alert Rules** (26 comprehensive alerts)
   - `/infrastructure/monitoring/rules/trading-alerts.yml`
   - Critical, Warning, and Info alert categories
   - Trading-specific, database, system, and risk alerts

2. **AlertManager Configuration**
   - `/infrastructure/monitoring/alertmanager/alertmanager.yml`
   - Smart alert routing based on severity and component
   - Alert grouping and inhibition rules
   - Multiple receiver configurations

3. **Email Notification System**
   - HTML and text email templates
   - `/infrastructure/monitoring/alertmanager/templates/email.tmpl`
   - Rich formatting with severity indicators
   - Embedded runbook links and action items

4. **Telegram Bot Integration**
   - `/infrastructure/monitoring/telegram-bot/telegram_alerts.py`
   - Real-time mobile notifications
   - FastAPI webhook receiver
   - Rich HTML formatting for Telegram

5. **Documentation**
   - `/docs/operations/ALERTING_GUIDE.md` - Complete guide
   - `/docs/operations/ALERT_RUNBOOKS.md` - Investigation procedures
   - Updated `/docs/MONITORING_GUIDE.md` with alerting rules

6. **Testing & Setup Scripts**
   - `/infrastructure/monitoring/scripts/test_alerts.sh` - Test suite
   - `/infrastructure/monitoring/scripts/setup_alerting.sh` - Interactive setup

---

## Alert Categories Summary

### CRITICAL Alerts (6 rules)

Require immediate action within 5-15 minutes:

| Alert | Condition | Notification |
|-------|-----------|-------------|
| TradingEngineDown | Service down for 30s | Email + Telegram |
| DailyLossExceeded | Daily loss > 5% | Email + Telegram |
| ServiceDown | Any service down for 1m | Email + Telegram |
| HighErrorRate | Error rate > 5% for 5m | Email + Telegram |
| DatabaseDown | Database unreachable for 1m | Email + Telegram |
| RiskLimitViolation | Risk limit breached | Email + Telegram |

**Repeat Interval:** 1 hour

### WARNING Alerts (14 rules)

Require investigation within 30-60 minutes:

- HighAPILatency
- HighMemoryUsage
- CircuitBreakerOpen
- LowWinRate
- BybitRateLimitHit
- HighDatabaseConnections
- LowCacheHitRate
- SlowDatabaseQueries
- HighUnrealizedLoss
- PositionSizeExceeded
- HighDrawdown
- ContainerRestarted
- HighFileDescriptorUsage
- PrometheusTargetDown

**Repeat Interval:** 4-8 hours
**Notification:** Email only

### INFO Alerts (6 rules)

Awareness notifications, grouped into daily summaries:

- HighCPUUsage
- LowDiskSpace
- DeploymentCompleted
- BackupCompleted
- NoTradesExecuted
- LowSharpeRatio

**Repeat Interval:** 24 hours
**Notification:** Email (daily digest)

---

## Notification Channels

### Email (All Alerts)

- **Protocol:** SMTP (Gmail)
- **Format:** HTML + Plain Text
- **Features:**
  - Color-coded severity indicators
  - Embedded action items
  - Links to dashboards and runbooks
  - Firing and resolved notifications
  - Alert statistics

### Telegram (Critical + Trading Alerts)

- **Method:** Webhook via FastAPI bot
- **Format:** HTML with emoji indicators
- **Features:**
  - Real-time mobile notifications
  - Rich formatting
  - Clickable dashboard links
  - Alert grouping
  - Resolution notifications

### Slack (Optional)

- Pre-configured receivers for:
  - #crypto-bot-critical
  - #crypto-bot-database
  - #crypto-bot-warnings

### PagerDuty (Optional)

- Ready for on-call escalation
- Requires service key configuration

---

## Alert Routing Configuration

### Routing Logic

```
Prometheus Alert → AlertManager Router
                    ├─→ severity: critical → Email + Telegram
                    ├─→ component: trading → Telegram + Email
                    ├─→ component: database → Email (database team)
                    ├─→ severity: warning → Email
                    └─→ severity: info → Email (daily summary)
```

### Alert Inhibition

Intelligent suppression of redundant alerts:

- Warning alerts suppressed when critical alert fires for same service
- Info alerts suppressed when warning or critical fires
- High latency alerts suppressed when service is down
- Memory alerts suppressed for 10 minutes after container restart

### Alert Grouping

Alerts grouped by:
- `alertname` - Same type of alert
- `severity` - Critical, warning, or info
- `component` - Service component

**Grouping Intervals:**
- Wait 10s before sending first notification (allows grouping)
- Wait 5m before sending updates on existing group
- Wait 4h before repeating same notification

---

## File Structure

```
infrastructure/monitoring/
├── alertmanager/
│   ├── alertmanager.yml                 # Main AlertManager config
│   ├── templates/
│   │   └── email.tmpl                   # Email notification template
│   └── .env                             # Environment variables (created by setup)
├── telegram-bot/
│   ├── telegram_alerts.py               # Telegram bot application
│   ├── requirements.txt                 # Python dependencies
│   ├── Dockerfile                       # Container build file
│   ├── .env                             # Bot configuration (created by setup)
│   └── .env.example                     # Example configuration
├── prometheus/
│   └── prometheus.yml                   # Updated with rule files
├── rules/
│   ├── trading-alerts.yml               # 26 trading bot alerts
│   └── phase3-alerts.yml                # Phase 3 service alerts
└── scripts/
    ├── setup_alerting.sh                # Interactive setup script
    └── test_alerts.sh                   # Comprehensive test suite

docs/operations/
├── ALERTING_GUIDE.md                    # Complete alerting documentation
└── ALERT_RUNBOOKS.md                    # Alert investigation procedures
```

---

## Quick Start Guide

### 1. Initial Setup

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring

# Run interactive setup (recommended)
./scripts/setup_alerting.sh
```

This will guide you through:
- Creating Telegram bot
- Configuring email SMTP
- Getting Telegram chat ID
- Generating secure webhook token
- Starting all services

### 2. Manual Setup (Alternative)

```bash
# Copy example configuration
cp telegram-bot/.env.example telegram-bot/.env

# Edit with your credentials
nano telegram-bot/.env

# Required variables:
# - TELEGRAM_BOT_TOKEN (from @BotFather)
# - TELEGRAM_CHAT_ID (your chat ID)
# - SMTP_USERNAME (Gmail address)
# - SMTP_PASSWORD (App-Specific Password)
# - ALERT_EMAIL (recipient email)

# Start services
docker-compose -f docker-compose.monitoring.yml up -d
```

### 3. Test Alerts

```bash
cd scripts

# Test all notification channels
./test_alerts.sh all

# Test specific alert types
./test_alerts.sh telegram      # Telegram bot only
./test_alerts.sh critical      # Critical alert
./test_alerts.sh trading       # Trading alert
./test_alerts.sh resolution    # Alert resolution
```

### 4. Verify Setup

Check that you received notifications:
- Email in your inbox (check spam folder)
- Telegram message on your phone
- Alerts visible in AlertManager: http://localhost:9093

---

## Configuration Details

### Telegram Bot Setup

1. **Create Bot:**
   - Open Telegram, search for @BotFather
   - Send `/newbot` and follow prompts
   - Copy token: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

2. **Get Chat ID:**
   ```bash
   # Send a message to your bot
   # Then run:
   curl http://localhost:8007/get-chat-id
   ```

3. **Test Bot:**
   ```bash
   curl -X POST http://localhost:8007/test
   ```

### Email (Gmail) Setup

1. **Enable 2FA:**
   - Go to Google Account settings
   - Enable 2-factor authentication

2. **Generate App Password:**
   - Visit: https://myaccount.google.com/apppasswords
   - Create password for "Mail"
   - Copy the 16-character password

3. **Configure:**
   - Use Gmail address as `SMTP_USERNAME`
   - Use app password as `SMTP_PASSWORD`

---

## Testing Results

After running `./test_alerts.sh all`, you should see:

```
✓ Telegram bot responding
✓ Critical alerts delivered via email + Telegram
✓ Warning alerts delivered via email
✓ Info alerts queued for daily summary
✓ Trading alerts delivered via Telegram + email
✓ Database alerts routed correctly
✓ Alert resolution notifications working

Active alerts: 7
AlertManager: http://localhost:9093
```

---

## Monitoring the Alerting System

### Health Checks

```bash
# Check AlertManager
curl http://localhost:9093/api/v1/status

# Check Telegram bot
curl http://localhost:8007/health

# Check Prometheus alert rules
curl http://localhost:9090/api/v1/rules
```

### View Active Alerts

```bash
# Via API
curl http://localhost:9093/api/v1/alerts | jq

# Via UI
open http://localhost:9093
```

### Check Alert History

```bash
# Prometheus alerts page
open http://localhost:9090/alerts

# AlertManager silences
curl http://localhost:9093/api/v1/silences
```

---

## Troubleshooting

### Emails Not Received

1. **Check SMTP credentials:**
   ```bash
   docker exec crypto-bot-alertmanager env | grep SMTP
   ```

2. **Use App-Specific Password:**
   - Not your regular Gmail password
   - Must enable 2FA first

3. **Check spam folder**

4. **View AlertManager logs:**
   ```bash
   docker logs crypto-bot-alertmanager | grep -i email
   ```

### Telegram Not Working

1. **Verify bot token:**
   ```bash
   curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
   ```

2. **Check chat ID:**
   ```bash
   curl http://localhost:8007/get-chat-id
   ```

3. **Test bot directly:**
   ```bash
   curl -X POST http://localhost:8007/test
   ```

4. **View bot logs:**
   ```bash
   docker logs crypto-bot-telegram-alerts
   ```

### Alerts Not Firing

1. **Check alert rules syntax:**
   ```bash
   docker exec crypto-bot-prometheus promtool check rules \
     /etc/prometheus/rules/trading-alerts.yml
   ```

2. **Reload Prometheus:**
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

3. **Verify metric exists:**
   ```bash
   curl "http://localhost:9090/api/v1/query?query=up{job='trading-engine'}"
   ```

---

## Production Deployment Checklist

- [ ] Configure Telegram bot token and chat ID
- [ ] Configure Gmail SMTP credentials
- [ ] Generate secure webhook token
- [ ] Test all alert channels
- [ ] Review and tune alert thresholds
- [ ] Set up Slack (if using)
- [ ] Set up PagerDuty (if using on-call)
- [ ] Configure on-call rotation
- [ ] Train team on alert response
- [ ] Document custom alerts
- [ ] Schedule regular alert reviews
- [ ] Set up alert metrics tracking

---

## Next Steps

### Immediate (Required)

1. **Run setup script:**
   ```bash
   ./scripts/setup_alerting.sh
   ```

2. **Test all channels:**
   ```bash
   ./scripts/test_alerts.sh all
   ```

3. **Verify notifications received**

### Short-term (1 week)

1. Monitor alert frequency
2. Tune thresholds based on observations
3. Train team on runbooks
4. Set up Slack integration (optional)

### Ongoing

1. Weekly: Review alert effectiveness
2. Monthly: Tune thresholds and add new alerts
3. Quarterly: Update runbooks
4. Track MTTA (Mean Time To Acknowledge)
5. Track MTTR (Mean Time To Resolve)

---

## Resources

### Documentation

- **Complete Guide:** `/docs/operations/ALERTING_GUIDE.md`
- **Runbooks:** `/docs/operations/ALERT_RUNBOOKS.md`
- **Monitoring Guide:** `/docs/MONITORING_GUIDE.md`

### Scripts

- **Setup:** `/infrastructure/monitoring/scripts/setup_alerting.sh`
- **Testing:** `/infrastructure/monitoring/scripts/test_alerts.sh`

### Configuration Files

- **AlertManager:** `/infrastructure/monitoring/alertmanager/alertmanager.yml`
- **Alert Rules:** `/infrastructure/monitoring/rules/trading-alerts.yml`
- **Email Template:** `/infrastructure/monitoring/alertmanager/templates/email.tmpl`
- **Telegram Bot:** `/infrastructure/monitoring/telegram-bot/telegram_alerts.py`

### External Resources

- [Prometheus Alerting](https://prometheus.io/docs/alerting/latest/overview/)
- [AlertManager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Telegram Bot API](https://core.telegram.org/bots/api)

---

## Summary

You now have a production-grade alerting system with:

- **26 comprehensive alert rules** covering all critical scenarios
- **Multi-channel notifications** (Email + Telegram)
- **Smart routing** based on severity and component
- **Rich HTML email templates** with actionable information
- **Real-time Telegram notifications** for critical events
- **Comprehensive runbooks** for alert investigation
- **Testing suite** to verify all channels
- **Interactive setup script** for easy configuration

The system is ready for production deployment. Run the setup script, configure your credentials, and start monitoring!

---

**Status:** ✅ Production Ready
**Last Updated:** 2025-11-21
**Contact:** DevOps Team
