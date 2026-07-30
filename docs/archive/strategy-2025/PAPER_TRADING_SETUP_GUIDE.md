# Paper Trading Validation Environment and Multi-Channel Alert System Setup Guide

**Created:** 2025-12-12
**Status:** Ready for Deployment
**Phase:** Paper Trading Validation (2-Week Minimum)

---

## Table of Contents

1. [Overview](#overview)
2. [Paper Trading Configuration](#paper-trading-configuration)
3. [SQZMOM Strategy Setup](#sqzmom-strategy-setup)
4. [Risk Management Configuration](#risk-management-configuration)
5. [Multi-Channel Alert System](#multi-channel-alert-system)
6. [Strategy Orchestration](#strategy-orchestration)
7. [Monitoring and Validation](#monitoring-and-validation)
8. [Testing Procedures](#testing-procedures)
9. [Troubleshooting](#troubleshooting)

---

## 1. Overview

This guide documents the setup and configuration of the paper trading validation environment with the following components:

- **SQZMOM Strategy:** Squeeze Momentum strategy configured for 7 profitable symbols
- **Risk Management:** 2% per trade risk, 5% portfolio emergency stop
- **Multi-Channel Alerts:** Telegram, Email, Slack, and SMS routing
- **Strategy Orchestration:** Centralized strategy management

### Key Configurations Created

| File | Purpose |
|------|---------|
| `/services/trading-engine/.env.paper_sqzmom` | Paper trading environment for SQZMOM |
| `/services/notification-service/.env` | Multi-channel alert configuration |
| `/docs/PAPER_TRADING_SETUP_GUIDE.md` | This documentation |

---

## 2. Paper Trading Configuration

### Activate Paper Trading Mode

```bash
# Navigate to trading-engine directory
cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine

# Backup current .env
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# Copy SQZMOM paper trading configuration
cp .env.paper_sqzmom .env

# Verify configuration
grep "TRADING_MODE" .env
# Expected output: TRADING_MODE=PAPER
```

### Critical Settings

```properties
# PAPER MODE ENFORCED - DO NOT CHANGE TO LIVE
TRADING_MODE=PAPER
AUTO_TRADING_ENABLED=true

# Paper Trading Initial Balance
PAPER_INITIAL_BALANCE=100.0
PAPER_COMMISSION_PCT=0.1
```

---

## 3. SQZMOM Strategy Setup

### Profitable Symbols (Dec 6 Analysis)

Based on the December 6, 2025 performance analysis, the following symbols have been selected:

| Symbol | Status | Expected Performance |
|--------|--------|---------------------|
| BNBUSDT | ACTIVE | Best performer, consistent profits |
| SOLUSDT | ACTIVE | Strong momentum, good signals |
| ADAUSDT | ACTIVE | Stable performer |
| ARBUSDT | ACTIVE | Good volatility |
| OPUSDT | ACTIVE | Good momentum |
| POLUSDT | ACTIVE | Consistent |
| SUIUSDT | ACTIVE | New performer |

### Excluded Symbols (Poor Performance)

| Symbol | Status | Reason |
|--------|--------|--------|
| XRPUSDT | EXCLUDED | -$39.73 loss, 25% WR |
| ETHUSDT | EXCLUDED | -$23.65 loss, 42.9% WR |
| BTCUSDT | EXCLUDED | -$10.59 loss, 40% WR |

### Strategy Configuration

```properties
DEFAULT_STRATEGY=sqzmom
SQZMOM_ENABLED=true
TRADING_SYMBOLS=["BNBUSDT","SOLUSDT","ADAUSDT","ARBUSDT","OPUSDT","POLUSDT","SUIUSDT"]
```

### Symbol Allocation

```json
{
  "BNBUSDT": 0.16,
  "SOLUSDT": 0.16,
  "ADAUSDT": 0.14,
  "ARBUSDT": 0.14,
  "OPUSDT": 0.14,
  "POLUSDT": 0.13,
  "SUIUSDT": 0.13
}
```

---

## 4. Risk Management Configuration

### Per-Trade Risk Limits

```properties
# Maximum 2% risk per trade (as per project requirements)
MAX_POSITION_SIZE_PCT=2.0

# Stop loss and take profit
DEFAULT_STOP_LOSS_PCT=2.0
DEFAULT_TAKE_PROFIT_PCT=4.0
```

### Portfolio Risk Limits

```properties
# 5% portfolio loss triggers emergency stop
MAX_DAILY_LOSS_PCT=5.0

# Total exposure limit
MAX_TOTAL_EXPOSURE_PCT=70.0
```

### Dynamic Risk Budgeting

```properties
ENABLE_DYNAMIC_RISK_BUDGETING=true
RISK_BUDGET_INITIAL=10000.0
RISK_BUDGET_DAILY_RESET=true
RISK_SCALING_FACTOR=0.5
MAX_RISK_MULTIPLIER=2.0
MIN_RISK_MULTIPLIER=0.25
```

---

## 5. Multi-Channel Alert System

### Alert Routing Matrix

| Severity | Telegram | Email | Slack | SMS | Dashboard |
|----------|----------|-------|-------|-----|-----------|
| CRITICAL | YES | YES | YES | NO* | YES |
| HIGH | YES | YES | NO | NO | YES |
| MEDIUM | YES | NO | NO | NO | YES |
| LOW | NO | YES | NO | NO | YES |
| INFO | NO | NO | NO | NO | YES |

*SMS only available when configured with Twilio credentials

### Channel Configuration

#### Telegram (Active)

```properties
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=<your_bot_token>
TELEGRAM_CHAT_ID=<your_chat_id>
```

#### Email (Placeholder - Configure as needed)

```properties
EMAIL_ENABLED=false
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your.email@gmail.com
SMTP_PASSWORD=<app_password>
```

#### Slack (Placeholder - Configure as needed)

```properties
SLACK_ENABLED=false
SLACK_WEBHOOK_URL=<your_webhook_url>
SLACK_CHANNEL_CRITICAL=#trading-critical
SLACK_CHANNEL_ALERTS=#trading-alerts
```

#### SMS/Twilio (Placeholder - Configure as needed)

```properties
SMS_ENABLED=false
TWILIO_ACCOUNT_SID=<your_sid>
TWILIO_AUTH_TOKEN=<your_token>
TWILIO_PHONE_NUMBER=+1234567890
SMS_RECIPIENT_NUMBERS=+1234567890
```

### Alert Rules

| Alert Condition | Severity | Action |
|----------------|----------|--------|
| Emergency stop triggered | CRITICAL | All channels |
| Daily loss > 3% | HIGH | Telegram + Email |
| Position loss > 10% | HIGH | Telegram + Email |
| Strategy win rate < 40% | HIGH | Telegram + Email |
| System errors | CRITICAL | All channels |

---

## 6. Strategy Orchestration

### Register SQZMOM Strategy

```bash
# Register the strategy with the orchestrator
curl -X POST http://localhost:8005/api/v1/orchestration/strategies/register \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "sqzmom_paper",
    "name": "SQZMOM Paper Trading",
    "strategy_type": "momentum",
    "symbols": ["BNBUSDT", "SOLUSDT", "ADAUSDT", "ARBUSDT", "OPUSDT", "POLUSDT", "SUIUSDT"],
    "allocation_pct": 100.0,
    "config": {
      "risk_per_trade": 0.02,
      "stop_loss_pct": 0.02,
      "take_profit_pct": 0.04
    }
  }'
```

### Activate Strategy

```bash
# Activate the strategy
curl -X POST http://localhost:8005/api/v1/orchestration/strategies/sqzmom_paper/activate
```

### Verify Status

```bash
# Check strategy status
curl -X GET http://localhost:8005/api/v1/orchestration/strategies/sqzmom_paper/status
```

---

## 7. Monitoring and Validation

### Daily P&L Tracking

```bash
# Get daily P&L summary
curl -X GET http://localhost:8005/api/v1/trading/paper/daily-summary
```

### Win Rate Monitoring

```bash
# Get performance metrics
curl -X GET http://localhost:8005/api/v1/trading/paper/metrics
```

### Position Size Validation

```bash
# Get current positions
curl -X GET http://localhost:8005/api/v1/trading/paper/positions
```

### Paper Trading Dashboard Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/trading/paper/balance` | GET | Current balance |
| `/api/v1/trading/paper/positions` | GET | Open positions |
| `/api/v1/trading/paper/trades` | GET | Trade history |
| `/api/v1/trading/paper/daily-summary` | GET | Daily P&L summary |
| `/api/v1/trading/paper/metrics` | GET | Performance metrics |

---

## 8. Testing Procedures

### Test Alert Channels

```bash
# Test Telegram
curl -X POST http://localhost:8006/api/v1/alerts/test/telegram

# Test Email (if enabled)
curl -X POST http://localhost:8006/api/v1/alerts/test/email

# Test Slack (if enabled)
curl -X POST http://localhost:8006/api/v1/alerts/test/slack

# Test SMS (if enabled)
curl -X POST http://localhost:8006/api/v1/alerts/test/sms
```

### Check Channel Status

```bash
# Get all channel status
curl -X GET http://localhost:8006/api/v1/alerts/channels/status
```

### Send Test Trade Alert

```bash
# Send a test trade alert
curl -X POST http://localhost:8006/api/v1/alerts/trade \
  -H "Content-Type: application/json" \
  -d '{
    "action": "BUY",
    "symbol": "BNBUSDT",
    "quantity": 0.1,
    "price": 650.0,
    "confidence": 0.75
  }'
```

### Send Test Risk Alert

```bash
# Send a test risk alert
curl -X POST http://localhost:8006/api/v1/alerts/risk \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "DAILY_LOSS_WARNING",
    "message": "Daily loss approaching 3% threshold",
    "severity": "HIGH",
    "current_value": 2.8,
    "threshold": 3.0
  }'
```

---

## 9. Troubleshooting

### Common Issues

#### Alert Not Received

1. Check channel is enabled in `.env`
2. Verify credentials are correct
3. Check rate limiting (20 messages/minute for Telegram)
4. Review logs: `/services/notification-service/logs/`

#### Strategy Not Trading

1. Verify `AUTO_TRADING_ENABLED=true`
2. Check signal confidence threshold
3. Verify time filters (trading hours 8-21 UTC)
4. Review trading-engine logs

#### Position Size Incorrect

1. Verify `MAX_POSITION_SIZE_PCT` setting
2. Check symbol allocation weights sum to 1.0
3. Review dynamic risk budget status

### Log Locations

```bash
# Trading Engine logs
/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine/logs/

# Notification Service logs
/mnt/d/Bimo_max/crypto-trading-bot/services/notification-service/logs/

# Paper trading specific log
/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine/logs/sqzmom_paper.log
```

### Health Check Commands

```bash
# Trading Engine health
curl http://localhost:8005/health

# Notification Service health
curl http://localhost:8006/health

# Technical Analysis health
curl http://localhost:8004/health
```

---

## Validation Checklist

Before going live, complete the following validation:

### Paper Trading Validation (Minimum 2 Weeks)

- [ ] Paper trading running for 14+ days
- [ ] Win rate > 50% across all symbols
- [ ] Daily P&L positive on 10+ days
- [ ] No emergency stop triggers
- [ ] All alert channels tested
- [ ] Risk management working correctly

### Alert System Validation

- [ ] Telegram alerts received
- [ ] Email alerts received (if enabled)
- [ ] Slack alerts received (if enabled)
- [ ] Critical alerts escalate properly
- [ ] Alert routing working as configured

### Performance Metrics

- [ ] Total P&L is positive
- [ ] Sharpe ratio > 1.0
- [ ] Max drawdown < 10%
- [ ] Average trade duration acceptable

---

## Quick Reference Commands

```bash
# Start services
docker-compose up -d trading-engine notification-service

# Check service status
docker-compose ps

# View logs
docker-compose logs -f trading-engine

# Stop services
docker-compose down

# Restart with fresh config
docker-compose down && docker-compose up -d
```

---

**Document Version:** 1.0
**Last Updated:** 2025-12-12
**Author:** Backend Developer Agent
