#!/bin/bash
# Script to start the profitable trading system

set -e  # Exit on any error

echo "💰 Starting Profitable Crypto Trading System"
echo "==========================================="

# Navigate to the project root (resolves from script location instead of a
# hardcoded WSL path so the script works on any machine).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔄 Checking configuration..."
echo "   - SHORT trading enabled: $(python -c "from services.trading-engine.app.config import get_settings; s = get_settings(); print(s.short_trading_enabled)")"
echo "   - Allowed trade sides: $(python -c "from services.trading-engine.app.config import get_settings; s = get_settings(); print(s.allowed_trade_sides)")"
echo "   - Min confidence: $(python -c "from services.trading-engine.app.config import get_settings; s = get_settings(); print(s.min_signal_confidence)")"
echo "   - Take profit: $(python -c "from services.trading-engine.app.config import get_settings; s = get_settings(); print(s.default_take_profit_pct)")"
echo ""

echo "🚀 Starting Trading Engine Service..."

# Start the trading engine service
cd services/trading-engine
uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload &

ENGINE_PID=$!
echo "📊 Trading Engine started with PID: $ENGINE_PID"

# Wait a moment for the service to start
sleep 5

echo ""
echo "🎉 Profitable Trading System is now running!"
echo "=============================================="
echo "📈 Trading Engine: http://localhost:8005"
echo "📊 API endpoints available at: http://localhost:8005/docs"
echo ""
echo "💡 The system is configured with:"
echo "   • Optimized symbol allocations"
echo "   • SHORT trading enabled for current market"
echo "   • 60% minimum confidence threshold"
echo "   • 2% stop loss / 4% take profit (2:1 R/R)"
echo "   • Advanced risk management"
echo ""
echo "🔧 To monitor: curl http://localhost:8005/api/v1/trading/status"
echo "📊 To check trades: curl http://localhost:8005/api/v1/trades/history"
echo ""

# Wait for the trading engine to finish
wait $ENGINE_PID