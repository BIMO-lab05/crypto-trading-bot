#!/bin/bash
# Start Monitoring Stack for Crypto Trading Bot
# This script starts Prometheus and Grafana monitoring for Phase 3 services

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Crypto Trading Bot - Monitoring Setup${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    echo -e "Please start Docker and try again"
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

# Check if monitoring configuration exists
if [ ! -f "infrastructure/monitoring/prometheus.yml" ]; then
    echo -e "${RED}Error: Prometheus configuration not found${NC}"
    echo -e "Expected: infrastructure/monitoring/prometheus.yml"
    exit 1
fi

if [ ! -f "docker-compose.monitoring.yml" ]; then
    echo -e "${RED}Error: Monitoring docker-compose file not found${NC}"
    echo -e "Expected: docker-compose.monitoring.yml"
    exit 1
fi

echo -e "${YELLOW}Step 1: Creating necessary directories...${NC}"
mkdir -p infrastructure/monitoring/rules
mkdir -p infrastructure/monitoring/grafana-provisioning/datasources
mkdir -p infrastructure/monitoring/grafana-provisioning/dashboards
echo -e "${GREEN}✓ Directories created${NC}\n"

echo -e "${YELLOW}Step 2: Checking if services are already running...${NC}"
if docker ps | grep -q "crypto-bot-prometheus"; then
    echo -e "${YELLOW}Prometheus is already running${NC}"
    read -p "Do you want to restart it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml restart prometheus
        echo -e "${GREEN}✓ Prometheus restarted${NC}"
    fi
else
    echo -e "${GREEN}✓ Prometheus not running${NC}"
fi

if docker ps | grep -q "crypto-bot-grafana"; then
    echo -e "${YELLOW}Grafana is already running${NC}"
    read -p "Do you want to restart it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml restart grafana
        echo -e "${GREEN}✓ Grafana restarted${NC}"
    fi
else
    echo -e "${GREEN}✓ Grafana not running${NC}"
fi
echo

echo -e "${YELLOW}Step 3: Starting monitoring stack...${NC}"
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d prometheus grafana

# Wait for services to start
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
sleep 5

# Check Prometheus health
echo -e "${YELLOW}Checking Prometheus health...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Prometheus is healthy${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Prometheus health check timeout${NC}"
        echo -e "${YELLOW}Check logs: docker logs crypto-bot-prometheus${NC}"
    fi
    sleep 2
done

# Check Grafana health
echo -e "${YELLOW}Checking Grafana health...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:3001/api/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Grafana is healthy${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Grafana health check timeout${NC}"
        echo -e "${YELLOW}Check logs: docker logs crypto-bot-grafana${NC}"
    fi
    sleep 2
done
echo

echo -e "${YELLOW}Step 4: Checking Prometheus targets...${NC}"
sleep 3  # Give Prometheus time to scrape

# Get target status
TARGETS_UP=$(curl -s http://localhost:9090/api/v1/targets | grep -o '"health":"up"' | wc -l)
TARGETS_DOWN=$(curl -s http://localhost:9090/api/v1/targets | grep -o '"health":"down"' | wc -l)

echo -e "Targets UP: ${GREEN}$TARGETS_UP${NC}"
echo -e "Targets DOWN: ${RED}$TARGETS_DOWN${NC}"

if [ "$TARGETS_DOWN" -gt 0 ]; then
    echo -e "${YELLOW}Warning: Some targets are down${NC}"
    echo -e "${YELLOW}This is expected if Phase 3 services are not running${NC}"
    echo -e "${YELLOW}Start services with: docker-compose up -d${NC}"
fi
echo

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Monitoring Stack Started Successfully!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "${BLUE}Access Points:${NC}"
echo -e "  Grafana Dashboard: ${GREEN}http://localhost:3001${NC}"
echo -e "    Username: ${YELLOW}admin${NC}"
echo -e "    Password: ${YELLOW}crypto-bot-admin${NC}"
echo -e ""
echo -e "  Prometheus UI: ${GREEN}http://localhost:9090${NC}"
echo -e ""
echo -e "  Phase 3 Service Metrics:"
echo -e "    ML Prediction: ${GREEN}http://localhost:8007/metrics${NC}"
echo -e "    Sentiment Analysis: ${GREEN}http://localhost:8008/metrics${NC}"
echo -e "    Risk Metrics: ${GREEN}http://localhost:8009/metrics${NC}"
echo -e ""

echo -e "${BLUE}Quick Commands:${NC}"
echo -e "  View logs: ${YELLOW}docker logs -f crypto-bot-prometheus${NC}"
echo -e "  View logs: ${YELLOW}docker logs -f crypto-bot-grafana${NC}"
echo -e "  Stop monitoring: ${YELLOW}docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml down${NC}"
echo -e "  Restart: ${YELLOW}docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml restart${NC}"
echo -e ""

echo -e "${BLUE}Documentation:${NC}"
echo -e "  Full Guide: ${YELLOW}infrastructure/monitoring/MONITORING_SETUP_GUIDE.md${NC}"
echo -e "  Quick Reference: ${YELLOW}infrastructure/monitoring/QUICK_REFERENCE.md${NC}"
echo -e "  Instrumentation: ${YELLOW}infrastructure/monitoring/PROMETHEUS_INSTRUMENTATION_GUIDE.md${NC}"
echo -e ""

echo -e "${YELLOW}Note: Change default Grafana password in production!${NC}"
echo -e "${YELLOW}See MONITORING_SETUP_GUIDE.md for security best practices.${NC}\n"

# Optionally open browser
read -p "Open Grafana in browser? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v xdg-open > /dev/null; then
        xdg-open http://localhost:3001
    elif command -v open > /dev/null; then
        open http://localhost:3001
    else
        echo -e "${YELLOW}Could not open browser automatically${NC}"
        echo -e "Please visit: http://localhost:3001"
    fi
fi

echo -e "\n${GREEN}Setup complete!${NC}"
