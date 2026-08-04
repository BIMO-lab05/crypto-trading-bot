# Bybit API Setup Guide
**Last Updated:** 2025-11-14
**Purpose:** Configure real Bybit API keys to enable live market data collection and trading

---

## Overview

The crypto trading bot currently uses **test/mock data** which has unrealistic price movements. To enable:
- ✅ Real market data collection
- ✅ Accurate backtesting
- ✅ Paper trading validation
- ✅ Live trading (future)

You need to configure authentic Bybit API credentials.

---

## Prerequisites

- Bybit account (create at https://www.bybit.com)
- Email verification completed
- 2FA enabled (recommended for security)
- Understanding of API key security risks

---

## Step 1: Choose Your Environment

### Testnet (Recommended for Development)
- **URL:** https://testnet.bybit.com
- **Pros:**
  - Free virtual funds ($100,000 USDT)
  - No financial risk
  - Full API functionality
  - Same data as mainnet
- **Cons:**
  - Cannot withdraw real money
  - Some features may be limited
- **Use For:** Development, testing, backtesting, paper trading validation

### Mainnet (Production Only)
- **URL:** https://www.bybit.com
- **Pros:**
  - Real trading with real funds
  - Full platform features
- **Cons:**
  - Financial risk
  - Requires capital deposit
- **Use For:** Live trading after 30+ days of paper trading validation

**⚠️ RECOMMENDATION:** Start with testnet. Only move to mainnet after:
- ✅ 90+ days of data collected
- ✅ Backtests show positive results
- ✅ Paper trading validated for 30+ days
- ✅ All risk management tested

---

## Step 2: Create API Keys (Testnet)

### 2.1 Register Testnet Account
1. Go to https://testnet.bybit.com
2. Click **Sign Up** (top right)
3. Use your email or Google account
4. Verify email
5. Set strong password
6. Enable 2FA (Google Authenticator recommended)

### 2.2 Get Free Testnet Funds
1. Login to testnet dashboard
2. Navigate to **Assets** → **USDT**
3. Look for testnet faucet (or contact support for test funds)
4. You should receive ~100,000 USDT virtual balance

### 2.3 Generate API Keys
1. Click your **profile icon** (top right)
2. Go to **API Management** → **API Keys**
3. Click **Create New Key**
4. Select **System-generated API Keys**

**Configuration:**
```
API Key Type: System-generated
API Key Name: crypto-trading-bot-dev
Key Permissions:
  ✅ Read-Write
  ⬜ NO IP Restriction (for development)
  ✅ Read Market Data
  ✅ Read Position
  ✅ Trade (only if you want paper trading)
  ⬜ Withdraw (NEVER enable for bots)

For production:
  ✅ IP Restriction: [Your Server IP]
```

5. Click **Submit**
6. **Complete 2FA verification**
7. **SAVE IMMEDIATELY:**
   - API Key: `xxxxxxxxxxx`
   - API Secret: `yyyyyyyyyyyy`

   ⚠️ **SECRET IS SHOWN ONLY ONCE** - Save to secure location (password manager)

---

## Step 3: Update Service Configuration

### 3.1 Update Bybit Connector Service

**File:** `services/bybit-connector/.env`

```bash
# Bybit API Configuration
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=true  # Set to false for mainnet
BYBIT_BASE_URL=https://api-testnet.bybit.com  # Change for mainnet

# Trading Mode
PAPER_TRADING=true  # ALWAYS start with paper trading

# Rate Limiting
MAX_REQUESTS_PER_SECOND=10
API_TIMEOUT=30

# WebSocket Configuration
WS_RECONNECT_DELAY=5
WS_MAX_RECONNECT_ATTEMPTS=10
```

### 3.2 Update Market Data Service

**File:** `services/market-data-service/.env`

```bash
# Bybit Connection
BYBIT_CONNECTOR_URL=http://bybit-connector:8001
BYBIT_API_KEY=your_api_key_here  # Same as bybit-connector

# Data Collection
COLLECTION_ENABLED=true
COLLECTION_INTERVAL=300  # 5 minutes (300 seconds)

# Symbols to Track
SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT

# Intervals to Collect
INTERVALS=1,5,15,60,240,1440  # 1m, 5m, 15m, 1h, 4h, 1d

# Database
DATABASE_URL=postgresql://crypto_user:crypto_pass@timescaledb:5432/crypto_trading

# Redis Cache
REDIS_URL=redis://redis:6379/0
CACHE_TTL=3600  # 1 hour
```

### 3.3 Security Best Practices

**DO:**
- ✅ Use environment variables (NEVER hardcode keys)
- ✅ Add `.env` to `.gitignore`
- ✅ Use different keys for testnet/mainnet
- ✅ Enable IP restrictions in production
- ✅ Rotate keys every 90 days
- ✅ Use read-only keys when possible
- ✅ Monitor API key usage regularly

**DON'T:**
- ❌ Commit API keys to git
- ❌ Share keys via email/Slack
- ❌ Enable withdrawal permissions
- ❌ Use same keys across environments
- ❌ Disable 2FA
- ❌ Use API keys with admin privileges

---

## Step 4: Restart Services

### 4.1 Rebuild Containers

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot

# Rebuild services that need API keys
docker-compose build bybit-connector market-data

# Restart services
docker-compose up -d bybit-connector market-data
```

### 4.2 Verify Connectivity

```bash
# Check bybit-connector health
curl http://localhost:8001/health | jq .

# Expected output:
{
  "status": "healthy",
  "service": "bybit-connector",
  "api_connected": true,
  "testnet": true
}

# Check market-data health
curl http://localhost:8002/health | jq .

# Expected output:
{
  "status": "healthy",
  "service": "market-data",
  "database_connected": true,
  "redis_connected": true,
  "collection_active": true
}
```

### 4.3 Test API Connection

```bash
# Test account balance retrieval
curl -X GET "http://localhost:8001/api/v1/account/balance" | jq .

# Expected output (testnet):
{
  "success": true,
  "data": {
    "USDT": {
      "available_balance": 100000.0,
      "wallet_balance": 100000.0
    }
  }
}

# Test market data retrieval
curl -X GET "http://localhost:8002/api/v1/klines/BTCUSDT?interval=60&limit=10" | jq .

# Expected output:
{
  "success": true,
  "count": 10,
  "data": [
    {
      "timestamp": "2025-11-14T14:00:00Z",
      "open": 37250.5,
      "high": 37380.2,
      "low": 37200.0,
      "close": 37350.8,
      "volume": 1234.56
    },
    ...
  ]
}
```

---

## Step 5: Start Data Collection

### 5.1 Trigger Initial Collection

```bash
# Collect 90 days of historical data for backtesting
curl -X POST "http://localhost:8002/api/v1/collect/kline" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_internal_api_key" \
  -d '{
    "symbol": "BTCUSDT",
    "interval": "60",
    "days_back": 90
  }'

