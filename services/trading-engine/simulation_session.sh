#!/bin/bash
# Live Trading Simulation Session
# Purpose: Monitor real market signals and learn system behavior

echo "🎬 Starting Live Trading Simulation"
echo "===================================="
echo ""
echo "Symbol: BTCUSDT"
echo "Interval: 60 minutes (1 hour timeframe)"
echo "Update Frequency: Every 60 seconds"
echo ""
echo "What you'll see:"
echo "  📊 Real-time signal analysis"
echo "  🎯 Indicator votes (BUY/SELL/HOLD)"
echo "  💡 Decision rationale"
echo "  📈 Confidence levels"
echo "  ⚖️  Consensus tracking"
echo ""
echo "Press Ctrl+C to stop the simulation"
echo "===================================="
echo ""
sleep 2

# Run continuous monitoring
python3 monitor_signals.py --symbol BTCUSDT --continuous --delay 60
