#!/bin/bash
# Crypto Trading Bot - Performance Report Generator
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Generate comprehensive performance reports
# Usage: ./scripts/generate_performance_report.sh [--period daily|weekly|monthly] [--format txt|json|html]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
PERIOD="daily"
FORMAT="txt"
OUTPUT_DIR="/tmp/crypto-bot-reports"
TODAY=$(date +%Y%m%d)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --period)
            PERIOD=$2
            shift 2
            ;;
        --format)
            FORMAT=$2
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR=$2
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--period daily|weekly|monthly] [--format txt|json|html] [--output-dir DIR]"
            exit 1
            ;;
    esac
done

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Report file
REPORT_FILE="${OUTPUT_DIR}/performance_${PERIOD}_${TODAY}.${FORMAT}"

# Log function
log() {
    local level=$1
    shift
    echo -e "${BLUE}[$(date '+%H:%M:%S')] $level:${NC} $@"
}

# Print header
print_header() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Performance Report Generator                             ║${NC}"
    echo -e "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log INFO "Generating $PERIOD performance report..."
    log INFO "Format: $FORMAT"
    log INFO "Output: $REPORT_FILE"
}

# Fetch portfolio metrics
fetch_portfolio_metrics() {
    log INFO "Fetching portfolio metrics..."

    local balance_response=$(curl -s http://localhost:8003/api/v1/balance 2>/dev/null)

    if [ ! -z "$balance_response" ]; then
        # Extract metrics using Python JSON parsing
        echo "$balance_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"TOTAL_BALANCE:{data.get('total_balance', 0)}\")
    print(f\"INITIAL_BALANCE:{data.get('initial_balance', 10000)}\")
    print(f\"AVAILABLE_BALANCE:{data.get('available_balance', 0)}\")
    print(f\"IN_POSITIONS:{data.get('in_positions', 0)}\")
except:
    print('ERROR:Failed to parse portfolio data')
" 2>/dev/null || echo "ERROR:API call failed"
    else
        echo "ERROR:No response from portfolio service"
    fi
}

# Fetch trading stats
fetch_trading_stats() {
    log INFO "Fetching trading statistics..."

    local stats_response=$(curl -s http://localhost:8005/api/v1/stats 2>/dev/null)

    if [ ! -z "$stats_response" ]; then
        echo "$stats_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"TOTAL_TRADES:{data.get('total_trades', 0)}\")
    print(f\"WINNING_TRADES:{data.get('winning_trades', 0)}\")
    print(f\"LOSING_TRADES:{data.get('losing_trades', 0)}\")
    print(f\"WIN_RATE:{data.get('win_rate', 0)}\")
    print(f\"TRADES_TODAY:{data.get('trades_today', 0)}\")
except:
    print('ERROR:Failed to parse trading stats')
" 2>/dev/null || echo "ERROR:API call failed"
    else
        echo "ERROR:No response from trading engine"
    fi
}

# Fetch risk metrics
fetch_risk_metrics() {
    log INFO "Fetching risk metrics..."

    local risk_response=$(curl -s http://localhost:8009/api/v1/metrics/portfolio 2>/dev/null)

    if [ ! -z "$risk_response" ]; then
        echo "$risk_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"SHARPE_RATIO:{data.get('sharpe_ratio', 0)}\")
    print(f\"MAX_DRAWDOWN:{data.get('max_drawdown', 0)}\")
    print(f\"VOLATILITY:{data.get('volatility', 0)}\")
    print(f\"VAR_95:{data.get('var_95', 0)}\")
except:
    print('ERROR:Failed to parse risk metrics')
" 2>/dev/null || echo "ERROR:API call failed"
    else
        echo "ERROR:No response from risk metrics service"
    fi
}

# Fetch position summary
fetch_positions() {
    log INFO "Fetching open positions..."

    local positions_response=$(curl -s "http://localhost:8005/api/v1/positions?status=open" 2>/dev/null)

    if [ ! -z "$positions_response" ]; then
        echo "$positions_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    positions = data.get('positions', [])
    print(f\"OPEN_POSITIONS:{len(positions)}\")

    total_pnl = sum(p.get('pnl', 0) for p in positions)
    print(f\"POSITIONS_PNL:{total_pnl}\")

    # Export positions detail
    for p in positions:
        symbol = p.get('symbol', 'UNKNOWN')
        side = p.get('side', 'UNKNOWN')
        pnl = p.get('pnl', 0)
        print(f\"POSITION:{symbol}|{side}|{pnl}\")
except:
    print('ERROR:Failed to parse positions')
" 2>/dev/null || echo "OPEN_POSITIONS:0"
    else
        echo "OPEN_POSITIONS:0"
    fi
}

# Generate text format report
generate_text_report() {
    local metrics_file="/tmp/metrics_${TODAY}.txt"

    # Collect all metrics
    {
        fetch_portfolio_metrics
        fetch_trading_stats
        fetch_risk_metrics
        fetch_positions
    } > "$metrics_file"

    # Parse metrics into variables
    source <(cat "$metrics_file" | grep -v "^ERROR:" | grep -v "^POSITION:")

    # Generate report
    {
        echo "════════════════════════════════════════════════════════════"
        echo "  Crypto Trading Bot - Performance Report"
        echo "  Period: $PERIOD"
        echo "  Generated: $TIMESTAMP"
        echo "════════════════════════════════════════════════════════════"
        echo ""

        echo "📊 PORTFOLIO SUMMARY"
        echo "────────────────────────────────────────────────────────────"
        echo "  Total Balance:      \$${TOTAL_BALANCE:-0}"
        echo "  Initial Balance:    \$${INITIAL_BALANCE:-10000}"
        echo "  Available:          \$${AVAILABLE_BALANCE:-0}"
        echo "  In Positions:       \$${IN_POSITIONS:-0}"

        # Calculate P&L
        local pnl=$(python3 -c "print(round(${TOTAL_BALANCE:-0} - ${INITIAL_BALANCE:-10000}, 2))" 2>/dev/null || echo "0")
        local pnl_pct=$(python3 -c "print(round((${TOTAL_BALANCE:-0} - ${INITIAL_BALANCE:-10000}) / ${INITIAL_BALANCE:-10000} * 100, 2))" 2>/dev/null || echo "0")

        echo ""
        if (( $(echo "$pnl >= 0" | bc -l 2>/dev/null || echo "0") )); then
            echo "  Total P&L:          +\$$pnl (+$pnl_pct%)"
        else
            echo "  Total P&L:          \$$pnl ($pnl_pct%)"
        fi

        echo ""
        echo "📈 TRADING STATISTICS"
        echo "────────────────────────────────────────────────────────────"
        echo "  Total Trades:       ${TOTAL_TRADES:-0}"
        echo "  Winning Trades:     ${WINNING_TRADES:-0}"
        echo "  Losing Trades:      ${LOSING_TRADES:-0}"
        echo "  Win Rate:           ${WIN_RATE:-0}%"
        echo "  Trades Today:       ${TRADES_TODAY:-0}"

        echo ""
        echo "⚠️  RISK METRICS"
        echo "────────────────────────────────────────────────────────────"
        echo "  Sharpe Ratio:       ${SHARPE_RATIO:-0}"
        echo "  Max Drawdown:       ${MAX_DRAWDOWN:-0}%"
        echo "  Volatility:         ${VOLATILITY:-0}%"
        echo "  VaR (95%):          \$${VAR_95:-0}"

        echo ""
        echo "💼 OPEN POSITIONS"
        echo "────────────────────────────────────────────────────────────"
        echo "  Count:              ${OPEN_POSITIONS:-0}"
        echo "  Unrealized P&L:     \$${POSITIONS_PNL:-0}"

        # List positions if any
        local positions=$(cat "$metrics_file" | grep "^POSITION:" | cut -d: -f2)
        if [ ! -z "$positions" ]; then
            echo ""
            echo "  Positions:"
            echo "$positions" | while IFS='|' read symbol side pnl; do
                printf "    - %-12s %-6s P&L: \$%.2f\n" "$symbol" "$side" "$pnl"
            done
        fi

        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "  Report generated at: $TIMESTAMP"
        echo "════════════════════════════════════════════════════════════"

    } > "$REPORT_FILE"

    # Clean up temp file
    rm -f "$metrics_file"

    log SUCCESS "Text report generated: $REPORT_FILE"
}

# Generate JSON format report
generate_json_report() {
    local metrics_file="/tmp/metrics_${TODAY}.txt"

    # Collect all metrics
    {
        fetch_portfolio_metrics
        fetch_trading_stats
        fetch_risk_metrics
        fetch_positions
    } > "$metrics_file"

    # Parse metrics and generate JSON
    cat "$metrics_file" | python3 -c "
import sys, json
from datetime import datetime

# Parse metrics
metrics = {}
positions = []

for line in sys.stdin:
    line = line.strip()
    if line.startswith('ERROR:'):
        continue
    elif line.startswith('POSITION:'):
        parts = line.split(':', 1)[1].split('|')
        if len(parts) == 3:
            positions.append({
                'symbol': parts[0],
                'side': parts[1],
                'pnl': float(parts[2])
            })
    elif ':' in line:
        key, value = line.split(':', 1)
        try:
            metrics[key.lower()] = float(value)
        except:
            metrics[key.lower()] = value

# Calculate P&L
total_balance = metrics.get('total_balance', 0)
initial_balance = metrics.get('initial_balance', 10000)
pnl = total_balance - initial_balance
pnl_pct = (pnl / initial_balance * 100) if initial_balance > 0 else 0

# Generate JSON report
report = {
    'report_type': '$PERIOD',
    'generated_at': '$TIMESTAMP',
    'portfolio': {
        'total_balance': total_balance,
        'initial_balance': initial_balance,
        'available_balance': metrics.get('available_balance', 0),
        'in_positions': metrics.get('in_positions', 0),
        'total_pnl': round(pnl, 2),
        'total_pnl_pct': round(pnl_pct, 2)
    },
    'trading': {
        'total_trades': int(metrics.get('total_trades', 0)),
        'winning_trades': int(metrics.get('winning_trades', 0)),
        'losing_trades': int(metrics.get('losing_trades', 0)),
        'win_rate': metrics.get('win_rate', 0),
        'trades_today': int(metrics.get('trades_today', 0))
    },
    'risk': {
        'sharpe_ratio': metrics.get('sharpe_ratio', 0),
        'max_drawdown': metrics.get('max_drawdown', 0),
        'volatility': metrics.get('volatility', 0),
        'var_95': metrics.get('var_95', 0)
    },
    'positions': {
        'count': len(positions),
        'unrealized_pnl': sum(p['pnl'] for p in positions),
        'details': positions
    }
}

print(json.dumps(report, indent=2))
" > "$REPORT_FILE"

    # Clean up temp file
    rm -f "$metrics_file"

    log SUCCESS "JSON report generated: $REPORT_FILE"
}

# Generate HTML format report
generate_html_report() {
    local metrics_file="/tmp/metrics_${TODAY}.txt"

    # Collect all metrics
    {
        fetch_portfolio_metrics
        fetch_trading_stats
        fetch_risk_metrics
        fetch_positions
    } > "$metrics_file"

    # Parse metrics into variables
    source <(cat "$metrics_file" | grep -v "^ERROR:" | grep -v "^POSITION:")

    # Calculate P&L
    local pnl=$(python3 -c "print(round(${TOTAL_BALANCE:-0} - ${INITIAL_BALANCE:-10000}, 2))" 2>/dev/null || echo "0")
    local pnl_pct=$(python3 -c "print(round((${TOTAL_BALANCE:-0} - ${INITIAL_BALANCE:-10000}) / ${INITIAL_BALANCE:-10000} * 100, 2))" 2>/dev/null || echo "0")

    # Determine P&L color
    local pnl_color="red"
    if (( $(echo "$pnl >= 0" | bc -l 2>/dev/null || echo "0") )); then
        pnl_color="green"
    fi

    # Generate HTML report
    {
        cat <<'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Performance Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1000px;
            margin: 40px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
        }
        .container {
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        h1 {
            text-align: center;
            color: #667eea;
            margin-bottom: 10px;
        }
        .timestamp {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
        }
        .section {
            margin: 30px 0;
            padding: 20px;
            border-radius: 8px;
            background: #f8f9fa;
        }
        .section h2 {
            margin-top: 0;
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #e0e0e0;
        }
        .metric:last-child {
            border-bottom: none;
        }
        .metric-label {
            font-weight: 500;
            color: #555;
        }
        .metric-value {
            font-weight: 600;
            color: #333;
        }
        .positive {
            color: #28a745;
        }
        .negative {
            color: #dc3545;
        }
        .positions-list {
            margin-top: 15px;
        }
        .position-item {
            padding: 10px;
            margin: 5px 0;
            background: white;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 2px solid #e0e0e0;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Trading Performance Report</h1>
        <div class="timestamp">
EOF
        echo "            Period: $PERIOD | Generated: $TIMESTAMP"
        cat <<EOF
        </div>

        <div class="section">
            <h2>💰 Portfolio Summary</h2>
            <div class="metric">
                <span class="metric-label">Total Balance</span>
                <span class="metric-value">\$${TOTAL_BALANCE:-0}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Initial Balance</span>
                <span class="metric-value">\$${INITIAL_BALANCE:-10000}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Available</span>
                <span class="metric-value">\$${AVAILABLE_BALANCE:-0}</span>
            </div>
            <div class="metric">
                <span class="metric-label">In Positions</span>
                <span class="metric-value">\$${IN_POSITIONS:-0}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Total P&L</span>
                <span class="metric-value $pnl_color">\$$pnl ($pnl_pct%)</span>
            </div>
        </div>

        <div class="section">
            <h2>📈 Trading Statistics</h2>
            <div class="metric">
                <span class="metric-label">Total Trades</span>
                <span class="metric-value">${TOTAL_TRADES:-0}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Winning Trades</span>
                <span class="metric-value positive">${WINNING_TRADES:-0}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Losing Trades</span>
                <span class="metric-value negative">${LOSING_TRADES:-0}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Win Rate</span>
                <span class="metric-value">${WIN_RATE:-0}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Trades Today</span>
                <span class="metric-value">${TRADES_TODAY:-0}</span>
            </div>
        </div>

        <div class="section">
            <h2>⚠️ Risk Metrics</h2>
            <div class="metric">
                <span class="metric-label">Sharpe Ratio</span>
                <span class="metric-value">${SHARPE_RATIO:-0}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Max Drawdown</span>
                <span class="metric-value negative">${MAX_DRAWDOWN:-0}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Volatility</span>
                <span class="metric-value">${VOLATILITY:-0}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">VaR (95%)</span>
                <span class="metric-value">\$${VAR_95:-0}</span>
            </div>
        </div>

        <div class="section">
            <h2>💼 Open Positions</h2>
            <div class="metric">
                <span class="metric-label">Count</span>
                <span class="metric-value">${OPEN_POSITIONS:-0}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Unrealized P&L</span>
                <span class="metric-value $pnl_color">\$${POSITIONS_PNL:-0}</span>
            </div>
EOF

        # List positions if any
        local positions=$(cat "$metrics_file" | grep "^POSITION:" | cut -d: -f2)
        if [ ! -z "$positions" ]; then
            echo "            <div class=\"positions-list\">"
            echo "$positions" | while IFS='|' read symbol side pnl; do
                local pos_color="negative"
                if (( $(echo "$pnl >= 0" | bc -l 2>/dev/null || echo "0") )); then
                    pos_color="positive"
                fi
                echo "                <div class=\"position-item\">"
                echo "                    <span>$symbol - $side</span>"
                echo "                    <span class=\"$pos_color\">\$$(printf "%.2f" "$pnl")</span>"
                echo "                </div>"
            done
            echo "            </div>"
        fi

        cat <<EOF
        </div>

        <div class="footer">
            <p>Crypto Trading Bot v1.0.0</p>
            <p>Report generated at: $TIMESTAMP</p>
        </div>
    </div>
</body>
</html>
EOF
    } > "$REPORT_FILE"

    # Clean up temp file
    rm -f "$metrics_file"

    log SUCCESS "HTML report generated: $REPORT_FILE"
    log INFO "Open in browser: file://$REPORT_FILE"
}

# Print summary
print_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Report Generation Complete${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✓ Report generated successfully${NC}"
    echo ""
    echo "Period:  $PERIOD"
    echo "Format:  $FORMAT"
    echo "Output:  $REPORT_FILE"
    echo ""

    if [ -f "$REPORT_FILE" ]; then
        local size=$(du -h "$REPORT_FILE" | cut -f1)
        echo "Size:    $size"

        if [ "$FORMAT" == "html" ]; then
            echo ""
            echo "View report in browser:"
            echo "  file://$REPORT_FILE"
        elif [ "$FORMAT" == "txt" ]; then
            echo ""
            echo "View report:"
            echo "  cat $REPORT_FILE"
        elif [ "$FORMAT" == "json" ]; then
            echo ""
            echo "View report:"
            echo "  cat $REPORT_FILE | jq"
        fi
    fi

    echo ""
}

# Main execution
main() {
    print_header

    echo ""

    # Generate report based on format
    case $FORMAT in
        txt)
            generate_text_report
            ;;
        json)
            generate_json_report
            ;;
        html)
            generate_html_report
            ;;
        *)
            log ERROR "Unknown format: $FORMAT"
            exit 1
            ;;
    esac

    print_summary
}

# Run main function
main
