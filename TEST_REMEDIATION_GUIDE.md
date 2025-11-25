# Test Infrastructure Remediation Guide

Detailed instructions for fixing identified test quality issues across the crypto trading bot.

---

## Issue 1: Missing Conftest.py Files

### Affected Services
1. portfolio-manager
2. notification-service
3. ml-prediction-service
4. sentiment-analysis-service

### Solution Template

Create `/services/[SERVICE]/tests/conftest.py`:

```python
"""
[SERVICE NAME] - pytest Configuration and Fixtures
Purpose: Shared test fixtures and configuration for all tests
"""

import pytest
import os
from typing import AsyncGenerator, Generator
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
import asyncio

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables"""
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DEBUG"] = "false"
    os.environ["LOG_LEVEL"] = "INFO"
    # Add service-specific env vars
    os.environ["SERVICE_PORT"] = "8000"


# ============================================================================
# CONFIGURATION FIXTURES
# ============================================================================

@pytest.fixture
def test_settings():
    """Provide test settings instance"""
    from app.config import Settings
    return Settings(
        environment="test",
        debug=False,
        service_port=8000,
        # Add all service-specific settings
    )


# ============================================================================
# FASTAPI TEST CLIENT
# ============================================================================

@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """
    FastAPI test client with dependency overrides

    Usage:
        response = client.get("/health")
    """
    from app.main import app

    with TestClient(app) as client:
        yield client


# ============================================================================
# MOCK FIXTURES
# ============================================================================

@pytest.fixture
async def mock_external_service() -> AsyncGenerator[Mock, None]:
    """Mock external service dependency"""
    mock = AsyncMock()
    # Configure mock methods with return values
    mock.get_data = AsyncMock(return_value={"status": "ok"})
    mock.post_data = AsyncMock(return_value={"id": "123"})
    mock.close = AsyncMock()

    yield mock

    # Cleanup
    await mock.close()


@pytest.fixture
def mock_database() -> Generator[Mock, None, None]:
    """Mock database connection"""
    mock_db = Mock()
    mock_db.query = Mock(return_value=[])
    mock_db.add = Mock()
    mock_db.commit = Mock()
    mock_db.rollback = Mock()
    mock_db.close = Mock()

    return mock_db


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_api_response():
    """Sample successful API response"""
    return {
        "success": True,
        "data": {
            "id": "test-123",
            "timestamp": 1700000000,
            "status": "active"
        }
    }


@pytest.fixture
def sample_error_response():
    """Sample error API response"""
    return {
        "success": False,
        "error": "Test error message",
        "code": 400
    }


# ============================================================================
# AUTO-USE FIXTURES (RUN BEFORE EVERY TEST)
# ============================================================================

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mocks before each test"""
    yield
    # Cleanup happens automatically


@pytest.fixture(autouse=True)
def isolate_async_tasks():
    """Isolate async tasks to prevent interference"""
    # Get current event loop
    loop = asyncio.get_event_loop()

    yield

    # Clean up any pending tasks
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()


# ============================================================================
# DEPENDENCY INJECTION HELPERS
# ============================================================================

@pytest.fixture
def mock_dependencies():
    """Setup mock dependencies for dependency injection"""
    from app.main import app

    # Create mocks
    mock_service = AsyncMock()

    # Override dependencies
    def override_service():
        return mock_service

    from app.dependencies import get_service
    app.dependency_overrides[get_service] = override_service

    yield {
        "service": mock_service
    }

    # Clear overrides
    app.dependency_overrides.clear()
```

### Implementation Steps

1. **For each service**, create `/services/[SERVICE]/tests/conftest.py`
2. **Copy template above** and customize:
   - Replace `[SERVICE NAME]`
   - Update Settings class name
   - Update mock fixture names
   - Add service-specific sample data
3. **Move existing fixtures** from test files into conftest
4. **Remove duplicate fixtures** from individual test files
5. **Test**: Run `pytest services/[SERVICE]/tests -v` to verify

### Verification

```bash
# Check conftest exists
test -f services/[SERVICE]/tests/conftest.py && echo "PASS" || echo "FAIL"

# Run tests to verify fixtures work
pytest services/[SERVICE]/tests -v --tb=short
```

---

## Issue 2: Coverage Gaming / Push Files

### Detecting Coverage Push Files

```bash
# Find suspicious test files
find services -name "test_*push*.py" -o -name "test_*80*.py" -o -name "test_*boost*.py" | sort

# Check file sizes (>20KB is suspicious)
find services -path "*/tests/test_*.py" -size +20k -exec wc -l {} \; | sort -n
```

### Files to Audit

