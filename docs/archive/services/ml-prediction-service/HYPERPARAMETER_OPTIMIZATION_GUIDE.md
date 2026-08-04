# ML Model Hyperparameter Optimization Guide

**Date**: 2025-11-20
**Purpose**: Optimize LSTM and GRU models to achieve R² > 0.95 (95%+ accuracy)
**Status**: Ready for execution

---

## Current Performance Baseline

Based on training logs from `training.log`:

| Symbol | Model | R² Score | MAE | RMSE | Status |
|--------|-------|----------|-----|------|--------|
| BTCUSDT | LSTM | 0.8437 | 0.0235 | 0.0311 | Needs optimization |
| BTCUSDT | GRU | **0.9039** | 0.0192 | 0.0244 | Best baseline |
| ETHUSDT | LSTM | 0.6968 | 0.0263 | 0.0319 | Needs optimization |
| ETHUSDT | GRU | 0.7973 | 0.0192 | 0.0261 | Needs optimization |

**Key Observation**: BTCUSDT GRU is closest to target (90.4%), needs +5% improvement.

---

## Optimization Strategy

### 1. Enhanced Feature Engineering

**Current Features**: 24 basic features
**New Features**: 40+ advanced technical indicators

#### New Indicators Added:
- **VWAP** (Volume-Weighted Average Price)
- **OBV** (On-Balance Volume) - cumulative volume indicator
- **ADX** (Average Directional Index) - trend strength
- **ROC** (Rate of Change) - momentum indicator
- **Ichimoku Cloud** components (Tenkan-sen, Kijun-sen, Senkou spans)
- **Enhanced Bollinger Bands** (position, width)
- **Multiple RSI periods** (7, 14)
- **MACD** with signal and histogram
- **Price correlation features** (autocorrelation)
- **Price vs VWAP** ratio

**Total Features**: 40+ predictive features per sample

### 2. Hyperparameter Optimization with Optuna

#### Search Space:

**Architecture Parameters:**
- `num_layers`: 2, 3, or 4 recurrent layers
- `first_layer_units`: 64, 128, or 256 units
- `dropout_rate`: 0.1 to 0.4 (prevents overfitting)
- `recurrent_dropout`: 0.0 to 0.2 (RNN-specific regularization)
- `dense_units`: 16, 32, 64, or 128 (final dense layer)
- `activation`: relu, tanh, or elu
- `l2_regularization`: 0.0 to 0.01
- `use_batch_norm`: True or False

**Training Parameters:**
- `batch_size`: 16, 32, or 64
- `learning_rate`: 1e-5 to 1e-2 (log scale)
- `optimizer`: Adam, AdamW, or RMSprop
- `scaler_type`: MinMax, Standard, or Robust

**Total Combinations**: 50 trials using Bayesian optimization

### 3. Advanced Training Techniques

#### Callbacks:
- **EarlyStopping**: patience=20, restores best weights
- **ReduceLROnPlateau**: reduces learning rate by 50% if no improvement

#### Regularization:
- Dropout layers (prevents overfitting)
- Recurrent dropout (RNN-specific)
- L2 kernel regularization
- Batch normalization (optional, optimized per model)

#### Data Splitting:
- Training: 85% of data
- Validation/Test: 15% of data
- Uses temporal ordering (no shuffle)

---

## Installation

### Install Dependencies

```bash
cd services/ml-prediction-service
pip install -r requirements.txt
```

**Key New Dependencies:**
- `optuna==3.5.0` - Bayesian hyperparameter optimization
- `optuna-dashboard==0.15.1` - Optional visualization

---

## Usage

### Step 1: Run Hyperparameter Optimization

This will optimize BTCUSDT and ETHUSDT models (both GRU and LSTM):

```bash
cd services/ml-prediction-service
python hyperparameter_optimizer.py
```

**What it does:**
1. Connects to TimescaleDB
2. Fetches 30 days of historical data
3. Creates 40+ enhanced features
4. Runs 50 optimization trials per model using Optuna
5. Trains final model with best hyperparameters
6. Saves optimized models to `trained_models_optimized/`

**Expected Duration:**
- Per symbol: ~30-60 minutes (50 trials × 2 models)
- Total: ~1-2 hours for BTCUSDT + ETHUSDT

