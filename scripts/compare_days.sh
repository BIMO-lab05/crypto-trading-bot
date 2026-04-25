#!/bin/bash
# =============================================================================
# Compare Performance Between Days
# Purpose: Compare trading performance between two days
# Created: 2025-12-12
# Usage: ./scripts/compare_days.sh [DAY1_DATE] [DAY2_DATE]
# =============================================================================

set -e

# Default dates
DAY1=${1:-$(date -d '1 day ago' +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d)}
DAY2=${2:-$(date +%Y-%m-%d)}

echo "================================================================="
echo "       PERFORMANCE COMPARISON: $DAY1 vs $DAY2"
echo "================================================================="
echo ""

# Check if docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not available. Cannot query database."
    exit 1
fi

# =================================================================
# SECTION 1: SIDE-BY-SIDE COMPARISON
# =================================================================
echo "=== SIDE-BY-SIDE COMPARISON ==="

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot << SQL
\pset format aligned
\pset border 1

SELECT
    DATE(created_at) as date,
    COUNT(*) as trades,
    COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as wins,
    COALESCE(SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END), 0) as losses,
    COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as total_pnl,
    COALESCE(ROUND(AVG(pnl)::numeric, 2), 0) as avg_pnl,
    CASE WHEN COUNT(*) > 0
        THEN ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1)
        ELSE 0
    END as win_rate
FROM trades
WHERE DATE(created_at) IN ('$DAY1', '$DAY2')
GROUP BY DATE(created_at)
ORDER BY date;
SQL

echo ""

# =================================================================
# SECTION 2: IMPROVEMENT ANALYSIS
# =================================================================
echo "=== IMPROVEMENT ANALYSIS ==="

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t << SQL
WITH day_stats AS (
    SELECT
        DATE(created_at) as date,
        SUM(pnl) as total_pnl,
        COUNT(*) as trades,
        ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100), 1) as win_rate,
        ROUND(AVG(pnl)::numeric, 2) as avg_pnl
    FROM trades
    WHERE DATE(created_at) IN ('$DAY1', '$DAY2')
    GROUP BY DATE(created_at)
),
comparison AS (
    SELECT
        MAX(CASE WHEN date = '$DAY1' THEN total_pnl END) as day1_pnl,
        MAX(CASE WHEN date = '$DAY2' THEN total_pnl END) as day2_pnl,
        MAX(CASE WHEN date = '$DAY1' THEN trades END) as day1_trades,
        MAX(CASE WHEN date = '$DAY2' THEN trades END) as day2_trades,
        MAX(CASE WHEN date = '$DAY1' THEN win_rate END) as day1_wr,
        MAX(CASE WHEN date = '$DAY2' THEN win_rate END) as day2_wr,
        MAX(CASE WHEN date = '$DAY1' THEN avg_pnl END) as day1_avg,
        MAX(CASE WHEN date = '$DAY2' THEN avg_pnl END) as day2_avg
    FROM day_stats
)
SELECT
    'P&L Change: $' || COALESCE(ROUND((day2_pnl - day1_pnl)::numeric, 2)::text, 'N/A') ||
    ' (' || COALESCE(ROUND(((day2_pnl - day1_pnl) / NULLIF(ABS(day1_pnl), 0) * 100)::numeric, 1)::text, 'N/A') || '%)' as result
FROM comparison
UNION ALL
SELECT
    'Trade Count Change: ' || COALESCE((day2_trades - day1_trades)::text, 'N/A') ||
    ' trades'
FROM comparison
UNION ALL
SELECT
    'Win Rate Change: ' || COALESCE(ROUND((day2_wr - day1_wr)::numeric, 1)::text, 'N/A') ||
    ' percentage points'
FROM comparison
UNION ALL
SELECT
    'Avg Trade P&L Change: $' || COALESCE(ROUND((day2_avg - day1_avg)::numeric, 2)::text, 'N/A')
FROM comparison;
SQL

echo ""

# =================================================================
# SECTION 3: SYMBOL PERFORMANCE COMPARISON
# =================================================================
echo "=== SYMBOL PERFORMANCE COMPARISON ==="

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot << SQL
\pset format aligned
\pset border 1

WITH symbol_daily AS (
    SELECT
        symbol,
        DATE(created_at) as date,
        COUNT(*) as trades,
        COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as pnl
    FROM trades
    WHERE DATE(created_at) IN ('$DAY1', '$DAY2')
    GROUP BY symbol, DATE(created_at)
)
SELECT
    s.symbol,
    COALESCE(d1.trades, 0) as day1_trades,
    COALESCE(d1.pnl, 0) as day1_pnl,
    COALESCE(d2.trades, 0) as day2_trades,
    COALESCE(d2.pnl, 0) as day2_pnl,
    COALESCE(d2.pnl, 0) - COALESCE(d1.pnl, 0) as pnl_change
