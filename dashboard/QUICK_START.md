# Dashboard Quick Start Guide

**Version:** 2.0.0
**For:** Crypto Trading Bot Dashboard

---

## 1-Minute Setup

### Step 1: Start Dashboard Server
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/dashboard
python3 -m http.server 3000
```

### Step 2: Open in Browser
```
http://localhost:3000
```

### Step 3: Verify
- Check top-right shows "10/10" services healthy
- System status shows green indicator
- No red error messages

**Done!** You're ready to monitor your trading bot.

---

## Critical Information

### Port Requirement
**Dashboard MUST run on port 3000**

Why? All backend services have CORS configured for port 3000 only.

**Wrong:**
```bash
python3 -m http.server 8080  # ❌ Will cause CORS errors
```

**Correct:**
```bash
python3 -m http.server 3000  # ✅ Works perfectly
```

### Prerequisites
Before starting dashboard:
```bash
# Check all services are running
docker-compose ps

# All should show "Up" and "(healthy)"
# If not, start services:
docker-compose up -d
```

---

## Dashboard Sections

### Header
- **System Status:** Green = all good, Yellow = some issues, Red = problems
- **Trading Mode:** Paper Trading (test mode) or Live Trading
- **Last Update:** When data was last refreshed (auto-updates every 5 seconds)
- **Services Counter:** Shows X/10 healthy services

### Portfolio
- **Total Balance:** Your current portfolio value in USDT
- **Today's P&L:** Profit/loss for today (green = profit, red = loss)

### Trading Stats
- **Trades Today:** Number of trades executed today
- **Win Rate:** Percentage of profitable trades

### Risk Metrics
- **Max Drawdown:** Worst loss from peak
- **Daily Limit Remaining:** How much more you can lose today (5% limit)

### Service Health
Grid showing all 10 microservices:
- Green dot = service is healthy
- Red dot = service is down or unhealthy

Hover over services to see port numbers.

### Active Positions
Table showing your current open trades:
- **Symbol:** Trading pair (e.g., BTCUSDT)
- **Side:** BUY (long) or SELL (short)
- **Entry/Current:** Entry price vs current price
- **P&L:** Unrealized profit/loss
- **Actions:** Close individual positions

### Trading Controls
- **Start Auto Trading:** Begin automated trading
- **Stop Auto Trading:** Pause automated trading
- **🚨 EMERGENCY STOP:** Immediately halt all trading

---

## Common Tasks

### Monitor System Health
1. Open dashboard at http://localhost:3000
2. Check service grid shows all green dots
3. Verify "10/10" in top-right corner

### Check Portfolio Balance
1. Look at "Portfolio" card
2. See "Total Balance" value
3. Check "Today's P&L" (green = profit, red = loss)

### View Open Positions
1. Scroll to "Active Positions" section
2. See all open trades with live P&L
3. Click "Close" to close a position

### Start Trading
1. Click "Start Auto Trading" button
2. Confirm action in popup
3. Bot will begin processing signals

### Emergency Stop
1. Click red "🚨 EMERGENCY STOP" button
2. Confirm you want to stop
3. All trading halts immediately

---

## Troubleshooting

### Problem: Dashboard shows "Cannot Connect"
**Solution:**
```bash
# Check if services are running
docker-compose ps

# Restart if needed
docker-compose restart
```

### Problem: CORS errors in browser console
**Solution:**
```bash
# Make sure dashboard is on port 3000
# Stop current server and restart:
python3 -m http.server 3000
```

### Problem: All services show red dots
**Solution:**
```bash
# Check Docker containers
docker-compose ps

# Start services if not running
docker-compose up -d

# Wait 30 seconds for startup
# Refresh dashboard
```

### Problem: Dashboard not updating
**Solution:**
- Check timestamp in header (should update every 5 seconds)
- Press F5 to reload page
- Check browser console (F12) for errors
- Verify internet/network connection

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F5 | Refresh dashboard |
| Ctrl+R | Refresh dashboard |
| F12 | Open browser developer tools |
| Ctrl+Shift+I | Open browser developer tools |

---

## FAQ

**Q: Why must I use port 3000?**
A: Backend services have CORS security configured to only accept requests from port 3000. Other ports will be blocked.

**Q: Can I access from another computer?**
A: Not by default. Dashboard uses localhost. For network access, use:
```bash
python3 -m http.server 3000 --bind 0.0.0.0
# Then access via http://[your-ip]:3000
```

**Q: Is my data safe?**
A: Dashboard is for local use only. For production, add authentication and HTTPS.

**Q: How often does data update?**
A: Every 5 seconds automatically. You can also click "Refresh" buttons for immediate updates.

**Q: Can I run multiple dashboards?**
A: Yes, each browser window/tab will have independent view but show same data.

**Q: What if balance shows $10,000?**
A: That's the default paper trading balance. Execute trades to see it change.

---

## Getting Help

### Check Logs
```bash
# Service logs
docker-compose logs -f [service-name]

# All logs
docker-compose logs

# Dashboard server logs
# (Check terminal where you ran python3 -m http.server)
```

### Debug Mode
```bash
# Open browser console (F12)
# Check for error messages
# Look for red text or CORS errors
```

### Documentation
- Full README: `/dashboard/README.md`
- Changelog: `/dashboard/CHANGELOG.md`
- Testing Report: `/dashboard/TESTING_REPORT.md`
- System Status: `/SYSTEM_STATUS_COMPLETE.md`

---

## Safety Reminders

⚠️ **Important:**
- Dashboard is in PAPER TRADING mode by default (test money, not real)
- Emergency stop button is for critical situations only
- Always verify trades before executing
- Monitor risk metrics regularly
- Set stop-losses for all positions

---

## Next Steps

After dashboard is running:
1. Monitor service health daily
2. Review portfolio balance regularly
3. Check active positions for P&L
4. Adjust risk settings as needed
5. Review trade history periodically

---

**Quick Reference URLs:**
- Dashboard: http://localhost:3000
- API Gateway: http://localhost:8000/docs
- Trading Engine: http://localhost:8005/docs
- Portfolio Manager: http://localhost:8003/docs

---

**Need More Help?**
- Check README.md for detailed documentation
- Review TROUBLESHOOTING section in README
- Check Docker logs for service errors
- Verify all containers are healthy

**Last Updated:** 2025-11-17
**Version:** 2.0.0
