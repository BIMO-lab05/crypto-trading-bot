# Telegram Notifications Setup Guide
**Last Updated:** 2025-11-14
**Purpose:** Enable real-time trading alerts via Telegram for monitoring and safety

---

## Overview

The notification service is already **configured but disabled**. This guide shows how to:
- ✅ Create a Telegram bot
- ✅ Get your chat ID
- ✅ Enable notifications
- ✅ Test alert delivery
- ✅ Customize alert settings

**Time Required:** 10-15 minutes

---

## Why Telegram Notifications?

**Benefits:**
- 🚨 **Emergency Alerts** - Instant notification when daily loss limit hit
- 📈 **Trade Confirmations** - Know immediately when trades execute
- ⚠️ **Error Monitoring** - Get alerted to system failures
- 📱 **Mobile Access** - Monitor from anywhere
- 🔔 **Real-time** - Faster than email (typically 1-2 seconds)

**Recommended For:**
- Paper trading validation
- Live trading monitoring
- System health checks
- Risk management enforcement

---

## Step 1: Create Telegram Bot

### 1.1 Install Telegram
- **Mobile:** Download from App Store / Google Play
- **Desktop:** Download from https://desktop.telegram.org
- Sign up with your phone number

### 1.2 Create Bot with BotFather

1. Open Telegram app
2. Search for `@BotFather` (official bot with blue checkmark)
3. Start conversation: `/start`
4. Create new bot: `/newbot`

**Conversation will look like:**
```
BotFather: Alright, a new bot. How are we going to call it?
           Please choose a name for your bot.

You: Crypto Trading Bot Alerts

BotFather: Good. Now let's choose a username for your bot.
           It must end in `bot`. Like this, for example: TetrisBot or tetris_bot.

You: crypto_trader_alerts_bot

BotFather: Done! Congratulations on your new bot.

Use this token to access the HTTP API:
123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567

Keep your token secure and store it safely, it can be used by anyone to control your bot.
```

5. **SAVE THE TOKEN** - You'll need it for configuration

### 1.3 Customize Bot (Optional)

Make your bot more professional:

```
# Set description
/setdescription
[Select your bot]
Real-time trading alerts for crypto trading bot

# Set profile picture
/setuserpic
[Select your bot]
[Upload an icon - maybe a chart or robot emoji]

# Set commands (for easy access)
/setcommands
[Select your bot]
status - Get current bot status
balance - Check account balance
positions - View open positions
stop - Emergency stop trading
```

---

## Step 2: Get Your Chat ID

### Method 1: Use IDBot (Easiest)

1. Search for `@myidbot` in Telegram
2. Start conversation: `/start`
3. Send: `/getid`
4. Bot will reply with your chat ID:
   ```
   Your user ID: 123456789
   ```
5. **SAVE THIS NUMBER** - This is your `TELEGRAM_CHAT_ID`

### Method 2: Manual API Call

1. Send any message to your bot (e.g., "Hello")
2. Open this URL in browser (replace `<BOT_TOKEN>` with your token):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```

   Example:
   ```
   https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567/getUpdates
   ```

3. Find your chat ID in the JSON response:
   ```json
   {
     "ok": true,
     "result": [{
       "message": {
         "chat": {
           "id": 123456789,  // <-- This is your chat ID
           "first_name": "John",
           "type": "private"
         }
       }
     }]
   }
   ```

4. **SAVE THE `id` VALUE** - This is your `TELEGRAM_CHAT_ID`

---

## Step 3: Configure Notification Service

### 3.1 Update Environment Variables

**File:** `/mnt/d/Bimo_max/crypto-trading-bot/services/notification-service/.env`

```bash
# ==========================================
# TELEGRAM CONFIGURATION
# ==========================================
# CHANGE THIS: Set to true to enable
TELEGRAM_ENABLED=true

# CHANGE THIS: Your bot token from BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567

# CHANGE THIS: Your chat ID from @myidbot
TELEGRAM_CHAT_ID=123456789

# ==========================================
# ALERT SETTINGS (Recommended Configuration)
# ==========================================
# Alert on every trade execution
ALERT_ON_TRADE=true

# Alert on profitable trades
ALERT_ON_PROFIT=true

# Alert on losing trades
ALERT_ON_LOSS=true

# Alert when daily loss limit is reached (CRITICAL!)
ALERT_ON_DAILY_LIMIT=true

# Alert on system errors
ALERT_ON_ERROR=true

# Alert when bot starts
ALERT_ON_STARTUP=true

# ==========================================
# ALERT THRESHOLDS
# ==========================================
# Minimum profit/loss to trigger alerts (in USD)

# Only alert if profit > $10 (reduce spam)
MIN_PROFIT_ALERT=10.0

# Alert on any loss (important for risk management)
MIN_LOSS_ALERT=5.0
```

### 3.2 Save and Close

After editing, save the file. The service will read these values on restart.

---

## Step 4: Restart Notification Service

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot

# Rebuild notification service to pick up new config
docker-compose build notification-service

# Restart service
docker-compose up -d notification-service

# Check logs for startup
docker-compose logs -f notification-service
```

