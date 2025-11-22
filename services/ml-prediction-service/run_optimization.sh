#!/bin/bash
# Quick Start Script for ML Model Hyperparameter Optimization
# Author: ML Optimization Agent
# Date: 2025-11-20

set -e  # Exit on error

echo "======================================================================"
echo "ML Model Hyperparameter Optimization Pipeline"
echo "======================================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "hyperparameter_optimizer.py" ]; then
    echo "Error: Must run from ml-prediction-service directory"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "======================================================================"
echo "Dependencies installed successfully"
echo "======================================================================"
echo ""

# Check database connection
echo "Checking TimescaleDB connection..."
python3 -c "
import asyncio
import asyncpg

async def check_db():
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5433,
            database='market_data',
            user='cryptobot',
            password='timescale_dev_password',
            timeout=5
        )
        result = await conn.fetchval('SELECT COUNT(*) FROM market_data.candles')
        await conn.close()
        print(f'✓ Database connected ({result} candles available)')
        return True
    except Exception as e:
        print(f'✗ Database connection failed: {e}')
        return False

if not asyncio.run(check_db()):
    exit(1)
" || {
    echo ""
    echo "ERROR: Cannot connect to TimescaleDB"
    echo "Please ensure TimescaleDB is running on localhost:5433"
    echo ""
    exit 1
}

echo ""
echo "======================================================================"
echo "Starting Hyperparameter Optimization"
echo "======================================================================"
echo ""
echo "This will optimize BTCUSDT and ETHUSDT models (GRU + LSTM)"
echo "Expected duration: 1-2 hours"
echo ""
echo "Progress will be logged to:"
echo "  - Console (stdout)"
echo "  - hyperparameter_optimization.log"
echo ""
read -p "Press Enter to start optimization, or Ctrl+C to cancel..."
echo ""

# Run optimization
python3 hyperparameter_optimizer.py

# Check if optimization succeeded
if [ $? -eq 0 ]; then
    echo ""
    echo "======================================================================"
    echo "Optimization Complete!"
    echo "======================================================================"
    echo ""

    # Generate comparison report
    echo "Generating comparison report..."
    python3 model_comparison.py

    echo ""
    echo "======================================================================"
    echo "Results Summary"
    echo "======================================================================"
    echo ""

    # Show optimization results
    if [ -f "trained_models_optimized/optimization_results.json" ]; then
        echo "Optimized models saved to: trained_models_optimized/"
        echo ""

        # Extract key results using Python
        python3 -c "
import json
from pathlib import Path

results_file = Path('trained_models_optimized/optimization_results.json')
if results_file.exists():
    with open(results_file, 'r') as f:
        results = json.load(f)

    print('Model Performance:')
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

    print('')
"

        echo "Detailed report: trained_models_optimized/optimization_report.md"
        echo "Hyperparameters: trained_models_optimized/best_hyperparameters.csv"
    fi

    echo ""
    echo "======================================================================"
    echo "Next Steps"
    echo "======================================================================"
    echo ""
    echo "1. Review optimization report:"
    echo "   cat trained_models_optimized/optimization_report.md"
    echo ""
    echo "2. View best hyperparameters:"
    echo "   cat trained_models_optimized/best_hyperparameters.csv"
    echo ""
    echo "3. Deploy optimized models (if R² ≥ 0.95):"
    echo "   - Copy models from trained_models_optimized/ to production"
    echo "   - Update API service to use optimized models"
    echo ""
    echo "4. Continue optimization if needed:"
    echo "   - Edit hyperparameter_optimizer.py (increase n_trials)"
    echo "   - Run this script again"
    echo ""

else
    echo ""
    echo "======================================================================"
    echo "Optimization Failed"
    echo "======================================================================"
    echo ""
    echo "Check logs for errors: hyperparameter_optimization.log"
    echo ""
    exit 1
fi