**Output Files:**
```
trained_models_optimized/
├── BTCUSDT_60m_gru_optimized.keras
├── BTCUSDT_60m_gru_optimized_metadata.json
├── BTCUSDT_60m_gru_optimized_scaler.pkl
├── BTCUSDT_60m_lstm_optimized.keras
├── BTCUSDT_60m_lstm_optimized_metadata.json
├── BTCUSDT_60m_lstm_optimized_scaler.pkl
├── ETHUSDT_60m_gru_optimized.keras
├── ETHUSDT_60m_gru_optimized_metadata.json
├── ETHUSDT_60m_gru_optimized_scaler.pkl
├── ETHUSDT_60m_lstm_optimized.keras
├── ETHUSDT_60m_lstm_optimized_metadata.json
├── ETHUSDT_60m_lstm_optimized_scaler.pkl
└── optimization_results.json
```

### Step 2: Compare Performance

After optimization completes, run comparison:

```bash
python model_comparison.py
```

**What it does:**
1. Loads baseline results from `trained_models/training_results.json`
2. Loads optimized results from `trained_models_optimized/optimization_results.json`
3. Generates comprehensive comparison report
4. Exports hyperparameters to CSV

**Output Files:**
```
trained_models_optimized/
├── optimization_report.md          # Detailed comparison report
└── best_hyperparameters.csv        # All optimized hyperparameters
```

---

## Monitoring Optimization Progress

### Real-time Logs

The optimizer logs to both console and file:

```bash
# Watch logs in real-time
tail -f hyperparameter_optimization.log
```

### Log Format

```
2025-11-20 14:30:15 - INFO - Starting hyperparameter optimization for BTCUSDT GRU
2025-11-20 14:30:15 - INFO - Trials: 50
2025-11-20 14:30:20 - INFO - Created 42 enhanced features from 615 samples
2025-11-20 14:31:05 - INFO - Trial 0: R²=0.8523, MAE=0.0221, RMSE=0.0289
2025-11-20 14:31:48 - INFO - Trial 1: R²=0.9012, MAE=0.0195, RMSE=0.0257
2025-11-20 14:32:30 - INFO - Trial 2: R²=0.9234, MAE=0.0178, RMSE=0.0239
...
```

### Optuna Dashboard (Optional)

For visual monitoring:

```bash
# Start Optuna dashboard
optuna-dashboard sqlite:///optuna_study.db
```

Then open http://localhost:8080 in browser.

---

## Success Criteria

### Primary Goal
- **BTCUSDT models**: R² ≥ 0.95 (95% accuracy)
- **ETHUSDT models**: R² ≥ 0.90 (90% accuracy)

### Secondary Goals
- **Directional Accuracy**: ≥70% (predicts price direction correctly)
- **Training Time**: <10 minutes per model
- **No Overfitting**: Validation loss close to training loss
- **MAPE**: <5% (Mean Absolute Percentage Error)

### Expected Improvements

Based on optimization techniques:

| Metric | Current | Target | Expected |
|--------|---------|--------|----------|
| BTCUSDT R² | 0.9039 | 0.95 | 0.92-0.96 |
| ETHUSDT R² | 0.7973 | 0.90 | 0.85-0.92 |
| MAE | 0.0192 | <0.015 | 0.015-0.018 |
| RMSE | 0.0244 | <0.020 | 0.018-0.022 |

---

## Understanding Results

### Metrics Explained

#### R² Score (Coefficient of Determination)
- **Range**: -∞ to 1.0
- **Interpretation**:
  - 1.0 = Perfect prediction
  - 0.95 = 95% of variance explained
  - 0.0 = No better than mean baseline
  - Negative = Worse than mean baseline
- **Target**: ≥0.95 for BTCUSDT, ≥0.90 for ETHUSDT

#### MAE (Mean Absolute Error)
- Average absolute difference between predicted and actual
- Lower is better
- Same units as target (scaled 0-1)

#### RMSE (Root Mean Squared Error)
- Square root of average squared errors
- Penalizes large errors more than MAE
- Lower is better

#### Directional Accuracy
- Percentage of predictions with correct direction (up/down)
- **Target**: ≥70%
- Critical for trading decisions

### Reading Optimization Report

The `optimization_report.md` contains:

1. **Executive Summary**: Overall improvements
2. **Performance Table**: Side-by-side comparison
3. **Detailed Analysis**: Per-symbol breakdown
4. **Key Findings**: Best improvements, remaining gaps
5. **Recommendations**: Production deployment guidance

---

## Troubleshooting

### Issue: Out of Memory

**Symptoms**: TensorFlow OOM errors

**Solutions:**
1. Reduce `num_layers` search space to 2-3
2. Reduce `first_layer_units` to max 128
3. Reduce `batch_size` to 16
4. Close other applications

### Issue: Optimization Too Slow

**Symptoms**: Taking >4 hours

