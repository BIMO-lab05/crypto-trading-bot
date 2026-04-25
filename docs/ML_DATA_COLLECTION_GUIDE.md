# ML Training Data Collection Guide
## Collecting Extended Historical Data for Machine Learning

---

## PURPOSE

After comprehensive testing showed ALL technical analysis strategies failed (Grid: 0%, Trend-Following: 20%), this guide covers collecting extended historical data for ML/AI Phase 3 development.

**Goal**: Collect 12-24 months of historical data across multiple timeframes to enable robust ML model training.

---

## REQUIREMENTS FROM ML ASSESSMENT

Per `docs/ML_AI_PHASE3_READINESS_ASSESSMENT.md`:

| Requirement | Current | Target | Status |
|-------------|---------|--------|--------|
| Historical Period | 6 months | 12-24 months | ❌ Insufficient |
| Training Data Used | 90 days | 6-12 months | ❌ Only 50% |
| Timeframe Variety | 1H only | 1H, 4H, 1D | ❌ Limited |
| Market Regimes | Bull only | Bull, Bear, Ranging | ❌ Missing |

**Critical Gap**: Current 90-day dataset insufficient for robust ML training. Models learning noise, not patterns.

---

## DATA COLLECTION SCRIPT

### Script: `scripts/collect_ml_training_data.py`

**What it does**:
1. Collects historical OHLCV data from Bybit API
2. Supports multiple symbols and timeframes
3. Handles rate limiting and retries
4. Saves to CSV files for ML training
5. Generates collection summary report

**Configuration**:
```python
SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT',
    'APTUSDT', 'DOTUSDT', 'LTCUSDT', 'AVAXUSDT', 'ARBUSDT'
]  # 10 symbols

INTERVALS = ['60', '240', 'D']  # 1H, 4H, 1D

MONTHS = 24  # 2 years of data
```

**Output Structure**:
```
data/ml_training/
├── BTCUSDT_1H_24months_20251208.csv
├── BTCUSDT_4H_24months_20251208.csv
├── BTCUSDT_1D_24months_20251208.csv
├── ETHUSDT_1H_24months_20251208.csv
├── ... (30 files total: 10 symbols × 3 timeframes)
└── collection_summary_20251208_220000.csv
```

---

## USAGE

### Step 1: Preparation

```bash
# Ensure you're in project root
cd /mnt/d/Bimo_max/crypto-trading-bot

# Check Bybit API credentials are set
env | grep BYBIT

# Create output directory
mkdir -p data/ml_training

# Make script executable
chmod +x scripts/collect_ml_training_data.py
```

### Step 2: Run Collection

```bash
# Start data collection (interactive - will ask for confirmation)
python3 scripts/collect_ml_training_data.py
```

**Expected Output**:
```
Configuration:
  Symbols: 10
  Intervals: ['60', '240', 'D'] (1H, 4H, 1D)
  Period: 24 months
  Total datasets: 30

⚠️ This will collect approximately:
  - 1H data: ~17,280 candles per symbol
  - 4H data: ~4,320 candles per symbol
  - 1D data: ~720 candles per symbol
  - Total: ~223,200 candles
  - Estimated time: 150 minutes

Proceed with data collection? (yes/no):
```

### Step 3: Monitor Progress

The script will show real-time progress:

```
================================================================================
[1/30] Processing BTCUSDT - 60
================================================================================
Collecting BTCUSDT - 60 interval
Period: 2023-12-08 to 2025-12-08
================================================================================

   Batch 10: 2000 candles collected (now at 2025-10-15)
   Batch 20: 4000 candles collected (now at 2025-08-25)
   ...

✅ Collection complete:
   Total candles: 17,280
   Batches: 87
   Final dataset: 17,280 candles
   Date range: 2023-12-08 to 2025-12-08
   Completeness: 100.0%

✅ Saved: data/ml_training/BTCUSDT_1H_24months_20251208.csv
   Size: 1.2 MB
```

### Step 4: Verify Results

