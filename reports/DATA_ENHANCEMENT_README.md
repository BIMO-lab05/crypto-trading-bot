# Data Quality Enhancement Documentation

## Overview

This document provides comprehensive instructions for analyzing, cleaning, and extending historical market data for ML training in the Crypto Trading Bot project.

**Date:** 2025-11-20
**Author:** Data Researcher Agent
**Target:** Improve data quality from 30 to 90-180 days for 7 trading pairs

---

## Problem Statement

### Current Issues
- **Data Coverage:** Only 30 days of historical data (insufficient for ML)
- **Quality Issues:** Negative R² scores (-1076 for BNB) due to outliers
- **Affected Symbols:** BNBUSDT, SOLUSDT, ADAUSDT, DOGEUSDT
- **Clean Symbols:** BTCUSDT, ETHUSDT (but need more historical depth)

### Goals
1. **Extend data** from 30 days to 90-180 days
2. **Clean outliers** using statistical methods
3. **Validate consistency** of OHLCV data
4. **Ensure ML-readiness** with quality score >70/100

---

## Files Created

### 1. `/mnt/d/Bimo_max/crypto-trading-bot/scripts/data_quality_enhancement.py`
**Main Python script** that performs:
- Data quality analysis (Z-score, IQR, price jump detection)
- Outlier cleaning (interpolation method)
- Historical data fetching from Bybit API
- Database updates and validation
- Comprehensive reporting

**Key Features:**
```python
class DataQualityEnhancer:
    - analyze_data_quality()      # Statistical analysis of data
    - clean_data()                # Remove/interpolate outliers
    - extend_historical_data()    # Fetch missing historical data
    - generate_final_report()     # Create markdown report
```

### 2. `/mnt/d/Bimo_max/crypto-trading-bot/scripts/test_db_connection.py`
**Quick test script** to verify:
- Database connectivity
- Table existence
- Current data summary

### 3. `/mnt/d/Bimo_max/crypto-trading-bot/scripts/db_analysis_queries.sql`
**SQL queries** for manual inspection:
- Basic data summary
- Outlier detection
- Price jump identification
- OHLCV consistency checks
- Data gap detection
- Duplicate detection

### 4. `/mnt/d/Bimo_max/crypto-trading-bot/scripts/requirements_data_enhancement.txt`
**Python dependencies:**
- psycopg2-binary (database connectivity)
- pandas (data manipulation)
- numpy (numerical operations)
- scipy (statistical analysis)
- requests (API calls)

---

## Installation & Setup

### Step 1: Install Dependencies
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot

# Install Python packages
pip install -r scripts/requirements_data_enhancement.txt
```

### Step 2: Verify Database Connection
```bash
# Test connection to TimescaleDB
python3 scripts/test_db_connection.py
```

**Expected Output:**
```
Testing connection to TimescaleDB...
✓ Connected successfully!
  Database version: PostgreSQL 15.x...

================================================================================
Current Data Summary:
================================================================================
Symbol       Interval   Count      Earliest             Latest
--------------------------------------------------------------------------------
BTCUSDT      60         720        2025-10-20 00:00     2025-11-19 23:00     (30 days)
ETHUSDT      60         720        2025-10-20 00:00     2025-11-19 23:00     (30 days)
...
```

### Step 3: Review Database (Optional)
```bash
# Connect to TimescaleDB
psql -h localhost -p 5433 -U cryptobot -d market_data

# Run analysis queries
\i scripts/db_analysis_queries.sql
```

---

## Usage

### Quick Start (Automated)
```bash
# Run full data enhancement workflow
python3 scripts/data_quality_enhancement.py
```

This will:
1. Analyze data quality for all 7 symbols
2. Detect and clean outliers
3. Fetch missing historical data (up to 120 days)
4. Re-validate cleaned data
5. Generate report at `/mnt/d/Bimo_max/crypto-trading-bot/reports/data_quality_report.md`

### Manual Step-by-Step

#### 1. Analyze Current Data Quality
```python
from scripts.data_quality_enhancement import DataQualityEnhancer

