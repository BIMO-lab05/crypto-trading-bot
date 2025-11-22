#!/bin/bash
# Stop Monitoring Stack
# Gracefully stops all monitoring services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONITORING_DIR="${PROJECT_ROOT}/infrastructure/monitoring"

echo "========================================="
echo "  Stopping Crypto Bot Monitoring Stack  "
echo "========================================="
echo ""

cd "${MONITORING_DIR}"

# Stop services
echo "🛑 Stopping monitoring services..."
docker-compose -f docker-compose.monitoring.yml down

echo ""
echo "✅ Monitoring stack stopped"
echo ""
echo "💾 Data preserved in Docker volumes:"
echo "   - prometheus-data"
echo "   - grafana-data"
echo "   - alertmanager-data"
echo "   - loki-data"
echo ""
echo "🔄 To restart: ${SCRIPT_DIR}/start_monitoring.sh"
echo "🗑️  To remove data: docker-compose -f docker-compose.monitoring.yml down -v"
echo ""
