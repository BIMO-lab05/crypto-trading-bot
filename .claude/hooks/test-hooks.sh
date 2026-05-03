#!/bin/bash
# Test script to demonstrate hooks in action
# Run this to see what Claude will see when hooks are configured

echo "════════════════════════════════════════════════════════════"
echo "  Claude Code Hooks - Interactive Demo"
echo "════════════════════════════════════════════════════════════"
echo ""

# Resolve from this script's location (was hardcoded WSL path).
HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Test scenarios
declare -a SCENARIOS=(
    "How does the authentication system work?"
    "Add RSI indicator to the trading bot"
    "Refactor the God class using Strangler Fig pattern"
    "Create a new React component for the dashboard"
    "Optimize the database query performance"
    "Write tests for the trading engine"
    "Fix the bug in order execution"
    "Document the API endpoints"
    "Deploy the microservices to production"
)

echo "This demo shows what Claude will see when hooks are active."
echo "Select a test scenario:"
echo ""

for i in "${!SCENARIOS[@]}"; do
    echo "  $((i+1)). ${SCENARIOS[$i]}"
done

echo ""
read -p "Enter scenario number (1-${#SCENARIOS[@]}) or type your own prompt: " choice
echo ""

if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#SCENARIOS[@]}" ]; then
    TEST_PROMPT="${SCENARIOS[$((choice-1))]}"
else
    TEST_PROMPT="$choice"
fi

echo "════════════════════════════════════════════════════════════"
echo "Testing with prompt: \"$TEST_PROMPT\""
echo "════════════════════════════════════════════════════════════"
echo ""

# Run UserPromptSubmit hook
echo "─── OUTPUT FROM: user-prompt-submit.sh ───"
"$HOOKS_DIR/user-prompt-submit.sh" "$TEST_PROMPT"
echo ""

# Run Agent Selector hook
echo "─── OUTPUT FROM: agent-selector.sh ───"
"$HOOKS_DIR/agent-selector.sh" "$TEST_PROMPT"
echo ""

# Simulate stop event
echo "════════════════════════════════════════════════════════════"
echo "  Simulating Stop Event Hook"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Creating test file with code quality issues..."

# Create a temporary test file with issues
TEST_FILE="/tmp/test_trading_service.py"
cat > "$TEST_FILE" << 'EOF'
import asyncio
from bybit import BybitAPI

class TradingService:
    def __init__(self):
        self.api_key = "hardcoded_key_123"  # Security issue!
        self.client = BybitAPI(self.api_key)

    async def place_order(self, symbol, quantity):
        # Missing error handling!
        result = await self.client.place_order(symbol, quantity)
        print("Order placed:", result)  # Should use logging
        return result

    def calculate_position_size(self):
        try:
            # TODO: Implement proper position sizing
            size = 0.02 * self.get_balance()
            return size
        except:
            # Missing logging!
            pass
EOF

echo "Test file created at: $TEST_FILE"
echo ""

# Run stop event hook
echo "─── OUTPUT FROM: stop-event.sh ───"
"$HOOKS_DIR/stop-event.sh"
echo ""

# Cleanup
rm -f "$TEST_FILE"

echo "════════════════════════════════════════════════════════════"
echo "  Demo Complete!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "This is what Claude will see automatically when you:"
echo "  1. Submit a prompt → user-prompt-submit + agent-selector run"
echo "  2. Claude finishes → stop-event runs"
echo ""
echo "To activate these hooks in Claude Code:"
echo "  1. See README.md for configuration instructions"
echo "  2. Add hooks to your settings.json"
echo "  3. Restart Claude Code"
echo ""

exit 0
