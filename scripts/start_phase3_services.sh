#!/bin/bash
###############################################################################
# Phase 3 Services Startup Script
# Starts ML Prediction and Sentiment Analysis services
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${GREEN}====================================================================${NC}"
echo -e "${GREEN}        Phase 3: ML + Sentiment Services Startup${NC}"
echo -e "${GREEN}====================================================================${NC}"
echo ""

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}Warning: Port $port is already in use${NC}"
        return 1
    fi
    return 0
}

# Function to wait for service to be ready
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1

    echo -n "Waiting for $service_name to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 1
        ((attempt++))
    done

    echo -e " ${RED}✗${NC}"
    echo -e "${RED}Error: $service_name failed to start after $max_attempts seconds${NC}"
    return 1
}

# Check prerequisites
echo "Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 not found${NC}"
    exit 1
fi
echo -e "  Python: ${GREEN}✓${NC}"

# Check TensorFlow
if ! python3 -c "import tensorflow" 2>/dev/null; then
    echo -e "  ${YELLOW}Warning: TensorFlow not installed. ML predictions will not work.${NC}"
    echo -e "  ${YELLOW}Install with: pip install tensorflow==2.15.0${NC}"
else
    echo -e "  TensorFlow: ${GREEN}✓${NC}"
fi

# Check transformers (optional)
if ! python3 -c "import transformers" 2>/dev/null; then
    echo -e "  ${YELLOW}Warning: transformers not installed. Will use basic sentiment analysis.${NC}"
    echo -e "  ${YELLOW}Install with: pip install transformers torch${NC}"
else
    echo -e "  transformers: ${GREEN}✓${NC}"
fi

echo ""

# Kill any existing services on target ports
echo "Checking for existing services..."

for port in 8007 8008 8009; do
    if check_port $port; then
        echo -e "  Port $port: ${GREEN}available${NC}"
    else
        echo -e "  Port $port: ${YELLOW}in use, killing process...${NC}"
        lsof -ti:$port | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
done

echo ""

# Start ML Prediction Service (port 8007)
echo "Starting ML Prediction Service..."

cd "$PROJECT_ROOT/services/ml-prediction-service"

if [ ! -f "app/main.py" ]; then
    echo -e "${RED}Error: ML Prediction Service not found at $PWD${NC}"
    exit 1
fi

PYTHONPATH=. nohup python3 -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8007 \
    > /tmp/ml-prediction.log 2>&1 &

ML_PID=$!
echo -e "  PID: ${GREEN}$ML_PID${NC}"
echo "  Log: /tmp/ml-prediction.log"

# Wait for service to be ready
if ! wait_for_service "http://localhost:8007/health" "ML Prediction Service"; then
    echo -e "${RED}Failed to start ML Prediction Service. Check logs:${NC}"
    echo "  tail -f /tmp/ml-prediction.log"
    exit 1
fi

echo ""

# Start Sentiment Analysis Service (port 8008)
echo "Starting Sentiment Analysis Service..."

cd "$PROJECT_ROOT/services/sentiment-analysis-service"

if [ ! -f "app/main.py" ]; then
    echo -e "${RED}Error: Sentiment Analysis Service not found at $PWD${NC}"
    exit 1
fi

PYTHONPATH=. nohup python3 -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8008 \
    > /tmp/sentiment-analysis.log 2>&1 &

SENTIMENT_PID=$!
echo -e "  PID: ${GREEN}$SENTIMENT_PID${NC}"
echo "  Log: /tmp/sentiment-analysis.log"

# Wait for service to be ready
if ! wait_for_service "http://localhost:8008/health" "Sentiment Analysis Service"; then
    echo -e "${RED}Failed to start Sentiment Analysis Service. Check logs:${NC}"
    echo "  tail -f /tmp/sentiment-analysis.log"
    exit 1
fi

echo ""

# Check if Risk Metrics Service needs to be restarted on new port (8009)
echo "Checking Risk Metrics Service..."

if lsof -Pi :8007 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "  ${YELLOW}Risk Metrics Service still on port 8007, restarting on port 8009...${NC}"

    # Kill old instance
    lsof -ti:8007 | xargs kill -9 2>/dev/null || true
    sleep 1

    # Start on new port
    cd "$PROJECT_ROOT/services/risk-metrics-service"

    PYTHONPATH=. nohup python3 -m uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8009 \
        > /tmp/risk-metrics.log 2>&1 &

    RISK_PID=$!
    echo -e "  PID: ${GREEN}$RISK_PID${NC}"
    echo "  Log: /tmp/risk-metrics.log"

    if wait_for_service "http://localhost:8009/health" "Risk Metrics Service"; then
        echo -e "  ${GREEN}Risk Metrics Service migrated to port 8009 successfully${NC}"
    fi
else
    echo -e "  ${GREEN}Risk Metrics Service not running or already on correct port${NC}"
fi

echo ""
echo -e "${GREEN}====================================================================${NC}"
echo -e "${GREEN}        Phase 3 Services Started Successfully!${NC}"
echo -e "${GREEN}====================================================================${NC}"
echo ""

# Service status
echo "Service Status:"
echo -e "  ML Prediction Service:      ${GREEN}http://localhost:8007${NC}"
echo -e "  Sentiment Analysis Service: ${GREEN}http://localhost:8008${NC}"
echo -e "  Risk Metrics Service:       ${GREEN}http://localhost:8009${NC}"
echo ""

# API docs
echo "API Documentation:"
echo "  ML Prediction:      http://localhost:8007/docs"
echo "  Sentiment Analysis: http://localhost:8008/docs"
echo "  API Gateway:        http://localhost:8000/docs"
echo ""

# Quick tests
echo "Quick Health Checks:"
echo "  curl http://localhost:8007/health  # ML Prediction"
echo "  curl http://localhost:8008/health  # Sentiment Analysis"
echo ""

# View logs
echo "View Logs:"
echo "  tail -f /tmp/ml-prediction.log"
echo "  tail -f /tmp/sentiment-analysis.log"
echo ""

# Next steps
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Train ML models for your symbols:"
echo "     See: PHASE3_ML_SENTIMENT_DEPLOYMENT.md (Training ML Models section)"
echo ""
echo "  2. Test the endpoints:"
echo "     curl \"http://localhost:8000/api/ml/predict/price/BTCUSDT?interval=60\""
echo "     curl \"http://localhost:8000/api/sentiment/combined/BTCUSDT\""
echo ""
echo "  3. View full documentation:"
echo "     cat PHASE3_ML_SENTIMENT_DEPLOYMENT.md"
echo ""

echo -e "${GREEN}====================================================================${NC}"
echo -e "${GREEN}                    Startup Complete!${NC}"
echo -e "${GREEN}====================================================================${NC}"
