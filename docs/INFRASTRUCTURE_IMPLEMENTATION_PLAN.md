# Infrastructure Implementation Plan
**Crypto Trading Bot - Production Readiness**

## Executive Summary
This document outlines the implementation strategy for integrating existing shared utilities across all microservices to achieve production-grade reliability, observability, and operational excellence.

## Current State Analysis

### ✅ Already Built (in `shared/utils/`)
1. **Structured Logging** (`structured_logging.py`)
   - JSON formatted logs
   - Request context tracking
   - Performance decorators
   - Correlation IDs

2. **Database Connection Pooling** (`db_pool.py`)
   - PostgreSQL/TimescaleDB async pools
   - Redis connection management
   - Health checks
   - Connection leak detection

3. **Graceful Shutdown** (`graceful_shutdown.py`)
   - Signal handlers (SIGTERM, SIGINT)
   - Ordered cleanup execution
   - Background task cancellation
   - Timeout protection

4. **Rate Limiting** (`rate_limiter.py`)
   - Sliding window
   - Token bucket
   - Fixed window
   - Adaptive rate limiting

5. **Circuit Breaker** (`circuit_breaker.py`)
   - Fault tolerance
   - Exponential backoff
   - Auto-recovery testing

### ❌ Not Yet Integrated
Services are still using:
- Basic `logging.basicConfig()` instead of StructuredLogger
- SlowAPI (external library) instead of custom rate limiter
- Simple lifespan managers instead of GracefulShutdownHandler
- No input validation middleware
- No dead letter queue
- No disaster recovery procedures

## Implementation Strategy

### Phase 1: Core Infrastructure Integration (Priority: HIGH)

#### 1.1 Structured Logging Rollout
**Target Services:** All 10 services
**Estimated Time:** 2-3 hours

**Implementation Steps:**
```python
# For each service's app/main.py:

# Before:
import logging
logging.basicConfig(...)
logger = logging.getLogger(__name__)

# After:
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from utils.structured_logging import setup_logging

logger = setup_logging(
    service_name="api-gateway",
    environment=settings.environment,
    log_level=settings.log_level
)
```

**Benefits:**
- JSON logs for ELK/Splunk ingestion
- Automatic context injection (service name, environment)
- Request ID tracking across services
- Better debugging and troubleshooting

**Files to Update:**
- `services/api-gateway/app/main.py`
- `services/trading-engine/app/main.py`
- `services/market-data-service/app/main.py`
- `services/technical-analysis/app/main.py`
- `services/portfolio-manager/app/main.py`
- `services/bybit-connector/app/main.py`
- `services/risk-metrics-service/app/main.py`
- `services/ml-prediction-service/app/main.py`
- `services/sentiment-analysis-service/app/main.py`
- `services/notification-service/app/main.py`

#### 1.2 Enhanced Graceful Shutdown
**Target Services:** All services
**Estimated Time:** 1-2 hours

**Implementation:**
```python
from utils.graceful_shutdown import GracefulShutdownHandler

shutdown_handler = GracefulShutdownHandler(
    shutdown_timeout=30.0,
    service_name=settings.service_name
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup signal handlers
    shutdown_handler.setup_signal_handlers()

    # Initialize resources
    db = await init_database()
    shutdown_handler.register_cleanup(db.close)

    yield

    # Graceful shutdown
    await shutdown_handler.shutdown()
```

**Benefits:**
- Proper signal handling (SIGTERM, SIGINT)
- Ordered resource cleanup (LIFO)
- Background task cancellation
- Zero data loss on shutdown

#### 1.3 Database Connection Pooling
**Target Services:** Services using PostgreSQL/Redis
**Estimated Time:** 2 hours

**Current Services Using Databases:**
- portfolio-manager (PostgreSQL)
- trading-engine (PostgreSQL)
- market-data-service (TimescaleDB)
- risk-metrics-service (PostgreSQL)