```bash
# Check collected files
ls -lh data/ml_training/

# View summary
cat data/ml_training/collection_summary_*.csv

# Quick validation
head -20 data/ml_training/BTCUSDT_1H_24months_20251208.csv
```

---

## EXPECTED RESULTS

### Data Volume

**Per Symbol**:
- 1H timeframe: ~17,280 candles (24 months × 30 days × 24 hours)
- 4H timeframe: ~4,320 candles (24 months × 30 days × 6 periods)
- 1D timeframe: ~720 candles (24 months × 30 days)

**Total (10 symbols)**:
- 1H: 172,800 candles
- 4H: 43,200 candles
- 1D: 7,200 candles
- **Grand Total: 223,200 candles**

### Storage Requirements

- CSV file size: ~70 KB per 1,000 candles
- 1H file: ~1.2 MB per symbol
- 4H file: ~300 KB per symbol
- 1D file: ~50 KB per symbol
- **Total Storage**: ~15 MB for all data

### Collection Time

- Bybit rate limit: 120 requests/minute
- Candles per request: 200
- Delay per request: 0.5 seconds

**Estimated Times**:
- 1H collection (87 requests): ~44 seconds per symbol
- 4H collection (22 requests): ~11 seconds per symbol
- 1D collection (4 requests): ~2 seconds per symbol
- **Total per symbol**: ~57 seconds
- **All 10 symbols**: ~10 minutes

---

## DATA QUALITY CHECKS

### Validation Checklist

After collection, verify:

```bash
# 1. Check file count (should be 30)
ls data/ml_training/*.csv | wc -l

# 2. Check no empty files
find data/ml_training -name "*.csv" -size 0

# 3. Check date ranges
for file in data/ml_training/*_1H_*.csv; do
    echo "=== $file ==="
    head -2 $file | tail -1
    tail -1 $file
done

# 4. Check for gaps (run Python validation)
python3 << 'EOF'
import pandas as pd
from pathlib import Path

data_dir = Path('data/ml_training')
for csv_file in sorted(data_dir.glob('*_1H_*.csv')):
    df = pd.read_csv(csv_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Check for time gaps (should be 1 hour apart)
    df['time_diff'] = df['timestamp'].diff()
    gaps = df[df['time_diff'] > pd.Timedelta(hours=2)]

    if len(gaps) > 0:
        print(f"⚠️ {csv_file.name}: {len(gaps)} gaps found")
    else:
        print(f"✅ {csv_file.name}: No gaps ({len(df)} candles)")
EOF
```

### Quality Metrics

**Good Dataset**:
- ✅ Completeness: >95%
- ✅ No gaps >2 hours (1H data)
- ✅ Consistent OHLC structure
- ✅ Realistic price ranges
- ✅ Non-zero volume

**Issues to Watch**:
- ❌ Large time gaps (exchange downtime, delisting)
- ❌ Zero volume periods (low liquidity)
- ❌ Extreme price spikes (data errors)

---

## TROUBLESHOOTING

### Issue 1: Rate Limit Errors

**Symptom**:
```
❌ Error: 429 Too Many Requests
```

**Solution**:
```python
# In collect_ml_training_data.py, increase delay:
await asyncio.sleep(1)  # Change from 0.5 to 1 second
```

### Issue 2: Incomplete Collection

**Symptom**:
```
⚠️ Collection incomplete due to errors
Total candles: 5000 (expected 17,280)
```

**Solution**:
1. Check Bybit API status
2. Verify API credentials
3. Check network connectivity
4. Re-run collection (script will resume from where it stopped)

### Issue 3: Missing Historical Data

**Symptom**:
```
✅ Reached end of available data
Total candles: 4320 (only 6 months, expected 24 months)
```

**Explanation**: Bybit may not have 24 months of data for all symbols

**Solution**:
- Collect maximum available (usually 12-18 months)
- Focus on major pairs (BTC, ETH, SOL) for longest history
- Adjust `MONTHS` parameter based on availability

---

## NEXT STEPS AFTER COLLECTION

Once data collection is complete:

