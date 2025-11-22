# Phase 1: Technical Analysis Testing - Completion Guide

**Status:** 25% Complete
**Created:** 2025-11-11
**Estimated Remaining:** 40-50 hours

---

## ✅ What's Already Complete

### 1. RSI Calculator Tests (`test_rsi_calculator.py`) - ✅ **COMPLETE**
- **File:** `/services/technical-analysis/tests/unit/test_rsi_calculator.py`
- **Tests:** 30+ comprehensive tests
- **Coverage:** Calculation, signals, edge cases, performance
- **Lines:** 450+

**Test Categories:**
- Initialization tests
- Calculation accuracy (uptrend, downtrend, sideways)
- Signal generation (oversold, overbought, neutral)
- Edge cases (all gains, all losses, flat prices, extreme volatility)
- Calculate with signal integration
- RSI series calculation
- Known values validation
- Performance tests (10k data points)
- Realistic Bitcoin scenario

### 2. MACD Calculator Tests (`test_macd_calculator.py`) - ✅ **COMPLETE**
- **File:** `/services/technical-analysis/tests/unit/test_macd_calculator.py`
- **Tests:** 30+ comprehensive tests
- **Coverage:** Calculation, signals, crossovers, edge cases
- **Lines:** 500+

**Test Categories:**
- Initialization with default/custom periods
- Calculation structure and accuracy
- Signal generation (positive/negative histogram)
- Crossover detection (bullish/bearish)
- Calculate with signal (confidence boost)
- MACD series calculation
- Edge cases (flat prices, extreme volatility, NaN handling)
- Performance tests
- Trend reversal detection

---

## 🔄 Remaining Work

### 3. Bollinger Bands Tests - ⏳ **NEXT**

**Template Pattern** (Follow RSI/MACD structure):

```python
#!/usr/bin/env python3
"""Unit Tests for Bollinger Bands Calculator"""

import pytest
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis')

from app.indicators.bollinger_bands import BollingerBandsCalculator
from app.models import SignalType

# Test Categories to Implement:

# 1. Initialization Tests
def test_bb_initialization():
    """Test default period=20, std_dev=2.0"""

def test_bb_custom_parameters():
    """Test custom period and std_dev"""

# 2. Calculation Tests
def test_bb_calculation_structure():
    """Test returns dict with upper_band, middle_band, lower_band, current_price, bandwidth"""

def test_bb_uptrend_bands_wider():
    """In uptrend with volatility, bands should be wider"""

def test_bb_band_math():
    """upper = middle + (std * std_dev), lower = middle - (std * std_dev)"""

# 3. Signal Tests
def test_signal_price_below_lower_band_buy():
    """Price < lower_band → BUY (oversold)"""

def test_signal_price_above_upper_band_sell():
    """Price > upper_band → SELL (overbought)"""

def test_signal_price_in_middle_hold():
    """Price near middle_band → HOLD"""

# 4. BB Squeeze Tests
def test_bb_squeeze_detection():
    """Low bandwidth indicates squeeze (low volatility)"""

def test_bb_expansion_detection():
    """High bandwidth indicates expansion (high volatility)"""

# 5. Edge Cases
def test_bb_flat_prices():
def test_bb_extreme_volatility():
def test_bb_insufficient_data():

# 6. Performance Tests
def test_bb_large_dataset():
def test_bb_series_calculation():
```

**Key Bollinger Bands Concepts:**
- **Upper Band:** SMA + (std_dev × StdDev)
- **Middle Band:** Simple Moving Average
- **Lower Band:** SMA - (std_dev × StdDev)
- **Bandwidth:** (Upper - Lower) / Middle (measures volatility)
- **%B:** (Price - Lower) / (Upper - Lower) (price position within bands)

**Signal Logic:**
- Price touches/crosses lower band → BUY (oversold)
- Price touches/crosses upper band → SELL (overbought)
- Price at middle band → HOLD
- BB Squeeze (low bandwidth) → Potential breakout coming
- BB Expansion → High volatility, trend in motion

**Estimated:** 25 tests, 2-3 hours

---

### 4. Moving Averages Tests (EMA/SMA) - ⏳ **PENDING**

**File:** `test_moving_averages.py`

```python
# Test both EMA (Exponential) and SMA (Simple) calculators

# EMA Tests:
def test_ema_calculation():
    """Test EMA more responsive to recent prices than SMA"""

def test_ema_convergence():
    """EMA converges to price over time"""

def test_ema_vs_sma_responsiveness():
    """EMA should react faster to price changes"""

# SMA Tests:
def test_sma_calculation():
    """Simple average of N periods"""

def test_sma_smoothing():
    """SMA smooths out noise"""

# Crossover Tests:
def test_golden_cross_detection():
    """Fast EMA crosses above slow EMA → BUY"""

def test_death_cross_detection():
    """Fast EMA crosses below slow EMA → SELL"""

# Signal Tests:
def test_price_above_ma_bullish():
def test_price_below_ma_bearish():
def test_ma_slope_trend_detection():
```