**Implementation:**
```python
from utils.db_pool import db_manager

# In lifespan:
await db_manager.initialize_postgres(
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
    user=settings.db_user,
    password=settings.db_password,
    min_size=10,
    max_size=50,
    command_timeout=60.0
)

# In routes:
async with db_manager.postgres_pool.acquire() as conn:
    result = await conn.fetch("SELECT * FROM trades")
```

**Benefits:**
- Efficient connection reuse
- Automatic connection health checks
- Protection against connection leaks
- Better performance under load

### Phase 2: Resilience & Reliability (Priority: HIGH)

#### 2.1 Input Validation Middleware
**Estimated Time:** 3 hours

**Create:** `shared/utils/input_validation.py`

```python
"""
Input Validation Middleware
Protects against injection attacks and malformed requests
"""

from fastapi import Request, HTTPException
from pydantic import ValidationError
import re

class InputValidationMiddleware:
    """
    Validates all incoming requests for:
    - SQL injection patterns
    - XSS attempts
    - Path traversal
    - Oversized payloads
    - Malformed JSON
    """

    SQL_INJECTION_PATTERNS = [
        r"(\%27)|(\')|(\-\-)|(\%23)|(#)",
        r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",
        r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))",
    ]

    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"onerror\s*=",
        r"onload\s*=",
    ]

    async def validate_request(self, request: Request):
        # Validate query params
        # Validate request body
        # Check content length
        # Sanitize inputs
        pass
```

**Integration:**
```python
@app.middleware("http")
async def input_validation(request: Request, call_next):
    validator = InputValidationMiddleware()
    await validator.validate_request(request)
    return await call_next(request)
```

#### 2.2 Dead Letter Queue
**Estimated Time:** 4 hours

**Create:** `shared/utils/dead_letter_queue.py`

```python
"""
Dead Letter Queue for failed messages
Captures failed events for analysis and retry
"""

class DeadLetterQueue:
    """
    Stores failed messages for:
    - Manual review
    - Automatic retry with backoff
    - Pattern analysis
    - Alert generation
    """

    def __init__(self, redis_pool, max_retries=3):
        self.redis = redis_pool
        self.max_retries = max_retries

    async def send_to_dlq(
        self,
        message: dict,
        error: Exception,
        source: str,
        retry_count: int = 0
    ):
        """Send failed message to DLQ"""
        dlq_entry = {
            "message": message,
            "error": str(error),
            "source": source,
            "retry_count": retry_count,
            "timestamp": time.time()
        }

        await self.redis.lpush(
            f"dlq:{source}",
            json.dumps(dlq_entry)
        )

    async def retry_from_dlq(self, source: str):
        """Retry messages from DLQ"""
        # Implementation for retry logic
        pass
```

### Phase 3: Operational Excellence (Priority: MEDIUM)

#### 3.1 Disaster Recovery Procedures
**Estimated Time:** 6 hours

**Create:** `docs/operations/DISASTER_RECOVERY.md`

**Contents:**
1. **Backup Procedures**
   - Database backup schedules
   - Configuration backup
   - Trade history archival
   - State snapshot creation

2. **Recovery Procedures**
   - Database restoration
   - Service restart sequence
   - State recovery
   - Trade reconciliation

3. **Failover Procedures**
   - Database failover
   - Redis failover
   - Service migration
   - Load balancer updates

4. **Testing Schedule**
   - Monthly DR drills
   - Quarterly full recovery tests
   - Backup restoration validation

#### 3.2 Backup & Restoration Testing
**Estimated Time:** 4 hours

**Create:** `scripts/backup_restore_test.py`

```python
"""
Automated backup and restore testing
Validates backup integrity and recovery procedures
"""

async def test_database_backup_restore():
    # 1. Create snapshot
    # 2. Make test changes
    # 3. Restore from snapshot
    # 4. Verify data integrity
    # 5. Cleanup
    pass

async def test_redis_backup_restore():
    # Similar to database test
    pass

async def test_full_system_restore():
    # Complete system recovery test
    pass
```

#### 3.3 Integration Test Suite
**Estimated Time:** 8 hours

