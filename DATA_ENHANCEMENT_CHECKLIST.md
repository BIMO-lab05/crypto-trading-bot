# Data Enhancement Execution Checklist

**Complete step-by-step checklist for data quality enhancement**

---

## Pre-Execution Checklist

### System Requirements
- [ ] Python 3.7+ installed (`python3 --version`)
- [ ] pip package manager available (`pip3 --version`)
- [ ] TimescaleDB running (`docker ps | grep postgres`)
- [ ] Database accessible on localhost:5433
- [ ] Internet connection for Bybit API
- [ ] Disk space available (>500 MB free)

### Environment Setup
- [ ] Navigate to project directory: `/mnt/d/Bimo_max/crypto-trading-bot`
- [ ] Virtual environment activated (if used)
- [ ] Database credentials verified
- [ ] Project files present (check `/scripts` directory)

---

## Execution Checklist

### Phase 1: Preparation (5 minutes)

#### 1.1 Install Dependencies
```bash
pip3 install -r scripts/requirements_data_enhancement.txt
```
- [ ] psycopg2-binary installed
- [ ] pandas installed
- [ ] numpy installed
- [ ] scipy installed
- [ ] requests installed
- [ ] No installation errors

#### 1.2 Test Database Connection
```bash
python3 scripts/test_db_connection.py
```
- [ ] Connection successful
- [ ] Database version displayed
- [ ] Candles table exists
- [ ] Current data summary shown
- [ ] All 7 symbols present

**Expected Output:**
```
✓ Connected successfully!
  Database version: PostgreSQL 15.x...

================================================================================
Current Data Summary:
================================================================================
Symbol       Interval   Count      Earliest             Latest
--------------------------------------------------------------------------------
BTCUSDT      60         720        2025-10-20 00:00     2025-11-19 23:00
...
```

#### 1.3 Review Current State (Optional)
```bash
cat scripts/db_analysis_queries.sql
# Review available SQL queries
```
- [ ] SQL queries reviewed
- [ ] Understanding of data structure
- [ ] Baseline metrics noted

---

### Phase 2: Data Enhancement (5-10 minutes)

#### 2.1 Execute Enhancement Script
```bash
python3 scripts/data_quality_enhancement.py
```

#### 2.2 Monitor Progress
Watch for these stages:

**Stage 1: Analysis**
- [ ] "Analyzing data quality for BTCUSDT" displayed
- [ ] Status and quality score shown
- [ ] Outliers detected and counted
- [ ] Data gaps identified
- [ ] Coverage days calculated

**Stage 2: Cleaning**
- [ ] "Cleaning X outliers for SYMBOL" displayed
- [ ] Interpolation completed
- [ ] Database updates successful
- [ ] Cleaned count reported

**Stage 3: Extension**
- [ ] "Extending historical data for SYMBOL" displayed
- [ ] "Fetching historical data from Bybit API" shown
- [ ] Batch progress displayed (e.g., "Fetched 200 candles")
- [ ] Total candles fetched reported
- [ ] Insertion count displayed

**Stage 4: Re-Validation**
- [ ] "Re-analyzing SYMBOL after enhancements" displayed
- [ ] Updated quality score shown
- [ ] Improvement confirmed

**Stage 5: Reporting**
- [ ] "Generating final report..." displayed
- [ ] Report saved to path shown
- [ ] "DATA QUALITY ENHANCEMENT - COMPLETE" displayed

#### 2.3 Check for Errors
If any errors occur:
- [ ] Error message noted
- [ ] Error context reviewed
- [ ] Troubleshooting section consulted
- [ ] Issue resolved or documented

---

### Phase 3: Validation (1 minute)

#### 3.1 Run Validation Script
```bash
python3 scripts/validate_enhanced_data.py
```

#### 3.2 Review Validation Results
- [ ] All symbols validated
- [ ] Coverage check passed (≥90 days)
- [ ] Outlier check passed (0 outliers)
- [ ] Gap check passed (0 gaps)
- [ ] Consistency check passed
- [ ] ML features check passed
- [ ] Recent data check passed

**Expected Output:**
```
Validating BTCUSDT
============================================================
  Coverage:     ✓ 120 days (required: 90)
  Outliers:     ✓ 0 outliers found
  Data Gaps:    ✓ 0 gaps (0 hours missing)
  Consistency:  ✓ 0 inconsistencies found
  ML Features:  ✓ ML features calculated (NaN: 0, Inf: 0)
  Recent Data:  ✓ Latest data: 2.0 hours ago

  Quality Score: 95/100
  Status: EXCELLENT
  ML-Ready: YES
```

