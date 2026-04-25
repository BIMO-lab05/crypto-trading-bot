# Advanced Performance Metrics API Documentation
**Status:** ✅ COMPLETE - All 9 Metrics Implemented
**Last Updated:** 2026-01-08
**Phase:** 5.2 Enhancement - Sterling & Burke Ratios Added

---

## 📊 **IMPLEMENTATION SUMMARY**

### **All 9 Advanced Metrics Implemented (100%)**

| # | Metric | Status | Category |
|---|--------|--------|----------|
| 1 | **Omega ratio** | ✅ Implemented | Risk-Adjusted Returns |
| 2 | **Gain-to-pain ratio** | ✅ Implemented | Risk-Adjusted Returns |
| 3 | **Ulcer index** | ✅ Implemented | Drawdown Analysis |
| 4 | **Information ratio** | ✅ Implemented | Risk-Adjusted Returns |
| 5 | **Treynor ratio** | ✅ Implemented | Risk-Adjusted Returns |
| 6 | **Jensen's alpha** | ✅ Implemented | Benchmark Comparison |
| 7 | **Capture ratios (up/down)** | ✅ Implemented | Benchmark Comparison |
| 8 | **Sterling ratio** | ✅ **NEWLY ADDED** | Risk-Adjusted Returns |
| 9 | **Burke ratio** | ✅ **NEWLY ADDED** | Risk-Adjusted Returns |

---

## 🚀 **QUICK START**

### **Test the API (Trading Engine Must Be Running)**

```bash
# Check if trading engine is running
docker ps | grep crypto-bot-trading

# Test advanced metrics endpoint
curl http://localhost:8005/api/v1/analytics/metrics/risk-adjusted

# Get all metrics at once
curl http://localhost:8005/api/v1/analytics/metrics/all
```

---

## 📡 **API ENDPOINTS**

### **Base URL:** `http://localhost:8005/api/v1/analytics/metrics`

### **1. Risk-Adjusted Metrics**
```
GET /api/v1/analytics/metrics/risk-adjusted
```

**Returns ALL 9 risk-adjusted return metrics:**
- ✅ Sharpe Ratio
- ✅ Sortino Ratio
- ✅ Calmar Ratio
- ✅ **Omega Ratio**
- ✅ **Treynor Ratio**
- ✅ **Information Ratio**
- ✅ **Gain-to-Pain Ratio**
- ✅ **Sterling Ratio** (NEW)
- ✅ **Burke Ratio** (NEW)

**Example Response:**
```json
{
  "success": true,
  "metrics": {
    "sharpe_ratio": 1.85,
    "sortino_ratio": 2.34,
    "calmar_ratio": 3.12,
    "omega_ratio": 1.67,
    "treynor_ratio": 0.045,
    "information_ratio": 0.82,
    "gain_to_pain_ratio": 2.45,
    "sterling_ratio": 2.89,
    "burke_ratio": 1.92
  },
  "generated_at": "2026-01-08T22:30:00Z"
}
```

---

### **2. Drawdown Analysis**
```
GET /api/v1/analytics/metrics/drawdown
```

**Returns comprehensive drawdown metrics:**
- Max Drawdown
- Average Drawdown
- **Ulcer Index**
- Recovery Factor
- Pain Index
- Time Underwater
- Current Drawdown

**Example Response:**
```json
{
  "success": true,
  "metrics": {
    "max_drawdown": -8.5,
    "avg_drawdown": -3.2,
    "ulcer_index": 4.7,
    "recovery_factor": 3.5,
    "pain_index": 12.3,
    "time_underwater": 0.15,
    "current_drawdown": 0.0
  },
  "generated_at": "2026-01-08T22:30:00Z"
}
```

---

### **3. Win/Loss Metrics**
```
GET /api/v1/analytics/metrics/win-loss
```

**Returns:**
- Win rate
- Profit factor
- Payoff ratio
- Expectancy
- Kelly percentage
- Consecutive win/loss streaks

---

### **4. Risk Metrics**
```
GET /api/v1/analytics/metrics/risk
```

**Returns:**
- VaR (Value at Risk)
- CVaR (Conditional VaR)
- Beta
- Volatility
- Downside deviation
- Skewness
- Kurtosis

---

### **5. Efficiency Metrics**
```
GET /api/v1/analytics/metrics/efficiency
```

**Returns:**
- Average trade duration
- Trades per day/week/month
- Capital utilization
- Turnover ratio
- Holding period return

---

### **6. Benchmark Comparison**
```
GET /api/v1/analytics/metrics/benchmark
```

**Returns:**
- **Jensen's Alpha**
- Beta
- Correlation
- **Upside Capture Ratio**
- **Downside Capture Ratio**
- Tracking Error
- Information Ratio

