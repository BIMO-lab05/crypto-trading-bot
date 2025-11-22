#!/bin/bash
# Quick service health check script

echo "🏥 CRYPTO BOT SERVICE HEALTH CHECK"
echo "=================================="
echo ""

services=(
  "8000:API Gateway"
  "8001:Bybit Connector"
  "8002:Market Data"
  "8003:Portfolio Manager"
  "8004:Technical Analysis"
  "8005:Trading Engine"
  "8006:Notification Service"
  "8007:ML Prediction"
  "8008:Sentiment Analysis"
  "8009:Risk Metrics"
)

healthy=0
unhealthy=0

for service in "${services[@]}"; do
  port="${service%%:*}"
  name="${service#*:}"

  echo -n "[$port] $name: "

  response=$(timeout 2 curl -s http://localhost:$port/health 2>/dev/null)

  if [ -n "$response" ]; then
    status=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null)
    if [ "$status" = "healthy" ]; then
      echo "✅ HEALTHY"
      ((healthy++))
    else
      echo "⚠️  $status"
      ((unhealthy++))
    fi
  else
    echo "❌ NOT RESPONDING"
    ((unhealthy++))
  fi
done

echo ""
echo "=================================="
echo "Summary: $healthy healthy, $unhealthy issues"
echo "=================================="
