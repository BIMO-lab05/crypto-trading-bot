#!/bin/bash
# Monitoring Stack Logs
# View logs from monitoring services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONITORING_DIR="${PROJECT_ROOT}/infrastructure/monitoring"

SERVICE="${1:-all}"
FOLLOW="${2:-}"

cd "${MONITORING_DIR}"

echo "========================================="
echo "  Monitoring Stack Logs                  "
echo "========================================="
echo ""

if [ "$SERVICE" = "all" ]; then
    if [ "$FOLLOW" = "-f" ] || [ "$FOLLOW" = "--follow" ]; then
        echo "📜 Following logs from all services (Ctrl+C to stop)..."
        echo ""
        docker-compose -f docker-compose.monitoring.yml logs -f --tail=100
    else
        echo "📜 Recent logs from all services..."
        echo ""
        docker-compose -f docker-compose.monitoring.yml logs --tail=50
        echo ""
        echo "💡 Tip: Use -f to follow logs: $0 all -f"
    fi
else
    if [ "$FOLLOW" = "-f" ] || [ "$FOLLOW" = "--follow" ]; then
        echo "📜 Following logs from $SERVICE (Ctrl+C to stop)..."
        echo ""
        docker-compose -f docker-compose.monitoring.yml logs -f --tail=100 "$SERVICE"
    else
        echo "📜 Recent logs from $SERVICE..."
        echo ""
        docker-compose -f docker-compose.monitoring.yml logs --tail=50 "$SERVICE"
        echo ""
        echo "💡 Tip: Use -f to follow logs: $0 $SERVICE -f"
    fi
fi

echo ""
echo "========================================="
echo "  Available Services                     "
echo "========================================="
echo ""
echo "   - prometheus"
echo "   - grafana"
echo "   - alertmanager"
echo "   - loki"
echo "   - promtail"
echo "   - node-exporter"
echo "   - cadvisor"
echo "   - redis-exporter"
echo "   - postgres-exporter"
echo ""
echo "Usage: $0 [service] [-f]"
echo "Examples:"
echo "   $0                    # Show recent logs from all services"
echo "   $0 all -f             # Follow all logs"
echo "   $0 prometheus         # Show Prometheus logs"
echo "   $0 grafana -f         # Follow Grafana logs"
echo ""
