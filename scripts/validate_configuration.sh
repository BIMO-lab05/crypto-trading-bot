#!/bin/bash
# Crypto Trading Bot - Configuration Validation Script
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Validate all configuration files and settings
# Usage: ./scripts/validate_configuration.sh [--fix] [--verbose]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
FIX_MODE=false
VERBOSE=false
ERRORS=0
WARNINGS=0
PROJECT_DIR="/mnt/d/Bimo_max/crypto-trading-bot"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_MODE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--fix] [--verbose]"
            exit 1
            ;;
    esac
done

# Log function
log() {
    local level=$1
    shift
    local message="$@"

    case $level in
        INFO)
            echo -e "${BLUE}[INFO]${NC} $message"
            ;;
        SUCCESS)
            echo -e "${GREEN}[OK]${NC} $message"
            ;;
        WARNING)
            echo -e "${YELLOW}[WARN]${NC} $message"
            ((WARNINGS++))
            ;;
        ERROR)
            echo -e "${RED}[ERROR]${NC} $message"
            ((ERRORS++))
            ;;
    esac
}

# Print header
print_header() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Configuration Validation                                  ║${NC}"
    echo -e "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    if $FIX_MODE; then
        log INFO "Running in FIX mode - will attempt to fix issues"
    else
        log INFO "Running in CHECK mode - use --fix to auto-fix issues"
    fi
    echo ""
}

# Check if file exists
check_file_exists() {
    local file=$1
    local description=$2

    if [ -f "$file" ]; then
        log SUCCESS "$description exists: $file"
        return 0
    else
        log ERROR "$description missing: $file"
        return 1
    fi
}

# Check environment variable in file
check_env_var() {
    local file=$1
    local var_name=$2
    local required=$3
    local description=$4

    if [ ! -f "$file" ]; then
        return 1
    fi

    if grep -q "^${var_name}=" "$file"; then
        local value=$(grep "^${var_name}=" "$file" | cut -d'=' -f2- | tr -d '"' | tr -d "'")

        if [ -z "$value" ] || [ "$value" == "your_value_here" ] || [ "$value" == "REPLACE_ME" ]; then
            if [ "$required" == "true" ]; then
                log ERROR "$description not configured in $file"
                return 1
            else
                log WARNING "$description not set in $file (optional)"
                return 2
            fi
        else
            if $VERBOSE; then
                # Mask sensitive values
                if [[ "$var_name" == *"KEY"* ]] || [[ "$var_name" == *"SECRET"* ]] || [[ "$var_name" == *"PASSWORD"* ]]; then
                    log SUCCESS "$description configured (value masked)"
                else
                    log SUCCESS "$description = $value"
                fi
            else
                log SUCCESS "$description configured"
            fi
            return 0
        fi
    else
        if [ "$required" == "true" ]; then
            log ERROR "$description missing in $file"
            return 1
        else
            log WARNING "$description missing in $file (optional)"
            return 2
        fi
    fi
}

# Validate docker-compose.yml
validate_docker_compose() {
    echo -e "${CYAN}═══ Docker Compose Configuration ═══${NC}"
    echo ""

    check_file_exists "$PROJECT_DIR/docker-compose.yml" "docker-compose.yml"

    # Validate docker-compose syntax
    if command -v docker-compose &> /dev/null; then
        if docker-compose config > /dev/null 2>&1; then
            log SUCCESS "docker-compose.yml syntax is valid"
        else
            log ERROR "docker-compose.yml has syntax errors"
            if $VERBOSE; then
                docker-compose config 2>&1
            fi
        fi
    fi

    echo ""
}

# Validate service environment files
validate_service_configs() {
    echo -e "${CYAN}═══ Service Configuration Files ═══${NC}"
    echo ""

    # Define services and required variables
    declare -A services=(
        ["bybit-connector"]="BYBIT_API_KEY BYBIT_API_SECRET BYBIT_TESTNET"
        ["market-data-service"]="BYBIT_API_KEY BYBIT_API_SECRET"
        ["trading-engine"]="MAX_RISK_PER_TRADE DAILY_LOSS_LIMIT CIRCUIT_BREAKER_THRESHOLD"
        ["portfolio-manager"]="INITIAL_BALANCE"
        ["notification-service"]="TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID"
    )

    for service in "${!services[@]}"; do
        local env_file="$PROJECT_DIR/services/$service/.env"

        echo "Service: $service"
        echo "────────────────────────────────────────"

        if [ -f "$env_file" ]; then
            log SUCCESS ".env file exists"

            # Check required variables
            for var in ${services[$service]}; do
                local required="false"

                # Determine if variable is required
                if [[ "$var" == "BYBIT_API_KEY" ]] || [[ "$var" == "BYBIT_API_SECRET" ]]; then
                    required="false"  # Optional for testnet
                elif [[ "$var" == "MAX_RISK_PER_TRADE" ]] || [[ "$var" == "DAILY_LOSS_LIMIT" ]]; then
                    required="true"   # Critical for risk management
                fi

                check_env_var "$env_file" "$var" "$required" "$var"
            done
        else
            log ERROR ".env file missing: $env_file"

            if $FIX_MODE; then
                log INFO "Creating template .env file..."
                mkdir -p "$(dirname $env_file)"

                cat > "$env_file" <<EOF
# $service Configuration
# Generated: $(date '+%Y-%m-%d %H:%M:%S')

$(for var in ${services[$service]}; do
    echo "# ${var}="
done)
EOF
                log SUCCESS "Template created: $env_file"
                log WARNING "Please configure the values in $env_file"
            fi
        fi

        echo ""
    done
}

