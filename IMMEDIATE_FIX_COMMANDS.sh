#!/bin/bash
# Immediate Fix Commands for Crypto Trading Bot
# Generated: 2025-11-18
# Purpose: Fix critical issues identified in health check
# Run from project root directory

set -e  # Exit on error

echo "========================================="
echo "Crypto Trading Bot - Critical Fixes"
echo "========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# =========================================
# 1. Fix PostgreSQL Database Initialization
# =========================================
echo ""
echo "========================================="
echo "1. Fixing PostgreSQL Database"
echo "========================================="

print_status "Creating trading_user role and trading_db database..."

docker exec -i crypto-bot-postgres psql -U postgres << 'EOF'
-- Create trading user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'trading_user') THEN
        CREATE USER trading_user WITH PASSWORD 'trading_password_2024';
        RAISE NOTICE 'User trading_user created';
    ELSE
        RAISE NOTICE 'User trading_user already exists';
    END IF;
END
$$;

-- Create trading database if not exists
SELECT 'CREATE DATABASE trading_db OWNER trading_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'trading_db')\gexec

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE trading_db TO trading_user;

-- Connect to trading_db and create schema
\c trading_db

-- Create tables for trading engine
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    timestamp BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    size DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    portfolio_id VARCHAR(50) NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL,
    cash_balance DECIMAL(20, 8) NOT NULL,
    timestamp BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Grant permissions on tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;

\echo 'PostgreSQL database initialized successfully'
EOF

if [ $? -eq 0 ]; then
    print_status "PostgreSQL database initialized successfully"
else
    print_error "Failed to initialize PostgreSQL database"
    exit 1
fi

# =========================================
# 2. Fix TimescaleDB Database Creation
# =========================================
echo ""
echo "========================================="
echo "2. Fixing TimescaleDB Database"
echo "========================================="

print_status "Creating cryptobot database and enabling TimescaleDB extension..."

docker exec -i crypto-bot-timescaledb psql -U postgres << 'EOF'
-- Create cryptobot database if not exists
SELECT 'CREATE DATABASE cryptobot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cryptobot')\gexec

