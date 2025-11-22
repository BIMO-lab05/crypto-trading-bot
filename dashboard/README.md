# Crypto Trading Bot - Real-Time Dashboard

**Version:** 2.0.0
**Last Updated:** 2025-11-17

---

## Overview

A lightweight, real-time monitoring dashboard for the crypto trading bot. Built with vanilla HTML/CSS/JavaScript - no build process or dependencies required.

**Features:**
- ✅ Real-time service health monitoring (all 10 microservices)
- ✅ Portfolio balance and P&L tracking
- ✅ Active positions display with live P&L
- ✅ Trading controls (start/stop/emergency stop)
- ✅ Auto-refresh every 5 seconds
- ✅ Responsive design
- ✅ Dark mode UI optimized for monitoring
- ✅ Aggregated health checks via API Gateway (optimized performance)
- ✅ Automatic retry logic with connection error handling
- ✅ CORS-enabled for seamless backend communication

---

## IMPORTANT: Port Configuration

**🚨 CRITICAL: The dashboard MUST run on port 3000**

All backend microservices have CORS configured to only accept requests from `http://localhost:3000`. Running the dashboard on any other port will result in CORS errors and prevent the dashboard from accessing backend services.

**Why port 3000?**
- All 10 microservices have `http://localhost:3000` in their CORS allowed origins
- This ensures secure cross-origin communication
- Prevents unauthorized access from other origins

---

## Quick Start

### Option 1: Local HTTP Server on Port 3000 (REQUIRED)

**Python (Recommended):**
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/dashboard
python3 -m http.server 3000
```
Then open http://localhost:3000

**Node.js:**
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/dashboard
npx serve -p 3000
```
Then open http://localhost:3000

**Alternative Python:**
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/dashboard
python -m http.server 3000
```

### Option 2: Direct File Access (NOT RECOMMENDED)

```bash
# ⚠️ WARNING: Opening directly will cause CORS errors
# Only use for viewing UI, not for functionality

# Windows
start index.html

# Linux
xdg-open index.html

# macOS
open index.html
```

**Note:** Direct file access (`file://` protocol) will encounter CORS restrictions. Use Option 1 instead.

### Option 3: Add to Docker Compose

Add to `docker-compose.yml`:

```yaml
services:
  dashboard:
    image: nginx:alpine
    ports:
      - "3000:80"  # Must expose on port 3000 for CORS
    volumes:
      - ./dashboard:/usr/share/nginx/html:ro
    networks:
      - crypto-net
```

Then access at http://localhost:3000

---

## Prerequisites

**Required:**
- All 10 microservices running (ports 8000-8009)
- Docker containers healthy
- Browser with JavaScript enabled
- Dashboard served on port 3000 (for CORS)

**Verify Services Running:**
```bash
# Check API Gateway aggregated health (recommended)
curl -s http://localhost:8000/health

# Or check individual services
for port in {8000..8009}; do
  curl -s http://localhost:$port/health | jq '.status'
done
```

---

## CORS Configuration

The dashboard communicates with backend services that have CORS (Cross-Origin Resource Sharing) configured.

**Allowed Origins:**
- `http://localhost:3000` (dashboard port)
- `http://localhost` (legacy support)
- Other configured origins per service

**What this means:**
- Dashboard requests to backend services will only work from port 3000
- Attempting to access from other ports will result in CORS errors
- This is a security feature to prevent unauthorized access

**Troubleshooting CORS:**
If you see CORS errors in browser console:
1. Verify dashboard is running on port 3000
2. Check that all services are running: `docker-compose ps`
3. Restart services if needed: `docker-compose restart`
4. Check browser console (F12) for specific error messages

---

## Dashboard Sections

### 1. Header - System Status

**Displays:**
- Overall system health indicator (green/yellow/red)
- Trading mode (Paper Trading / Live Trading)
- Last update timestamp
- Service count (X/10 healthy)

**Health Indicators:**
- 🟢 **Green (All Systems Operational):** 10/10 services healthy
- 🟡 **Yellow (Some Services Down):** 7-9 services healthy
- 🔴 **Red (System Degraded):** <7 services healthy

### 2. Portfolio Summary

**Metrics:**
- **Total Balance:** Current portfolio value in USDT
- **Today's P&L:** Daily profit/loss in $ and %
- **Trades Today:** Number of trades executed
- **Win Rate:** Percentage of winning trades

