#!/bin/bash
# Live Log Aggregator
# Tails logs from all services in real-time with color coding

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       CRYPTO TRADING BOT - LIVE LOG MONITOR           ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Service to monitor (default: all critical services)
SERVICES=${1:-"crypto-bot-trading crypto-bot-portfolio crypto-bot-bybit crypto-bot-market-data crypto-bot-ta"}

echo -e "${YELLOW}Monitoring services: ${SERVICES}${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Tail logs from multiple services with color coding
docker logs -f --tail=20 crypto-bot-trading 2>&1 | sed "s/^/$(echo -e ${GREEN})[TRADING]$(echo -e ${NC}) /" &
docker logs -f --tail=20 crypto-bot-portfolio 2>&1 | sed "s/^/$(echo -e ${BLUE})[PORTFOLIO]$(echo -e ${NC}) /" &
docker logs -f --tail=20 crypto-bot-bybit 2>&1 | sed "s/^/$(echo -e ${YELLOW})[BYBIT]$(echo -e ${NC}) /" &
docker logs -f --tail=20 crypto-bot-market-data 2>&1 | sed "s/^/$(echo -e ${MAGENTA})[MARKET-DATA]$(echo -e ${NC}) /" &
docker logs -f --tail=20 crypto-bot-ta 2>&1 | sed "s/^/$(echo -e ${CYAN})[TECH-ANALYSIS]$(echo -e ${NC}) /" &

# Wait for user interrupt
wait