**Expected log output:**
```
notification-service_1  | INFO: Notification service starting...
notification-service_1  | INFO: Telegram notifications ENABLED
notification-service_1  | INFO: Email notifications DISABLED
notification-service_1  | INFO: Service ready on port 8006
```

---

## Step 5: Test Notifications

### 5.1 Health Check

```bash
curl http://localhost:8006/health | jq .
```

**Expected response:**
```json
{
  "status": "healthy",
  "service": "notification-service",
  "telegram_enabled": true,
  "email_enabled": false
}
```

### 5.2 Send Test Alert

```bash
# Test trade alert
curl -X POST "http://localhost:8006/api/v1/notify/trade" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "action": "BUY",
    "quantity": 0.001,
    "entry_price": 37500.50,
    "stop_loss": 36750.00,
    "take_profit": 38625.00,
    "timestamp": "2025-11-14T15:30:00Z"
  }'
```

**You should receive on Telegram:**
```
🚀 TRADE EXECUTED

Symbol: BTCUSDT
Action: BUY
Quantity: 0.001
Entry Price: $37,500.50
Stop Loss: $36,750.00
Take Profit: $38,625.00
Time: 2025-11-14 15:30:00 UTC

Risk/Reward: 1:1.5
```

### 5.3 Test Error Alert

```bash
# Test error notification
curl -X POST "http://localhost:8006/api/v1/notify/error" \
  -H "Content-Type: application/json" \
  -d '{
    "service": "trading-engine",
    "error": "Connection timeout to Bybit API",
    "severity": "WARNING",
    "timestamp": "2025-11-14T15:35:00Z"
  }'
```

**You should receive on Telegram:**
```
⚠️ SYSTEM ERROR

Service: trading-engine
Error: Connection timeout to Bybit API
Severity: WARNING
Time: 2025-11-14 15:35:00 UTC

Please investigate immediately.
```

### 5.4 Test Startup Alert

```bash
# Restart service to trigger startup alert
docker-compose restart notification-service
```

**You should receive on Telegram:**
```
✅ BOT STARTED

Crypto Trading Bot is now online.
Monitoring enabled.
Paper Trading Mode: Active

System ready at 2025-11-14 15:40:00 UTC
```

---

## Step 6: Customize Alert Settings

### Alert Types Configuration

**File:** `services/notification-service/.env`

#### Reduce Spam (Recommended for Paper Trading)
```bash
# Only alert on important events
ALERT_ON_TRADE=true           # All trades
ALERT_ON_PROFIT=false         # Disable profit alerts (too noisy)
ALERT_ON_LOSS=true            # Only losses (important)
ALERT_ON_DAILY_LIMIT=true     # CRITICAL - always enable
ALERT_ON_ERROR=true           # System issues
ALERT_ON_STARTUP=false        # Disable startup spam

# Higher thresholds
MIN_PROFIT_ALERT=50.0         # Only alert if profit > $50
MIN_LOSS_ALERT=10.0           # Alert on any loss > $10
```

#### Maximum Monitoring (Recommended for Live Trading)
```bash
# Alert on everything
ALERT_ON_TRADE=true
ALERT_ON_PROFIT=true
ALERT_ON_LOSS=true
ALERT_ON_DAILY_LIMIT=true
ALERT_ON_ERROR=true
ALERT_ON_STARTUP=true

# Low thresholds
MIN_PROFIT_ALERT=1.0
MIN_LOSS_ALERT=1.0
```

#### Silent Mode (Development Only)
```bash
# Disable most alerts
ALERT_ON_TRADE=false
ALERT_ON_PROFIT=false
ALERT_ON_LOSS=false
ALERT_ON_DAILY_LIMIT=true     # Keep critical alerts
ALERT_ON_ERROR=true
ALERT_ON_STARTUP=false
```

---

## Step 7: Integration with Trading Engine

The trading engine automatically sends notifications when:

1. **Trade Executed** - Any BUY/SELL order filled
2. **Position Closed** - Stop-loss or take-profit hit
3. **Daily Limit Reached** - Risk management triggered
4. **API Error** - Connection failures or order rejections

**No additional configuration needed** - notifications happen automatically once enabled.

---

## Advanced: Group Notifications

### For Team Monitoring

1. Create a Telegram group
2. Add your bot to the group:
   - Group Settings → Add Members → [Your Bot Name]
3. Make bot admin (optional):
   - Group Settings → Edit → Administrators → Add
4. Get group chat ID:
   ```bash
   # Send message in group mentioning your bot
   # Then visit:
   https://api.telegram.org/bot<TOKEN>/getUpdates

   # Look for "chat": {"id": -1234567890, "type": "group"}
   # Negative ID = group
   ```
5. Update `.env` with group chat ID:
   ```bash
   TELEGRAM_CHAT_ID=-1234567890
   ```

**Benefits:**
- Multiple people get alerts
- Team can discuss trades in real-time
- Shared accountability

---

## Troubleshooting

### Issue 1: Bot Not Responding
```
Error: Telegram API returned 404 Not Found
```

**Solutions:**
1. Verify bot token is correct (no extra spaces)
2. Check if token was revoked:
   - Talk to @BotFather
   - Send `/mybots`
   - Select your bot
   - Check API Token
