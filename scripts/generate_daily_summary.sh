#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# =============================================================================
# Generate Daily Trading Summary
# Purpose: Create comprehensive daily summary report for paper trading
# Created: 2025-12-12
# Usage: ./scripts/generate_daily_summary.sh [YYYY-MM-DD]
# =============================================================================

set -e

# Configuration
PROJECT_DIR="${PROJECT_ROOT}"
REPORTS_DIR="$PROJECT_DIR/reports"

# Default to today's date if not provided
DATE=${1:-$(date +%Y-%m-%d)}
OUTPUT_FILE="$REPORTS_DIR/daily_summary_$DATE.txt"

# Create reports directory if it doesn't exist
mkdir -p "$REPORTS_DIR"

# Service endpoints
TRADING_ENGINE="http://localhost:8005"
PORTFOLIO_MANAGER="http://localhost:8003"
RISK_METRICS="http://localhost:8009"

echo "Generating daily summary for $DATE..."

# Start building the report
cat > "$OUTPUT_FILE" << EOF
================================================================
          DAILY TRADING SUMMARY - $DATE
================================================================
Generated: $(date '+%Y-%m-%d %H:%M:%S UTC')
Strategy: SQZMOM (Squeeze Momentum)
Mode: Paper Trading

================================================================
                    OVERALL STATISTICS
================================================================
EOF

# Get statistics from database
if command -v docker &> /dev/null; then
    docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot >> "$OUTPUT_FILE" 2>/dev/null << SQL
\pset format aligned
\pset border 1
\pset null 'N/A'

SELECT
  COUNT(*) as total_trades,
  COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as wins,
  COALESCE(SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END), 0) as losses,
  CASE WHEN COUNT(*) > 0
    THEN ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 2)
    ELSE 0
  END as win_rate_pct,
  COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as total_pnl,
  COALESCE(ROUND(AVG(pnl)::numeric, 2), 0) as avg_pnl,
  COALESCE(ROUND(MAX(pnl)::numeric, 2), 0) as best_trade,
  COALESCE(ROUND(MIN(pnl)::numeric, 2), 0) as worst_trade
FROM trades
WHERE DATE(created_at) = '$DATE';
SQL

    echo "" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"
    echo "                 PERFORMANCE BY SYMBOL" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"

    docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot >> "$OUTPUT_FILE" 2>/dev/null << SQL
\pset format aligned
\pset border 1

SELECT
  symbol,
  COUNT(*) as trades,
  COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as wins,
  COALESCE(SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END), 0) as losses,
  COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as total_pnl,
  CASE WHEN COUNT(*) > 0
    THEN ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1)
    ELSE 0
  END as win_rate
FROM trades
WHERE DATE(created_at) = '$DATE'
GROUP BY symbol
ORDER BY total_pnl DESC;
SQL

    echo "" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"
    echo "                 PERFORMANCE BY HOUR" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"

    docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot >> "$OUTPUT_FILE" 2>/dev/null << SQL
\pset format aligned
\pset border 1

SELECT
  EXTRACT(HOUR FROM entry_time)::int as hour_utc,
  COUNT(*) as trades,
  COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as pnl,
  CASE WHEN COUNT(*) > 0
    THEN ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1)
    ELSE 0
  END as win_rate
FROM trades
WHERE DATE(created_at) = '$DATE'
GROUP BY EXTRACT(HOUR FROM entry_time)
ORDER BY hour_utc;
SQL

    echo "" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"
    echo "                 PERFORMANCE BY SIDE" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"

    docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot >> "$OUTPUT_FILE" 2>/dev/null << SQL
\pset format aligned
\pset border 1

SELECT
  side,
  COUNT(*) as trades,
  COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as total_pnl,
  COALESCE(ROUND(AVG(pnl)::numeric, 2), 0) as avg_pnl,
  CASE WHEN COUNT(*) > 0
    THEN ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1)
    ELSE 0
  END as win_rate
FROM trades
WHERE DATE(created_at) = '$DATE'
GROUP BY side
ORDER BY side;
SQL

    echo "" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"
    echo "                 TRADE DURATION ANALYSIS" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"

    docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot >> "$OUTPUT_FILE" 2>/dev/null << SQL
\pset format aligned
\pset border 1

SELECT
  CASE
    WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 300 THEN '< 5 min'
    WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 900 THEN '5-15 min'
    WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 1800 THEN '15-30 min'
    WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 3600 THEN '30-60 min'
    ELSE '> 1 hour'
  END as duration_bucket,
  COUNT(*) as trades,
  COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as total_pnl,
  CASE WHEN COUNT(*) > 0
    THEN ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1)
    ELSE 0
  END as win_rate
