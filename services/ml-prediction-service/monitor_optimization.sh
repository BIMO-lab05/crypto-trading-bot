#!/bin/bash
# Monitor hyperparameter optimization progress

echo "======================================================================"
echo "ML Hyperparameter Optimization Progress Monitor"
echo "======================================================================"
echo ""

# Check if optimization is running
if docker exec crypto-bot-ml-prediction pgrep -f hyperparameter_optimizer.py > /dev/null; then
    echo "Status: RUNNING"

    # Get process info
    PID=$(docker exec crypto-bot-ml-prediction pgrep -f hyperparameter_optimizer.py)
    UPTIME=$(docker exec crypto-bot-ml-prediction ps -p $PID -o etime= 2>/dev/null | tr -d ' ')
    echo "Runtime: $UPTIME"
    echo ""

    # Show recent trials
    echo "======================================================================"
    echo "Recent Trial Results:"
    echo "======================================================================"
    docker exec crypto-bot-ml-prediction tail -100 /app/optimization_output.log 2>/dev/null | \
        grep -E "Trial [0-9]+ finished|Best is trial|R² =|symbol|model_type" | tail -20

    echo ""
    echo "======================================================================"
    echo "Current Activity (last 10 lines):"
    echo "======================================================================"
    docker exec crypto-bot-ml-prediction tail -10 /app/optimization_output.log 2>/dev/null

else
    echo "Status: NOT RUNNING or COMPLETED"
    echo ""

    # Check if completed
    if docker exec crypto-bot-ml-prediction test -f /app/trained_models_optimized/optimization_results.json 2>/dev/null; then
        echo "======================================================================"
        echo "Optimization COMPLETED! Results available."
        echo "======================================================================"
        echo ""

        # Show summary
        docker exec crypto-bot-ml-prediction python3 -c "
import json
from pathlib import Path

results_file = Path('/app/trained_models_optimized/optimization_results.json')
if results_file.exists():
    with open(results_file, 'r') as f:
        results = json.load(f)

    print('Final Results:')
    print('-' * 60)
    for result in results:
        symbol = result.get('symbol')
        model_type = result.get('model_type')
        r2 = result.get('final_metrics', {}).get('r2_score', 0)
        mae = result.get('final_metrics', {}).get('mae', 0)

        # Determine if meets target
        target = 0.95 if symbol == 'BTCUSDT' else 0.90
        status = '✓' if r2 >= target else '✗'

        print(f'{symbol} {model_type:4s}: R²={r2:.4f} {status}  MAE={mae:.4f}')
" 2>/dev/null
    else
        echo "Results file not yet created."
    fi
fi

echo ""
echo "======================================================================"
echo "To view full log: docker exec crypto-bot-ml-prediction cat /app/optimization_output.log"
echo "======================================================================"