**CRITICAL** - Remove or rewrite:
1. `ml-prediction-service/tests/test_easy_wins_80.py` (60 lines - trivial)
2. `ml-prediction-service/tests/test_80_percent_push_supplement.py`
3. `ml-prediction-service/tests/test_coverage_boost.py`
4. `ml-prediction-service/tests/test_final_80_boost.py`
5. `ml-prediction-service/tests/test_final_80_push.py`
6. `ml-prediction-service/tests/test_final_coverage_push.py`
7. `ml-prediction-service/tests/test_integration_coverage_boost.py`
8. `ml-prediction-service/tests/test_one_more_percent.py`
9. `ml-prediction-service/tests/test_reach_80_percent.py`
10. `portfolio-manager/tests/test_80_percent_push.py`
11. `portfolio-manager/tests/test_push_to_80.py`
12. `notification-service/tests/test_80_coverage_push.py`
13. `sentiment-analysis-service/tests/test_80_coverage_push.py`

### Remediation Steps

#### Step 1: Audit the File

```python
# Example audit script
import ast
import sys

def analyze_test_file(filepath):
    """Analyze test file for quality issues"""
    with open(filepath, 'r') as f:
        content = f.read()

    issues = []

    # Check for trivial tests (only assert status_code)
    if content.count("assert response.status_code") > content.count("assert") * 0.8:
        issues.append("Too many simple status code assertions")

    # Check for repeated test patterns
    if content.count("response = client.get") > 20:
        issues.append("Excessive test repetition (possible duplication)")

    # Check for test names indicating coverage goals
    if any(keyword in filepath for keyword in ["push", "boost", "80", "easy_wins"]):
        issues.append("Filename indicates coverage-driven testing")

    # Check file size
    lines = len(content.split('\n'))
    if lines > 200:
        issues.append(f"Large test file ({lines} lines) - may need splitting")

    return issues

# Run analysis
if __name__ == "__main__":
    issues = analyze_test_file(sys.argv[1])
    for issue in issues:
        print(f"WARNING: {issue}")
```

#### Step 2: Categorize Tests

```python
# For each suspicious test file, categorize:

TRIVIAL_TESTS = []      # Single assertion, no real test
DUPLICATE_TESTS = []    # Same test repeated multiple times
WEAK_TESTS = []         # Assertions that don't validate behavior
GOOD_TESTS = []         # Tests that should be kept

for test_class in file.classes:
    for test_method in test_class.methods:
        assertions = count_assertions(test_method)
        if assertions == 1 and is_status_code_check(test_method):
            TRIVIAL_TESTS.append(test_method)
        elif has_meaningful_assertions(test_method):
            GOOD_TESTS.append(test_method)
        else:
            WEAK_TESTS.append(test_method)
```

#### Step 3: Decision Matrix

```
Test Quality Level:

REMOVE:
  - Trivial tests (only status code check)
  - Exact duplicates
  - Tests that don't verify behavior
  - "Easy wins" tests

REWRITE:
  - Weak tests (few assertions, unclear intent)
  - Tests with comments indicating coverage goal
  - Tests without failure scenarios

CONSOLIDATE:
  - Repeated test patterns
  - Similar test scenarios
  - Large test methods that test multiple things

KEEP:
  - Tests with meaningful assertions
  - Tests that cover error paths
  - Tests that validate data integrity
  - Edge case tests
```

#### Step 4: Implementation

```python
# Example: Fixing test_easy_wins_80.py

# BEFORE (bad - trivial test file):
class TestSimpleEndpoints:
    def test_root_endpoint_many_times(self):
        for _ in range(5):  # Artificial test repetition
            response = client.get("/")
            assert response.status_code == 200  # Single assertion

    def test_health_endpoint_many_times(self):
        for _ in range(5):  # More artificial repetition
            response = client.get("/health")
            assert response.status_code == 200

# AFTER (good - meaningful tests):
class TestRootEndpoint:
    def test_root_returns_service_info(self, client):
        """Test root endpoint returns service information"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert data["service"] == "ml-prediction"
        assert "version" in data
        assert "timestamp" in data

    def test_root_response_structure(self, client):
        """Test root endpoint response has correct structure"""
        response = client.get("/")
        data = response.json()

        # Validate response structure
        required_fields = ["service", "version", "timestamp"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


class TestHealthEndpoint:
    def test_health_returns_healthy_status(self, client):
        """Test health endpoint returns healthy status"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ml-prediction"

    def test_health_includes_timestamp(self, client):
        """Test health endpoint includes timestamp"""
        response = client.get("/health")
        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], int)
        assert data["timestamp"] > 0
```

---

## Issue 3: Test Suite Expansion

### For Services with <10 Test Files

#### Notification Service (Currently: 4 files → Target: 10+ files)