# Validate database configuration
validate_database_config() {
    echo -e "${CYAN}═══ Database Configuration ═══${NC}"
    echo ""

    local db_env_files=$(find "$PROJECT_DIR/services" -name "db_config.env" 2>/dev/null)

    if [ -z "$db_env_files" ]; then
        log WARNING "No db_config.env files found"
    else
        while IFS= read -r db_file; do
            echo "Database config: $(dirname $db_file | xargs basename)"

            check_env_var "$db_file" "DB_HOST" "true" "Database host"
            check_env_var "$db_file" "DB_PORT" "true" "Database port"
            check_env_var "$db_file" "DB_NAME" "true" "Database name"
            check_env_var "$db_file" "DB_USER" "true" "Database user"
            check_env_var "$db_file" "DB_PASSWORD" "true" "Database password"

            echo ""
        done <<< "$db_env_files"
    fi
}

# Validate risk management settings
validate_risk_settings() {
    echo -e "${CYAN}═══ Risk Management Settings ═══${NC}"
    echo ""

    local trading_env="$PROJECT_DIR/services/trading-engine/.env"

    if [ -f "$trading_env" ]; then
        # Check critical risk limits
        local max_risk=$(grep "^MAX_RISK_PER_TRADE=" "$trading_env" 2>/dev/null | cut -d'=' -f2)
        local daily_loss=$(grep "^DAILY_LOSS_LIMIT=" "$trading_env" 2>/dev/null | cut -d'=' -f2)
        local circuit_breaker=$(grep "^CIRCUIT_BREAKER_THRESHOLD=" "$trading_env" 2>/dev/null | cut -d'=' -f2)

        # Validate max risk per trade (should be <= 2%)
        if [ ! -z "$max_risk" ]; then
            if (( $(echo "$max_risk > 2" | bc -l 2>/dev/null || echo "1") )); then
                log ERROR "MAX_RISK_PER_TRADE too high: $max_risk% (recommended: 2% or less)"
            else
                log SUCCESS "MAX_RISK_PER_TRADE: $max_risk%"
            fi
        else
            log ERROR "MAX_RISK_PER_TRADE not configured"
        fi

        # Validate daily loss limit (should be <= 5%)
        if [ ! -z "$daily_loss" ]; then
            if (( $(echo "$daily_loss > 5" | bc -l 2>/dev/null || echo "1") )); then
                log WARNING "DAILY_LOSS_LIMIT high: $daily_loss% (recommended: 5% or less)"
            else
                log SUCCESS "DAILY_LOSS_LIMIT: $daily_loss%"
            fi
        else
            log ERROR "DAILY_LOSS_LIMIT not configured"
        fi

        # Validate circuit breaker
        if [ ! -z "$circuit_breaker" ]; then
            if (( $(echo "$circuit_breaker > 10" | bc -l 2>/dev/null || echo "1") )); then
                log WARNING "CIRCUIT_BREAKER_THRESHOLD high: $circuit_breaker% (recommended: 10% or less)"
            else
                log SUCCESS "CIRCUIT_BREAKER_THRESHOLD: $circuit_breaker%"
            fi
        else
            log ERROR "CIRCUIT_BREAKER_THRESHOLD not configured"
        fi
    else
        log ERROR "Trading engine .env not found"
    fi

    echo ""
}