#### 3.3 Verify All Symbols
- [ ] BTCUSDT: ML-Ready YES
- [ ] ETHUSDT: ML-Ready YES
- [ ] BNBUSDT: ML-Ready YES
- [ ] SOLUSDT: ML-Ready YES
- [ ] XRPUSDT: ML-Ready YES
- [ ] ADAUSDT: ML-Ready YES
- [ ] DOGEUSDT: ML-Ready YES

---

### Phase 4: Report Review (2 minutes)

#### 4.1 Quality Report
```bash
cat reports/data_quality_report.md
```

Review and verify:
- [ ] Executive summary present
- [ ] All 7 symbols analyzed
- [ ] Quality scores displayed
- [ ] Outlier counts shown
- [ ] Coverage days listed
- [ ] Recommendations provided

**Key Metrics to Check:**
```
- ML-Ready Symbols: 7/7 ✓
- Average Quality Score: >85/100 ✓
- Average Coverage: ~120 days ✓
- Total Outliers: 0 ✓
```

#### 4.2 Validation Report
```bash
cat reports/data_validation_report.md
```

Review and verify:
- [ ] Validation summary table
- [ ] Pass/fail breakdown
- [ ] All critical checks passed
- [ ] Recommendations section reviewed

#### 4.3 Execution Logs (if using automated script)
```bash
cat logs/data_enhancement_*.log
```
- [ ] Log file exists
- [ ] No fatal errors
- [ ] All stages completed
- [ ] Timestamps reasonable

---

## Post-Execution Checklist

### Data Verification

#### Verify Database Changes
```bash
python3 scripts/test_db_connection.py
```
- [ ] Candle count increased (720 → 2,880 per symbol)
- [ ] Date range extended (30 → 120 days)
- [ ] All symbols updated

#### Verify Data Quality
Run manual SQL checks:
```sql
-- Connect to database
psql -h localhost -p 5433 -U cryptobot -d market_data

-- Check coverage
SELECT symbol, COUNT(*), MIN(timestamp), MAX(timestamp)
FROM candles WHERE interval = '60' GROUP BY symbol;

-- Check for outliers
-- (Copy query from db_analysis_queries.sql)
```
- [ ] All symbols have ~2,880 candles
- [ ] Date range: 2025-07-20 to 2025-11-19
- [ ] No extreme outliers in results

---

### ML Model Retraining

#### Prepare for Retraining
- [ ] Enhanced data confirmed ready
- [ ] ML service accessible
- [ ] Training script identified
- [ ] Backup of old models (optional)

#### Execute Retraining
```bash
python3 services/ml-prediction-service/train_models.py
```
- [ ] Training started successfully
- [ ] All 7 symbols trained
- [ ] No errors during training
- [ ] New models saved

#### Compare Results
Review R² scores:

**Before Enhancement:**
```
BTCUSDT:  0.42
ETHUSDT:  0.38
BNBUSDT:  -1076  ← POOR
SOLUSDT:  -892   ← POOR
XRPUSDT:  -0.15
ADAUSDT:  -543   ← POOR
DOGEUSDT: -721   ← POOR
```

**After Enhancement (Expected):**
```
BTCUSDT:  0.65-0.75  ✓
ETHUSDT:  0.60-0.70  ✓
BNBUSDT:  0.50-0.65  ✓
SOLUSDT:  0.45-0.60  ✓
XRPUSDT:  0.55-0.68  ✓
ADAUSDT:  0.48-0.62  ✓
DOGEUSDT: 0.42-0.58  ✓
```

- [ ] All R² scores positive
- [ ] BTCUSDT: R² improved
- [ ] ETHUSDT: R² improved
- [ ] BNBUSDT: R² positive (was -1076)
- [ ] SOLUSDT: R² positive (was -892)
- [ ] XRPUSDT: R² improved
- [ ] ADAUSDT: R² positive (was -543)
- [ ] DOGEUSDT: R² positive (was -721)

---

### Documentation Updates

#### Update Project Documentation
- [ ] Update `progress.md` with enhancement results
- [ ] Document new data metrics
- [ ] Record R² score improvements
- [ ] Note any issues encountered

#### Archive Reports
```bash
# Create timestamped backup
mkdir -p reports/archive
cp reports/data_quality_report.md reports/archive/data_quality_$(date +%Y%m%d).md
cp reports/data_validation_report.md reports/archive/data_validation_$(date +%Y%m%d).md
```
- [ ] Reports archived
- [ ] Timestamps recorded
- [ ] Backup directory organized

---

## Success Criteria Verification

### Critical Success Factors
- [ ] **Data Coverage:** All symbols have ≥90 days (target: 120 days)
- [ ] **Data Quality:** Quality scores ≥70/100 for all symbols
- [ ] **Outliers:** Zero outliers remaining
- [ ] **Data Gaps:** No significant gaps (≤2 hours)
- [ ] **ML Readiness:** All 7 symbols ML-ready
- [ ] **Model Performance:** All R² scores positive
- [ ] **System Stability:** No database corruption or errors