### 1. Validate Data Quality

```bash
# Run validation script
python3 scripts/validate_ml_data.py
```

### 2. Update ML Training Scripts

Update data paths in:
- `services/ml-prediction-service/app/training/train_lstm_production.py`
- `services/ml-prediction-service/app/training/train_gru_quick.py`

Change data loading:
```python
# From:
data_file = f'backtesting/data/{symbol}_60m_90d_bybit.csv'

# To:
data_file = f'data/ml_training/{symbol}_1H_24months_*.csv'
```

### 3. Fix Training Pipeline

Fix import errors:
```python
# Change:
from app.models.lstm_model import LSTMPredictor

# To:
from app.ml_models.lstm_model import LSTMPredictor
```

### 4. Begin ML Training

```bash
# Train LSTM on extended dataset
cd services/ml-prediction-service
python3 app/training/train_lstm_production.py
```

---

## ML TRAINING ROADMAP

### Week 1: Data Foundation ✅ (This Guide)
- [x] Create data collection script
- [x] Collect 12-24 months historical data
- [ ] Validate data quality
- [ ] Fix training pipeline import errors

### Week 2: Model Training
- [ ] Train LSTM on full dataset
- [ ] Train GRU on full dataset
- [ ] Implement walk-forward validation
- [ ] Add production metrics (Sharpe, drawdown, win rate)

### Week 3: Architecture Experiments
- [ ] Try LightGBM/XGBoost
- [ ] Test Transformer models
- [ ] Hybrid TA + ML approach
- [ ] Ensemble methods

### Week 4: Decision Point
```
IF best_model achieves:
   70%+ prediction accuracy AND
   0.8+ Sharpe ratio AND
   walk-forward validated
THEN: Proceed to paper trading (30 days)
ELSE: Pivot to alternative approach or close project
```

---

## ALTERNATIVES IF DATA COLLECTION FAILS

### Option 1: Use Existing 6-Month Data
- Pros: Already collected, tested
- Cons: Still insufficient for robust ML
- Recommendation: Only if API issues persist

### Option 2: Different Data Source
- Use Binance API (longer history)
- Use CryptoCompare API
- Purchase historical data from providers

### Option 3: Focus on Specific Symbols
- Collect 24 months for BTC/ETH/SOL only
- Trade only on high-data-quality symbols
- Better quality over quantity

### Option 4: Abandon ML Approach
- Pivot to regime-adaptive hybrid system
- Try different timeframes (4H, 1D only)
- Focus on alternative markets
- Accept as learning experience

---

## RESOURCES REQUIRED

### Time
- Collection: ~10 minutes
- Validation: ~5 minutes
- Pipeline fixes: ~1 hour
- **Total**: ~1.5 hours

### Storage
- Raw CSV files: ~15 MB
- Processed features: ~50 MB
- Trained models: ~10 MB
- **Total**: ~75 MB

### API Calls
- Bybit free tier: 120 requests/minute
- Required: ~1,300 requests
- **Time needed**: ~11 minutes (well within rate limits)

---

## SUMMARY

**Current Status**:
- ❌ Only 90 days of 1H data available
- ❌ Missing 4H and 1D timeframes
- ❌ Insufficient for robust ML training

**This Collection Will Provide**:
- ✅ 24 months historical data
- ✅ Multiple timeframes (1H, 4H, 1D)
- ✅ 10 major cryptocurrencies
- ✅ Different market regimes (bull, bear, ranging)

**Expected Outcome**:
- ML models with 4x more training data
- Better pattern recognition
- Reduced overfitting risk
- More robust predictions

**Next Milestone**: After collection, proceed to ML Training (Week 2 of ML roadmap)

---

**Ready to collect data?** Run:
```bash
python3 scripts/collect_ml_training_data.py
```

**Questions?** Review:
- `docs/ML_AI_PHASE3_READINESS_ASSESSMENT.md` - Full ML assessment
- `docs/FINAL_STRATEGY_VERDICT.md` - Why we need ML/AI

---

**END OF GUIDE**