**Solutions:**
1. Reduce `n_trials` from 50 to 30
2. Use only one model type (GRU is faster)
3. Enable Optuna pruning (already enabled)
4. Run on GPU if available

### Issue: No Improvement

**Symptoms**: Optimized R² same or worse

**Solutions:**
1. Check for data quality issues
2. Increase `n_trials` to 100
3. Try different `scaler_type` manually
4. Review feature engineering (may need domain-specific features)

### Issue: Models Overfit

**Symptoms**: High training R², low validation R²

**Solutions:**
- Already handled by:
  - Dropout layers
  - L2 regularization
  - Early stopping
  - Batch normalization
- If persists: Increase `dropout_rate` range to 0.2-0.5

---

## Advanced Usage

### Optimize Single Symbol

Edit `hyperparameter_optimizer.py` line 1013:

```python
priority_symbols = ['BTCUSDT']  # Only BTCUSDT
```

### Optimize Single Model Type

Edit line 1014:

```python
model_types = ['GRU']  # Only GRU
```

### Increase Trials for Better Results

Edit line 11:

```python
OPTIMIZATION_TRIALS = 100  # More trials = better optimization (slower)
```

### Custom Feature Engineering

Edit `EnhancedFeatureEngineer.create_enhanced_features()` method to add custom indicators.

### Ensemble Models

Create ensemble by averaging predictions from multiple optimized models:

```python
# Load both LSTM and GRU
gru_pred = gru_model.predict(X)
lstm_pred = lstm_model.predict(X)

# Ensemble prediction (weighted average)
ensemble_pred = 0.6 * gru_pred + 0.4 * lstm_pred
```

---

## Next Steps After Optimization

### 1. Review Results
```bash
python model_comparison.py
cat trained_models_optimized/optimization_report.md
```

### 2. Deploy Best Models

If R² ≥ 0.95:
1. Copy optimized models to production directory
2. Update `train_all_models.py` to use optimized hyperparameters
3. Update API service to load optimized models

### 3. Continuous Improvement

**Schedule Retraining:**
- Retrain weekly with new data
- Re-run optimization monthly
- A/B test new hyperparameters

**Monitor Production:**
- Track prediction accuracy
- Compare actual vs predicted prices
- Alert if R² drops below 0.90

---

## File Structure

```
services/ml-prediction-service/
├── hyperparameter_optimizer.py      # Main optimization script
├── model_comparison.py              # Comparison tool
├── train_all_models.py              # Baseline training (existing)
├── HYPERPARAMETER_OPTIMIZATION_GUIDE.md  # This file
├── requirements.txt                 # Updated dependencies
├── hyperparameter_optimization.log  # Optimization logs
├── trained_models/                  # Baseline models
│   ├── BTCUSDT_60m_gru.keras
│   ├── BTCUSDT_60m_lstm.keras
│   └── training_results.json
└── trained_models_optimized/        # Optimized models
    ├── BTCUSDT_60m_gru_optimized.keras
    ├── BTCUSDT_60m_gru_optimized_metadata.json
    ├── BTCUSDT_60m_gru_optimized_scaler.pkl
    ├── optimization_results.json
    ├── optimization_report.md
    └── best_hyperparameters.csv
```

---

## Optimization Theory

### Why Bayesian Optimization?

**Traditional Grid Search:**
- Tests ALL combinations: 10 params × 3 values = 59,049 trials
- Time: 59,049 × 30 sec = 20 days

**Bayesian Optimization (Optuna):**
- Tests SMART combinations: 50 trials
- Time: 50 × 30 sec = 25 minutes
- Uses past trial results to guide next trials
- Focuses on promising regions of hyperparameter space

### Key Techniques

1. **Acquisition Function**: Balances exploration vs exploitation
2. **Surrogate Model**: Gaussian Process estimates objective function
3. **Pruning**: Stops unpromising trials early
4. **Multi-objective**: Can optimize for multiple metrics

---

## References

- **Optuna Documentation**: https://optuna.readthedocs.io/
- **TensorFlow Guides**: https://www.tensorflow.org/guide
- **Time Series Forecasting**: https://otexts.com/fpp3/
- **Hyperparameter Tuning Best Practices**: https://arxiv.org/abs/2003.05689

---

## Support

For issues or questions:
1. Check logs: `hyperparameter_optimization.log`
2. Review training metrics in console output
3. Compare with baseline: `python model_comparison.py`
4. Consult this guide's Troubleshooting section

---

**Generated by**: ML Optimization Agent
**Version**: 1.0
**Date**: 2025-11-20
