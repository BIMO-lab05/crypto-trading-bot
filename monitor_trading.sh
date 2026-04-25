#!/bin/bash
# Trading Activity Monitor
# Real-time monitoring of trading operations, positions, and P&L

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

clear

echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         CRYPTO TRADING BOT - TRADING MONITOR          ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check Portfolio Summary
echo -e "${BLUE}┌─ PORTFOLIO SUMMARY ─────────────────────────────────┐${NC}"
portfolio=$(curl -s http://localhost:8003/api/v1/portfolio/summary 2>/dev/null)
if [ ! -z "$portfolio" ] && [ "$portfolio" != '{"detail":"Not Found"}' ]; then
    echo "$portfolio" | python3 -m json.tool 2>/dev/null | grep -v "detail" || echo "No portfolio data yet"
else
    echo -e "${YELLOW}Portfolio not initialized${NC}"
    echo "This is normal if no trades have been executed yet"
fi
echo -e "${BLUE}└─────────────────────────────────────────────────────┘${NC}"
echo ""

# Check Active Positions
echo -e "${BLUE}┌─ ACTIVE POSITIONS ──────────────────────────────────┐${NC}"
positions=$(curl -s http://localhost:8003/api/v1/positions 2>/dev/null)
if [ ! -z "$positions" ] && [ "$positions" != "null" ] && [ "$positions" != '{"detail":"Not Found"}' ]; then
    echo "$positions" | python3 -m json.tool 2>/dev/null | head -30
else
    echo -e "${YELLOW}No active positions${NC}"
fi
echo -e "${BLUE}└─────────────────────────────────────────────────────┘${NC}"
echo ""

# Check Recent Signals
echo -e "${BLUE}┌─ RECENT TRADING SIGNALS ────────────────────────────┐${NC}"
symbols=("BTCUSDT" "ETHUSDT" "SOLUSDT")
for symbol in "${symbols[@]}"; do
    signal=$(curl -s "http://localhost:8004/api/v1/signals/${symbol}" 2>/dev/null)
    if [ ! -z "$signal" ] && [ "$signal" != "null" ]; then
        echo -e "${GREEN}${symbol}:${NC}"
        echo "$signal" | python3 -m json.tool 2>/dev/null | head -10
    fi
done
echo -e "${BLUE}└─────────────────────────────────────────────────────┘${NC}"
echo ""

# Check Current Prices
echo -e "${BLUE}┌─ CURRENT MARKET PRICES ─────────────────────────────┐${NC}"
for symbol in "${symbols[@]}"; do
    price=$(curl -s "http://localhost:8002/api/v1/price/${symbol}" 2>/dev/null)
    if [ ! -z "$price" ] && [ "$price" != "null" ] && [[ ! "$price" =~ "detail" ]]; then
        echo -e "${GREEN}${symbol}:${NC} $price"
    else
        echo -e "${YELLOW}${symbol}:${NC} Data not available"
    fi
done
echo -e "${BLUE}└─────────────────────────────────────────────────────┘${NC}"
echo ""

# Check Trading Engine Status
echo -e "${BLUE}┌─ TRADING ENGINE STATUS ─────────────────────────────┐${NC}"
engine_status=$(curl -s "http://localhost:8005/api/v1/status" 2>/dev/null)
if [ ! -z "$engine_status" ]; then
    echo "$engine_status" | python3 -m json.tool 2>/dev/null || echo "$engine_status"
else
    echo -e "${YELLOW}Engine status not available${NC}"
fi
echo -e "${BLUE}└─────────────────────────────────────────────────────┘${NC}"
echo ""

# Check Recent Orders
echo -e "${BLUE}┌─ RECENT ORDERS (Last 5) ────────────────────────────┐${NC}"
orders=$(curl -s "http://localhost:8005/api/v1/orders?limit=5" 2>/dev/null)
if [ ! -z "$orders" ] && [ "$orders" != "null" ] && [[ ! "$orders" =~ "detail" ]]; then
    echo "$orders" | python3 -m json.tool 2>/dev/null | head -30
else
    echo -e "${YELLOW}No recent orders${NC}"
fi
echo -e "${BLUE}└─────────────────────────────────────────────────────┘${NC}"
echo ""

# Risk Metrics
echo -e "${BLUE}┌─ RISK METRICS ──────────────────────────────────────┐${NC}"
risk=$(curl -s "http://localhost:8009/api/v1/metrics" 2>/dev/null)
if [ ! -z "$risk" ] && [ "$risk" != "null" ]; then
    echo "$risk" | python3 -m json.tool 2>/dev/null | head -20
else
    echo -e "${YELLOW}Risk metrics not available${NC}"
fi
echo -e "${BLUE}└─────────────────────────────────────────────────────┘${NC}"

echo ""
echo -e "${CYAN}Tip: Run with --continuous to auto-refresh every 10 seconds${NC}"

# Continuous mode
if [ "$1" = "--continuous" ] || [ "$1" = "-c" ]; then
    sleep 10
    exec bash "$0" "$@"
fi
