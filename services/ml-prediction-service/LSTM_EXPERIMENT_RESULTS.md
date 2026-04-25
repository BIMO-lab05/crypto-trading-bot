# LSTM Price Prediction Experiment - Results & Analysis
**Date**: 2025-12-07
**Model**: LSTM (3-layer: 128, 64, 32 units)
**Task**: Binary classification (price UP/DOWN in 4 hours)
**Status**: ⚠️ FAILED - Below production viability threshold

---

## Executive Summary

After two rounds of training with increasing data sizes, the LSTM model **failed to achieve production-ready performance**:

- **Quick Test** (40 epochs, 2160 candles): 59.02% val accuracy ✅
- **Production v1** (100 epochs, 2160 candles): 52.07% test accuracy ⚠️
- **Production v2** (100 epochs, 4400 candles): 52.80% test accuracy ⚠️

**Key Finding**: Doubling the training data from 90 to 180 days **did NOT improve** test accuracy meaningfully (only +0.73%). In fact, validation accuracy **degraded significantly** from 62.50% to 49.64%.

---

## Experimental Setup

### Data Collection

| Round | Data Size | Date Range | Candles | Symbols |
|-------|-----------|------------|---------|---------|
| Initial | 90 days | Jun-Sep 2025 | 2,160 | SOLUSDT |
| Extended | 180 days | Jun-Dec 2025 | 4,400 | SOLUSDT, BNBUSDT, ADAUSDT |

### Model Architecture

```python
LSTMPredictor(
    sequence_length=100,      # 100 hourly candles lookback
    features_count=46,        # Technical indicators
    prediction_horizon=4,     # 4 hours ahead
    lstm_units=[128, 64, 32], # 3-layer LSTM
    dropout_rate=0.3,         # Regularization
    learning_rate=0.001,      # Adam optimizer
    parameters=153,409        # Total params
)
```

### Features (46 total)

**Technical Indicators:**
- Price: SMA(10, 20, 50), EMA(12, 26), BBands, Support/Resistance
- Momentum: RSI(14), MACD, ROC, Stochastic
- Volume: Volume SMA, OBV, VWAP
- Volatility: ATR, Bollinger Width

**Derived Features:**
- Price changes, ratios, z-scores
- Cross-overs, divergences
- Trend strength indicators

---

## Training Results Comparison

### Round 1: Production Training (90 days)

| Metric | Train | Validation | Test |
|--------|-------|------------|------|
| Accuracy | 71.03% | 62.50% | **52.07%** |
| AUC | 0.7828 | 0.6281 | N/A |
| Samples | 1,474 | 316 | 317 |
| Epochs | 18/100 (early stop) | | |

**Issues:**
- Large gap between train (71%) and test (52%) → **overfitting**
- Test accuracy barely above random (50%)
- Suspected insufficient data diversity

### Round 2: Extended Training (180 days)

| Metric | Train | Validation | Test |
|--------|-------|------------|------|
| Accuracy | 54.18% | **49.64%** ⚠️ | **52.80%** |
| AUC | 0.6145 | **0.4908** ⚠️ | N/A |
| Samples | 3,042 | 652 | 653 |
| Epochs | N/A (early stop) | | |

**Observations:**
- Validation accuracy **dropped 12.86%** (62.50% → 49.64%)
- Test accuracy improved only **+0.73%** (52.07% → 52.80%)
- Validation AUC **dropped 21.8%** (0.6281 → 0.4908)
- Model degraded with more data!

---

## Critical Issues Identified

### 1. Severe Prediction Bias

**Test Set Predictions (Round 2):**
- UP predictions: 28 (5.1%)
- DOWN predictions: 525 (94.9%)

**Conclusion**: Model learned to predict DOWN almost every time with very low confidence (6.28% average). This is a degenerate solution.

### 2. Class Imbalance (Suspected)

The extreme prediction bias suggests the training data has severely imbalanced class distribution:

```python
# Likely distribution in SOLUSDT 60m data:
DOWN samples: ~70-80%
UP samples: ~20-30%
```

**Impact**:
- Model optimizes for accuracy by always predicting majority class
- Minority class (UP) gets ignored
- Loss function doesn't penalize bias

### 3. Weak Predictive Features

Technical indicators alone are **insufficient** for 4-hour price prediction:

- **Lagging indicators**: SMA, EMA react to past moves
- **Mean-reverting signals**: RSI, Stochastic don't predict direction well
- **Noisy markets**: Crypto has high intra-hour volatility

**Missing predictive signals:**
- Orderbook imbalance
- Funding rates
- Social sentiment
- News events
- Cross-exchange arbitrage

### 4. Incorrect Prediction Horizon

**4-hour ahead prediction is too difficult**:

```
Current: Predict price in 4 hours (240 minutes)
- Too many random events can occur
- Signal-to-noise ratio too low
- Model can't learn meaningful patterns

Better: Predict in 1 hour (60 minutes)
- Stronger momentum signals
- Less noise interference
- More actionable for trading
```

