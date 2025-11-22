#!/bin/bash
# Monitoring Stack Status
# Displays detailed status of all monitoring services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONITORING_DIR="${PROJECT_ROOT}/infrastructure/monitoring"

echo "========================================="
echo "  Monitoring Stack Status                "
echo "========================================="
echo ""

cd "${MONITORING_DIR}"

# Check if any containers are running
if ! docker-compose -f docker-compose.monitoring.yml ps | grep -q "Up"; then
    echo "❌ Monitoring stack is not running"
    echo ""
    echo "Start monitoring: ${SCRIPT_DIR}/start_monitoring.sh"
    exit 1
fi

# Display container status
echo "🐳 Container Status:"
echo ""
docker-compose -f docker-compose.monitoring.yml ps
echo ""

# Check service health
echo "========================================="
echo "  Service Health Checks                  "
echo "========================================="
echo ""

check_service() {
    local name=$1
    local url=$2
    local health_endpoint=$3

    if [ -z "$health_endpoint" ]; then
        health_endpoint="$url"
    fi

    if response=$(curl -sf "$health_endpoint" 2>&1); then
        echo "   ✅ $name: Healthy"
        return 0
    else
        echo "   ❌ $name: Not responding"
        return 1
    fi
}

# Prometheus
check_service "Prometheus" "http://localhost:9090" "http://localhost:9090/-/healthy"

# Grafana
check_service "Grafana" "http://localhost:3000" "http://localhost:3000/api/health"

# AlertManager
check_service "AlertManager" "http://localhost:9093" "http://localhost:9093/-/healthy"

# Loki
check_service "Loki" "http://localhost:3100" "http://localhost:3100/ready"

# Node Exporter
check_service "Node Exporter" "http://localhost:9100" "http://localhost:9100/metrics"

# cAdvisor
check_service "cAdvisor" "http://localhost:8080" "http://localhost:8080/healthz"

# Redis Exporter
check_service "Redis Exporter" "http://localhost:9121" "http://localhost:9121/metrics"

# Postgres Exporter
check_service "Postgres Exporter" "http://localhost:9187" "http://localhost:9187/metrics"

echo ""

# Check Prometheus targets
echo "========================================="
echo "  Prometheus Targets                     "
echo "========================================="
echo ""

if command -v jq &> /dev/null; then
    targets=$(curl -s http://localhost:9090/api/v1/targets 2>/dev/null)

    if [ -n "$targets" ]; then
        echo "$targets" | jq -r '.data.activeTargets[] | "   \(.labels.job): \(.health)"' 2>/dev/null || echo "   Unable to parse targets"
    else
        echo "   Unable to fetch targets"
    fi
else
    echo "   Install jq to see Prometheus targets status"
fi

echo ""

# Check for active alerts
echo "========================================="
echo "  Active Alerts                          "
echo "========================================="
echo ""

if command -v jq &> /dev/null; then
    alerts=$(curl -s http://localhost:9093/api/v1/alerts 2>/dev/null)

    if [ -n "$alerts" ]; then
        firing_count=$(echo "$alerts" | jq '[.data[] | select(.status.state=="firing")] | length' 2>/dev/null)

        if [ "$firing_count" -gt 0 ]; then
            echo "   🚨 $firing_count alerts firing:"
            echo "$alerts" | jq -r '.data[] | select(.status.state=="firing") | "      - \(.labels.alertname): \(.annotations.summary)"' 2>/dev/null
        else
            echo "   ✅ No active alerts"
        fi
    else
        echo "   Unable to fetch alerts"
    fi
else
    echo "   Install jq to see active alerts"
fi

echo ""

# Display resource usage
echo "========================================="
echo "  Resource Usage                         "
echo "========================================="
echo ""

docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    $(docker-compose -f docker-compose.monitoring.yml ps -q) 2>/dev/null || echo "   Unable to fetch resource usage"

echo ""
echo "========================================="
echo "  Quick Access                           "
echo "========================================="
echo ""
echo "📊 Dashboards:"
echo "   Grafana:       http://localhost:3000"
echo "   Prometheus:    http://localhost:9090"
echo "   AlertManager:  http://localhost:9093"
echo ""
echo "📝 View logs:    ${SCRIPT_DIR}/monitoring_logs.sh"
echo "🛑 Stop:         ${SCRIPT_DIR}/stop_monitoring.sh"
echo ""
