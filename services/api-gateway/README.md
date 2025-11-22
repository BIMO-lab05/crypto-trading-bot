# API Gateway Service

Unified entry point for all Crypto Trading Bot microservices.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env

# 3. Generate JWT secret (REQUIRED)
openssl rand -hex 32
# Add to .env: JWT_SECRET_KEY=<generated_value>

# 4. Start service
uvicorn app.main:app --port 8000 --reload
```

## Features

- Service routing to backend microservices
- Health monitoring and aggregation
- CORS configuration
- Comprehensive error handling
- Request logging
- Dashboard data aggregation
- **Phase 3 AI Integration**: Sentiment Analysis & Multi-Timeframe Analysis

## Documentation

- **API Docs**: http://localhost:8000/docs (when running)
- **Code Review**: [CODE_REVIEW.md](CODE_REVIEW.md)
- **Phase 3 Implementation**: See project root `/PHASE3_ENDPOINTS_IMPLEMENTATION_REPORT.md`

## Testing

### Running Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run unit tests with coverage
pytest tests/ -v --cov=app --cov-report=html --cov-report=term

# Run only Phase 3 endpoint tests
pytest tests/test_phase3_endpoints.py -v

# Run with markers
pytest tests/ -v -m "not slow"
```

### Integration Tests

Integration tests require backend services to be running:

```bash
# Start required services first
docker-compose up -d sentiment-analysis-service technical-analysis

# Run integration tests
pytest tests/integration/test_phase3_integration.py -v -m integration

# Run all integration tests (slower)
pytest tests/integration/ -v -m integration
```

### Test Coverage Requirements

- **Unit Tests**: >90% coverage target
- **Phase 3 Endpoints**: 100% coverage (all endpoints tested)
- **Integration Tests**: E2E flow validation

### Phase 3 Testing Guide

#### Unit Test Structure

The Phase 3 unit tests (`test_phase3_endpoints.py`) cover:

1. **Sentiment Analysis Endpoints** (4 endpoints)
   - News sentiment: `/api/sentiment/news/{symbol}`
   - Social sentiment: `/api/sentiment/social/{symbol}`
   - Combined sentiment: `/api/sentiment/combined/{symbol}`
   - Sentiment trend: `/api/sentiment/trend/{symbol}`

2. **Multi-Timeframe Analysis Endpoints** (2 endpoints)
   - Multi-timeframe analysis: `/api/analysis/multi-timeframe/{symbol}`
   - Indicator signals: `/api/analysis/indicators/signal/{symbol}`

3. **Test Categories**:
   - Successful response handling
   - Response structure validation
   - Error handling (404, 503, timeout)
   - Query parameter handling
   - Multiple symbols testing
   - Edge cases (invalid data, service unavailable)

#### Mock Setup for Development

Phase 3 tests use mocked backend services, so no actual services need to be running for unit tests:

```python
# Example: Mocking sentiment service response
@pytest.fixture
def mock_news_sentiment_response():
    return {
        "symbol": "BTCUSDT",
        "sentiment_label": "BULLISH",
        "sentiment_score": 0.72,
        "confidence": 0.85,
        "news_count": 15,
        "analyzed_at": 1700000000000
    }
```

#### Running Specific Test Classes

```bash
# Test only news sentiment endpoint
pytest tests/test_phase3_endpoints.py::TestNewsSentimentEndpoint -v

# Test only multi-timeframe analysis
pytest tests/test_phase3_endpoints.py::TestMultiTimeframeAnalysisEndpoint -v

# Test error handling
pytest tests/test_phase3_endpoints.py::TestPhase3ErrorHandling -v
```

#### Continuous Integration

Add to CI/CD pipeline:

```yaml
# .github/workflows/test.yml
- name: Run Phase 3 Unit Tests
  run: |
    pytest tests/test_phase3_endpoints.py -v --cov=app --cov-report=xml

- name: Check Coverage
  run: |
    coverage report --fail-under=90
```

#### Test Data Fixtures

Common test fixtures are available in `tests/conftest.py`:
- `mock_service_proxy`: Mock ServiceProxy for testing
- `test_client`: FastAPI TestClient
- `mock_httpx_client`: Mock HTTP client

Phase 3 specific fixtures in `test_phase3_endpoints.py`:
- `mock_news_sentiment_response`
- `mock_social_sentiment_response`
- `mock_combined_sentiment_response`
- `mock_sentiment_trend_response`
- `mock_multi_timeframe_response`
- `mock_indicator_signal_response`

#### Debugging Failed Tests

```bash
# Run with verbose output and show print statements
pytest tests/test_phase3_endpoints.py -vvs

# Run specific failing test
pytest tests/test_phase3_endpoints.py::TestNewsSentimentEndpoint::test_get_news_sentiment_success -vvs

# Run with debugger on failure
pytest tests/test_phase3_endpoints.py --pdb
```

### Integration Test Requirements

Integration tests (`test_phase3_integration.py`) require:

1. **Running Services**:
   - API Gateway: http://localhost:8000
   - Sentiment Analysis: http://localhost:8008
   - Technical Analysis: http://localhost:8004

2. **Service Setup**:
   ```bash
   # Start all required services
   docker-compose up -d api-gateway sentiment-analysis-service technical-analysis

   # Verify services are healthy
   curl http://localhost:8000/health
   curl http://localhost:8008/health
   curl http://localhost:8004/health
   ```

3. **Running Integration Tests**:
   ```bash
   # Run all integration tests
   pytest tests/integration/test_phase3_integration.py -v -m integration

   # Skip slow tests
   pytest tests/integration/test_phase3_integration.py -v -m "integration and not slow"
   ```

4. **Integration Test Categories**:
   - End-to-end flow validation
   - Response format verification
   - Cross-service communication
   - Error propagation testing
   - Performance benchmarks
   - Data consistency checks

## Environment Variables

See `.env.example` for all configuration options.

**Required**:
- `JWT_SECRET_KEY` - Minimum 32 characters

**Phase 3 Services**:
- `SENTIMENT_ANALYSIS_URL` - Default: http://localhost:8008
- `TECHNICAL_ANALYSIS_URL` - Default: http://localhost:8004

## Status

✅ **Production Ready** - All tests passing, Phase 3 AI integration complete

### Test Status
- Unit Tests: 100% passing
- Phase 3 Unit Tests: 50+ tests covering all endpoints
- Integration Tests: E2E validation for all Phase 3 flows
- Coverage Target: >90% (achieved)
