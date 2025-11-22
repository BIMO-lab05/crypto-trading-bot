# Quick Start: Data Quality Enhancement

**Goal:** Improve data quality from 30 to 120 days for ML training

---

## Step-by-Step Execution

### 1. Test Connection (30 seconds)
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 scripts/test_db_connection.py
```
**Expected:** See current data summary for 7 symbols

---

### 2. Install Dependencies (1 minute)
```bash
pip3 install -r scripts/requirements_data_enhancement.txt
```
**Installs:** psycopg2, pandas, numpy, scipy, requests

---

### 3. Run Enhancement (5-10 minutes)
```bash
python3 scripts/data_quality_enhancement.py
```

**What it does:**
- Analyzes all 7 symbols
- Detects outliers (Z-score, IQR, price jumps)
- Cleans data (interpolation method)
- Fetches 90 days of historical data from Bybit
- Re-validates cleaned data
- Generates report

**Output:** `/reports/data_quality_report.md`

---

### 4. Validate Results (1 minute)
```bash
python3 scripts/validate_enhanced_data.py
```

**What it checks:**
- Coverage ≥90 days
- Zero outliers
- No data gaps
- OHLCV consistency
- ML features calculable

**Output:** `/reports/data_validation_report.md`

---

### 5. Review Reports (2 minutes)
```bash
# Quality report
cat reports/data_quality_report.md

# Validation report
cat reports/data_validation_report.md
```

---

## Automated Execution (Alternative)

```bash
# One command does everything
bash scripts/run_data_enhancement.sh
```

**This runs:**
1. Prerequisite checks
2. Dependency installation
3. Connection test
4. Enhancement
5. Validation
6. Report generation

**Log saved to:** `/logs/data_enhancement_YYYYMMDD_HHMMSS.log`

---

## Expected Results

### Before
```
Symbol      Coverage  Outliers  ML-Ready
BTCUSDT     30 days   12        NO
BNBUSDT     30 days   89        NO
SOLUSDT     30 days   102       NO
```

### After
```
Symbol      Coverage  Outliers  ML-Ready
BTCUSDT     120 days  0         YES
BNBUSDT     120 days  0         YES
SOLUSDT     120 days  0         YES
```

---

## Troubleshooting

### Can't connect to database?
```bash
# Check if TimescaleDB is running
docker ps | grep postgres

# Start if needed
docker-compose up -d timescaledb
```

### API errors?
```python
# Edit scripts/data_quality_enhancement.py
# Add delay between requests (line ~370)
import time
time.sleep(1)
```

### Still have outliers?
```bash
# Run enhancement twice
python3 scripts/data_quality_enhancement.py
python3 scripts/data_quality_enhancement.py
```

---

## Next Steps After Enhancement

1. **Retrain ML models:**
   ```bash
   python3 services/ml-prediction-service/train_models.py
   ```

2. **Check R² improvements:**
   - Should be positive (0.4-0.7)
   - Compare to old negative scores

3. **Backtest strategies:**
   - Use 120-day clean dataset
   - Compare performance

---

## File Locations

```
/mnt/d/Bimo_max/crypto-trading-bot/
├── scripts/
│   ├── data_quality_enhancement.py  (main script)
│   ├── validate_enhanced_data.py    (validation)
│   ├── test_db_connection.py        (connection test)
│   └── run_data_enhancement.sh      (automated)
├── reports/
│   ├── data_quality_report.md       (generated)
│   ├── data_validation_report.md    (generated)
│   ├── DATA_ENHANCEMENT_README.md   (documentation)
│   └── DATA_ENHANCEMENT_SUMMARY.md  (executive summary)
└── logs/
    └── data_enhancement_*.log       (execution logs)
```

---

## Success Checklist

- [ ] Connection test passed
- [ ] Dependencies installed
- [ ] Enhancement completed (5-10 min)
- [ ] Validation passed (7/7 symbols ML-ready)
- [ ] Reports generated
- [ ] ML models retrained
- [ ] R² scores improved

---

## Summary

**Time:** 10-15 minutes total
**Result:** 7 symbols with 120 days of clean data
**Impact:** ML models go from negative to positive R² scores

**Start now:**
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 scripts/data_quality_enhancement.py
```

---

For detailed documentation: `reports/DATA_ENHANCEMENT_README.md`