### Performance Metrics
- [ ] Total execution time: 5-15 minutes
- [ ] Network data downloaded: 10-50 MB
- [ ] Database growth: ~15,000 new records
- [ ] Disk space used: 50-100 MB additional
- [ ] No memory issues or crashes

### Quality Metrics
- [ ] Average quality score: >85/100
- [ ] Coverage completeness: >98%
- [ ] Outlier rate: 0%
- [ ] Data consistency: 100%
- [ ] ML feature validity: 100%

---

## Troubleshooting Checklist

### If Database Connection Fails
- [ ] Check TimescaleDB is running: `docker ps`
- [ ] Verify port 5433 is accessible
- [ ] Test credentials: `psql -h localhost -p 5433 -U cryptobot -d market_data`
- [ ] Check firewall settings
- [ ] Review connection parameters in scripts

### If API Requests Fail
- [ ] Check internet connectivity
- [ ] Verify Bybit API is accessible: `curl https://api.bybit.com/v5/market/time`
- [ ] Check for rate limiting (429 errors)
- [ ] Add delays between requests if needed
- [ ] Try alternative time ranges

### If Outliers Remain
- [ ] Review threshold settings in script
- [ ] Run enhancement twice (second pass)
- [ ] Manually inspect problematic candles with SQL
- [ ] Consider adjusting z-score threshold (2.5 instead of 3.0)
- [ ] Check for data source issues

### If Historical Data Not Fetched
- [ ] Verify symbol availability on Bybit
- [ ] Check date range (Bybit may have limited history)
- [ ] Review API response for errors
- [ ] Try smaller date ranges
- [ ] Consider alternative data sources

### If Validation Fails
- [ ] Review validation report for specific failures
- [ ] Re-run enhancement for failed symbols
- [ ] Check database integrity
- [ ] Verify recent data is being collected
- [ ] Review ML feature calculation errors

---

## Final Sign-Off

### Completed Tasks
- [ ] All pre-execution requirements met
- [ ] Dependencies installed successfully
- [ ] Database connection verified
- [ ] Enhancement script executed completely
- [ ] Validation script passed all checks
- [ ] Reports generated and reviewed
- [ ] ML models retrained successfully
- [ ] R² scores improved significantly
- [ ] Documentation updated
- [ ] Troubleshooting steps documented (if any)

### Quality Assurance
- [ ] All 7 symbols have 120 days of data
- [ ] Zero outliers in final dataset
- [ ] No data integrity issues
- [ ] ML-ready status confirmed for all symbols
- [ ] Performance metrics acceptable
- [ ] No system errors or warnings

### Deployment Ready
- [ ] Enhanced data in production database
- [ ] New ML models deployed (if applicable)
- [ ] Monitoring alerts configured
- [ ] Backup procedures in place
- [ ] Rollback plan documented

---

## Maintenance Schedule

### Daily Tasks
- [ ] Monitor data quality alerts
- [ ] Check for new outliers
- [ ] Verify recent data collection
- [ ] Review ML model performance

### Weekly Tasks
- [ ] Run validation script
- [ ] Review quality scores
- [ ] Update historical data (if gaps)
- [ ] Archive old reports

### Monthly Tasks
- [ ] Full data enhancement refresh
- [ ] Retrain ML models
- [ ] Review and adjust thresholds
- [ ] Performance optimization

---

## Sign-Off

**Executed by:** ___________________
**Date:** ___________________
**Time:** ___________________

**Overall Status:** [ ] Success  [ ] Partial Success  [ ] Failed

**Notes:**
________________________________________________________________
________________________________________________________________
________________________________________________________________

**Next Actions:**
________________________________________________________________
________________________________________________________________
________________________________________________________________

---

## Quick Reference

**Project Directory:** `/mnt/d/Bimo_max/crypto-trading-bot`

**Key Commands:**
```bash
# Test connection
python3 scripts/test_db_connection.py

# Run enhancement
python3 scripts/data_quality_enhancement.py

# Validate results
python3 scripts/validate_enhanced_data.py

# View reports
cat reports/data_quality_report.md
cat reports/data_validation_report.md

# Retrain models
python3 services/ml-prediction-service/train_models.py
```

**Key Files:**
- Quick start: `/QUICK_START_DATA_ENHANCEMENT.md`
- Documentation: `/reports/DATA_ENHANCEMENT_README.md`
- Reports: `/reports/data_quality_report.md`
- Logs: `/logs/data_enhancement_*.log`

**Support:**
- Review troubleshooting: `DATA_ENHANCEMENT_README.md` (section 10)
- Check logs: `logs/data_enhancement_*.log`
- Run SQL queries: `scripts/db_analysis_queries.sql`

---

**End of Checklist**