**Estimated:** 20 tests, 2 hours

---

### 5. Additional Indicator Tests - ⏳ **PENDING**

**ATR (Average True Range)** - `test_atr.py` (15 tests, 1.5 hours)
- Volatility measurement
- High ATR = high volatility
- Low ATR = low volatility
- No directional signal, just volatility

**Stochastic Oscillator** - `test_stochastic.py` (20 tests, 2 hours)
- %K and %D lines
- Overbought > 80, Oversold < 20
- Crossovers
- Divergence detection

**Trend Filter** - `test_trend_filter.py` (15 tests, 1.5 hours)
- Identifies market trend (BULLISH/BEARISH/NEUTRAL)
- Uses multiple MA or price action
- Filters out counter-trend signals

**Volume Confirmation** - `test_volume_confirmation.py` (15 tests, 1.5 hours)
- Confirms price moves with volume
- High volume = strong signal
- Low volume = weak signal
- Volume divergence

---

### 6. Integration Tests - ⏳ **PENDING**

**File:** `tests/integration/test_indicator_pipeline.py`

```python
"""Integration tests for indicator pipeline"""

def test_all_indicators_calculated_together():
    """Test calculating all indicators on same dataset"""
    # RSI, MACD, BB, EMA, ATR, Stochastic, Trend, Volume
    # All should work together without conflicts

def test_indicator_signal_aggregation():
    """Test combining signals from multiple indicators"""
    # Example: RSI oversold + MACD bullish crossover + Price below BB lower
    # Should produce strong BUY signal

def test_indicator_performance_batch():
    """Test calculating all indicators is reasonably fast"""

def test_indicator_consistency():
    """Same data should produce same results every time"""

def test_conflicting_indicators_handled():
    """When indicators conflict (RSI buy, MACD sell), system handles it"""

def test_indicator_caching():
    """Indicator results are cached to avoid recalculation"""

def test_multi_timeframe_indicators():
    """Indicators calculated on different timeframes (1h, 4h, 1d)"""

def test_indicator_updates_streaming():
    """Indicators update correctly with new data arriving"""
```

**Estimated:** 15 tests, 3 hours

---

### 7. API Endpoint Integration Tests - ⏳ **PENDING**

**File:** `tests/integration/test_api_endpoints.py`

```python
"""Test Technical Analysis Service API endpoints"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    """GET /health"""
    response = client.get("/health")
    assert response.status_code == 200

def test_calculate_rsi_endpoint():
    """POST /indicators/rsi"""
    data = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "period": 14
    }
    response = client.post("/indicators/rsi", json=data)
    assert response.status_code == 200
    assert "value" in response.json()

def test_calculate_all_indicators_endpoint():
    """POST /indicators/all"""
    # Returns all indicators in one call

def test_invalid_parameters_return_400():
    """Test validation"""

def test_insufficient_data_returns_appropriate_response():
    """When not enough data, return clear message"""

def test_concurrent_requests_handled():
    """Multiple simultaneous requests work"""
```

**Estimated:** 15 tests, 2 hours

---

### 8. Performance & Load Tests - ⏳ **PENDING**

**File:** `tests/performance/test_ta_performance.py`

```python
"""Performance and load testing"""

def test_indicator_calculation_latency():
    """Target: <100ms for all indicators on 1000 candles"""

def test_concurrent_symbol_processing():
    """Process 10 symbols concurrently"""

def test_memory_usage_stable():
    """Memory doesn't grow over time"""

def test_sustained_load():
    """Handle 100 req/sec for 60 seconds"""
```

**K6 Load Test Script:** `tests/performance/load_test.js`

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '30s', target: 20 },  // Ramp up
    { duration: '1m', target: 50 },   // Sustained load
    { duration: '30s', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% < 500ms
    http_req_failed: ['rate<0.01'],    // <1% errors
  },
};

