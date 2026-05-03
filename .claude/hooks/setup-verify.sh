#!/bin/bash
# Hook Setup Verification Script
# Run this to verify your hooks are properly installed

echo "════════════════════════════════════════════════════════════"
echo "  Claude Code Hooks - Installation Verification"
echo "════════════════════════════════════════════════════════════"
echo ""

# Resolve from this script's location (was hardcoded WSL path).
HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALL_GOOD=true

# Check if hooks directory exists
echo "[1/5] Checking hooks directory..."
if [ -d "$HOOKS_DIR" ]; then
    echo "  ✅ Hooks directory exists: $HOOKS_DIR"
else
    echo "  ❌ Hooks directory not found: $HOOKS_DIR"
    ALL_GOOD=false
fi
echo ""

# Check if all hook files exist
echo "[2/5] Checking hook files..."
HOOKS=("user-prompt-submit.sh" "stop-event.sh" "agent-selector.sh")
for hook in "${HOOKS[@]}"; do
    if [ -f "$HOOKS_DIR/$hook" ]; then
        echo "  ✅ $hook exists"
    else
        echo "  ❌ $hook not found"
        ALL_GOOD=false
    fi
done
echo ""

# Check if hooks are executable
echo "[3/5] Checking execute permissions..."
for hook in "${HOOKS[@]}"; do
    if [ -x "$HOOKS_DIR/$hook" ]; then
        echo "  ✅ $hook is executable"
    else
        echo "  ⚠️  $hook is not executable - fixing..."
        chmod +x "$HOOKS_DIR/$hook"
        if [ -x "$HOOKS_DIR/$hook" ]; then
            echo "     ✅ Fixed!"
        else
            echo "     ❌ Could not fix permissions"
            ALL_GOOD=false
        fi
    fi
done
echo ""

# Test hooks with sample input
echo "[4/5] Testing hooks functionality..."
echo "  Testing user-prompt-submit.sh..."
TEST_OUTPUT=$("$HOOKS_DIR/user-prompt-submit.sh" "test bybit trading bot" 2>&1)
if [ $? -eq 0 ]; then
    echo "  ✅ user-prompt-submit.sh runs successfully"
else
    echo "  ❌ user-prompt-submit.sh failed"
    ALL_GOOD=false
fi

echo "  Testing agent-selector.sh..."
TEST_OUTPUT=$("$HOOKS_DIR/agent-selector.sh" "refactor god class" 2>&1)
if [ $? -eq 0 ]; then
    echo "  ✅ agent-selector.sh runs successfully"
else
    echo "  ❌ agent-selector.sh failed"
    ALL_GOOD=false
fi

echo "  Testing stop-event.sh..."
TEST_OUTPUT=$("$HOOKS_DIR/stop-event.sh" 2>&1)
if [ $? -eq 0 ]; then
    echo "  ✅ stop-event.sh runs successfully"
else
    echo "  ❌ stop-event.sh failed"
    ALL_GOOD=false
fi
echo ""

# Check Claude Code configuration
echo "[5/5] Checking Claude Code configuration..."
CONFIG_LOCATIONS=(
    "$HOME/.config/claude-code/settings.json"
    "$HOME/Library/Application Support/claude-code/settings.json"
    "$APPDATA/claude-code/settings.json"
)

CONFIG_FOUND=false
for config in "${CONFIG_LOCATIONS[@]}"; do
    if [ -f "$config" ]; then
        echo "  ℹ️  Found config: $config"
        if grep -q "hooks" "$config" 2>/dev/null; then
            echo "  ✅ Hooks configuration found in settings"
            CONFIG_FOUND=true
        else
            echo "  ⚠️  Config file exists but no hooks configured"
            echo "     Add hooks configuration as described in README.md"
        fi
        break
    fi
done

if [ "$CONFIG_FOUND" = false ]; then
    echo "  ⚠️  Claude Code config not found or no hooks configured"
    echo "     Please add hooks to your Claude Code settings.json"
    echo "     See README.md for configuration instructions"
fi
echo ""

# Final summary
echo "════════════════════════════════════════════════════════════"
if [ "$ALL_GOOD" = true ] && [ "$CONFIG_FOUND" = true ]; then
    echo "  ✅ ALL CHECKS PASSED!"
    echo "  Your hooks are properly installed and configured."
elif [ "$ALL_GOOD" = true ]; then
    echo "  ⚠️  HOOKS INSTALLED BUT NOT CONFIGURED"
    echo "  Files are ready, but you need to configure Claude Code."
    echo "  See README.md for configuration instructions."
else
    echo "  ❌ SOME ISSUES FOUND"
    echo "  Please review the errors above and fix them."
fi
echo "════════════════════════════════════════════════════════════"
echo ""

# Provide next steps
if [ "$ALL_GOOD" = true ] && [ "$CONFIG_FOUND" = false ]; then
    echo "NEXT STEPS:"
    echo "1. Open your Claude Code settings.json file"
    echo "2. Add the hooks configuration from README.md"
    echo "3. Restart Claude Code"
    echo "4. Test with a prompt like 'how does the trading bot work?'"
    echo ""
fi

exit 0
