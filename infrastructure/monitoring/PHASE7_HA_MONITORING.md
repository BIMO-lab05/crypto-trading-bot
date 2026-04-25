# Phase 7: High Availability & Advanced Monitoring

## Overview

This phase implements production-grade High Availability (HA) monitoring and observability infrastructure for the Crypto Trading Bot. The implementation includes standardized health checks, comprehensive alerting, service discovery, load balancing, and advanced Grafana dashboards.

## Components Implemented

### 1. Standardized Health Check System

**File:** `/shared/health_check.py`

A comprehensive health check module providing:

- **Liveness Probes**: Fast checks to verify service is alive (used by Kubernetes to restart containers)
- **Readiness Probes**: Checks if service can accept traffic (used by load balancers)
- **Deep Health Checks**: Comprehensive dependency checks for debugging

**Features:**
- Async-first design with sync fallback
- Configurable timeouts per check type
- Health result caching to reduce load
- Pre-built checks for PostgreSQL, Redis, RabbitMQ, HTTP services, and Bybit API
- Consul service registration integration
- FastAPI route helpers for easy integration

**Usage Example:**
```python
from shared.health_check import (
    HealthCheckManager,
    check_postgres,
    check_redis,
    create_health_routes,
    DependencyType
)

# Initialize health manager
health_manager = HealthCheckManager(
    service_name="trading-engine",
    version="3.5.0"
)

# Add dependencies
health_manager.add_dependency(
    "postgres",
    lambda: check_postgres(host="postgres", database="trading"),
    DependencyType.DATABASE,
    critical=True
)

health_manager.add_dependency(
    "redis",
    lambda: check_redis(url="redis://redis:6379"),
    DependencyType.CACHE,
    critical=True
)

# Add routes to FastAPI app
app.include_router(create_health_routes(health_manager))
```

### 2. Enhanced Prometheus Configuration

**File:** `/prometheus/prometheus-ha.yml`

Production-grade Prometheus configuration with:

- **Consul Service Discovery**: Automatic discovery of services tagged with `prometheus-scrape`
- **File-based Service Discovery**: JSON/YAML targets for Docker Compose environments
- **Comprehensive Relabeling**: Metric enrichment with service metadata
- **Blackbox Probing**: External endpoint monitoring
- **Recording Rules**: Pre-computed metrics for dashboard performance

**Key Features:**
- 15-second scrape interval (production-grade)
- AlertManager integration
- Remote write support (commented, for Thanos/Cortex/VictoriaMetrics)
- Per-service scrape configurations with appropriate intervals

### 3. Comprehensive Alert Rules

**File:** `/prometheus/alerts-comprehensive.yml`

Alert categories:

| Category | Description | Severity Levels |
|----------|-------------|-----------------|
| Service Health | Service availability, latency, error rates | critical, warning |
| Trading Engine | Trade execution, WebSocket, market data | critical, warning, info |
| Risk Management | Daily loss, drawdown, position limits | critical, warning |
| Database | PostgreSQL connections, replication, queries | critical, warning |
| Redis | Memory, connections, evictions | critical, warning |
| RabbitMQ | Queue depth, consumers, memory | critical, warning |
| Infrastructure | CPU, memory, disk, network | critical, warning |
| Business Metrics | P&L, win rate, volume | warning, info |

**Alert Naming Convention:**
- Alerts include `runbook_url` for critical issues
- Labels: `severity`, `component`, service-specific labels
- Annotations: `summary`, `description`, `impact`, `action`

### 4. Recording Rules

**File:** `/prometheus/recording-rules.yml`

Pre-computed metrics for faster queries:

- **Service Health**: Request rates, error rates, latency percentiles
- **Trading Metrics**: Trades/minute, volume, win rate, execution latency
- **Portfolio Metrics**: Value changes, drawdown, position analysis
- **Risk Metrics**: Correlation, concentration, VaR approximation
- **Infrastructure**: CPU, memory, disk, network aggregations
- **Database**: Connection percentages, query rates, hit rates

### 5. Service Discovery (Consul)

**File:** `/consul/consul-config.json`

Consul configuration for:

- Service registration for all microservices
- Health check configuration per service
- Service metadata (version, phase, tier)
- Tags for filtering and routing

**Registered Services:**
- api-gateway, trading-engine, market-data-service
- technical-analysis, portfolio-manager, bybit-connector
- notification-service, ml-prediction, sentiment-analysis
- risk-metrics, signal-aggregator

### 6. NGINX Load Balancer

**File:** `/nginx/load-balancer.conf`

Production load balancer features:

- **Upstream Groups**: Weighted round-robin with health checks
- **Rate Limiting**: Per-endpoint rate limits (API: 100rps, Trading: 20rps)
- **SSL/TLS Termination**: Modern cipher configuration
- **WebSocket Support**: For real-time data streaming
- **Health-based Routing**: Remove unhealthy upstreams
- **JSON Logging**: For log aggregation and analysis
- **Request Tracing**: X-Request-ID header propagation

**Endpoints:**
| Path | Upstream | Rate Limit |
|------|----------|------------|
| /api/ | api_gateway | 100r/s |
| /api/v1/trading/ | trading_engine | 20r/s |
| /api/v1/market/ | market_data | 100r/s |
| /ws/ | websocket_backend | - |
| /prometheus/ | prometheus | - |
| /grafana/ | grafana | - |

### 7. Grafana Dashboards

Three production-ready dashboards:

#### System Health Dashboard (`system-health-ha.json`)
- Service status indicators (UP/DOWN)
- Cluster health percentage
- Service latency (P99)
- Request rate by service
- CPU, Memory, Disk usage
- Database connections, Redis memory
- Active alerts table

