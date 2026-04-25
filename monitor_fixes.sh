#!/bin/bash
# Crypto Trading Bot - Fix Monitoring Script
# Created: 2026-01-16
# Monitors Fix #1 (SHORT enforcement) and Fix #2 (Max hold time)

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   CRYPTO TRADING BOT - FIX MONITORING DASHBOARD          ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "Generated: $(date)"
echo ""

# ============================================================
# CRITICAL CHECK #1: SHORT Positions (Must be 0)
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚨 CRITICAL: SHORT Positions (Target: 0)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SHORT_COUNT=$(docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT COUNT(*) FROM positions WHERE side='SHORT' AND opened_at > NOW() - INTERVAL '24 hours';
" 2>/dev/null | grep -E '^\s*[0-9]+' | tr -d ' ')

if [ "$SHORT_COUNT" = "0" ]; then
    echo "✅ STATUS: PASS"
    echo "   No SHORT positions opened in last 24h"
else
    echo "❌ STATUS: FAIL"
    echo "   WARNING: $SHORT_COUNT SHORT positions found!"
    echo ""
    docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
    SELECT symbol, side, entry_price, opened_at
    FROM positions
    WHERE side='SHORT' AND opened_at > NOW() - INTERVAL '24 hours'
    ORDER BY opened_at DESC;
    " 2>/dev/null
fi
echo ""

# ============================================================
# CRITICAL CHECK #2: Position Hold Times (Max 48h)
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏱️  CRITICAL: Position Hold Times (Max: 48h)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

OPEN_COUNT=$(docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT COUNT(*) FROM positions WHERE status='OPEN';
" 2>/dev/null | grep -E '^\s*[0-9]+' | tr -d ' ')

if [ "$OPEN_COUNT" = "0" ]; then
    echo "ℹ️  STATUS: No open positions"
else
    echo "📊 Open Positions: $OPEN_COUNT"
    echo ""
    docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
    SELECT
        symbol,
        side,
        ROUND(EXTRACT(EPOCH FROM (NOW() - opened_at))/3600, 1) as hours_held,
        ROUND(unrealized_pnl::numeric, 2) as pnl,
        CASE
            WHEN EXTRACT(EPOCH FROM (NOW() - opened_at))/3600 > 48 THEN '⚠️ OVER LIMIT'
            WHEN EXTRACT(EPOCH FROM (NOW() - opened_at))/3600 > 40 THEN '⚡ APPROACHING'
            ELSE '✅ OK'
        END as status
    FROM positions
    WHERE status='OPEN'
    ORDER BY hours_held DESC;
    " 2>/dev/null
fi
echo ""

# ============================================================
# INFO: Trade Side Rejections
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Trade Side Rejections (Last 24h)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

REJECTION_COUNT=$(docker logs crypto-bot-trading --since 24h 2>/dev/null | grep 'RISK_GATE.*REJECTING' | wc -l)

echo "Total Rejections: $REJECTION_COUNT"

if [ "$REJECTION_COUNT" -gt 0 ]; then
    echo ""
    echo "Recent rejection log:"
    docker logs crypto-bot-trading --since 24h 2>/dev/null | grep 'RISK_GATE.*REJECTING' | tail -5
fi
echo ""

# ============================================================
# INFO: Max Hold Time Force Closes
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔨 Force Closes (Last 24h)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

FORCE_CLOSE_COUNT=$(docker logs crypto-bot-trading --since 24h 2>/dev/null | grep 'MAX_HOLD.*Successfully closed' | wc -l)

echo "Total Force Closes: $FORCE_CLOSE_COUNT"

if [ "$FORCE_CLOSE_COUNT" -gt 0 ]; then
    echo ""
    echo "Recent force close log:"
    docker logs crypto-bot-trading --since 24h 2>/dev/null | grep 'MAX_HOLD.*Successfully closed' | tail -5
fi
echo ""

# ============================================================
# INFO: Service Health
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏥 Service Health"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker ps --filter name=crypto-bot-trading --format "{{.Names}}: {{.Status}}" | while read line; do
    if echo "$line" | grep -q "healthy"; then
        echo "✅ $line"
    else
        echo "⚠️  $line"
    fi
done
echo ""

# ============================================================
# INFO: Recent Performance
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 Recent Performance (Last 24h)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT
    COUNT(*) as total_trades,
    COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
    COUNT(CASE WHEN realized_pnl < 0 THEN 1 END) as losses,
    ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
    ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
FROM positions
WHERE closed_at > NOW() - INTERVAL '24 hours';
" 2>/dev/null

echo ""

# ============================================================
# VALIDATION SUMMARY
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ VALIDATION SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Calculate overall status
if [ "$SHORT_COUNT" = "0" ]; then
    echo "✅ Fix #1 (SHORT Enforcement): WORKING"
else
    echo "❌ Fix #1 (SHORT Enforcement): FAILING"
fi

OVER_LIMIT=$(docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT COUNT(*) FROM positions
WHERE status='OPEN' AND EXTRACT(EPOCH FROM (NOW() - opened_at))/3600 > 48;
" 2>/dev/null | grep -E '^\s*[0-9]+' | tr -d ' ')

if [ "$OVER_LIMIT" = "0" ] || [ -z "$OVER_LIMIT" ]; then
    echo "✅ Fix #2 (Max Hold Time): WORKING"
else
    echo "❌ Fix #2 (Max Hold Time): FAILING ($OVER_LIMIT positions over 48h)"
fi

echo ""
echo "Next check: Run this script again in 4-6 hours"
echo "Full validation: 2026-01-17 22:00 UTC (24 hours)"
echo ""
echo "╚═══════════════════════════════════════════════════════════╝"