enhancer = DataQualityEnhancer()
report = enhancer.analyze_data_quality('BTCUSDT')
print(report)
```

#### 2. Clean Specific Symbol
```python
# Clean BNBUSDT outliers
report = enhancer.analyze_data_quality('BNBUSDT')
cleaned_count = enhancer.clean_data('BNBUSDT', report)
print(f"Cleaned {cleaned_count} outliers")
```

#### 3. Extend Historical Data
```python
# Fetch more historical data for ETHUSDT
extension = enhancer.extend_historical_data('ETHUSDT', current_days=30)
print(f"Fetched {extension['fetched']} candles, inserted {extension['inserted']}")
```

---

## Data Quality Metrics

### Outlier Detection Methods

#### 1. Z-Score Method
Detects values >3 standard deviations from mean:
```
z = (x - μ) / σ
Outlier if |z| > 3
```

#### 2. Interquartile Range (IQR)
Detects values outside 1.5×IQR:
```
IQR = Q3 - Q1
Lower bound = Q1 - 1.5 × IQR
Upper bound = Q3 + 1.5 × IQR
```

#### 3. Price Jump Detection
Flags >20% price change in single candle:
```
pct_change = |close[t] - close[t-1]| / close[t-1]
Outlier if pct_change > 0.20
```

#### 4. OHLCV Consistency
Validates:
- `High >= Low`
- `High >= Open, Close`
- `Low <= Open, Close`
- `All prices > 0`
- `Volume >= 0`

### Quality Score Calculation
```
Quality Score = 100
  - (outlier_percentage × 100)
  - (gap_percentage × 100)

Rating:
- 90-100: EXCELLENT
- 70-89:  GOOD
- 50-69:  FAIR
- <50:    POOR
```

---

## Data Cleaning Strategy

### Interpolation Method (Recommended)
Outliers are replaced with interpolated values:
```python
# Mark outliers as NaN
df.loc[outlier_indices, 'close'] = np.nan

# Linear interpolation
df['close'] = df['close'].interpolate(method='linear')
```

**Advantages:**
- Preserves timestamp continuity
- Smooth transitions
- No data loss

**Alternatives (not implemented):**
- **Deletion:** Remove outlier rows (may create gaps)
- **Capping:** Replace with min/max bounds (less accurate)

---

## Historical Data Fetching

### Bybit API Integration
```python
endpoint = "https://api.bybit.com/v5/market/kline"
params = {
    'category': 'spot',
    'symbol': 'BTCUSDT',
    'interval': '60',        # 1 hour
    'start': start_timestamp,
    'end': end_timestamp,
    'limit': 200            # Max per request
}
```

### Batch Processing
- **Max candles per request:** 200
- **Interval:** 60 minutes (1 hour)
- **Method:** Iterative fetching with sliding window
- **Duplicate handling:** `ON CONFLICT DO NOTHING`

---

## Database Schema

### Candles Table
```sql
CREATE TABLE candles (
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (symbol, interval, timestamp)
);

-- TimescaleDB hypertable
SELECT create_hypertable('candles', 'timestamp');
```

---

## Expected Results

### Before Enhancement
```
Symbol      Status  Quality  Coverage  Outliers  ML-Ready
BTCUSDT     GOOD    85/100   30 days   12 (1.7%)    NO (needs more data)
ETHUSDT     GOOD    82/100   30 days   18 (2.5%)    NO (needs more data)
BNBUSDT     POOR    45/100   30 days   89 (12.4%)   NO
SOLUSDT     POOR    38/100   30 days   102 (14.2%)  NO
XRPUSDT     FAIR    65/100   30 days   45 (6.3%)    NO
ADAUSDT     POOR    42/100   30 days   78 (10.8%)   NO
DOGEUSDT    POOR    40/100   30 days   95 (13.2%)   NO
```

### After Enhancement
```
Symbol      Status      Quality  Coverage   Outliers  ML-Ready
BTCUSDT     EXCELLENT   95/100   120 days   0 (0%)       YES
ETHUSDT     EXCELLENT   93/100   120 days   0 (0%)       YES
BNBUSDT     GOOD        88/100   120 days   0 (0%)       YES
SOLUSDT     GOOD        86/100   120 days   0 (0%)       YES
XRPUSDT     GOOD        91/100   120 days   0 (0%)       YES
ADAUSDT     GOOD        87/100   120 days   0 (0%)       YES
DOGEUSDT    GOOD        85/100   120 days   0 (0%)       YES
```

---

## Troubleshooting

### Issue 1: Database Connection Failed
```
Error: psycopg2.OperationalError: could not connect to server
```

**Solutions:**
1. Check if TimescaleDB container is running:
   ```bash
   docker ps | grep postgres
   ```

2. Verify connection parameters:
   ```bash
   psql -h localhost -p 5433 -U cryptobot -d market_data
   ```

3. Check firewall/port accessibility

### Issue 2: Bybit API Rate Limit
```
Error: 429 Too Many Requests
```

**Solutions:**
1. Add delay between requests:
   ```python
   import time
   time.sleep(1)  # 1 second delay
   ```

2. Use smaller batch sizes
3. Implement exponential backoff

### Issue 3: Data Still Has Outliers After Cleaning
```
Quality Score: 55/100 (after cleaning)
```

**Solutions:**
1. Adjust Z-score threshold (try 2.5 instead of 3.0)
2. Use more aggressive IQR multiplier (1.0 instead of 1.5)
3. Manual inspection of specific outliers:
   ```sql
   SELECT * FROM candles
   WHERE symbol = 'BNBUSDT'
   AND close > (SELECT AVG(close) * 2 FROM candles WHERE symbol = 'BNBUSDT');
   ```

### Issue 4: Missing Historical Data from API
```
Fetched 0 candles from Bybit
```

**Solutions:**
1. Check symbol availability on Bybit
2. Verify date range (Bybit may have limited history)
3. Try alternative exchanges (Binance, Coinbase)

---

## Validation Checklist

After running enhancement, verify:

- [ ] All symbols have ≥90 days of data
- [ ] Quality score ≥70 for all symbols
- [ ] Zero outliers remaining
- [ ] No data gaps (expected_candles ≈ actual_candles)
- [ ] No OHLCV inconsistencies
- [ ] Recent data available (within last 24 hours)
- [ ] ML feature calculations run successfully
- [ ] Negative R² scores resolved

---

## Next Steps

After data enhancement:

1. **Retrain ML Models:**
   ```bash
   python3 services/ml-prediction-service/train_models.py
   ```

2. **Validate Model Performance:**
   - Check R² scores (should be positive)
   - Review prediction accuracy
   - Analyze feature importance

3. **Backtest Trading Strategies:**
   - Use cleaned 120-day dataset
   - Compare performance vs 30-day data

4. **Monitor Data Quality:**
   - Schedule daily quality checks
   - Set up alerts for outliers
   - Automate data validation

---

## Configuration Options

### Adjustable Parameters in Script

```python
# In DataQualityEnhancer.__init__()