**Example Response:**
```json
{
  "success": true,
  "metrics": {
    "strategy_return": 15.5,
    "benchmark_return": 12.3,
    "excess_return": 3.2,
    "alpha": 2.8,
    "beta": 1.15,
    "correlation": 0.82,
    "up_capture": 1.12,
    "down_capture": 0.88,
    "tracking_error": 3.5,
    "information_ratio": 0.91
  },
  "generated_at": "2026-01-08T22:30:00Z"
}
```

---

### **7. All Metrics (Complete Overview)**
```
GET /api/v1/analytics/metrics/all
```

**Returns:** All metrics from all categories in one response

---

### **8. Period Comparison**
```
GET /api/v1/analytics/metrics/compare?period=30
```

**Query Parameters:**
- `period` (default: 30) - Number of days to compare

**Returns:** Comparison between recent period and all-time metrics

---

### **9. Daily Performance Report**
```
GET /api/v1/analytics/report/daily?date=2026-01-08
```

**Query Parameters:**
- `date` (optional) - Date in YYYY-MM-DD format (defaults to today)

**Returns:** Comprehensive daily performance report

---

### **10. Monthly Performance Report**
```
GET /api/v1/analytics/report/monthly?month=2026-01
```

**Query Parameters:**
- `month` (optional) - Month in YYYY-MM format (defaults to current month)

**Returns:** Comprehensive monthly performance report

---

### **11. Monte Carlo Simulation**
```
POST /api/v1/analytics/report/monte-carlo
```

**Request Body:**
```json
{
  "num_simulations": 1000,
  "num_days": 252,
  "confidence_level": 0.95
}
```

**Returns:** Monte Carlo simulation results with risk projections

---

## 📈 **METRIC DEFINITIONS**

### **Risk-Adjusted Returns**

#### **1. Omega Ratio**
```
Probability-weighted ratio of gains to losses at a threshold
Formula: Sum(Returns above threshold) / Sum(|Returns below threshold|)
Higher is better | Threshold typically 0 (risk-free rate)
```

#### **2. Gain-to-Pain Ratio**
```
Sum of all returns / Absolute sum of negative returns
Higher is better | Measures reward vs. pain
```

#### **3. Information Ratio**
```
Excess return over benchmark / Tracking error
Higher is better | Measures consistency of outperformance
```

#### **4. Treynor Ratio**
```
(Return - Risk Free Rate) / Beta
Higher is better | Risk-adjusted return relative to market risk
```

#### **5. Sterling Ratio (NEW)**
```
(Annualized Return - Risk Free) / Average Drawdown
Higher is better | Similar to Calmar but uses average DD
More representative than max DD for typical risk
```

#### **6. Burke Ratio (NEW)**
```
(Return - Risk Free) / sqrt(Sum of Squared Drawdowns)
Higher is better | Penalizes large drawdowns heavily
Uses RMS of drawdowns like Sharpe uses volatility
```

---

### **Drawdown Analysis**

#### **7. Ulcer Index**
```
Root mean square of drawdowns (percentage-based)
Lower is better | Measures severity and duration of drawdowns
Formula: sqrt(Mean(Drawdowns²))
Particularly useful for assessing pain of holding position
```

---

### **Benchmark Comparison**

#### **8. Jensen's Alpha**
```
Actual Return - (Beta × Benchmark Return)
Positive is better | Excess return after adjusting for market risk
Measures skill vs. luck in outperforming market
```

#### **9. Capture Ratios**
```
Upside Capture: Strategy return in up markets / Benchmark return in up markets
Downside Capture: Strategy return in down markets / Benchmark return in down markets

Upside > 1.0 = Capturing more gains than market (good)
Downside < 1.0 = Capturing less losses than market (good)
```

---

## 🔧 **IMPLEMENTATION FILES**

### **Core Implementation:**
```
/services/trading-engine/app/analytics/advanced_metrics.py
  - Line 1181-1212: Sterling Ratio implementation
  - Line 1214-1252: Burke Ratio implementation
  - Line 81-107: Updated RiskAdjustedMetrics data model
  - Line 931-940: Risk-adjusted metrics calculation
```

### **API Endpoints:**
```
/services/trading-engine/app/handlers/analytics.py
  - Line 317-350: Risk-adjusted metrics endpoint
  - Line 353-386: Drawdown metrics endpoint
  - Line 389-422: Win/loss metrics endpoint
  - Line 425-459: Risk metrics endpoint
  - Line 462-495: Efficiency metrics endpoint
  - Line 498-536: All metrics endpoint
  - Line 539-575: Benchmark comparison endpoint
```

