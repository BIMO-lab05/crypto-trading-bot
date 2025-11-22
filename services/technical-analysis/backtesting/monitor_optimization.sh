#!/bin/bash
# Monitor Parameter Optimization Progress
# Usage: ./monitor_optimization.sh

echo "========================================"
echo "Parameter Optimization Monitor"
echo "========================================"
echo ""

# Check if optimization is running
OPTIMIZE_PID=$(pgrep -f "optimize_(focused|parameters).py")

if [ -n "$OPTIMIZE_PID" ]; then
    echo "✓ Optimization is RUNNING (PID: $OPTIMIZE_PID)"

    # Get CPU and memory usage
    CPU=$(ps -p $OPTIMIZE_PID -o %cpu= | xargs)
    MEM=$(ps -p $OPTIMIZE_PID -o %mem= | xargs)
    ELAPSED=$(ps -p $OPTIMIZE_PID -o etime= | xargs)

    echo "  CPU Usage: ${CPU}%"
    echo "  Memory: ${MEM}%"
    echo "  Running Time: ${ELAPSED}"
    echo ""
else
    echo "✗ No optimization currently running"
    echo ""
fi

# Check for output files
echo "Output Files:"
echo "-------------"

BACKTEST_DIR="/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting"

if [ -f "${BACKTEST_DIR}/PARAMETER_OPTIMIZATION_REPORT.md" ]; then
    FILE_TIME=$(stat -c %y "${BACKTEST_DIR}/PARAMETER_OPTIMIZATION_REPORT.md" | cut -d'.' -f1)
    echo "✓ PARAMETER_OPTIMIZATION_REPORT.md (${FILE_TIME})"
else
    echo "⏳ PARAMETER_OPTIMIZATION_REPORT.md (pending)"
fi

# Check for symbol-specific JSON files
for symbol in SOLUSDT DOGEUSDT BNBUSDT; do
    FOCUSED_FILE="${BACKTEST_DIR}/optimization_${symbol}_focused.json"
    FULL_FILE="${BACKTEST_DIR}/optimization_${symbol}.json"

    if [ -f "$FOCUSED_FILE" ]; then
        FILE_TIME=$(stat -c %y "$FOCUSED_FILE" | cut -d'.' -f1)
        SIZE=$(du -h "$FOCUSED_FILE" | cut -f1)
        echo "✓ optimization_${symbol}_focused.json (${SIZE}, ${FILE_TIME})"
    elif [ -f "$FULL_FILE" ]; then
        FILE_TIME=$(stat -c %y "$FULL_FILE" | cut -d'.' -f1)
        SIZE=$(du -h "$FULL_FILE" | cut -f1)
        echo "✓ optimization_${symbol}.json (${SIZE}, ${FILE_TIME})"
    else
        echo "⏳ optimization_${symbol}*.json (pending)"
    fi
done

# Check for combined results
if [ -f "${BACKTEST_DIR}/all_optimizations_focused.json" ]; then
    FILE_TIME=$(stat -c %y "${BACKTEST_DIR}/all_optimizations_focused.json" | cut -d'.' -f1)
    SIZE=$(du -h "${BACKTEST_DIR}/all_optimizations_focused.json" | cut -f1)
    echo "✓ all_optimizations_focused.json (${SIZE}, ${FILE_TIME})"
elif [ -f "${BACKTEST_DIR}/all_optimizations.json" ]; then
    FILE_TIME=$(stat -c %y "${BACKTEST_DIR}/all_optimizations.json" | cut -d'.' -f1)
    SIZE=$(du -h "${BACKTEST_DIR}/all_optimizations.json" | cut -f1)
    echo "✓ all_optimizations.json (${SIZE}, ${FILE_TIME})"
else
    echo "⏳ all_optimizations*.json (pending)"
fi

echo ""
echo "========================================"
echo ""

# If optimization is running, provide status
if [ -n "$OPTIMIZE_PID" ]; then
    echo "Status: Optimization in progress..."
    echo ""
    echo "Estimated completion time:"
    echo "  - Focused optimization: 15-30 minutes total"
    echo "  - Full optimization: 90-180 minutes total"
    echo ""
    echo "You can safely close this terminal."
    echo "Results will be saved to files above."
else
    echo "Status: No active optimization"
    echo ""
    echo "To start optimization, run:"
    echo "  python3 optimize_focused.py       (fast, 15-30 min)"
    echo "  python3 optimize_parameters.py    (comprehensive, 90-180 min)"
fi

echo ""