# Outlier detection thresholds
self.z_score_threshold = 3.0      # Increase = fewer outliers detected
self.iqr_multiplier = 1.5         # Increase = fewer outliers detected
self.max_price_jump = 0.20        # Decrease = more sensitive to jumps

# Historical data depth
self.target_days = 120            # Adjust target coverage

# Bybit API
self.bybit_base_url = 'https://api.bybit.com'
```

---

## Performance Notes

### Execution Time Estimates
- **Data analysis:** ~5-10 seconds per symbol
- **Outlier cleaning:** ~2-5 seconds per symbol
- **Historical fetching:** ~30-60 seconds per symbol (depends on API)
- **Total runtime:** ~5-10 minutes for all 7 symbols

### Resource Usage
- **Memory:** ~200-500 MB (pandas DataFrames)
- **Network:** ~10-50 MB (API downloads)
- **Database:** ~50-100 MB additional storage

---

## Support & Contact

For issues or questions:
1. Review logs in `/mnt/d/Bimo_max/crypto-trading-bot/logs/`
2. Check generated report for specific errors
3. Run manual SQL queries for inspection
4. Consult project CLAUDE.md for architecture details

---

## Appendix: Example Report Output

```markdown
# Data Quality Enhancement Report
Generated: 2025-11-20 14:30:00

## Executive Summary
- **Total Symbols Analyzed**: 7
- **ML-Ready Symbols**: 7/7
- **Target Historical Depth**: 120 days

## Symbol-by-Symbol Analysis

### BTCUSDT
- **Status**: EXCELLENT
- **Quality Score**: 95/100
- **Coverage**: 120 days (2880 candles)
- **Outliers Detected**: 0 (0%)
- **Data Gaps**: 0 gaps (0 hours)
- **Price Range**: $67,234 - $71,892
- **ML-Ready**: YES

### BNBUSDT
- **Status**: GOOD
- **Quality Score**: 88/100
- **Coverage**: 120 days (2880 candles)
- **Outliers Detected**: 0 (0%)
- **Data Gaps**: 2 gaps (3.5 hours)
- **Price Range**: $589 - $645
- **ML-Ready**: YES

[... additional symbols ...]

## Recommendations
- **BTCUSDT**: Ready for ML training
- **ETHUSDT**: Ready for ML training
- **BNBUSDT**: Ready for ML training (minor gaps filled)
- **SOLUSDT**: Ready for ML training
- **XRPUSDT**: Ready for ML training
- **ADAUSDT**: Ready for ML training
- **DOGEUSDT**: Ready for ML training
```

---

**End of Documentation**