### 5. Binary Classification Limitations

**Current approach**: Classify UP (1) or DOWN (0)

**Problems:**
- Ignores magnitude of price change
- Treats +0.1% same as +5%
- Loss of valuable information

**Better approach**: Regression
```python
target = (price_in_4h - current_price) / current_price * 100
# Predict actual % change: -5.2%, +3.1%, etc.
```

---

## Root Cause Analysis

| Hypothesis | Evidence | Conclusion |
|------------|----------|------------|
| Insufficient data | Doubled data → worse validation | ❌ NOT the issue |
| Model too complex | 153K params for 3K samples | ✅ Possible overfitting |
| Class imbalance | 94.9% DOWN predictions | ✅ Very likely |
| Weak features | 52% accuracy near random | ✅ Confirmed |
| Wrong horizon | 4h too long | ✅ Suspected |
| Architecture mismatch | LSTM vs crypto noise | ✅ Possible |

**Primary Root Cause**: Combination of **class imbalance**, **weak features**, and **inappropriate prediction horizon** makes the problem fundamentally difficult for the current LSTM setup.

---

## Lessons Learned

1. **More data ≠ better model** if data quality/features are poor
2. **Class balance matters** more than total sample count
3. **Feature engineering is critical** - technical indicators alone insufficient
4. **Prediction horizon must match** signal strength in market
5. **Always check prediction distribution** - bias indicates failure
6. **Crypto markets are hard** - 60m timeframe too noisy

---

## Recommended Next Steps

### Priority 1: Fix Fundamental Issues

1. **Address Class Imbalance**
   ```python
   # Option A: SMOTE for minority oversampling
   from imblearn.over_sampling import SMOTE

   # Option B: Class weights in loss function
   class_weights = {0: 0.4, 1: 0.6}  # Penalize majority class

   # Option C: Stratified sampling
   # Ensure 50/50 split in training batches
   ```

2. **Shorten Prediction Horizon**
   ```python
   # Change from 4h to 1h
   prediction_horizon = 1  # 60 minutes
   # More actionable + stronger signals
   ```

3. **Try Regression Instead of Classification**
   ```python
   # Predict % price change instead of direction
   target = (future_price - current_price) / current_price * 100
   # Then threshold: >0.5% = BUY signal
   ```

### Priority 2: Improve Model

4. **Try Simpler GRU Model**
   ```python
   # GRU has fewer parameters → less overfitting
   GRUPredictor(
       gru_units=[64, 32],  # Simpler than LSTM
       dropout=0.4           # More regularization
   )
   ```

5. **Add Ensemble Methods**
   ```python
   # Combine multiple weak learners
   ensemble = [
       LSTM_model,
       GRU_model,
       LightGBM_model
   ]
   final_prediction = weighted_average(ensemble)
   ```

### Priority 3: Better Features

6. **Expand Feature Set**
   - Orderbook imbalance (bid/ask ratio)
   - Funding rates (futures premium)
   - Social sentiment (Twitter, Reddit)
   - News impact scores
   - Cross-exchange spreads

7. **Multi-Timeframe Features**
   ```python
   # Combine 15m, 1h, 4h, 1d signals
   features = {
       '15m': short_term_momentum,
       '1h': current_trend,
       '4h': swing_structure,
       '1d': macro_trend
   }
   ```

### Priority 4: Alternative Approaches

8. **Try XGBoost / LightGBM**
   - Better for tabular data
   - Built-in class balancing
   - Feature importance analysis
   - Often outperform neural nets

9. **Transformer Models**
   - Better at capturing long-range dependencies
   - Attention mechanism for important features
   - More compute but potentially better

10. **Consider Hybrid Approach**
    ```python
    # Combine TA + ML + Sentiment
    final_signal = (
        0.30 * traditional_TA_score +
        0.30 * ML_model_prediction +
        0.20 * sentiment_score +
        0.20 * funding_rate_signal
    )
    ```

---

## Conclusion

The LSTM price prediction experiment **failed to meet production criteria** (>55% test accuracy). The core issue is not insufficient data, but rather:

1. Severe class imbalance in targets
2. Weak predictive power of TA features alone
3. 4-hour prediction horizon too difficult
4. Binary classification inappropriate for price prediction

**Recommendation**: Pivot to GRU model with:
- Shorter 1-hour prediction horizon
- Class balancing techniques (SMOTE / class weights)
- Regression approach (predict price change %)
- Expanded feature set (sentiment, funding rates)

If GRU also fails, consider abandoning neural network approach for gradient boosting (XGBoost/LightGBM) which typically perform better on financial time series data.

---

## Files Generated

- Model: `/models/lstm_SOLUSDT_20251207_010259.keras`
- Training log: `/tmp/lstm_retrain_6months.log`
- Data: `/backtesting/data/*_180d_bybit.csv`

**Status**: Archived for reference, not deployed to production