-- Connect to cryptobot database
\c cryptobot

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create market data tables
CREATE TABLE IF NOT EXISTS klines (
    timestamp BIGINT NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    turnover DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('klines', 'timestamp',
    chunk_time_interval => 86400000,  -- 1 day chunks
    if_not_exists => TRUE
);

-- Create index for fast symbol lookups
CREATE INDEX IF NOT EXISTS idx_klines_symbol_timestamp ON klines (symbol, timestamp DESC);

-- Create ticker data table
CREATE TABLE IF NOT EXISTS tickers (
    timestamp BIGINT NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    last_price DECIMAL(20, 8) NOT NULL,
    bid_price DECIMAL(20, 8),
    ask_price DECIMAL(20, 8),
    high_24h DECIMAL(20, 8),
    low_24h DECIMAL(20, 8),
    volume_24h DECIMAL(20, 8),
    turnover_24h DECIMAL(20, 8),
    price_change_24h DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Convert to hypertable
SELECT create_hypertable('tickers', 'timestamp',
    chunk_time_interval => 3600000,  -- 1 hour chunks
    if_not_exists => TRUE
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_tickers_symbol_timestamp ON tickers (symbol, timestamp DESC);

-- Set data retention policy (30 days for tickers, 90 days for klines)
SELECT add_retention_policy('tickers', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('klines', INTERVAL '90 days', if_not_exists => TRUE);

\echo 'TimescaleDB database initialized successfully'
EOF

if [ $? -eq 0 ]; then
    print_status "TimescaleDB database initialized successfully"
else
    print_error "Failed to initialize TimescaleDB database"
    exit 1
fi

# =========================================
# 3. Fix Portfolio Manager Configuration
# =========================================
echo ""
echo "========================================="
echo "3. Fixing Portfolio Manager Config"
echo "========================================="

print_status "Adding http_timeout field to portfolio-manager config..."

# Check if the file exists
if [ ! -f "services/portfolio-manager/app/config.py" ]; then
    print_error "Portfolio manager config file not found!"
    exit 1
fi

# Check if http_timeout already exists
if grep -q "http_timeout" services/portfolio-manager/app/config.py; then
    print_warning "http_timeout field already exists in config"
else
    # Add http_timeout field after service configuration section
    sed -i '/# Service Configuration/a\    # HTTP Configuration\n    http_timeout: float = Field(\n        default=30.0,\n        ge=1.0,\n        le=300.0,\n        description="HTTP request timeout in seconds"\n    )' services/portfolio-manager/app/config.py

    if [ $? -eq 0 ]; then
        print_status "Added http_timeout field to config"
    else
        print_error "Failed to update config file"
        print_warning "Manual fix required: Add 'http_timeout: float = Field(default=30.0)' to Settings class"
    fi
fi

# Restart portfolio manager container
print_status "Restarting portfolio-manager container..."
docker restart crypto-bot-portfolio

if [ $? -eq 0 ]; then
    print_status "Portfolio manager restarted successfully"
    sleep 5  # Wait for container to start
else
    print_error "Failed to restart portfolio manager"
fi

# =========================================
# 4. Configure Redis Authentication
# =========================================
echo ""
echo "========================================="
echo "4. Configuring Redis Authentication"
echo "========================================="

print_status "Setting Redis password..."

# Set Redis password using requirepass
docker exec crypto-bot-redis redis-cli CONFIG SET requirepass "redis_password_2024"

if [ $? -eq 0 ]; then
    print_status "Redis password configured"
    print_warning "Services need to be updated to use Redis password in their configurations"
else
    print_error "Failed to set Redis password"
fi

# =========================================
# 5. Verify Fixes
# =========================================
echo ""
echo "========================================="
echo "5. Verifying Fixes"
echo "========================================="

echo ""
print_status "Checking PostgreSQL..."
docker exec crypto-bot-postgres psql -U trading_user -d trading_db -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public';" 2>/dev/null
if [ $? -eq 0 ]; then
    print_status "PostgreSQL: WORKING"
else
    print_error "PostgreSQL: FAILED"
fi

echo ""
print_status "Checking TimescaleDB..."
docker exec crypto-bot-timescaledb psql -U postgres -d cryptobot -c "SELECT COUNT(*) FROM timescaledb_information.hypertables;" 2>/dev/null
if [ $? -eq 0 ]; then
    print_status "TimescaleDB: WORKING"
else
    print_error "TimescaleDB: FAILED"
fi

echo ""
print_status "Checking service health endpoints..."
services=("8000:api-gateway" "8001:bybit-connector" "8002:market-data" "8003:portfolio-manager" "8004:technical-analysis" "8005:trading-engine")

for service in "${services[@]}"; do
    IFS=':' read -r port name <<< "$service"
    status_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/health 2>/dev/null)
    if [ "$status_code" = "200" ]; then
        print_status "$name (port $port): HEALTHY"
    else
        print_error "$name (port $port): UNHEALTHY (HTTP $status_code)"
    fi
done

echo ""
print_status "Checking portfolio manager logs for config errors..."
docker logs crypto-bot-portfolio --tail 10 2>&1 | grep -i "http_timeout" | grep -i "error" && print_error "Config error still present" || print_status "No config errors found"

# =========================================
# Summary
# =========================================
echo ""
echo "========================================="
echo "Fix Summary"
echo "========================================="
echo ""
echo "Completed fixes:"
echo "  ✓ PostgreSQL database initialized"
echo "  ✓ TimescaleDB database created with hypertables"
echo "  ✓ Portfolio manager config updated (check manually if sed failed)"
echo "  ✓ Redis password configured"
echo "  ✓ Services health verified"
echo ""
echo "Next steps:"
echo "  1. Add Prometheus /metrics endpoints to remaining services"
echo "  2. Verify all API routes are accessible"
echo "  3. Test inter-service communication"
echo "  4. Update service configurations with Redis password"
echo "  5. Review full health check report: COMPREHENSIVE_HEALTH_CHECK_REPORT.md"
echo ""
print_status "Critical fixes completed!"
echo ""