export default function () {
  let response = http.post('http://localhost:8004/indicators/all',
    JSON.stringify({
      symbol: 'BTCUSDT',
      interval: '1h'
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'has RSI': (r) => r.json().RSI !== undefined,
  });

  sleep(1);
}
```

**Run:** `k6 run tests/performance/load_test.js`

**Estimated:** 10 tests + K6 script, 3 hours

---

### 9. CI/CD Setup - ⏳ **PENDING**

**File:** `.github/workflows/technical-analysis-tests.yml`

```yaml
name: Technical Analysis Tests

on:
  push:
    paths:
      - 'services/technical-analysis/**'
  pull_request:
    paths:
      - 'services/technical-analysis/**'

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          cd services/technical-analysis
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio

      - name: Run unit tests
        run: |
          cd services/technical-analysis
          pytest tests/unit -v --cov=app --cov-report=xml

      - name: Run integration tests
        run: |
          cd services/technical-analysis
          pytest tests/integration -v

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./services/technical-analysis/coverage.xml
          flags: technical-analysis
```

**Pre-commit Hook:** `.pre-commit-config.yaml`

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest-technical-analysis
        name: Test Technical Analysis
        entry: bash -c 'cd services/technical-analysis && pytest tests/unit --tb=short -q'
        language: system
        pass_filenames: false
        always_run: true
```

**Estimated:** 2 hours

---

### 10. Documentation - ⏳ **PENDING**

**File:** `services/technical-analysis/tests/README.md`

```markdown
# Technical Analysis Service - Test Suite

## Overview
Comprehensive test suite with 150+ tests covering all indicators.

## Test Coverage
- **RSI:** 30 tests ✅
- **MACD:** 30 tests ✅
- **Bollinger Bands:** 25 tests
- **Moving Averages:** 20 tests
- **ATR:** 15 tests
- **Stochastic:** 20 tests
- **Trend Filter:** 15 tests
- **Volume:** 15 tests
- **Integration:** 15 tests
- **API:** 15 tests
- **Performance:** 10 tests

**Total:** 200+ tests, 85%+ coverage

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit -v

# Specific indicator
pytest tests/unit/test_rsi_calculator.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html

# Performance tests
pytest tests/performance -v
```

## Test Patterns

All indicator tests follow this structure:
1. Initialization tests
2. Calculation tests (uptrend, downtrend, sideways)
3. Signal generation tests
4. Edge cases (flat, volatile, NaN)
5. Performance tests (large datasets)
6. Integration scenarios

See `test_rsi_calculator.py` and `test_macd_calculator.py` for examples.
```

**Estimated:** 1 hour

---

## 📊 Phase 1 Summary

### Progress Tracker

| Component | Tests | Status | Time |
|-----------|-------|--------|------|
| RSI Calculator | 30 | ✅ Complete | 3 hrs |
| MACD Calculator | 30 | ✅ Complete | 3 hrs |
| Bollinger Bands | 25 | ⏳ Pending | 3 hrs |
| Moving Averages | 20 | ⏳ Pending | 2 hrs |
| ATR | 15 | ⏳ Pending | 1.5 hrs |
| Stochastic | 20 | ⏳ Pending | 2 hrs |
| Trend Filter | 15 | ⏳ Pending | 1.5 hrs |
| Volume | 15 | ⏳ Pending | 1.5 hrs |
| Integration Tests | 15 | ⏳ Pending | 3 hrs |
| API Tests | 15 | ⏳ Pending | 2 hrs |
| Performance | 10 | ⏳ Pending | 3 hrs |
| CI/CD Setup | - | ⏳ Pending | 2 hrs |
| Documentation | - | ⏳ Pending | 1 hr |
| **TOTAL** | **210** | **25% Done** | **29 hrs remaining** |

### Current Status
- **Completed:** 60 tests (RSI + MACD)
- **Remaining:** 150 tests
- **Estimated Time:** 29 hours
- **Coverage Target:** 85%+ (currently ~30%)

---

## 🚀 Quick Start Guide

### To Continue Phase 1:

1. **Create remaining indicator tests** following RSI/MACD pattern:
   ```bash
   # Copy template
   cp test_rsi_calculator.py test_bollinger_bands.py

   # Modify for Bollinger Bands logic
   # Update fixtures, test cases, assertions
   ```

2. **Run tests as you create them:**
   ```bash
   pytest tests/unit/test_bollinger_bands.py -v
   ```

3. **Check coverage:**
   ```bash
   pytest tests/unit --cov=app.indicators --cov-report=term-missing
   ```

4. **Create integration tests** after all unit tests done

5. **Setup CI/CD** once tests are stable

6. **Document** patterns and results

---

## 📝 Key Patterns Established

### Test Structure (from RSI/MACD):

```python
# 1. Fixtures
@pytest.fixture
def calculator():
    return IndicatorCalculator()

@pytest.fixture
def sample_data():
    return pd.DataFrame({'close': [...]})

# 2. Initialization
def test_initialization():
    """Test default parameters"""

# 3. Calculation
def test_calculation_uptrend():
    """Test with uptrending data"""

# 4. Signals
def test_signal_buy_condition():
    """Test BUY signal generation"""

# 5. Edge Cases
def test_insufficient_data():
    """Returns None when not enough data"""

# 6. Performance
def test_large_dataset():
    """Handles 10k+ points efficiently"""
```

### Naming Conventions:
- Test files: `test_<indicator>_calculator.py`
- Test functions: `test_<component>_<scenario>_<expected>`
- Fixtures: Descriptive names (`macd_calculator`, `sample_uptrend_data`)

---

## 🎯 Success Criteria

Phase 1 complete when:
- ✅ All 8 indicators have comprehensive unit tests
- ✅ Integration tests validate indicator pipeline
- ✅ API endpoint tests pass
- ✅ Performance tests meet SLA (<100ms)
- ✅ Test coverage > 85%
- ✅ CI/CD pipeline runs automatically
- ✅ Documentation complete

---

## 📞 Next Steps

After completing Phase 1:
1. Review test coverage report
2. Fix any gaps
3. Document learnings
4. Move to **Phase 2: Market Data Service**

---

**Status:** Guide Complete
**Last Updated:** 2025-11-11
**Maintainer:** Development Team