### **API Registration:**
```
/services/trading-engine/app/main.py
  - Line 111-112: Import analytics routers
  - Line 527-528: Include analytics routers
```

---

## ✅ **VERIFICATION CHECKLIST**

- [x] Sterling ratio function implemented
- [x] Burke ratio function implemented
- [x] Data models updated to include new metrics
- [x] API handlers already existed
- [x] Routers imported in main.py
- [x] Routers included in FastAPI app
- [x] All 9 metrics from Phase 5.2 requirements present

---

## 🧪 **TESTING THE NEW METRICS**

### **1. Restart Trading Engine**
```bash
docker-compose restart trading-engine

# Wait for startup
sleep 5

# Check logs
docker logs crypto-bot-trading --tail 50
```

### **2. Test Risk-Adjusted Metrics Endpoint**
```bash
# Get all risk-adjusted metrics (includes Sterling and Burke)
curl -s http://localhost:8005/api/v1/analytics/metrics/risk-adjusted | python3 -m json.tool

# Expected output should include:
# "sterling_ratio": <value>
# "burke_ratio": <value>
```

### **3. Test Complete Metrics**
```bash
# Get ALL metrics
curl -s http://localhost:8005/api/v1/analytics/metrics/all | python3 -m json.tool

# Should return:
# - risk_adjusted (with 9 metrics including Sterling & Burke)
# - drawdown (with Ulcer Index)
# - benchmark (with Jensen's Alpha & Capture Ratios)
```

### **4. Verify Calculations**
```bash
# After a few trades, check the metrics are calculating:
curl -s http://localhost:8005/api/v1/analytics/metrics/risk-adjusted | \
  python3 -c "import sys, json; m = json.load(sys.stdin)['metrics']; \
  print(f\"Sterling: {m['sterling_ratio']:.4f}\"); \
  print(f\"Burke: {m['burke_ratio']:.4f}\")"
```

---

## 📊 **INTERPRETATION GUIDE**

### **Good Values (Institutional Benchmarks)**

| Metric | Good Value | Excellent Value |
|--------|-----------|-----------------|
| Sharpe Ratio | > 1.0 | > 2.0 |
| Sortino Ratio | > 1.5 | > 3.0 |
| Calmar Ratio | > 3.0 | > 5.0 |
| Omega Ratio | > 1.5 | > 2.0 |
| Sterling Ratio | > 2.5 | > 4.0 |
| Burke Ratio | > 1.5 | > 2.5 |
| Information Ratio | > 0.5 | > 1.0 |
| Gain-to-Pain | > 2.0 | > 3.0 |
| Ulcer Index | < 5.0 | < 3.0 |
| Jensen's Alpha | > 0 | > 5% |
| Upside Capture | > 1.0 | > 1.2 |
| Downside Capture | < 1.0 | < 0.8 |

---

## 🎯 **USE CASES**

### **Strategy Comparison**
Use these metrics to compare different trading strategies:
```bash
# Compare current strategy vs benchmark
curl http://localhost:8005/api/v1/analytics/metrics/benchmark
```

### **Risk Assessment**
Monitor drawdown and risk metrics:
```bash
# Check drawdown health
curl http://localhost:8005/api/v1/analytics/metrics/drawdown

# Check risk metrics
curl http://localhost:8005/api/v1/analytics/metrics/risk
```

### **Performance Reporting**
Generate comprehensive reports:
```bash
# Daily report
curl http://localhost:8005/api/v1/analytics/report/daily

# Monthly report
curl http://localhost:8005/api/v1/analytics/report/monthly
```

---

## 🔗 **RELATED DOCUMENTATION**

- **Phase 5.2 Requirements:** See original task specification
- **Advanced Metrics Module:** `/services/trading-engine/app/analytics/advanced_metrics.py`
- **API Handlers:** `/services/trading-engine/app/handlers/analytics.py`
- **OpenAPI Docs:** `http://localhost:8005/docs` (when service running)

---

## 🎉 **COMPLETION STATUS**

**Phase 5.2 Advanced Performance Metrics: 100% COMPLETE**

All 9 requested metrics are:
- ✅ Implemented in code
- ✅ Exposed via API endpoints
- ✅ Documented
- ✅ Ready for testing

**Files Modified:**
1. `/services/trading-engine/app/analytics/advanced_metrics.py` - Added Sterling & Burke ratios
2. `/services/trading-engine/app/main.py` - Registered analytics routers

**No breaking changes** - All existing code continues to work, new metrics are additions only.

---

*Documentation generated: 2026-01-08*
*Trading System Version: 1.0.0*
*Phase: 5.2 Enhancement Complete*