FROM trades
WHERE DATE(created_at) = '$DATE'
  AND exit_time IS NOT NULL
GROUP BY duration_bucket
ORDER BY duration_bucket;
SQL

    echo "" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"
    echo "                 TRADE LIST (ALL TRADES)" >> "$OUTPUT_FILE"
    echo "================================================================" >> "$OUTPUT_FILE"

    docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot >> "$OUTPUT_FILE" 2>/dev/null << SQL
\pset format aligned
\pset border 1

SELECT
  TO_CHAR(entry_time, 'HH24:MI') as entry,
  TO_CHAR(exit_time, 'HH24:MI') as exit,
  symbol,
  side,
  ROUND(entry_price::numeric, 4) as entry_price,
  ROUND(exit_price::numeric, 4) as exit_price,
  ROUND(pnl::numeric, 2) as pnl,
  close_reason
FROM trades
WHERE DATE(created_at) = '$DATE'
ORDER BY entry_time;
SQL

fi

# Add portfolio status
echo "" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"
echo "                 PORTFOLIO STATUS" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"

portfolio=$(curl -s "$PORTFOLIO_MANAGER/api/v1/portfolio/status" 2>/dev/null)
if [ -n "$portfolio" ]; then
    echo "$portfolio" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(json.dumps(data, indent=2))
except:
    print('Unable to parse portfolio status')
" >> "$OUTPUT_FILE" 2>/dev/null
else
    echo "Unable to fetch portfolio status" >> "$OUTPUT_FILE"
fi

# Add risk metrics
echo "" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"
echo "                 RISK METRICS" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"

risk=$(curl -s "$RISK_METRICS/api/v1/risk/current" 2>/dev/null)
if [ -n "$risk" ]; then
    echo "$risk" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(json.dumps(data, indent=2))
except:
    print('Unable to parse risk metrics')
" >> "$OUTPUT_FILE" 2>/dev/null
else
    echo "Unable to fetch risk metrics" >> "$OUTPUT_FILE"
fi

# Add cumulative performance
echo "" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"
echo "              CUMULATIVE PERFORMANCE (All Days)" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"

if command -v docker &> /dev/null; then
    docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot >> "$OUTPUT_FILE" 2>/dev/null << SQL
\pset format aligned
\pset border 1

SELECT
  DATE(created_at) as date,
  COUNT(*) as trades,
  COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as daily_pnl,
  SUM(COALESCE(ROUND(SUM(pnl)::numeric, 2), 0)) OVER (ORDER BY DATE(created_at)) as cumulative_pnl,
  CASE WHEN COUNT(*) > 0
    THEN ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1)
    ELSE 0
  END as win_rate
FROM trades
GROUP BY DATE(created_at)
ORDER BY date;
SQL
fi

# Summary section
echo "" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"
echo "                     SUMMARY" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"

if command -v docker &> /dev/null; then
    summary=$(docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t -A -c "
        SELECT
            COUNT(*) as trades,
            COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as pnl,
            CASE WHEN COUNT(*) > 0
                THEN ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1)
                ELSE 0
            END as win_rate
        FROM trades
        WHERE DATE(created_at) = '$DATE';
    " 2>/dev/null || echo "0|0|0")

    trades=$(echo "$summary" | cut -d'|' -f1)
    pnl=$(echo "$summary" | cut -d'|' -f2)
    win_rate=$(echo "$summary" | cut -d'|' -f3)

    cat >> "$OUTPUT_FILE" << EOF

Day: $DATE
Total Trades: $trades
Win Rate: $win_rate%
Daily P&L: \$$pnl
EOF

    # Assessment
    if [ "$(echo "$pnl >= 0" | bc -l 2>/dev/null)" == "1" ]; then
        echo "Assessment: PROFITABLE DAY" >> "$OUTPUT_FILE"
    else
        echo "Assessment: LOSING DAY" >> "$OUTPUT_FILE"
    fi

    if [ "$(echo "$win_rate >= 45" | bc -l 2>/dev/null)" == "1" ]; then
        echo "Win Rate: MEETS TARGET (>= 45%)" >> "$OUTPUT_FILE"
    else
        echo "Win Rate: BELOW TARGET (< 45%)" >> "$OUTPUT_FILE"
    fi
fi

echo "" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"
echo "                 END OF DAILY SUMMARY" >> "$OUTPUT_FILE"
echo "================================================================" >> "$OUTPUT_FILE"

# Display the report
echo ""
cat "$OUTPUT_FILE"
echo ""
echo "Summary saved to: $OUTPUT_FILE"
