# Production-Grade Alerting System - Complete Setup

**Status:** Production Ready ✅  
**Last Updated:** 2025-11-21  
**Documentation:** Complete

---

## What You Have Now

A complete, production-grade alerting system with:

- **26 comprehensive alert rules** covering all critical scenarios
- **Email notifications** with professional HTML templates
- **Telegram bot** for real-time mobile notifications
- **Smart alert routing** by severity and component
- **Alert grouping and inhibition** to prevent alert fatigue
- **Comprehensive runbooks** for each alert
- **Testing suite** to verify everything works
- **Interactive setup script** for easy configuration

---

## Quick Start (5 Minutes)

### Step 1: Create Telegram Bot (2 minutes)

1. Open Telegram and search for **@BotFather**
2. Send command: `/newbot`
3. Follow prompts to create your bot
4. **Copy the token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Get Gmail App Password (2 minutes)

1. Go to your Google Account settings
2. Enable **2-Factor Authentication** if not already enabled
3. Visit: https://myaccount.google.com/apppasswords
4. Create an **App-Specific Password** for "Mail"
5. **Copy the 16-character password**

### Step 3: Run Setup Script (1 minute)

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring
./scripts/setup_alerting.sh
```

The script will:
- Ask for your Telegram bot token
- Ask for your Gmail credentials
- Generate secure webhook token
- Create configuration files
- Start all services
- Help you get your Telegram chat ID

### Step 4: Test Everything

```bash
cd scripts
./test_alerts.sh all
```

Check:
- Your email inbox (and spam folder)
- Your Telegram app for notifications
- AlertManager UI: http://localhost:9093

**Done!** Your alerting system is now operational.

---

## What Gets Monitored

### Critical Alerts (Immediate Action Required)

These alerts send **Email + Telegram** notifications:

| Alert | Triggers When | What It Means |
|-------|--------------|---------------|
| **TradingEngineDown** | Service down for 30s | Trading has stopped |
| **DailyLossExceeded** | Daily loss > 5% | Significant financial loss |
| **ServiceDown** | Any service down for 1m | Service outage |
| **HighErrorRate** | Error rate > 5% for 5m | System degradation |
| **DatabaseDown** | Database unreachable | Complete system failure |
| **RiskLimitViolation** | Risk limits breached | Compliance issue |

**Response Time:** 5-15 minutes  
**Notification:** Email + Telegram  
**Repeat:** Every 1 hour if not resolved

### Warning Alerts (Investigation Needed)

These alerts send **Email only** notifications:

- High API Latency (> 1 second)
- High Memory Usage (> 1 GB)
- Circuit Breaker Triggered
- Low Win Rate (< 40%)
- Bybit Rate Limit Hit
- High Database Connections
- Low Cache Hit Rate
- Slow Database Queries
- High Unrealized Loss
- Position Size Exceeded
- High Drawdown
- Container Restarted
- High File Descriptor Usage
- Prometheus Target Down

**Response Time:** 30-60 minutes  
**Notification:** Email only  
**Repeat:** Every 4-8 hours if not resolved

### Info Alerts (Awareness)

These alerts are grouped into **daily summaries**:

- High CPU Usage
- Low Disk Space
- Deployment Completed
- Backup Completed
- No Trades Executed
- Low Sharpe Ratio

**Response Time:** 4-24 hours  
**Notification:** Email (daily digest)  
**Repeat:** Every 24 hours

---

## How Notifications Work

### Email Notifications

Every alert sends a professional HTML email with:

- Color-coded severity indicator
- Clear summary and description
- Recommended action steps
- Links to runbooks
- Links to Grafana dashboards
- Alert start time and instance details

**Example Email Structure:**
```
Subject: [FIRING] TradingEngineDown - Crypto Bot

🚨 CRITICAL ALERT
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

### Telegram Notifications

Critical and trading alerts also send to Telegram:

- Real-time mobile notifications
- Rich HTML formatting
- Emoji severity indicators
- Clickable dashboard links
- Alert grouping