FROM (SELECT DISTINCT symbol FROM symbol_daily) s
LEFT JOIN symbol_daily d1 ON s.symbol = d1.symbol AND d1.date = '$DAY1'
LEFT JOIN symbol_daily d2 ON s.symbol = d2.symbol AND d2.date = '$DAY2'
ORDER BY pnl_change DESC;
SQL

echo ""

# =================================================================
# SECTION 4: HOURLY COMPARISON
# =================================================================
echo "=== HOURLY PERFORMANCE COMPARISON ==="

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot << SQL
\pset format aligned
\pset border 1

WITH hourly_stats AS (
    SELECT
        EXTRACT(HOUR FROM entry_time)::int as hour,
        DATE(created_at) as date,
        COUNT(*) as trades,
        COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as pnl
    FROM trades
    WHERE DATE(created_at) IN ('$DAY1', '$DAY2')
    GROUP BY EXTRACT(HOUR FROM entry_time), DATE(created_at)
)
SELECT
    h.hour as hour_utc,
    COALESCE(d1.trades, 0) as day1_trades,
    COALESCE(d1.pnl, 0) as day1_pnl,
    COALESCE(d2.trades, 0) as day2_trades,
    COALESCE(d2.pnl, 0) as day2_pnl
FROM (SELECT DISTINCT hour FROM hourly_stats) h
LEFT JOIN hourly_stats d1 ON h.hour = d1.hour AND d1.date = '$DAY1'
LEFT JOIN hourly_stats d2 ON h.hour = d2.hour AND d2.date = '$DAY2'
ORDER BY h.hour;
SQL

echo ""

# =================================================================
# SECTION 5: LONG VS SHORT COMPARISON
# =================================================================
echo "=== LONG VS SHORT COMPARISON ==="

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot << SQL
\pset format aligned
\pset border 1

WITH side_stats AS (
    SELECT
        side,
        DATE(created_at) as date,
        COUNT(*) as trades,
        COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as pnl,
        ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100), 1) as win_rate
    FROM trades
    WHERE DATE(created_at) IN ('$DAY1', '$DAY2')
    GROUP BY side, DATE(created_at)
)
SELECT
    s.side,
    COALESCE(d1.trades, 0) as day1_trades,
    COALESCE(d1.pnl, 0) as day1_pnl,
    COALESCE(d1.win_rate, 0) as day1_wr,
    COALESCE(d2.trades, 0) as day2_trades,
    COALESCE(d2.pnl, 0) as day2_pnl,
    COALESCE(d2.win_rate, 0) as day2_wr
FROM (SELECT DISTINCT side FROM side_stats) s
LEFT JOIN side_stats d1 ON s.side = d1.side AND d1.date = '$DAY1'
LEFT JOIN side_stats d2 ON s.side = d2.side AND d2.date = '$DAY2'
ORDER BY s.side;
SQL

echo ""

# =================================================================
# SECTION 6: SUMMARY ASSESSMENT
# =================================================================
echo "=== SUMMARY ASSESSMENT ==="

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t << SQL
WITH comparison AS (
    SELECT
        DATE(created_at) as date,
        SUM(pnl) as total_pnl,
        ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100), 1) as win_rate
    FROM trades
    WHERE DATE(created_at) IN ('$DAY1', '$DAY2')
    GROUP BY DATE(created_at)
)
SELECT
    CASE
        WHEN (SELECT total_pnl FROM comparison WHERE date = '$DAY2') >
             (SELECT total_pnl FROM comparison WHERE date = '$DAY1')
        THEN 'IMPROVEMENT: Day 2 P&L is better than Day 1'
        WHEN (SELECT total_pnl FROM comparison WHERE date = '$DAY2') <
             (SELECT total_pnl FROM comparison WHERE date = '$DAY1')
        THEN 'REGRESSION: Day 2 P&L is worse than Day 1'
        ELSE 'STABLE: P&L is similar between days'
    END as pnl_assessment,
    CASE
        WHEN (SELECT win_rate FROM comparison WHERE date = '$DAY2') >
             (SELECT win_rate FROM comparison WHERE date = '$DAY1')
        THEN 'IMPROVEMENT: Day 2 win rate is higher'
        WHEN (SELECT win_rate FROM comparison WHERE date = '$DAY2') <
             (SELECT win_rate FROM comparison WHERE date = '$DAY1')
        THEN 'REGRESSION: Day 2 win rate is lower'
        ELSE 'STABLE: Win rate is similar between days'
    END as wr_assessment;
SQL

echo ""
echo "================================================================="
echo "Comparison complete."
echo "================================================================="
