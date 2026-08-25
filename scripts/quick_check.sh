#!/bin/bash
# Crypto Trading Bot - Quick Status Check
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Fast 2-minute status check during trading day
# Usage: ./scripts/quick_check.sh

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Print header
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo -e "${CYAN}⚡ Quick Status Check${NC}"
echo -e "${CYAN}$(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo ""

# Check if services are running
echo -e "${BLUE}[1/5] Service Health${NC}"
healthy=$(curl -s http://localhost:8000/health 2>/dev/null && echo "1" || echo "0")

if [ "$healthy" == "1" ]; then
    # Quick check all services
    service_count=0
    for port in {8000..8009}; do
        if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
            ((service_count++))
        fi
    done

    if [ $service_count -eq 10 ]; then
        echo -e "  ${GREEN}✓${NC} All services running ($service_count/10)"
    elif [ $service_count -ge 7 ]; then
        echo -e "  ${YELLOW}⚠${NC} Some services down ($service_count/10)"
    else
        echo -e "  ${RED}✗${NC} Multiple services down ($service_count/10)"
    fi
else
    echo -e "  ${RED}✗${NC} Services not responding"
fi

# Check portfolio
echo ""
echo -e "${BLUE}[2/5] Portfolio Status${NC}"
balance_response=$(curl -s http://localhost:8003/api/v1/balance 2>/dev/null)

if [ ! -z "$balance_response" ]; then
    balance=$(echo "$balance_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_balance', 0))" 2>/dev/null)
    initial=$(echo "$balance_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('initial_balance', __import__('shared.account', fromlist=['ACCOUNT_EQUITY_USD']).ACCOUNT_EQUITY_USD))" 2>/dev/null)

    if [ ! -z "$balance" ] && [ ! -z "$initial" ]; then
        pnl=$(python3 -c "print(round($balance - $initial, 2))" 2>/dev/null)
        pnl_pct=$(python3 -c "print(round(($balance - $initial) / $initial * 100, 2))" 2>/dev/null)

        echo -e "  Balance:  \$$balance"

        if (( $(echo "$pnl >= 0" | bc -l) )); then
            echo -e "  Daily P&L: ${GREEN}+\$$pnl (+$pnl_pct%)${NC}"
        else
            echo -e "  Daily P&L: ${RED}\$$pnl ($pnl_pct%)${NC}"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} Could not parse balance"
    fi
else
    echo -e "  ${RED}✗${NC} Portfolio service not responding"
fi

# Check positions
echo ""
echo -e "${BLUE}[3/5] Active Positions${NC}"
positions_response=$(curl -s http://localhost:8005/api/v1/positions?status=open 2>/dev/null)

if [ ! -z "$positions_response" ]; then
    position_count=$(echo "$positions_response" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('positions', [])))" 2>/dev/null)

    if [ ! -z "$position_count" ]; then
        if [ $position_count -eq 0 ]; then
            echo -e "  ${BLUE}ℹ${NC} No open positions"
        elif [ $position_count -le 3 ]; then
            echo -e "  ${GREEN}✓${NC} $position_count open position(s)"

            # Show position symbols
            symbols=$(echo "$positions_response" | python3 -c "import sys, json; positions = json.load(sys.stdin).get('positions', []); print(', '.join([p['symbol'] for p in positions]))" 2>/dev/null)
            if [ ! -z "$symbols" ]; then
                echo -e "    Symbols: $symbols"
            fi
        elif [ $position_count -le 5 ]; then
            echo -e "  ${YELLOW}⚠${NC} $position_count open positions (near limit)"
        else
            echo -e "  ${RED}✗${NC} $position_count open positions (exceeds limit!)"
        fi
    fi
else
    echo -e "  ${RED}✗${NC} Trading engine not responding"
fi

# Check trading status
echo ""
echo -e "${BLUE}[4/5] Trading Status${NC}"
status_response=$(curl -s http://localhost:8005/api/v1/status 2>/dev/null)

if [ ! -z "$status_response" ]; then
    trading_active=$(echo "$status_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('trading_active', False))" 2>/dev/null)
    circuit_breaker=$(echo "$status_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('circuit_breaker_active', False))" 2>/dev/null)

    if [ "$trading_active" == "True" ]; then
        echo -e "  ${GREEN}▶${NC} Auto-trading ACTIVE"
    else
        echo -e "  ${BLUE}⏸${NC} Auto-trading PAUSED"
    fi

    if [ "$circuit_breaker" == "True" ]; then
        echo -e "  ${RED}🚨${NC} Circuit breaker ACTIVATED"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} Cannot determine trading status"
fi

# Check recent alerts
echo ""
echo -e "${BLUE}[5/5] Recent Alerts${NC}"

# Check monitor log for recent alerts
TODAY=$(date +%Y%m%d)
MONITOR_LOG="/tmp/monitor_${TODAY}.log"

if [ -f "$MONITOR_LOG" ]; then
    recent_alerts=$(grep "ALERT" "$MONITOR_LOG" | tail -3)

    if [ ! -z "$recent_alerts" ]; then
        echo -e "${YELLOW}Recent alerts (last 3):${NC}"
        echo "$recent_alerts" | while read line; do
            echo -e "  ${YELLOW}⚠${NC} $line"
        done
    else
        echo -e "  ${GREEN}✓${NC} No recent alerts"
    fi
else
    echo -e "  ${BLUE}ℹ${NC} Monitor log not found (monitor may not be running)"
fi

# Summary
echo ""
echo -e "${CYAN}════════════════════════════════════════${NC}"

# Calculate overall status
overall_status="UNKNOWN"
status_color=$NC

if [ "$healthy" == "1" ] && [ $service_count -ge 9 ]; then
    if [ "$circuit_breaker" == "True" ]; then
        overall_status="CIRCUIT BREAKER"
        status_color=$RED
    elif [ $position_count -gt 5 ]; then
        overall_status="TOO MANY POSITIONS"
        status_color=$RED
    elif (( $(echo "$pnl_pct < -4" | bc -l 2>/dev/null) )); then
        overall_status="HIGH LOSS"
        status_color=$YELLOW
    elif [ "$trading_active" == "True" ]; then
        overall_status="TRADING ACTIVE"
        status_color=$GREEN
    else
        overall_status="HEALTHY (PAUSED)"
        status_color=$BLUE
    fi
else
    overall_status="SERVICES DOWN"
    status_color=$RED
fi

echo -e "Status: ${status_color}${overall_status}${NC}"

# Quick actions
echo ""
echo -e "${CYAN}Quick Actions:${NC}"
echo "  Dashboard:  http://localhost:8080"
echo "  Stop:       curl -X POST http://localhost:8005/api/v1/stop"
echo "  Emergency:  curl -X POST http://localhost:8005/api/v1/emergency/stop"
echo "  Full check: ./scripts/health_check.sh --verbose"
echo ""