```
CURRENT:
test_80_coverage_push.py      (27 KB) - DELETE AFTER AUDIT
test_email_notifier.py        (22 KB)
test_main.py
test_telegram_notifier.py     (27 KB)

NEW STRUCTURE:
tests/
├── unit/
│   ├── test_email_notifier.py
│   ├── test_telegram_notifier.py
│   ├── test_message_templates.py
│   ├── test_notification_scheduler.py
│   └── test_retry_logic.py
├── integration/
│   ├── test_email_service_integration.py
│   ├── test_telegram_service_integration.py
│   └── test_notification_routing.py
├── test_main.py              (API endpoints)
├── test_config.py            (Configuration)
├── test_models.py            (Data models)
└── conftest.py
```

#### Sentiment Analysis Service (Currently: 5 files → Target: 12+ files)

```
CURRENT:
test_80_coverage_push.py
test_api.py
test_news_fetcher.py
test_sentiment_analyzer.py
test_twitter_fetcher.py

NEW STRUCTURE:
tests/
├── unit/
│   ├── test_sentiment_analyzer.py
│   ├── test_news_fetcher.py
│   ├── test_twitter_fetcher.py
│   ├── test_sentiment_models.py
│   ├── test_sentiment_scoring.py
│   └── test_text_preprocessing.py
├── integration/
│   ├── test_news_service_integration.py
│   ├── test_twitter_service_integration.py
│   ├── test_sentiment_aggregation.py
│   └── test_database_persistence.py
├── test_main.py              (API endpoints)
├── test_config.py            (Configuration)
├── test_models.py            (Data models)
└── conftest.py
```

### Template: New Unit Test File

```python
"""
[Module Name] - Unit Tests
Purpose: Test [module] business logic in isolation
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


class Test[ClassName]:
    """Test suite for [ClassName]"""

    @pytest.fixture
    def service(self):
        """Provide service instance for testing"""
        return [ClassName](config=Mock())

    # HAPPY PATH TESTS

    def test_successful_operation(self, service):
        """Test successful operation with valid inputs"""
        # Setup
        input_data = {"key": "value"}

        # Execute
        result = service.process(input_data)

        # Assert
        assert result is not None
        assert result["status"] == "success"
        assert result["data"] == expected_data

    # ERROR PATH TESTS

    def test_handles_invalid_input(self, service):
        """Test handling of invalid input"""
        # Setup
        invalid_input = None

        # Execute & Assert
        with pytest.raises(ValueError):
            service.process(invalid_input)

    def test_handles_empty_input(self, service):
        """Test handling of empty input"""
        empty_input = {}

        with pytest.raises(ValueError):
            service.process(empty_input)

    # EDGE CASE TESTS

    def test_handles_large_input(self, service):
        """Test with large input size"""
        large_input = {"items": [{"id": i} for i in range(10000)]}
        result = service.process(large_input)
        assert len(result) == 10000

    def test_handles_special_characters(self, service):
        """Test with special characters in input"""
        special_input = {"text": "Test@#$%^&*()_+-=[]{}|;:'\",.<>?/~`"}
        result = service.process(special_input)
        assert result["status"] == "success"