**Example Telegram Message:**
```
🚨 ALERT FIRING
💹 TradingEngineDown

Severity: CRITICAL
Component: trading-engine
Firing: 1 alert(s)

━━━━━━━━━━━━━━━━━━━━
Summary: Trading Engine is down
Description: Trading Engine has been down for 30 seconds. 
No trades can be executed.

Action: Check service logs

━━━━━━━━━━━━━━━━━━━━
Quick Links:
• Grafana Dashboard
• AlertManager
```

---

## Configuration Files

### Created Automatically by Setup Script

These files are created when you run `./scripts/setup_alerting.sh`:

```
infrastructure/monitoring/
├── telegram-bot/.env          ← Your Telegram bot credentials
└── alertmanager/.env          ← Your email credentials
```

**Never commit these files to Git!** They contain sensitive credentials.

### Pre-Configured Files (Ready to Use)

These files are already configured and ready:

```
infrastructure/monitoring/
├── alertmanager/
│   ├── alertmanager.yml                  ← Alert routing configuration
│   └── templates/email.tmpl              ← Email HTML template
├── telegram-bot/
│   ├── telegram_alerts.py                ← Telegram bot application
│   ├── Dockerfile                        ← Container build
│   └── requirements.txt                  ← Python dependencies
├── rules/
│   └── trading-alerts.yml                ← 26 alert rules
├── scripts/
│   ├── setup_alerting.sh                 ← Interactive setup
│   └── test_alerts.sh                    ← Testing suite
└── prometheus/
    └── prometheus.yml                    ← Updated to load rules
```

---

## Testing Your Setup

### Test All Channels

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/scripts
./test_alerts.sh all
```

This will send test alerts to:
- Telegram (test bot connectivity)
- Email (critical alert test)
- Email (warning alert test)
- Email (info alert test)
- Telegram + Email (trading alert test)
- Email (database alert test)
- Resolution notification test

### Test Specific Channels

```bash
# Test Telegram only
./test_alerts.sh telegram

# Test critical alert
./test_alerts.sh critical

# Test trading-specific alert
./test_alerts.sh trading

# Test alert resolution
./test_alerts.sh resolution
```

### Manual Testing

```bash
# Send custom test alert
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

# Check active alerts
curl http://localhost:9093/api/v1/alerts | jq

# Test Telegram bot health
curl http://localhost:8007/health
```

---

## Troubleshooting

### "No Emails Received"

**Possible Causes:**
1. Using regular Gmail password instead of App-Specific Password
2. 2FA not enabled in Google Account
3. Emails going to spam folder
4. Wrong SMTP credentials

**Solution:**
```bash
# 1. Check credentials
docker exec crypto-bot-alertmanager env | grep SMTP

# 2. Check AlertManager logs
docker logs crypto-bot-alertmanager | grep -i email

# 3. Verify you're using App-Specific Password (16 characters)
# NOT your regular Gmail password

# 4. Generate new App Password:
#    https://myaccount.google.com/apppasswords
```

### "No Telegram Notifications"

**Possible Causes:**
1. Wrong bot token
2. Wrong chat ID
3. Telegram bot not started
4. Webhook token mismatch

**Solution:**
```bash
# 1. Test bot token directly
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"

# 2. Get your chat ID
curl http://localhost:8007/get-chat-id

# 3. Test bot directly
curl -X POST http://localhost:8007/test

# 4. Check bot logs
docker logs crypto-bot-telegram-alerts

# 5. Verify bot is running
docker ps | grep telegram
```

### "Alerts Not Firing"

**Possible Causes:**
1. Alert rule syntax error
2. Prometheus not reloaded after rule changes
3. Metric doesn't exist
4. Threshold not met

**Solution:**
```bash
# 1. Validate alert rules
docker exec crypto-bot-prometheus promtool check rules \
  /etc/prometheus/rules/trading-alerts.yml

# 2. Reload Prometheus
curl -X POST http://localhost:9090/-/reload

# 3. Check if metric exists
curl "http://localhost:9090/api/v1/query?query=up{job='trading-engine'}"

# 4. View alert status
curl http://localhost:9090/api/v1/alerts | jq
```

---

## Useful Commands

### View Active Alerts

```bash
# In AlertManager
curl http://localhost:9093/api/v1/alerts | jq

# In Prometheus
curl http://localhost:9090/api/v1/alerts | jq

