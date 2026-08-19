# Alerting System Guide - Crypto Trading Bot

**Version:** 1.0
**Last Updated:** 2025-11-21
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Alert Categories](#alert-categories)
4. [Notification Channels](#notification-channels)
5. [Alert Rules](#alert-rules)
6. [Configuration](#configuration)
7. [Testing](#testing)
8. [Troubleshooting](#troubleshooting)
9. [Best Practices](#best-practices)

---

## Overview

The Crypto Trading Bot uses a production-grade alerting system built on Prometheus AlertManager with multiple notification channels:

- **Email**: HTML and text notifications for all alert levels
- **Telegram**: Real-time mobile notifications for critical and trading alerts
- **Slack**: Optional team notifications (configurable)
- **PagerDuty**: Optional on-call escalation (configurable)

### Architecture

```
Prometheus → Alert Rules → AlertManager → Notification Channels
                                        ├─→ Email (SMTP)
                                        ├─→ Telegram (Webhook)
                                        ├─→ Slack (Webhook)
                                        └─→ PagerDuty (API)
```

### Key Features

- **Multi-channel notifications**: Email + Telegram for critical alerts
- **Smart routing**: Different channels for different alert types
- **Alert grouping**: Related alerts grouped together
- **Alert inhibition**: Suppress redundant alerts
- **Rich formatting**: HTML emails with actionable runbooks
- **Test mode**: Comprehensive testing scripts included

---

## Quick Start

### 1. Configure Environment Variables

```bash
cd infrastructure/monitoring/telegram-bot
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Required variables:
```bash
# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321

# Email
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
ALERT_EMAIL=alerts@yourdomain.com
```

### 2. Create Telegram Bot

1. **Open Telegram and search for @BotFather**
2. **Send command:** `/newbot`
3. **Follow prompts** to create your bot
4. **Copy the token** to `TELEGRAM_BOT_TOKEN`

### 3. Get Your Chat ID

```bash
# Start the Telegram bot
docker-compose -f infrastructure/monitoring/docker-compose.monitoring.yml up -d telegram-bot

# Send a message to your bot in Telegram
# Then get your chat ID:
curl http://localhost:8007/get-chat-id
```

Copy the returned `chat_id` to `TELEGRAM_CHAT_ID` in `.env`

### 4. Start Monitoring Stack

```bash
cd infrastructure/monitoring

# Start all monitoring services
docker-compose -f docker-compose.monitoring.yml up -d

# Verify services are running
docker-compose -f docker-compose.monitoring.yml ps
```

### 5. Test Alerting

```bash
cd infrastructure/monitoring/scripts

# Make test script executable
chmod +x test_alerts.sh

# Run all tests
./test_alerts.sh all

# Or test specific channel
./test_alerts.sh telegram
./test_alerts.sh critical
```

### 6. Verify Notifications

- **Check your email** for HTML-formatted alert
- **Check Telegram** for mobile notification
- **Check AlertManager UI**: http://localhost:9093

---

## Alert Categories

### CRITICAL (Immediate Action Required)

**Response Time:** 5-15 minutes
**Notification:** Email + Telegram + (optional) PagerDuty
**Repeat Interval:** 1 hour

| Alert | Condition | Impact |
|-------|-----------|--------|
| TradingEngineDown | Service down for 30s | No trades can be executed |
| DailyLossExceeded | Daily loss > 12% (ADR-028) | Significant financial loss |
| ServiceDown | Any service down for 1m | Service unavailable |
| HighErrorRate | Error rate > 5% for 5m | Service degradation |
| DatabaseDown | Database unreachable for 1m | All services affected |
| RiskLimitViolation | Risk limit breached | Compliance violation |

### WARNING (Investigation Required)

**Response Time:** 30-60 minutes
**Notification:** Email
**Repeat Interval:** 4-8 hours

| Alert | Condition | Impact |
|-------|-----------|--------|
| HighAPILatency | P99 latency > 1s for 5m | Slow responses |
| HighMemoryUsage | Memory > 1GB for 10m | Potential OOM |
| CircuitBreakerOpen | Circuit breaker triggered | Requests blocked |
| LowWinRate | Win rate < 40% for 1h | Poor strategy performance |
| BybitRateLimitHit | Rate limit exceeded | API throttling |
| HighDatabaseConnections | Connections > 180 for 5m | Connection pool exhaustion |
| SlowDatabaseQueries | Avg query time > 1s | Database performance issue |

### INFO (Awareness)

**Response Time:** 4-24 hours
**Notification:** Email (daily summary)
**Repeat Interval:** 24 hours

| Alert | Condition | Impact |
|-------|-----------|--------|
| HighCPUUsage | CPU > 80% for 15m | Monitor for scaling |
| LowDiskSpace | Disk < 20% for 10m | Cleanup needed |
| DeploymentCompleted | Deployment successful | Awareness |
| BackupCompleted | Backup successful | Awareness |
| NoTradesExecuted | No trades for 2h | Potential issue |

---

## Notification Channels

### Email Notifications

**Features:**
- HTML-formatted emails with visual severity indicators
- Embedded action items and runbook links
- Support for firing and resolved states
- Links to Grafana dashboards
- Plain text fallback

**Template:** `/infrastructure/monitoring/alertmanager/templates/email.tmpl`

**Configuration:**
```yaml
# In alertmanager.yml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: '${SMTP_USERNAME}'
  smtp_auth_username: '${SMTP_USERNAME}'
  smtp_auth_password: '${SMTP_PASSWORD}'
  smtp_require_tls: true
```

**Gmail Setup:**
1. Enable 2-factor authentication
2. Create App-Specific Password
3. Use app password in `SMTP_PASSWORD`

### Telegram Notifications

**Features:**
- Real-time mobile notifications
- Rich formatting with HTML
- Emoji indicators for severity
- Clickable links to dashboards
- Support for groups and channels

**Bot:** `/infrastructure/monitoring/telegram-bot/telegram_alerts.py`

**Configuration:**
```python
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
WEBHOOK_TOKEN=secure-random-token
```

**Test Endpoint:**
```bash
curl -X POST http://localhost:8007/test
```

### Slack (Optional)

**Configuration:**
```yaml
# Uncomment in alertmanager.yml
receivers:
  - name: 'slack-critical'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL_CRITICAL}'
        channel: '#crypto-bot-critical'
```

**Webhook Setup:**
1. Go to Slack App Directory
2. Add "Incoming Webhooks" integration
3. Copy webhook URL to `.env`

### PagerDuty (Optional)

**Configuration:**
```yaml
# Uncomment in alertmanager.yml
receivers:
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '${PAGERDUTY_SERVICE_KEY}'
```

---

## Alert Rules

### Location

- **Trading Alerts:** `/infrastructure/monitoring/rules/trading-alerts.yml`
- **Phase 3 Alerts:** `/infrastructure/monitoring/rules/phase3-alerts.yml`

### Rule Structure

```yaml
groups:
  - name: critical_alerts
    interval: 15s
    rules:
      - alert: AlertName
        expr: prometheus_query > threshold
        for: duration
        labels:
          severity: critical
          component: service-name
          category: availability
          runbook: "url-to-runbook"
        annotations:
          summary: "Brief description"
          description: "Detailed description with {{ $value }}"
          action: "Steps to resolve"
          dashboard: "http://grafana-url"
```

### Complete Alert List

See [MONITORING_GUIDE.md](MONITORING_GUIDE.md#alerting-rules) for all 26 alert rules.

### Adding Custom Alerts

1. **Edit alert rules file:**
   ```bash
   vim infrastructure/monitoring/rules/trading-alerts.yml
   ```

2. **Add new rule:**
   ```yaml
   - alert: MyCustomAlert
     expr: my_metric > 100
     for: 5m
     labels:
       severity: warning
     annotations:
       summary: "My custom alert fired"
   ```

3. **Validate syntax:**
   ```bash
   docker exec crypto-bot-prometheus promtool check rules \
     /etc/prometheus/rules/trading-alerts.yml
   ```

4. **Reload Prometheus:**
   ```bash
   curl -X POST http://localhost:9090/-/reload
   # Or restart container
   docker restart crypto-bot-prometheus
   ```

---

## Configuration

### AlertManager Configuration

**File:** `/infrastructure/monitoring/alertmanager/alertmanager.yml`

#### Alert Routing

```yaml
route:
  receiver: 'default'
  group_by: ['alertname', 'severity', 'component']
  group_wait: 10s        # Wait before sending initial notification
  group_interval: 5m     # Wait before sending updates
  repeat_interval: 4h    # Wait before re-sending

  routes:
    # Critical: Send immediately to all channels
    - match:
        severity: critical
      receiver: 'critical-all'
      group_wait: 0s
      repeat_interval: 1h

    # Trading: Send to Telegram + Email
    - match:
        component: risk-management
      receiver: 'telegram-trading'

    # Database: Send to database team
    - match:
        component: database
      receiver: 'email-database'
```

#### Alert Inhibition

Suppress redundant alerts:

```yaml
inhibit_rules:
  # Suppress warning if critical is firing
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'service']

  # Suppress high latency if service is down
  - source_match:
      alertname: 'ServiceDown'
    target_match_re:
      alertname: '^High.*Latency$'
    equal: ['service']
```

### Prometheus Configuration

**File:** `/infrastructure/monitoring/prometheus/prometheus.yml`

#### Load Alert Rules

```yaml
rule_files:
  - 'alerts.yml'
  - 'rules/trading-alerts.yml'
  - 'rules/phase3-alerts.yml'
```

#### Connect to AlertManager

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093
```

### Docker Compose Configuration

**File:** `/infrastructure/monitoring/docker-compose.monitoring.yml`

Add Telegram bot service:

```yaml
services:
  telegram-bot:
    build: ./telegram-bot
    container_name: crypto-bot-telegram-alerts
    ports:
      - "8007:8007"
    env_file:
      - ./telegram-bot/.env
    networks:
      - crypto-bot-network
    restart: unless-stopped
```

---

## Testing

### Test Script

**Location:** `/infrastructure/monitoring/scripts/test_alerts.sh`

#### Run All Tests

```bash
cd infrastructure/monitoring/scripts
./test_alerts.sh all
```

This will test:
- Telegram bot connectivity
- Critical alerts (immediate notification)
- Warning alerts (email notification)
- Info alerts (daily summary)
- Trading alerts (Telegram + Email)
- Database alerts (specialized routing)
- Alert resolution notifications

#### Run Specific Tests

```bash
# Test Telegram only
./test_alerts.sh telegram

# Test critical alerts
./test_alerts.sh critical

# Test alert resolution
./test_alerts.sh resolution
```

### Manual Testing

#### Send Test Alert via API

```bash
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

#### Test Email Configuration

```bash
# From AlertManager container
docker exec crypto-bot-alertmanager amtool config show
```

#### Test Telegram Bot

```bash
# Send test message
curl -X POST http://localhost:8007/test

# Check health
curl http://localhost:8007/health
```

### Verification Checklist

- [ ] Telegram bot responds to /test
- [ ] Email received for critical alert
- [ ] Telegram notification received for critical alert
- [ ] Email received for warning alert
- [ ] Resolved alerts send notifications
- [ ] Alert grouping works correctly
- [ ] Alert inhibition works correctly
- [ ] Runbook links are accessible
- [ ] Dashboard links work

---

## Troubleshooting

### Emails Not Received

**Symptoms:**
- Alerts firing but no email received

**Diagnosis:**
```bash
# Check AlertManager logs
docker logs crypto-bot-alertmanager | grep -i email

# Check SMTP configuration
docker exec crypto-bot-alertmanager cat /etc/alertmanager/alertmanager.yml | grep smtp

# Test SMTP connectivity
docker exec crypto-bot-alertmanager telnet smtp.gmail.com 587
```

**Solutions:**

1. **Verify SMTP credentials**
   ```bash
   # Check environment variables
   docker exec crypto-bot-alertmanager env | grep SMTP
   ```

2. **Use App-Specific Password for Gmail**
   - Enable 2FA in Google Account
   - Generate App-Specific Password
   - Use that password, not your regular password

3. **Check spam folder**

4. **Verify email template**
   ```bash
   docker exec crypto-bot-alertmanager ls -la /etc/alertmanager/templates/
   ```

### Telegram Notifications Not Received

**Symptoms:**
- Telegram bot not sending messages

**Diagnosis:**
```bash
# Check Telegram bot logs
docker logs crypto-bot-telegram-alerts

# Test bot directly
curl -X POST http://localhost:8007/test

# Check bot health
curl http://localhost:8007/health
```

**Solutions:**

1. **Verify bot token**
   ```bash
   # Test token directly
   curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
   ```

2. **Verify chat ID**
   ```bash
   # Get chat ID
   curl http://localhost:8007/get-chat-id
   ```

3. **Check webhook token**
   - Ensure `WEBHOOK_TOKEN` matches in AlertManager and Telegram bot

4. **Verify network connectivity**
   ```bash
   docker exec crypto-bot-telegram-alerts ping -c 3 api.telegram.org
   ```

### Alerts Not Firing

**Symptoms:**
- Expected alerts not triggering

**Diagnosis:**
```bash
# Check Prometheus alert rules
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.type=="alerting")'

# Check alert status
curl http://localhost:9090/api/v1/alerts | jq

# Validate rule syntax
docker exec crypto-bot-prometheus promtool check rules /etc/prometheus/rules/*.yml
```

**Solutions:**

1. **Verify metric exists**
   ```bash
   curl -s http://localhost:9090/api/v1/query \
     --data-urlencode 'query=up{job="trading-engine"}' | jq
   ```

2. **Check alert expression**
   - Test expression in Prometheus UI: http://localhost:9090/graph

3. **Reload Prometheus**
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

### Too Many Alerts

**Symptoms:**
- Alert fatigue from too many notifications

**Solutions:**

1. **Increase thresholds**
   ```yaml
   # Make alerts less sensitive
   - alert: HighMemoryUsage
     expr: memory > 2g  # Increased from 1g
     for: 30m  # Increased from 10m
   ```

2. **Adjust repeat intervals**
   ```yaml
   route:
     repeat_interval: 12h  # Increased from 4h
   ```

3. **Use alert inhibition**
   - Suppress less important alerts when critical alerts fire

4. **Group related alerts**
   ```yaml
   route:
     group_by: ['alertname', 'severity', 'component']
     group_interval: 10m  # Group alerts for 10 minutes
   ```

---

## Best Practices

### Alert Design

1. **Make alerts actionable**
   - Include clear action steps in annotations
   - Link to runbooks and dashboards
   - Provide context in descriptions

2. **Set appropriate thresholds**
   - Use historical data to determine baselines
   - Avoid alert fatigue with too-sensitive thresholds
   - Consider business impact when setting severity

3. **Use the `for` clause**
   ```yaml
   # Avoid flapping alerts
   - alert: HighLatency
     expr: latency > 1s
     for: 5m  # Must be true for 5 minutes
   ```

4. **Include helpful labels**
   ```yaml
   labels:
     severity: critical
     component: trading-engine
     category: financial
     runbook: "url-to-runbook"
   ```

### Notification Management

1. **Route alerts appropriately**
   - Critical → All channels (Email + Telegram + PagerDuty)
   - Warning → Email
   - Info → Daily summary

2. **Use alert grouping**
   - Group related alerts to reduce notification volume
   - Group by: alertname, severity, component

3. **Configure repeat intervals wisely**
   - Critical: 1 hour
   - Warning: 4-8 hours
   - Info: 24 hours

4. **Implement alert inhibition**
   - Suppress redundant alerts
   - Don't alert on symptoms when root cause is known

### On-Call Management

1. **Define clear escalation paths**
   ```
   L1 (0-15 min) → L2 (15-60 min) → L3 (60+ min)
   ```

2. **Maintain runbooks**
   - Document investigation steps
   - Provide resolution procedures
   - Include contact information

3. **Conduct regular alert reviews**
   - Weekly: Review alert frequency
   - Monthly: Tune thresholds
   - Quarterly: Update runbooks

4. **Track alert metrics**
   - Mean Time To Acknowledge (MTTA)
   - Mean Time To Resolve (MTTR)
   - False positive rate
   - Alert fatigue indicators

### Testing and Validation

1. **Test alerts regularly**
   ```bash
   # Weekly alert testing
   ./test_alerts.sh all
   ```

2. **Verify after changes**
   - Test after modifying alert rules
   - Test after changing notification channels
   - Test after infrastructure changes

3. **Monitor alerting system**
   - Track AlertManager health
   - Monitor email delivery rate
   - Monitor Telegram bot uptime

4. **Document incidents**
   - Record alert effectiveness
   - Track false positives
   - Update runbooks based on incidents

---

## Summary

### Active Alert Rules

**Total:** 26 alert rules configured

**By Severity:**
- Critical: 6 alerts
- Warning: 14 alerts
- Info: 6 alerts

**By Category:**
- Availability: 4 alerts
- Performance: 6 alerts
- Financial: 4 alerts
- Resources: 6 alerts
- Operations: 6 alerts

### Notification Channels

- **Email:** All alert levels
- **Telegram:** Critical and trading alerts
- **Slack:** Optional (configurable)
- **PagerDuty:** Optional (configurable)

### Test Results

After running `./test_alerts.sh all`:

```
✓ Telegram bot responding
✓ Critical alerts delivered via email + Telegram
✓ Warning alerts delivered via email
✓ Info alerts queued for daily summary
✓ Trading alerts delivered via Telegram + email
✓ Database alerts routed correctly
✓ Alert resolution notifications working
```

### Next Steps

1. **Configure credentials** in `.env`
2. **Start monitoring stack** with docker-compose
3. **Run test suite** to verify all channels
4. **Review and tune** alert thresholds
5. **Train team** on alert response procedures
6. **Schedule regular** alert reviews

---

## Resources

- [MONITORING_GUIDE.md](MONITORING_GUIDE.md) - Comprehensive monitoring guide
- [ALERT_RUNBOOKS.md](/docs/operations/ALERT_RUNBOOKS.md) - Alert investigation procedures
- [Prometheus Alerting](https://prometheus.io/docs/alerting/latest/overview/)
- [AlertManager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Telegram Bot API](https://core.telegram.org/bots/api)

---

**Document Status:** Production Ready
**Last Updated:** 2025-11-21
**Maintained By:** DevOps Team
**Contact:** alerts@cryptobot.com