```

---

## Issue 4: Integration Testing

### Add Integration Tests to Each Service

#### Template: Service Integration Test

```python
"""
[Service Name] - Integration Tests
Purpose: Test service-to-service communication and data flow
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio


@pytest.mark.integration
class Test[Service]Integration:
    """Integration tests for [Service]"""

    @pytest.fixture
    async def service(self):
        """Initialize service with real(ish) dependencies"""
        from app.main import app
        from app.dependencies import get_service

        service = [Service]()
        await service.initialize()
        yield service
        await service.cleanup()

    # DATABASE INTEGRATION

    @pytest.mark.asyncio
    async def test_database_persistence(self, service):
        """Test data persistence in database"""
        # Setup: Create test data
        test_data = {"id": "test-123", "value": 100}

        # Execute: Store in database
        await service.database.save(test_data)

        # Verify: Retrieve and validate
        retrieved = await service.database.get("test-123")
        assert retrieved["value"] == 100

        # Cleanup
        await service.database.delete("test-123")

    # SERVICE-TO-SERVICE COMMUNICATION

    @pytest.mark.asyncio
    async def test_upstream_service_communication(self, service):
        """Test communication with upstream service"""
        # Mock upstream service response
        with patch.object(service.client, 'get') as mock_get:
            mock_get.return_value = {"status": "ok", "data": []}

            # Execute: Call upstream service
            result = await service.get_upstream_data()

            # Verify: Check result and call
            assert result["status"] == "ok"
            mock_get.assert_called_once()

    # MESSAGE QUEUE INTEGRATION

    @pytest.mark.asyncio
    async def test_message_queue_publishing(self, service):
        """Test publishing messages to queue"""
        # Setup: Create message
        message = {"type": "order", "symbol": "BTCUSDT"}

        # Mock queue
        with patch.object(service.queue, 'publish') as mock_publish:
            # Execute: Publish message
            await service.publish_message(message)

            # Verify: Check published
            mock_publish.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_message_queue_consumption(self, service):
        """Test consuming messages from queue"""
        # Setup: Mock queue message
        test_message = {"type": "signal", "action": "BUY"}

        with patch.object(service.queue, 'consume') as mock_consume:
            mock_consume.return_value = test_message

            # Execute: Consume message
            message = await service.consume_message()

            # Verify: Process message
            assert message["action"] == "BUY"
```

---

## Issue 5: End-to-End Testing

### Create E2E Test for Each Service

#### Template: Service E2E Test

```python
"""
[Service Name] - End-to-End Tests
Purpose: Test complete workflow from API request to data persistence
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.e2e
class Test[Service]E2E:
    """End-to-end tests for [Service]"""

    @pytest.fixture
    def client(self):
        """Provide test client"""
        from app.main import app
        return TestClient(app)

    def test_complete_workflow(self, client):
        """Test complete workflow: Request → Process → Store → Retrieve"""

        # Step 1: Create resource via API
        create_response = client.post("/api/v1/resource", json={
            "name": "test-resource",
            "data": {"key": "value"}
        })
        assert create_response.status_code == 201
        resource_id = create_response.json()["id"]

        # Step 2: Verify resource stored
        get_response = client.get(f"/api/v1/resource/{resource_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == "test-resource"

        # Step 3: Update resource
        update_response = client.put(f"/api/v1/resource/{resource_id}", json={
            "data": {"key": "updated-value"}
        })
        assert update_response.status_code == 200

        # Step 4: Verify update
        get_response = client.get(f"/api/v1/resource/{resource_id}")
        assert get_response.json()["data"]["key"] == "updated-value"

        # Step 5: Delete resource
        delete_response = client.delete(f"/api/v1/resource/{resource_id}")
        assert delete_response.status_code == 204

        # Step 6: Verify deletion
        get_response = client.get(f"/api/v1/resource/{resource_id}")
        assert get_response.status_code == 404

    def test_error_handling_workflow(self, client):
        """Test error handling in complete workflow"""

        # Try to get non-existent resource
        response = client.get("/api/v1/resource/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

        # Try to create with invalid data
        response = client.post("/api/v1/resource", json={
            "name": "",  # Invalid: empty name
            "data": None  # Invalid: null data
        })
        assert response.status_code == 422  # Validation error
```

---

## Issue 6: Test Quality Validation with Mutation Testing

### Setup Mutation Testing

```bash
# Install mutmut
pip install mutmut

# Run mutation tests for a service
cd services/[SERVICE]
mutmut run --tests-dir=tests

# Generate HTML report
mutmut html

# Open report
open html/index.html
```

### Interpret Results

```
Mutation Testing Results:
- Killed mutations: Tests caught the defect (GOOD)
- Survived mutations: Tests missed the defect (BAD)
- Skipped mutations: Code not applicable

Kill Rate Target: >90% (90% of mutations caught by tests)

If kill rate < 90%:
1. Add more assertions
2. Test error paths
3. Test edge cases
4. Validate data integrity
```

---

## Implementation Timeline

### Week 1: Critical Fixes
```
Day 1-2: Create missing conftest.py files
Day 3-4: Audit coverage push files
Day 5: Document test standards
```

### Week 2: Expansion
```
Day 1-2: Expand notification service tests (4 → 10)
Day 3-4: Expand sentiment analysis tests (5 → 12)
Day 5: Code review
```

### Week 3-4: Integration Testing
```
Week 3: Create integration test templates
Week 4: Implement integration tests for all services
```

### Week 5-6: Quality Assurance
```
Week 5: Implement mutation testing
Week 6: Performance optimization
```

---

## Validation Checklist

After implementing fixes:

- [ ] All conftest.py files created
- [ ] Coverage push files audited and rewritten
- [ ] All trivial tests removed
- [ ] Test counts per service:
  - api-gateway: 11 ✓
  - bybit-connector: 11 ✓
  - market-data: 18 ✓
  - portfolio-manager: 15 → 20+
  - technical-analysis: 19 ✓
  - trading-engine: 29 ✓
  - notification-service: 4 → 10+
  - ml-prediction: 18 → 20+ (with proper tests)
  - sentiment-analysis: 5 → 15+
  - risk-metrics: 12 ✓
- [ ] Integration test directories created
- [ ] E2E tests for all services
- [ ] Mutation testing setup
- [ ] All tests passing locally
- [ ] CI/CD pipeline updated
- [ ] Coverage >= 80% (organically, not forced)

---

*Created*: November 25, 2025
*Last Updated*: November 25, 2025