# View in browser
open http://localhost:9093
open http://localhost:9090/alerts
```

### Silence an Alert

```bash
# Silence for 2 hours
curl -X POST http://localhost:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name": "alertname", "value": "HighAPILatency"}],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "endsAt": "'$(date -u -d '+2 hours' +%Y-%m-%dT%H:%M:%SZ)'",
    "createdBy": "admin",
    "comment": "Under investigation"
  }'
```

### Restart Services

```bash
# Restart all monitoring services
docker-compose -f docker-compose.monitoring.yml restart

# Restart specific service
docker restart crypto-bot-alertmanager
docker restart crypto-bot-telegram-alerts
docker restart crypto-bot-prometheus
```

### View Logs

```bash
# AlertManager logs
docker logs crypto-bot-alertmanager

# Telegram bot logs
docker logs crypto-bot-telegram-alerts

# Prometheus logs
docker logs crypto-bot-prometheus

# Follow logs in real-time
docker logs -f crypto-bot-alertmanager
```

---

## Documentation

### Complete Guides

1. **ALERTING_GUIDE.md** (600+ lines)
   - Location: `/docs/operations/ALERTING_GUIDE.md`
   - Complete alerting system documentation
   - Configuration details
   - Best practices

2. **ALERT_RUNBOOKS.md** (500+ lines)
   - Location: `/docs/operations/ALERT_RUNBOOKS.md`
   - Investigation steps for each alert
   - Resolution procedures
   - Common troubleshooting

3. **ALERTING_QUICK_REFERENCE.md**
   - Location: `/infrastructure/monitoring/ALERTING_QUICK_REFERENCE.md`
   - One-page quick reference
   - Common commands
   - Quick fixes

4. **ALERTING_SETUP_COMPLETE.md**
   - Location: `/infrastructure/monitoring/ALERTING_SETUP_COMPLETE.md`
   - Complete setup summary
   - All deliverables listed
   - Configuration details

### Quick Links

- **AlertManager UI:** http://localhost:9093
- **Prometheus Alerts:** http://localhost:9090/alerts
- **Telegram Bot Health:** http://localhost:8007/health
- **Grafana Dashboards:** http://localhost:3000

---

## Production Deployment Checklist

Before deploying to production, ensure:

- [ ] Telegram bot created and tested
- [ ] Gmail App-Specific Password configured
- [ ] All test alerts pass (`./test_alerts.sh all`)
- [ ] Email notifications received
- [ ] Telegram notifications received
- [ ] Alert thresholds reviewed and tuned
- [ ] Team trained on alert response procedures
- [ ] Runbooks accessible to on-call team
- [ ] Escalation procedures documented
- [ ] On-call rotation configured (if using PagerDuty)

---

## Next Steps

### Immediate (Do Now)

1. Run the setup script:
   ```bash
   ./scripts/setup_alerting.sh
   ```

2. Test all channels:
   ```bash
   ./scripts/test_alerts.sh all
   ```

3. Verify notifications received

### Short-term (This Week)

1. Monitor alert frequency
2. Tune thresholds if too sensitive
3. Train team on runbooks
4. Set up Slack integration (optional)

### Ongoing (Regular Maintenance)

1. **Weekly:** Review alert frequency and false positives
2. **Monthly:** Tune thresholds based on actual metrics
3. **Quarterly:** Update runbooks with new learnings
4. **Track metrics:** MTTA (Mean Time To Acknowledge), MTTR (Mean Time To Resolve)

---

## Support

### Getting Help

- **Documentation:** See files listed above
- **Testing:** Use `./test_alerts.sh` to diagnose issues
- **Logs:** Check container logs with `docker logs`
- **Community:** Prometheus and AlertManager communities

### External Resources

- [Prometheus Alerting Docs](https://prometheus.io/docs/alerting/latest/overview/)
- [AlertManager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)

---

## Summary

You now have a complete, production-grade alerting system:

- **26 alert rules** covering all critical scenarios
- **Multi-channel notifications** (Email + Telegram)
- **Smart routing** by severity and component
- **Professional templates** with actionable information
- **Testing suite** to verify everything works
- **Complete documentation** for operations

**The system is ready to deploy. Run the setup script to get started!**

---

**Status:** ✅ Production Ready  
**Version:** 1.0  
**Last Updated:** 2025-11-21  
**Maintained By:** DevOps Team