**Color Coding:**
- Green text = Positive P&L
- Red text = Negative P&L

### 3. Trading Stats

**Shows:**
- Active positions count
- Total trades today
- Win rate percentage
- Other performance metrics

### 4. Risk Metrics

**Displays:**
- **Max Drawdown:** Worst peak-to-trough loss
- **Daily Limit Remaining:** How much more you can lose today (5% limit)
- Circuit breaker status

**Alerts:**
- Warning if daily loss approaching 5%
- Red indicator if circuit breaker activated

### 5. Service Health Grid

**Monitors 10 Services:**
1. api-gateway (Port 8000)
2. bybit-connector (Port 8001)
3. market-data (Port 8002)
4. portfolio-manager (Port 8003)
5. technical-analysis (Port 8004)
6. trading-engine (Port 8005)
7. notification (Port 8006)
8. ml-prediction (Port 8007)
9. sentiment-analysis (Port 8008)
10. risk-metrics (Port 8009)

**Status:**
- 🟢 Green dot = Healthy
- 🔴 Red dot = Unavailable/Unhealthy

### 6. Active Positions Table

**Columns:**
- **Symbol:** Trading pair (e.g., BTCUSDT)
- **Side:** BUY (long) or SELL (short)
- **Entry:** Entry price
- **Current:** Current market price
- **Quantity:** Position size
- **P&L:** Unrealized profit/loss (green=profit, red=loss)
- **Actions:** Close button

**Features:**
- Real-time P&L updates
- One-click position closing
- Close All button for emergency

### 7. Trading Controls

**Buttons:**
- **Start Auto Trading:** Begin automated signal processing
- **Stop Auto Trading:** Halt signal processing (keeps positions open)
- **🚨 EMERGENCY STOP:** Immediately halt all trading (critical situations)

**Safety:**
- All actions require confirmation
- Emergency stop highlighted in red
- Clear warnings before execution

---

## Auto-Refresh Behavior

**Update Frequency:** Every 5 seconds

**What Updates:**
- Service health status
- Portfolio balance
- Active positions (including unrealized P&L)
- Trading statistics
- Alerts

**Manual Refresh:**
- Click "Refresh" buttons for on-demand updates
- Browser refresh (F5) resets entire dashboard

---

## Alerts & Warnings

### Built-in Alerts

**Mock Data Warning (Orange):**
```
⚠️ Mock Data Detected: System is using test data with unrealistic prices.
```
**Action:** Configure real Bybit API keys (see BYBIT_API_SETUP_GUIDE.md)

**Notifications Disabled (Blue):**
```
ℹ️ Notifications Disabled: Telegram alerts are not enabled.
```
**Action:** Configure Telegram bot (see TELEGRAM_NOTIFICATIONS_SETUP.md)

### Future Alerts (Coming Soon)

- Daily loss limit approaching
- Circuit breaker activated
- Position stop-loss hit
- API connection failures
- High memory/CPU usage

---

## Troubleshooting

### Dashboard Shows "Error Loading"

**Problem:** Cannot connect to services

**Solutions:**
1. Verify all services are running:
   ```bash
   docker-compose ps
   ```
2. Check service health manually:
   ```bash
   curl http://localhost:8003/health
   ```
3. Restart services:
   ```bash
   docker-compose restart
   ```
4. Check browser console for errors (F12)

### Services Show Red Dots

**Problem:** One or more services unhealthy

**Solutions:**
1. Check service logs:
   ```bash
   docker-compose logs -f [service-name]
   ```
2. Restart unhealthy service:
   ```bash
   docker-compose restart [service-name]
   ```
3. Rebuild if code changed:
   ```bash
   docker-compose build [service-name]
   docker-compose up -d [service-name]
   ```

### CORS Errors in Browser Console

**Problem:** Cross-origin request blocked

**Error Example:**
```
Access to fetch at 'http://localhost:8000/health' from origin 'http://localhost:8080'
has been blocked by CORS policy
```

**Solutions:**

1. **MOST COMMON FIX:** Run dashboard on port 3000 (REQUIRED)
   ```bash
   # Stop current server
   # Then start on correct port:
   cd /mnt/d/Bimo_max/crypto-trading-bot/dashboard
   python3 -m http.server 3000
   ```
   Access at http://localhost:3000

