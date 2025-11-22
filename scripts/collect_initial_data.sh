#!/bin/bash
#
# Initial Data Collection Script
# Purpose: Collect 30 days of 1-hour candle data for all trading pairs
# Usage: bash scripts/collect_initial_data.sh
#

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
BYBIT_URL="http://localhost:8001"
SYMBOLS=("BTCUSDT" "ETHUSDT" "BNBUSDT" "SOLUSDT" "XRPUSDT" "ADAUSDT" "DOGEUSDT")
INTERVAL="60"  # 1 hour
LIMIT=720  # 30 days of hourly candles

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  CRYPTO BOT - INITIAL DATA COLLECTION${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Configuration:"
echo "  - Symbols: ${#SYMBOLS[@]}"
echo "  - Interval: ${INTERVAL} minutes (1 hour)"
echo "  - Candles per symbol: ${LIMIT}"
echo "  - Wait between requests: 5 seconds"
echo ""

# Check if bybit connector is healthy
echo -e "${YELLOW}Checking Bybit Connector...${NC}"
if curl -s "${BYBIT_URL}/health" | grep -q "healthy"; then
    echo -e "${GREEN}✓ Bybit Connector is healthy${NC}"
else
    echo -e "${RED}✗ Bybit Connector is not responding${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Starting Data Collection${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

SUCCESS_COUNT=0
FAILURE_COUNT=0
TOTAL_CANDLES=0

# Collect data for each symbol
for i in "${!SYMBOLS[@]}"; do
    symbol="${SYMBOLS[$i]}"
    num=$((i+1))

    echo -e "${YELLOW}[$num/${#SYMBOLS[@]}] Collecting data for ${symbol}...${NC}"

    # Make API request
    response=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
        "${BYBIT_URL}/api/v1/market/kline?category=linear&symbol=${symbol}&interval=${INTERVAL}&limit=${LIMIT}")

    # Extract HTTP status
    http_status=$(echo "$response" | grep "HTTP_STATUS" | cut -d: -f2)
    body=$(echo "$response" | sed '$d')  # Remove last line (status)

    if [ "$http_status" = "200" ]; then
        # Count candles received
        candle_count=$(echo "$body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('list', [])))")

        echo -e "  ${GREEN}✓ Success - Received ${candle_count} candles${NC}"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        TOTAL_CANDLES=$((TOTAL_CANDLES + candle_count))
    elif [ "$http_status" = "429" ]; then
        echo -e "  ${RED}✗ Rate limited - Waiting 60 seconds...${NC}"
        sleep 60
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
    else
        echo -e "  ${RED}✗ Failed with HTTP ${http_status}${NC}"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
    fi

    # Wait between requests to avoid rate limiting
    if [ $num -lt ${#SYMBOLS[@]} ]; then
        echo -e "  ${YELLOW}Waiting 5 seconds before next symbol...${NC}"
        sleep 5
    fi

    echo ""
done

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  COLLECTION SUMMARY${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Total Symbols: ${#SYMBOLS[@]}"
echo -e "  ${GREEN}✓ Successful: ${SUCCESS_COUNT}${NC}"
echo -e "  ${RED}✗ Failed: ${FAILURE_COUNT}${NC}"
echo "  Total Candles Fetched: ${TOTAL_CANDLES}"
echo ""

if [ $FAILURE_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠ Warning: Some collections failed${NC}"
    echo -e "${YELLOW}  Suggestion: Run this script again or wait for scheduler${NC}"
    echo ""
fi

echo -e "${GREEN}✓ Data collection complete!${NC}"
echo ""
echo "Note: This script fetched data from Bybit Connector."
echo "      Market Data Service scheduler stores it in TimescaleDB."
echo "      Check database with: docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data"
echo ""
