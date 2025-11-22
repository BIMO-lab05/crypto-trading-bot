#!/bin/bash
# Start Monitoring Stack
# Starts Prometheus, Grafana, AlertManager, Loki, and all exporters

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONITORING_DIR="${PROJECT_ROOT}/infrastructure/monitoring"

echo "========================================="
echo "  Starting Crypto Bot Monitoring Stack  "
echo "========================================="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ ERROR: Docker is not running"
    exit 1
fi

# Ensure crypto-bot-network exists
echo "📡 Ensuring crypto-bot-network exists..."
docker network create crypto-bot-network 2>/dev/null || echo "   Network already exists"

# Navigate to monitoring directory
cd "${MONITORING_DIR}"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  WARNING: .env file not found"
    echo "   Creating .env from template..."
    cat > .env << 'EOF'
# Grafana
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin

# Database
DB_USER=cryptobot
DB_PASSWORD=changeme
DB_NAME=cryptobot

# Redis
REDIS_PASSWORD=

# Alerting (configure these)
SLACK_WEBHOOK_URL=
PAGERDUTY_SERVICE_KEY=
ALERT_EMAIL=alerts@example.com
SMTP_USERNAME=
SMTP_PASSWORD=
WEBHOOK_TOKEN=changeme
EOF
    echo "   ✅ Created .env file - please configure it"
fi

# Start monitoring stack
echo ""
echo "🚀 Starting monitoring services..."
docker-compose -f docker-compose.monitoring.yml up -d

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service health
echo ""
echo "🏥 Checking service health..."
echo ""

services=(
    "prometheus:9090"
    "grafana:3000"
    "alertmanager:9093"
    "loki:3100"
    "node-exporter:9100"
    "cadvisor:8080"
)

all_healthy=true

for service in "${services[@]}"; do
    name="${service%%:*}"
    port="${service##*:}"

    if curl -sf "http://localhost:${port}" > /dev/null 2>&1 || \
       curl -sf "http://localhost:${port}/metrics" > /dev/null 2>&1 || \
       curl -sf "http://localhost:${port}/ready" > /dev/null 2>&1; then
        echo "   ✅ ${name} is healthy"
    else
        echo "   ⚠️  ${name} is not responding yet"
        all_healthy=false
    fi
done

echo ""
echo "========================================="
echo "  Monitoring Stack Started              "
echo "========================================="
echo ""
echo "📊 Access URLs:"
echo "   Grafana:       http://localhost:3000"
echo "   Prometheus:    http://localhost:9090"
echo "   AlertManager:  http://localhost:9093"
echo "   cAdvisor:      http://localhost:8080"
echo ""
echo "🔐 Default Credentials:"
echo "   Grafana: admin / admin (change on first login)"
echo ""
echo "📝 View logs:"
echo "   docker-compose -f ${MONITORING_DIR}/docker-compose.monitoring.yml logs -f"
echo ""
echo "🛑 Stop monitoring:"
echo "   ${SCRIPT_DIR}/stop_monitoring.sh"
echo ""

if [ "$all_healthy" = false ]; then
    echo "⚠️  Some services are not responding yet. Give them a few more seconds."
    echo "   Check status: ${SCRIPT_DIR}/monitoring_status.sh"
fi