# Repeat for each symbol
for symbol in ETHUSDT BNBUSDT SOLUSDT XRPUSDT ADAUSDT DOGEUSDT; do
  curl -X POST "http://localhost:8002/api/v1/collect/kline" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your_internal_api_key" \
    -d "{\"symbol\":\"$symbol\",\"interval\":\"60\",\"days_back\":90}"
  sleep 2
done
```

### 5.2 Enable Automated Collection

The market-data service should automatically collect new candles every 5 minutes based on `COLLECTION_INTERVAL` setting.

**Verify automated collection:**
```bash
# Check service logs
docker-compose logs -f market-data

# Expected log output every 5 minutes:
# INFO: Collecting kline data for BTCUSDT (60m)
# INFO: Saved 1 new candle(s) to database
```

### 5.3 Monitor Data Accumulation

```bash
# Check how much data you have
curl "http://localhost:8002/api/v1/klines/BTCUSDT?interval=60&limit=1000" | jq '.count'

# Day 1: ~24 candles
# Day 7: ~168 candles
# Day 30: ~720 candles
# Day 90: ~2160 candles (ready for ML training)
```

---

## Step 6: Wait for Data Accumulation

### Timeline

| Days | Candles | Readiness |
|------|---------|-----------|
| 1 | 24 | ❌ Insufficient |
| 7 | 168 | ⚠️ Minimal backtesting |
| 30 | 720 | ✅ Basic ML training |
| 90 | 2,160 | ✅ Full production ready |

**Recommended Timeline:**
- **Week 1:** Verify data collection is working (24-168 candles)
- **Week 2-4:** Wait for 30 days of data accumulation
- **Month 2-3:** Accumulate 90 days for robust ML training
- **Month 4+:** Begin paper trading with validated strategies

---

## Step 7: Validate Data Quality

### 7.1 Check for Gaps

```bash
# Download recent data
curl "http://localhost:8002/api/v1/klines/BTCUSDT?interval=60&limit=720" > btc_data.json

# Analyze for missing timestamps
python3 << 'EOF'
import json
from datetime import datetime, timedelta

with open('btc_data.json') as f:
    data = json.load(f)['data']

timestamps = [datetime.fromisoformat(d['timestamp'].replace('Z', '+00:00')) for d in data]
timestamps.sort()

# Check for gaps > 1 hour
gaps = []
for i in range(len(timestamps) - 1):
    diff = (timestamps[i+1] - timestamps[i]).total_seconds() / 3600
    if diff > 1.5:  # More than 90 minutes gap
        gaps.append({
            'after': timestamps[i],
            'before': timestamps[i+1],
            'gap_hours': diff
        })

if gaps:
    print(f"⚠️ Found {len(gaps)} data gaps:")
    for gap in gaps[:5]:
        print(f"  Gap: {gap['gap_hours']:.1f}h between {gap['after']} and {gap['before']}")
else:
    print("✅ No significant data gaps found")
EOF
```

### 7.2 Validate Price Ranges

```bash
# Check if prices are realistic
curl "http://localhost:8002/api/v1/klines/BTCUSDT?interval=60&limit=100" | jq -r '.data[] | "\(.timestamp): \(.close)"' | head

# BTCUSDT should be $30K-$90K range (as of 2025)
# NOT $100K-$600K (that's mock data)
```

---

## Step 8: Update ML Models with Real Data

After 30+ days of data collection:

```bash
# Retrain LSTM models with real data
for symbol in BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT; do
  echo "Training $symbol model with real data..."
  curl -X POST "http://localhost:8007/api/v1/models/train" \
    -H "Content-Type: application/json" \
    -d "{
      \"symbol\": \"$symbol\",
      \"interval\": \"60\",
      \"lookback_days\": 90,
      \"force_retrain\": true
    }"
  sleep 10
