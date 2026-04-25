#!/bin/bash
# =============================================================================
# Statistical Arbitrage Paper Trading Deployment Script
# Purpose: Deploy and configure paper trading for Stat Arb strategies
# Created: 2025-12-11
# =============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$SERVICE_DIR")")"

echo "=================================================================="
echo -e "${BLUE}  STATISTICAL ARBITRAGE - PAPER TRADING DEPLOYMENT${NC}"
echo "=================================================================="
echo ""
echo "Service Directory: $SERVICE_DIR"
echo "Project Root: $PROJECT_ROOT"
echo ""

# Functions
log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Step 1: Backup existing .env
backup_env() {
    log_step "Backing up existing .env file..."

    if [ -f "$SERVICE_DIR/.env" ]; then
        BACKUP_FILE="$SERVICE_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$SERVICE_DIR/.env" "$BACKUP_FILE"
        log_success "Backup created: $BACKUP_FILE"
    else
        log_warning "No existing .env file found"
    fi
}

# Step 2: Deploy Stat Arb config
deploy_config() {
    log_step "Deploying Statistical Arbitrage paper trading configuration..."

    if [ -f "$SERVICE_DIR/.env.stat_arb_paper" ]; then
        cp "$SERVICE_DIR/.env.stat_arb_paper" "$SERVICE_DIR/.env"
        log_success "Configuration deployed from .env.stat_arb_paper"
    else
        log_error "Configuration file not found: $SERVICE_DIR/.env.stat_arb_paper"
        exit 1
    fi
}

# Step 3: Verify configuration
verify_config() {
    log_step "Verifying configuration settings..."

    # Check critical settings
    TRADING_MODE=$(grep "^TRADING_MODE=" "$SERVICE_DIR/.env" | cut -d'=' -f2)
    STAT_ARB_ENABLED=$(grep "^STAT_ARB_ENABLED=" "$SERVICE_DIR/.env" | cut -d'=' -f2)
    PAPER_BALANCE=$(grep "^PAPER_INITIAL_BALANCE=" "$SERVICE_DIR/.env" | cut -d'=' -f2)

    echo ""
    echo "Configuration Verification:"
    echo "----------------------------"

    if [ "$TRADING_MODE" = "PAPER" ]; then
        log_success "Trading Mode: PAPER (Safe)"
    else
        log_error "Trading Mode: $TRADING_MODE (UNSAFE!)"
        exit 1
    fi

    if [ "$STAT_ARB_ENABLED" = "true" ]; then
        log_success "Statistical Arbitrage: ENABLED"
    else
        log_warning "Statistical Arbitrage: DISABLED"
    fi

    log_success "Paper Initial Balance: \$$PAPER_BALANCE"

    # Check disabled strategies
    GRID_ENABLED=$(grep "^GRID_TRADING_ENABLED=" "$SERVICE_DIR/.env" | cut -d'=' -f2)
    TREND_ENABLED=$(grep "^TREND_FOLLOWING_ENABLED=" "$SERVICE_DIR/.env" | cut -d'=' -f2)

    if [ "$GRID_ENABLED" = "false" ]; then
        log_success "Grid Trading: DISABLED (Isolated testing)"
    fi
    if [ "$TREND_ENABLED" = "false" ]; then
        log_success "Trend Following: DISABLED (Isolated testing)"
    fi

    echo ""
}

# Step 4: Check service dependencies
check_dependencies() {
    log_step "Checking service dependencies..."

    BYBIT_URL=$(grep "^BYBIT_CONNECTOR_URL=" "$SERVICE_DIR/.env" | cut -d'=' -f2)
    TA_URL=$(grep "^TECHNICAL_ANALYSIS_URL=" "$SERVICE_DIR/.env" | cut -d'=' -f2)

    # Check Bybit Connector
    echo -n "  Bybit Connector ($BYBIT_URL/health): "
    if curl -s -o /dev/null -w "%{http_code}" "$BYBIT_URL/health" 2>/dev/null | grep -q "200"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}NOT RESPONDING${NC}"
        log_warning "Bybit Connector may not be running"
    fi

    # Check Technical Analysis
    echo -n "  Technical Analysis ($TA_URL/health): "
    if curl -s -o /dev/null -w "%{http_code}" "$TA_URL/health" 2>/dev/null | grep -q "200"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}NOT RESPONDING${NC}"
        log_warning "Technical Analysis service may not be running"
    fi

    echo ""
}

# Step 5: Check Bybit testnet configuration
check_bybit_testnet() {
    log_step "Checking Bybit connector configuration..."

    BYBIT_ENV="$PROJECT_ROOT/services/bybit-connector/.env"

    if [ -f "$BYBIT_ENV" ]; then
        BYBIT_TESTNET=$(grep "^BYBIT_TESTNET=" "$BYBIT_ENV" | cut -d'=' -f2)

        if [ "$BYBIT_TESTNET" = "true" ]; then
            log_success "Bybit Connector: TESTNET MODE"
        else
            log_warning "Bybit Connector: MAINNET MODE (Real prices, paper trades only)"
        fi

        # Check if API keys are configured
        API_KEY=$(grep "^BYBIT_API_KEY=" "$BYBIT_ENV" | cut -d'=' -f2)
        if [ -n "$API_KEY" ] && [ "$API_KEY" != "your_api_key_here" ]; then
            log_success "Bybit API Key: Configured"
        else
            log_warning "Bybit API Key: Not configured"
        fi
    else
        log_error "Bybit connector .env not found"
    fi

    echo ""
}

# Step 6: Display summary
display_summary() {
    echo "=================================================================="
    echo -e "${GREEN}  DEPLOYMENT COMPLETE${NC}"
    echo "=================================================================="
    echo ""
    echo "Statistical Arbitrage Paper Trading Configuration:"
    echo ""
    echo "  Mode:               PAPER TRADING (Safe)"
    echo "  Initial Balance:    \$10,000 (Virtual)"
    echo "  Active Symbols:     BTCUSDT, ETHUSDT"
    echo "  Max Position Size:  5% per trade"
    echo "  Strategy:           Statistical Arbitrage ONLY"
    echo ""
    echo "Sub-Strategy Allocations:"
    echo "  - Pairs Trading:    40%"
    echo "  - Funding Rate:     40%"
    echo "  - Triangular:       20%"
    echo ""
    echo "Other Strategies: DISABLED"
    echo "  - Grid Trading:     OFF"
    echo "  - Trend Following:  OFF"
    echo "  - Momentum:         OFF"
    echo ""
    echo "To start the trading engine:"
    echo "  cd $SERVICE_DIR"
    echo "  python -m uvicorn app.main:app --reload --port 8005"
    echo ""
    echo "To revert to original configuration:"
    echo "  cp $SERVICE_DIR/.env.backup.* $SERVICE_DIR/.env"
    echo ""
    echo "=================================================================="
}

# Main execution
main() {
    echo "Starting deployment at $(date)"
    echo ""

    backup_env
    deploy_config
    verify_config
    check_dependencies
    check_bybit_testnet
    display_summary

    echo ""
    log_success "Paper trading environment configured successfully!"
    echo ""
}

# Run main
main