2. **If services not responding:** Check all Docker containers are running
   ```bash
   docker-compose ps
   # All should show "Up" and "(healthy)"
   ```

3. **If still issues:** Restart services to reload CORS configuration
   ```bash
   docker-compose restart
   ```

4. **For development only:** Temporarily disable browser CORS
   - Chrome: `chrome --disable-web-security --user-data-dir=/tmp/chrome`
   - **WARNING:** Only for testing, creates security risk

### No Data Showing

**Problem:** Dashboard loads but shows $0 everywhere

**Solutions:**
1. Ensure portfolio-manager has data:
   ```bash
   curl http://localhost:8003/api/v1/balance
   ```
2. Check if paper trading initialized:
   ```bash
   curl http://localhost:8005/api/v1/paper/balance
   ```
3. Initialize paper trading if needed:
   ```bash
   curl -X POST http://localhost:8005/api/v1/paper/reset
   ```

---

## API Endpoints Used

The dashboard connects to these endpoints:

**Health Checks:**
```
GET http://localhost:{8000-8009}/health
```

**Portfolio:**
```
GET http://localhost:8003/api/v1/balance
```

**Positions:**
```
GET http://localhost:8005/api/v1/positions?status=open
POST http://localhost:8005/api/v1/positions/{id}/close
POST http://localhost:8005/api/v1/emergency/close-all
```

**Trading Control:**
```
POST http://localhost:8005/api/v1/start
POST http://localhost:8005/api/v1/stop
POST http://localhost:8005/api/v1/emergency/stop
```

---

## Customization

### Change Update Frequency

Edit line in `index.html`:
```javascript
updateInterval = setInterval(updateAll, 5000); // 5000ms = 5 seconds

// Change to 10 seconds:
updateInterval = setInterval(updateAll, 10000);
```

### Change Color Scheme

Modify CSS variables in `<style>` section:
```css
/* Background colors */
background: #0f1419;  /* Dark background */
background: #192734;  /* Card background */

/* Accent colors */
--primary: #3b82f6;   /* Blue */
--success: #10b981;   /* Green */
--warning: #f59e0b;   /* Orange */
--danger: #ef4444;    /* Red */
```

### Add New Metrics

Add new card to dashboard:
```html
<div class="card">
    <div class="card-header">
        <h2 class="card-title">Your Metric</h2>
    </div>
    <div class="metric">
        <div class="metric-label">Metric Label</div>
        <div class="metric-value" id="yourMetric">0</div>
    </div>
</div>
```

Add JavaScript to update it:
```javascript
async function updateYourMetric() {
    const response = await fetch('http://localhost:8xxx/api/v1/your-endpoint');
    const data = await response.json();
    document.getElementById('yourMetric').textContent = data.value;
}

// Add to updateAll() function
await updateYourMetric();
```

---

## Security Considerations

**⚠️ WARNING:** This dashboard is for LOCAL USE ONLY

**DO NOT:**
- ❌ Expose dashboard to the internet without authentication
- ❌ Use in production without proper security
- ❌ Share dashboard URL publicly
- ❌ Allow Cross-Origin requests from unknown domains

**TODO for Production:**
- Implement authentication (OAuth, JWT)
- Add HTTPS/TLS encryption
- Implement rate limiting
- Add audit logging
- Use environment-specific API URLs
- Implement role-based access control

---

## Performance Tips

**Optimize Loading:**
1. Reduce update frequency if CPU high:
   ```javascript
   updateInterval = setInterval(updateAll, 10000); // 10 seconds
   ```

2. Disable auto-refresh if not monitoring:
   ```javascript
   // Comment out in init() function
   // updateInterval = setInterval(updateAll, 5000);
   ```

3. Use browser caching for static assets

**Monitor Browser Performance:**
- Open DevTools (F12)
- Go to Performance tab
- Record while dashboard updates
- Look for slow functions

---

## Future Enhancements

**Planned Features:**

### Short-term
- [ ] Charts for P&L over time
- [ ] Trade history log viewer
- [ ] Signal strength visualization
- [ ] ML prediction confidence meters
- [ ] WebSocket for real-time updates (vs polling)

### Medium-term
- [ ] TradingView chart integration
- [ ] Custom alert configuration
- [ ] Performance analytics dashboard
- [ ] Backtest results viewer
- [ ] Strategy comparison tool

