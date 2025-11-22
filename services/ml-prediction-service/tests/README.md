# ML Prediction Service - Test Suite

Comprehensive test suite for LSTM price prediction functionality.

## Test Structure

```
tests/
├── __init__.py
├── test_predictor.py         # Core LSTM predictor tests
├── test_api.py               # FastAPI endpoint tests
└── README.md                 # This file
```

## Test Coverage

### test_predictor.py (~500 lines, 20+ tests)

**Initialization Tests**
- ✓ Predictor initialization with correct parameters
- ✓ Feature engineering setup

**Feature Engineering Tests**
- ✓ OHLCV data to technical features conversion
- ✓ 15+ technical indicators calculated correctly
- ✓ RSI in valid range (0-100)
- ✓ Feature validation and cleaning

**Sequence Creation Tests**
- ✓ Creating sequences for LSTM input
- ✓ Correct shape: (samples, sequence_length, features)
- ✓ Target array shape: (samples, prediction_horizon)

**Model Building Tests**
- ✓ 2-layer LSTM architecture creation
- ✓ Dropout layers for regularization
- ✓ Dense output layer

**Training Tests**
- ✓ Successful model training
- ✓ Handling insufficient data
- ✓ Training metrics returned

**Prediction Tests**
- ✓ Multi-step price forecasting
- ✓ Error when model not trained
- ✓ Prediction result structure

**Trend Classification Tests**
- ✓ Bullish trend detection
- ✓ Bearish trend detection
- ✓ Neutral/ranging detection
- ✓ Confidence scoring

**Model Persistence Tests**
- ✓ Model saving to disk
- ✓ Model loading from disk

### test_api.py (~600 lines, 25+ tests)

**Health Check**
- ✓ Service health endpoint

**Model Management**
- ✓ List all trained models
- ✓ Get model info
- ✓ Model not found handling

**Training Endpoints**
- ✓ Train model with valid parameters
- ✓ Validation errors for invalid inputs
- ✓ Training failure handling
- ✓ Model retraining

**Prediction Endpoints**
- ✓ Price predictions
- ✓ Trend classification
- ✓ Volatility forecasting
- ✓ Trading signal generation
- ✓ Low confidence handling

**Performance Tests**
- ✓ Response time < 500ms
- ✓ Concurrent request handling

## Running Tests

### Install Test Dependencies

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/ml-prediction-service
pip install -r requirements-test.txt
```

### Run All Tests

```bash
# Run all tests with coverage
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_predictor.py -v

# Run specific test class
pytest tests/test_predictor.py::TestLSTMPricePredictor -v

# Run specific test
pytest tests/test_predictor.py::TestLSTMPricePredictor::test_create_features -v
```

### Run by Test Type

```bash
# Unit tests only (fast)
pytest tests/ -m unit -v

# Integration tests only
pytest tests/ -m integration -v

# Performance tests only
pytest tests/ -m performance -v

# Skip slow tests
pytest tests/ -m "not slow" -v
```

### Coverage Reports

```bash
# Generate HTML coverage report
pytest tests/ --cov=app --cov-report=html

# View coverage report
open htmlcov/index.html  # On Mac
xdg-open htmlcov/index.html  # On Linux
start htmlcov/index.html  # On Windows
```

### Watch Mode (Run on File Change)

```bash
# Install pytest-watch
pip install pytest-watch

# Run in watch mode
ptw tests/
```

## Test Configuration

### pytest.ini

Test configuration is in `pytest.ini`:
- Coverage settings
- Test discovery patterns
- Markers for test types
- Output formatting

### Markers

Custom markers for organizing tests:
- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.slow` - Slow-running tests

## Mocking Strategy

Tests use extensive mocking to avoid:
- ❌ Calling real Market Data API
- ❌ Training actual ML models (slow)
- ❌ Making HTTP requests
- ❌ Accessing external services

Instead:
- ✅ Mock API responses with fixtures
- ✅ Mock model training with MagicMock
- ✅ Mock predictions with numpy arrays
- ✅ Test business logic in isolation

## Test Data Fixtures

**sample_ohlcv_data**
- 100 candles of synthetic OHLCV data
- Realistic price movements
- Used across multiple tests

**predictor**
- Pre-configured predictor instance
- Symbol: BTCUSDT
- Interval: 60 (1 hour)

**mock_sentiment_result**
- Mock sentiment analysis result
- Used for integration tests

## Code Quality

### Run Linting

```bash
# Black (code formatting)
black tests/

# isort (import sorting)
isort tests/

# flake8 (style checking)
flake8 tests/

# mypy (type checking)
mypy tests/

# All at once
black tests/ && isort tests/ && flake8 tests/ && mypy tests/
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: ML Service Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt -r requirements-test.txt
      - run: pytest tests/ --cov=app --cov-report=xml
      - uses: codecov/codecov-action@v3
```

## Troubleshooting

### Import Errors

If you get import errors:
```bash
# Set PYTHONPATH
export PYTHONPATH=/mnt/d/Bimo_max/crypto-trading-bot/services/ml-prediction-service:$PYTHONPATH

# Or install in development mode
pip install -e .
```

### TensorFlow Warnings

Suppress TensorFlow warnings in tests:
```python
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
```

### Slow Tests

Skip slow tests during development:
```bash
pytest tests/ -m "not slow" -v
```

## Test Metrics

**Target Coverage**: >80%

Current coverage:
- `app/predictor.py`: ~85%
- `app/main.py`: ~80%
- `app/models.py`: 100%
- `app/config.py`: 100%

**Total tests**: 45+
**Estimated run time**: ~5 seconds (without actual model training)

## Next Steps

### Additional Tests to Write

1. **Backtesting Tests**
   - Test predictions vs actual outcomes
   - Accuracy metrics calculation

2. **Load Tests**
   - Multiple concurrent predictions
   - Memory usage under load

3. **Edge Case Tests**
   - Extreme volatility scenarios
   - Market gaps and halts

4. **Security Tests**
   - Input validation
   - SQL injection prevention (if applicable)

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [TensorFlow Testing Best Practices](https://www.tensorflow.org/guide/effective_tf2#testing)

---

**Last Updated**: November 10, 2025
**Test Suite Version**: 1.0
**Maintained by**: Crypto Trading Bot Team