#### Trading Performance Dashboard (`trading-performance-ha.json`)
- Portfolio value and P&L
- Trade execution metrics
- Win rate and fill rate
- Position analysis
- Strategy performance
- Exchange connectivity status
- Volume by symbol

#### Risk Metrics Dashboard (`risk-metrics-dashboard.json`)
- Daily P&L and drawdown
- Risk exposure indicators
- Position allocation pie chart
- Correlation and diversification scores
- VaR monitoring
- Active risk alerts

## File Structure

```
infrastructure/monitoring/
├── PHASE7_HA_MONITORING.md          # This documentation
├── docker-compose.ha.yml            # Full HA monitoring stack
├── prometheus/
│   ├── prometheus-ha.yml            # Enhanced Prometheus config
│   ├── alerts-comprehensive.yml     # Comprehensive alert rules
│   ├── recording-rules.yml          # Pre-computed metrics
│   └── targets/
│       └── services.json            # File-based service discovery
├── alertmanager/
│   └── alertmanager.yml             # Alert routing (existing)
├── grafana/
│   ├── dashboards/
│   │   ├── system-health-ha.json    # System health dashboard
│   │   ├── trading-performance-ha.json # Trading dashboard
│   │   └── risk-metrics-dashboard.json # Risk dashboard
│   └── provisioning/
│       └── dashboards/
│           └── dashboards.yml       # Dashboard provisioning
├── consul/
│   └── consul-config.json           # Service discovery config
├── nginx/
│   └── load-balancer.conf           # Load balancer config
├── blackbox/
│   └── blackbox.yml                 # Endpoint probing config
└── ...
```

## Deployment

### Prerequisites

1. Docker and Docker Compose installed
2. Network `crypto-trading-bot_default` exists (from main docker-compose)
3. Environment variables configured

### Environment Variables

```bash
# AlertManager
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=app-password
ALERT_EMAIL=alerts@example.com
WEBHOOK_TOKEN=your-webhook-token

# Grafana
GF_ADMIN_USER=admin
GF_ADMIN_PASSWORD=secure-password

# Database Exporters
POSTGRES_DSN=postgresql://user:pass@postgres:5432/trading
REDIS_URL=redis://redis:6379
RABBITMQ_URL=http://rabbitmq:15672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
```

### Starting the Stack

```bash
cd infrastructure/monitoring

# Start full HA monitoring stack
docker-compose -f docker-compose.ha.yml up -d

# Verify services are healthy
docker-compose -f docker-compose.ha.yml ps

# View logs
docker-compose -f docker-compose.ha.yml logs -f prometheus
```

### Accessing Services

| Service | URL | Purpose |
|---------|-----|---------|
| Prometheus | http://localhost:9090 | Metrics queries |
| Grafana | http://localhost:3000 | Dashboards |
| AlertManager | http://localhost:9093 | Alert management |
| Consul | http://localhost:8500 | Service discovery UI |
| Node Exporter | http://localhost:9100 | System metrics |
| cAdvisor | http://localhost:8080 | Container metrics |

## Integrating Health Checks in Services

### Step 1: Install dependencies

```bash
pip install asyncpg redis httpx aio_pika
```

### Step 2: Add to your service

```python
# main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from shared.health_check import (
    HealthCheckManager,
    create_health_routes,
    check_postgres,
    check_redis,
    DependencyType
)

# Create health manager
health_manager = HealthCheckManager(
    service_name="my-service",
    version="1.0.0"
)

# Add dependencies
health_manager.add_dependency(
    "database",
    lambda: check_postgres(
        host=settings.db_host,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password
    ),
    DependencyType.DATABASE,
    critical=True
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan)
app.include_router(create_health_routes(health_manager))
```

### Step 3: Verify endpoints

```bash
# Liveness
curl http://localhost:8000/health

# Readiness
curl http://localhost:8000/ready

# Deep check
curl http://localhost:8000/health/deep

# Prometheus metrics
curl http://localhost:8000/health/metrics
```

## Success Metrics

The Phase 7 implementation targets these metrics:

| Metric | Target |
|--------|--------|
| Service Uptime | 99.9% |
| Alert Detection Time | < 30s |
| Dashboard Load Time | < 3s |
| Health Check Latency | < 100ms |
| MTTR (Mean Time to Recovery) | < 15 minutes |

## Troubleshooting

### Prometheus not scraping targets

1. Check target status: Prometheus UI -> Status -> Targets
2. Verify network connectivity: `docker exec prometheus ping trading-engine`
3. Check service metrics endpoint: `curl http://trading-engine:8001/metrics`

### Alerts not firing

1. Check alert rules: Prometheus UI -> Alerts
2. Verify AlertManager connection: Prometheus UI -> Status -> Runtime & Build Information
3. Check AlertManager logs: `docker logs alertmanager`

### Grafana dashboards not loading

1. Verify datasource: Grafana -> Configuration -> Data Sources
2. Check Prometheus connectivity
3. Review dashboard JSON for syntax errors

### Consul services not registering

1. Check Consul logs: `docker logs consul`
2. Verify service health checks are passing
3. Check network connectivity between Consul and services

## Future Enhancements

1. **Distributed Tracing**: Add Jaeger/Zipkin integration
2. **Anomaly Detection**: ML-based alerting with Prophet/ARIMA
3. **SLO/SLI Monitoring**: Error budget tracking
4. **Chaos Engineering**: Automated failure injection
5. **Cost Monitoring**: Cloud cost tracking integration
