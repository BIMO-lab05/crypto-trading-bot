#!/bin/bash
# Quick optimization progress check

echo "======================================================================"
echo "ML Hyperparameter Optimization - Quick Check"
echo "======================================================================"
echo ""

# Check if running
if docker exec crypto-bot-ml-prediction ps aux | grep -q hyperparameter_optimizer.py; then
    echo "✓ Status: RUNNING"

    # Get runtime
    START_TIME=$(docker logs crypto-bot-ml-prediction 2>&1 | grep "Optimization Pipeline" -A1 | tail -1 | awk '{print $1, $2}')
    echo "  Started: $START_TIME"

    # Show latest trials
    echo ""
    echo "Latest Activity:"
    echo "----------------------------------------------------------------------"
    docker logs crypto-bot-ml-prediction --tail 30 2>&1 | grep -E "Trial [0-9]+:|Best trial" | tail -5

    # Count completed trials
    TRIALS=$(docker logs crypto-bot-ml-prediction 2>&1 | grep "Trial [0-9]+:" | wc -l)
    echo ""
    echo "  Completed Trials: $TRIALS / 200"
    echo "  Progress: $(($TRIALS * 100 / 200))%"

else
    echo "✗ Status: NOT RUNNING"

    # Check if completed
    if docker exec crypto-bot-ml-prediction test -d /app/trained_models_optimized 2>/dev/null; then
        echo ""
        echo "✓ Optimization appears to be COMPLETED!"
        echo ""
        echo "Results location: /app/trained_models_optimized/"
        echo ""
        echo "To view results:"
        echo "  docker exec crypto-bot-ml-prediction cat /app/trained_models_optimized/optimization_report.md"
    fi
fi

echo ""
echo "======================================================================"
echo "For detailed monitoring:"
echo "  docker logs crypto-bot-ml-prediction -f"
echo "======================================================================"