### Long-term
- [ ] Mobile app (React Native)
- [ ] Multi-account support
- [ ] Advanced charting tools
- [ ] AI-powered insights
- [ ] Social trading features

---

## Support & Documentation

**Related Docs:**
- [System Status](../SYSTEM_STATUS_COMPLETE.md) - Complete system assessment
- [Trading Engine Capabilities](../docs/TRADING_ENGINE_CAPABILITIES.md) - API reference
- [Deployment Runbook](../docs/DEPLOYMENT_RUNBOOK.md) - Operations guide

**Quick Links:**
- API Gateway Swagger: http://localhost:8000/docs
- Trading Engine API: http://localhost:8005/docs
- Portfolio Manager API: http://localhost:8003/docs

**Troubleshooting:**
- Check service logs: `docker-compose logs -f [service]`
- View all logs: `docker-compose logs`
- Restart all services: `docker-compose restart`

---

## FAQ

**Q: Why is the balance always $10,000?**
A: You're in paper trading mode with initial balance of $10,000. Execute trades to see balance change.

**Q: Can I use this in production?**
A: Not as-is. Add authentication, HTTPS, and security measures first.

**Q: How do I add my own trading pair?**
A: Configure in market-data service and trading-engine. Dashboard will automatically display it.

**Q: Can I run this on mobile?**
A: Yes, the dashboard is responsive. Access from mobile browser at http://[your-ip]:8080

**Q: Does this work offline?**
A: No, it requires connection to microservices on localhost. Services must be running.

**Q: Can multiple people view the dashboard simultaneously?**
A: Yes, if served via HTTP server. Each user gets independent view but see same data.

---

## License

Same license as main project.

---

## Version History

**v2.0.0 (2025-11-17)** - Performance & Reliability Update
- **BREAKING CHANGE:** Dashboard must now run on port 3000 for CORS compatibility
- **NEW:** Aggregated health checks via API Gateway (10x performance improvement)
- **NEW:** Automatic retry logic with connection error handling
- **NEW:** Better error messages and timeout management
- **IMPROVED:** Service health check reduced from 10 HTTP requests to 1
- **IMPROVED:** Timeout handling (5-10 second timeouts instead of 2-3 seconds)
- **IMPROVED:** Error handling for slow or unresponsive services
- **IMPROVED:** Connection status indicators with retry buttons
- **FIXED:** Position table now handles missing data gracefully
- **FIXED:** Portfolio updates don't clear on temporary errors
- **DOCUMENTATION:** Comprehensive CORS configuration guide
- **DOCUMENTATION:** Port 3000 requirement clearly explained

**v1.0.0 (2025-11-14)**
- Initial release
- Service health monitoring
- Portfolio display
- Position management
- Trading controls
- Auto-refresh every 5 seconds

---

## What's New in v2.0.0

### Performance Improvements

**Before (v1.0.0):**
- Made 10 separate HTTP requests to check service health
- Each request had 2-3 second timeout
- Total health check time: ~2-3 seconds (if all services respond)
- Could take 20-30 seconds if services are slow

**After (v2.0.0):**
- Makes 1 HTTP request to API Gateway aggregated endpoint
- API Gateway queries all services internally
- Total health check time: <1 second (even with slow services)
- 10x performance improvement

### Reliability Improvements

**Automatic Retry Logic:**
- Dashboard now retries failed connections automatically
- Shows retry counter (1/3, 2/3, 3/3)
- Stops auto-refresh after 3 failures to prevent spam
- Provides "Retry Connection" button for manual retry

**Better Timeout Handling:**
- Increased timeouts from 2-3 seconds to 5-10 seconds
- Accounts for slow Docker container responses
- Services have time to respond even under load

**Graceful Error Handling:**
- Errors don't clear existing data
- Shows specific error messages
- Maintains last known good state
- Better visual feedback for issues

### CORS Configuration

**Why Port 3000?**
All microservices have FastAPI CORS middleware configured with:
```python
allow_origins=[
    "http://localhost:3000",  # Dashboard port
    "http://localhost",
    # ... other origins
]
```

Running on any other port will trigger CORS security errors.

---

**Maintained By:** Crypto Trading Bot Development Team
**Last Updated:** 2025-11-17
**Access URL:** http://localhost:3000 (MUST use port 3000)
