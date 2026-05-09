#!/usr/bin/env bash
# Staged paper-trading startup. Avoids simultaneous-import RAM spike
# that crashes 8 GB hosts. Brings up DBs first, then services in 4 phases.
#
# Usage: ./scripts/start-paper-trading.sh
#
# Pre-reqs (do once):
#   - .env contains: AUTO_TRADING_ENABLED=true, BYBIT_TESTNET=false,
#     PAPER_TRADING_MODE=true, TRADING_MODE=PAPER, TELEGRAM_ENABLED=true,
#     TELEGRAM_BOT_TOKEN=<token>, TELEGRAM_CHAT_ID=<id>
#   - rm EMERGENCY_STOP   (delete the kill-switch file)
#   - .wslconfig in C:\Users\<user>\ caps WSL memory at 3 GB

set -euo pipefail
cd "$(dirname "$0")/.."

CF=docker-compose.unified.yml

wait_healthy() {
  local svc=$1
  local timeout=${2:-90}
  local elapsed=0
  while [ $elapsed -lt $timeout ]; do
    status=$(docker compose -f "$CF" ps "$svc" --format '{{.Status}}' 2>/dev/null || true)
    case "$status" in
      *healthy*)  echo "  $svc: healthy"; return 0 ;;
      *unhealthy*) echo "  $svc: UNHEALTHY"; docker compose -f "$CF" logs "$svc" --tail=30; return 1 ;;
    esac
    sleep 3
    elapsed=$((elapsed + 3))
  done
  echo "  $svc: timeout after ${timeout}s"
  docker compose -f "$CF" logs "$svc" --tail=30
  return 1
}

echo "=== Phase 1: DB layer (postgres, timescaledb, redis, rabbitmq) ==="
docker compose -f "$CF" up -d postgres timescaledb redis rabbitmq
wait_healthy postgres 60
wait_healthy timescaledb 60
wait_healthy redis 60
wait_healthy rabbitmq 90

echo
echo "=== Phase 1.5: ensure max_locks_per_transaction=1024 ==="
current=$(docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -t -c "SHOW max_locks_per_transaction;" 2>/dev/null | tr -d ' \n')
if [ "$current" != "1024" ]; then
  echo "  current=$current, bumping to 1024..."
  docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
    -c "ALTER SYSTEM SET max_locks_per_transaction = 1024;"
  docker compose -f "$CF" restart timescaledb
  wait_healthy timescaledb 60
else
  echo "  max_locks_per_transaction already 1024"
fi

echo
echo "=== Phase 2: data services (bybit-connector, market-data) ==="
docker compose -f "$CF" up -d bybit-connector market-data
wait_healthy bybit-connector 90
wait_healthy market-data 90

echo
echo "=== Phase 3: signal services (technical-analysis, portfolio-manager) ==="
docker compose -f "$CF" up -d technical-analysis portfolio-manager
wait_healthy technical-analysis 90
wait_healthy portfolio-manager 90

echo
echo "=== Phase 4: trading-engine + notification-service ==="
docker compose -f "$CF" up -d trading-engine notification-service
wait_healthy trading-engine 120
wait_healthy notification-service 90

echo
echo "=== Auto-trader gate state ==="
docker compose -f "$CF" logs trading-engine --tail=200 \
  | grep -E "AUTO TRADER|AUTO_TRADING|EMERGENCY" | tail -10

echo
echo "=== Stack up. Watch trades: ==="
echo "  docker compose -f $CF logs -f trading-engine | grep -E 'NOTIFY|trade|signal'"