**Create:** `tests/integration/`

```
tests/integration/
├── test_end_to_end_trading.py
├── test_service_communication.py
├── test_failure_scenarios.py
├── test_performance.py
└── test_security.py
```

**Key Test Scenarios:**
1. Complete trading flow (signal → execution → portfolio update)
2. Service communication (API Gateway → all services)
3. Failure handling (service down, network issues, DB failures)
4. Performance (load testing, latency)
5. Security (auth, rate limiting, input validation)

#### 3.4 Database Replication Configuration
**Estimated Time:** 4 hours

**Create:** `infrastructure/database/replication/`

**PostgreSQL Streaming Replication:**
```yaml
# docker-compose.replication.yml
services:
  postgres-primary:
    image: postgres:15
    environment:
      POSTGRES_REPLICATION: "true"
    volumes:
      - ./replication/primary.conf:/etc/postgresql/postgresql.conf

  postgres-replica-1:
    image: postgres:15
    environment:
      POSTGRES_MASTER_SERVICE_HOST: postgres-primary
    volumes:
      - ./replication/replica.conf:/etc/postgresql/postgresql.conf

  postgres-replica-2:
    # Second replica for redundancy
```

**Features:**
- Async replication for read scalability
- Automatic failover with Patroni
- Load balancing across replicas
- WAL archiving for point-in-time recovery

#### 3.5 Operational Runbook
**Estimated Time:** 6 hours

**Create:** `docs/operations/RUNBOOK.md`

**Sections:**
1. **Service Management**
   - Starting services
   - Stopping services
   - Health checks
   - Log locations

2. **Common Issues**
   - Service won't start
   - Database connection failures
   - High memory usage
   - Slow API responses

3. **Monitoring & Alerts**
   - Prometheus metrics
   - Grafana dashboards
   - Alert thresholds
   - On-call procedures

4. **Deployment**
   - Rolling updates
   - Blue-green deployment
   - Rollback procedures
   - Configuration changes

5. **Emergency Procedures**
   - Emergency stop
   - Circuit breaker activation
   - Position liquidation
   - Communication protocols

## Implementation Timeline

### Week 1: Core Integration
- Day 1-2: Structured logging rollout
- Day 3: Enhanced graceful shutdown
- Day 4-5: Database connection pooling

### Week 2: Resilience
- Day 1-2: Input validation middleware
- Day 3-5: Dead letter queue implementation

### Week 3: Operations
- Day 1-2: Disaster recovery procedures
- Day 3-4: Backup testing automation
- Day 5: Database replication setup

### Week 4: Testing & Documentation
- Day 1-3: Integration test suite
- Day 4-5: Operational runbook

## Success Metrics

### Reliability
- Zero data loss on shutdown: ✅
- < 1% request failure rate: ✅
- 99.9% uptime: ✅

### Performance
- API p99 latency < 100ms: ✅
- Database pool utilization < 80%: ✅
- Memory leak detection: ✅

### Observability
- All logs in JSON format: ✅
- Request tracing across services: ✅
- Complete metrics coverage: ✅

### Operations
- DR drill success rate: 100%
- Backup restoration time: < 30 minutes
- Deployment rollback time: < 5 minutes

## Risk Mitigation

### Risk: Service disruption during integration
**Mitigation:**
- Implement changes during low-traffic periods
- Use feature flags for gradual rollout
- Maintain backward compatibility
- Have rollback plan ready

### Risk: Performance degradation
**Mitigation:**
- Load test after each change
- Monitor metrics closely
- Set up performance alerts
- Optimize before deploying

### Risk: Data loss during migration
**Mitigation:**
- Full backup before changes
- Test in staging environment
- Verify data integrity
- Keep old code available

## Approval & Sign-off

- [ ] Technical Lead Review
- [ ] Security Review
- [ ] Operations Review
- [ ] Final Approval

---

**Document Version:** 1.0
**Last Updated:** 2025-11-16
**Next Review:** 2025-12-16