done
```

---

## Step 9: Re-run Backtests

After 90 days of real data:

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/backtesting

# Run Phase 1 vs Phase 3 comparison with real data
python3 run_phase_comparison.py \
  --symbols BTCUSDT ETHUSDT BNBUSDT \
  --interval 60 \
  --days 90 \
  --capital 10000

# Check results
cat backtesting/results/BACKTEST_COMPARISON_SUMMARY_*.md
```

**Expected Improvement:**
- ❌ Current: 0 trades (mock data too volatile)
- ✅ With real data: 10-50 trades per 90 days
- ✅ Realistic P&L metrics
- ✅ Valid risk-adjusted returns

---

## Troubleshooting

### Issue 1: API Authentication Failed
```
Error: {"retCode":10003,"retMsg":"Invalid API key"}
```

**Solutions:**
1. Verify API key is copied correctly (no spaces)
2. Check if using testnet key with testnet URL
3. Regenerate API key if compromised
4. Verify 2FA was completed during key creation

### Issue 2: Rate Limit Exceeded
```
Error: {"retCode":10006,"retMsg":"Too many requests"}
```

**Solutions:**
1. Reduce `COLLECTION_INTERVAL` from 300 to 600 (10 minutes)
2. Reduce number of symbols being tracked
3. Implement exponential backoff in bybit-connector
4. Upgrade to higher rate limit tier (paid accounts)

### Issue 3: No Data Collected
```
INFO: Collecting kline data for BTCUSDT (60m)
INFO: Saved 0 new candle(s) to database
```

**Solutions:**
1. Check if candle already exists (query database directly)
2. Verify symbol name matches Bybit format (BTCUSDT not BTC-USDT)
3. Check database connection: `docker-compose logs timescaledb`
4. Manually trigger collection with force flag

### Issue 4: Testnet Funds Depleted
```
Error: {"retCode":10004,"retMsg":"Insufficient balance"}
```

**Solutions:**
1. Request more testnet funds from Bybit support
2. Create new testnet account
3. Reduce position sizes in paper trading
4. Check if virtual funds have expiration policy

---

## Security Checklist

Before going to production:

- [ ] API keys stored in `.env` files only
- [ ] `.env` files added to `.gitignore`
- [ ] Different keys for testnet vs mainnet
- [ ] IP restrictions enabled for mainnet keys
- [ ] Withdrawal permissions disabled
- [ ] 2FA enabled on Bybit account
- [ ] Key rotation schedule set (90 days)
- [ ] Audit log monitoring enabled
- [ ] Emergency shutdown procedure documented
- [ ] Backup keys stored in encrypted vault

---

## Next Steps

1. **Complete this setup** → Enable real data collection
2. **Wait 30-90 days** → Let data accumulate
3. **Validate data quality** → Check for gaps and accuracy
4. **Retrain ML models** → Use real market data
5. **Re-run backtests** → Validate strategy performance
6. **Enable paper trading** → Test with simulated orders
7. **Monitor for 30 days** → Validate profitability
8. **Move to mainnet** → Only after validation succeeds

---

## Support

- **Bybit API Docs:** https://bybit-exchange.github.io/docs/
- **Testnet Dashboard:** https://testnet.bybit.com
- **Support:** support@bybit.com
- **Project Issues:** Check `/crypto-trading-bot/docs/TROUBLESHOOTING.md`

---

**⚠️ CRITICAL REMINDER:**

NEVER enable live trading until:
- ✅ 90+ days of real data collected
- ✅ Backtests show consistent profitability
- ✅ Paper trading validated for 30+ days
- ✅ All risk management tested
- ✅ Emergency procedures documented

**Paper trading first. Always.**