3. Regenerate token if needed:
   - @BotFather → `/mybots` → [Your Bot] → API Token → Revoke & Generate New

### Issue 2: Wrong Chat ID
```
Error: Telegram API returned 400 Bad Request: chat not found
```

**Solutions:**
1. Verify chat ID is a number (not username)
2. Make sure you sent at least one message to bot first
3. Re-check chat ID with @myidbot
4. For groups, ensure chat ID is negative (e.g., `-123456789`)

### Issue 3: Notifications Not Sent
```
Service shows healthy but no messages received
```

**Solutions:**
1. Check if notifications are enabled:
   ```bash
   curl http://localhost:8006/api/v1/config | jq .
   ```
2. Verify alert thresholds aren't too high
3. Check notification service logs:
   ```bash
   docker-compose logs -f notification-service | grep ERROR
   ```
4. Test with manual API call (Step 5.2)

### Issue 4: Rate Limiting
```
Error: Telegram API returned 429 Too Many Requests
```

**Solutions:**
1. Telegram allows 30 messages/second max
2. Reduce alert frequency in `.env`
3. Increase `MIN_PROFIT_ALERT` and `MIN_LOSS_ALERT`
4. Disable `ALERT_ON_TRADE` if trading very frequently (>100 trades/day)

---

## Email Notifications (Alternative)

If you prefer email over Telegram:

### Gmail Setup

1. **Enable 2FA** on your Google account
2. **Generate App Password:**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and "Other (Custom name)"
   - Name: "Crypto Trading Bot"
   - Copy the 16-character password

3. **Update `.env`:**
```bash
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your.email@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop  # 16-char app password
EMAIL_FROM=your.email@gmail.com
EMAIL_TO=your.email@gmail.com,partner@gmail.com  # Multiple recipients
```

4. **Restart service:**
```bash
docker-compose restart notification-service
```

**Note:** Email is slower than Telegram (30s-2min vs 1-2s)

---

## Security Best Practices

**DO:**
- ✅ Keep bot token secret (treat like password)
- ✅ Only share chat ID with trusted team members
- ✅ Use private chats (not public channels)
- ✅ Enable 2FA on Telegram account
- ✅ Revoke old bot tokens when creating new ones

**DON'T:**
- ❌ Share bot token publicly
- ❌ Commit token to git (use `.env` only)
- ❌ Add bot to public groups
- ❌ Allow unknown users to message bot
- ❌ Use same bot for multiple projects

---

## Alert Examples

### Trade Execution
```
🚀 TRADE EXECUTED

Symbol: ETHUSDT
Action: SELL
Quantity: 0.05
Entry Price: $2,450.30
Stop Loss: $2,523.06
Take Profit: $2,304.79
Time: 2025-11-14 16:20:00 UTC

Risk/Reward: 1:2.0
```

### Position Closed (Profit)
```
💰 POSITION CLOSED - PROFIT

Symbol: BTCUSDT
Action: BUY → SELL
Entry Price: $37,250.00
Exit Price: $38,125.50
Quantity: 0.001
Profit: +$0.88 (+2.35%)
Duration: 4.5 hours

Great trade!
```

### Position Closed (Loss)
```
❌ POSITION CLOSED - LOSS

Symbol: SOLUSDT
Action: BUY → SELL (Stop Loss Hit)
Entry Price: $105.40
Exit Price: $103.31
Quantity: 1.0
Loss: -$2.09 (-1.98%)
Duration: 2.1 hours

Review strategy for SOLUSDT.
```

### Daily Loss Limit
```
🚨 EMERGENCY: DAILY LOSS LIMIT REACHED

Total Loss Today: -$500.00 (-5.00%)
Trades Today: 12 (4 wins, 8 losses)

🛑 TRADING STOPPED AUTOMATICALLY

No new trades will be executed until tomorrow.
Review your strategy and risk management.
```

### System Error
```
⚠️ SYSTEM ERROR

Service: bybit-connector
Error: WebSocket connection lost
Severity: ERROR
Time: 2025-11-14 16:45:00 UTC

Auto-reconnect in progress...
Monitor closely.
```

---

## Next Steps

After enabling Telegram notifications:

1. **Test thoroughly** - Send test messages for all alert types
2. **Adjust thresholds** - Fine-tune what triggers alerts
3. **Monitor for 24 hours** - Ensure alerts are working during trading
4. **Set quiet hours** (optional) - Mute non-critical alerts at night
5. **Add team members** (optional) - Create group for shared monitoring

---

## Support

- **Telegram Bot API Docs:** https://core.telegram.org/bots/api
- **BotFather Commands:** Send `/help` to @BotFather
- **Get Chat ID:** Talk to @myidbot
- **Project Issues:** Check `/crypto-trading-bot/docs/TROUBLESHOOTING.md`

---

**⚠️ IMPORTANT:**

Notifications are critical for risk management. NEVER disable:
- `ALERT_ON_DAILY_LIMIT` - Prevents catastrophic losses
- `ALERT_ON_ERROR` - Keeps you informed of system failures

**These alerts can save you thousands of dollars.**