# Validate API keys configuration
validate_api_keys() {
    echo -e "${CYAN}═══ API Keys Configuration ═══${NC}"
    echo ""

    local bybit_env="$PROJECT_DIR/services/bybit-connector/.env"

    if [ -f "$bybit_env" ]; then
        local testnet=$(grep "^BYBIT_TESTNET=" "$bybit_env" 2>/dev/null | cut -d'=' -f2)
        local api_key=$(grep "^BYBIT_API_KEY=" "$bybit_env" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'")

        if [ "$testnet" == "true" ] || [ "$testnet" == "True" ]; then
            log SUCCESS "Running in TESTNET mode (safe for testing)"

            if [ -z "$api_key" ] || [ "$api_key" == "your_api_key_here" ]; then
                log WARNING "Testnet API keys not configured - using mock data"
            else
                log SUCCESS "Testnet API keys configured"
            fi
        else
            log WARNING "Running in MAINNET mode"

            if [ -z "$api_key" ] || [ "$api_key" == "your_api_key_here" ]; then
                log ERROR "Mainnet API keys not configured but testnet=false"
            else
                log SUCCESS "Mainnet API keys configured"
                log WARNING "Ensure you have tested thoroughly on testnet first!"
            fi
        fi
    else
        log ERROR "Bybit connector .env not found"
    fi

    echo ""
}

# Validate notification configuration
validate_notifications() {
    echo -e "${CYAN}═══ Notification Configuration ═══${NC}"
    echo ""

    local notif_env="$PROJECT_DIR/services/notification-service/.env"

    if [ -f "$notif_env" ]; then
        check_env_var "$notif_env" "TELEGRAM_BOT_TOKEN" "false" "Telegram Bot Token"
        check_env_var "$notif_env" "TELEGRAM_CHAT_ID" "false" "Telegram Chat ID"

        # Test telegram connection if configured
        local bot_token=$(grep "^TELEGRAM_BOT_TOKEN=" "$notif_env" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'")

        if [ ! -z "$bot_token" ] && [ "$bot_token" != "your_bot_token_here" ]; then
            if $VERBOSE; then
                log INFO "Testing Telegram connection..."
                if curl -s "https://api.telegram.org/bot${bot_token}/getMe" | grep -q '"ok":true'; then
                    log SUCCESS "Telegram bot connection successful"
                else
                    log ERROR "Telegram bot connection failed"
                fi
            fi
        fi
    else
        log WARNING "Notification service .env not found (optional)"
    fi

    echo ""
}

# Validate port configuration
validate_ports() {
    echo -e "${CYAN}═══ Port Configuration ═══${NC}"
    echo ""

    local ports=(8000 8001 8002 8003 8004 8005 8006 8007 8008 8009)

    for port in "${ports[@]}"; do
        if lsof -i :$port >/dev/null 2>&1; then
            log WARNING "Port $port is already in use"
            if $VERBOSE; then
                lsof -i :$port | tail -1
            fi
        else
            log SUCCESS "Port $port is available"
        fi
    done

    echo ""
}

# Check Docker availability
validate_docker() {
    echo -e "${CYAN}═══ Docker Configuration ═══${NC}"
    echo ""

    if command -v docker &> /dev/null; then
        log SUCCESS "Docker is installed"

        if docker ps >/dev/null 2>&1; then
            log SUCCESS "Docker daemon is running"

            local version=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
            log INFO "Docker version: $version"
        else
            log ERROR "Docker daemon is not running"
        fi
    else
        log ERROR "Docker is not installed"
    fi

    if command -v docker-compose &> /dev/null; then
        log SUCCESS "Docker Compose is installed"

        local compose_version=$(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1)
        log INFO "Docker Compose version: $compose_version"
    else
        log ERROR "Docker Compose is not installed"
    fi

    echo ""
}

# Validate Python environment
validate_python() {
    echo -e "${CYAN}═══ Python Environment ═══${NC}"
    echo ""

    if command -v python3 &> /dev/null; then
        log SUCCESS "Python3 is installed"

        local python_version=$(python3 --version | cut -d' ' -f2)
        log INFO "Python version: $python_version"

        # Check required packages
        local packages=("requests" "python-dotenv" "redis" "psycopg2" "pandas")

        for package in "${packages[@]}"; do
            if python3 -c "import $package" 2>/dev/null; then
                log SUCCESS "Package installed: $package"
            else
                log WARNING "Package missing: $package"
            fi
        done
    else
        log ERROR "Python3 is not installed"
    fi

    echo ""
}

# Print summary
print_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Validation Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✓ All checks passed - system is ready${NC}"
        return 0
    elif [ $ERRORS -eq 0 ]; then
        echo -e "${YELLOW}⚠ Validation passed with $WARNINGS warning(s)${NC}"
        echo ""
        echo "Review warnings above before starting the system"
        return 0
    else
        echo -e "${RED}✗ Validation failed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
        echo ""
        echo "Fix the errors above before starting the system"

        if ! $FIX_MODE; then
            echo ""
            echo "Try running with --fix to auto-fix some issues:"
            echo "  $0 --fix"
        fi

        return 1
    fi
}

# Main execution
main() {
    print_header

    validate_docker
    validate_python
    validate_docker_compose
    validate_service_configs
    validate_database_config
    validate_risk_settings
    validate_api_keys
    validate_notifications
    validate_ports

    print_summary
    exit_code=$?

    echo ""
    exit $exit_code
}

# Run main function
main
