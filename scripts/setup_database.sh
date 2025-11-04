#!/bin/bash
# Database Setup Script for Crypto Trading Bot
# Run with: sudo bash scripts/setup_database.sh

set -e  # Exit on error

echo "======================================"
echo "Crypto Trading Bot - Database Setup"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Creating PostgreSQL user 'cryptobot'${NC}"
sudo -u postgres psql <<EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'cryptobot') THEN
        CREATE USER cryptobot WITH PASSWORD 'cryptobot2024';
        RAISE NOTICE 'User cryptobot created';
    ELSE
        RAISE NOTICE 'User cryptobot already exists';
    END IF;
END
\$\$;

-- Grant necessary privileges
ALTER USER cryptobot CREATEDB;
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ PostgreSQL user created successfully${NC}"
else
    echo -e "${RED}❌ Failed to create user${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 2: Creating databases${NC}"
sudo -u postgres psql <<EOF
-- Create market_data database
SELECT 'CREATE DATABASE market_data OWNER cryptobot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'market_data')\gexec

-- Create cryptobot database (for application data)
SELECT 'CREATE DATABASE cryptobot OWNER cryptobot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cryptobot')\gexec

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE market_data TO cryptobot;
GRANT ALL PRIVILEGES ON DATABASE cryptobot TO cryptobot;
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Databases created successfully${NC}"
else
    echo -e "${RED}❌ Failed to create databases${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 3: Enabling TimescaleDB extension${NC}"
sudo -u postgres psql -d market_data <<EOF
-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ TimescaleDB extension enabled${NC}"
else
    echo -e "${YELLOW}⚠️  TimescaleDB extension not available (optional)${NC}"
fi

echo ""
echo -e "${YELLOW}Step 4: Creating database schema${NC}"

# Run the TimescaleDB initialization script
if [ -f "/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/scripts/init-timescale.sql" ]; then
    sudo -u postgres psql -d market_data -f /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/scripts/init-timescale.sql
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Database schema created successfully${NC}"
    else
        echo -e "${RED}❌ Failed to create schema${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  Schema file not found, skipping${NC}"
fi

echo ""
echo -e "${YELLOW}Step 5: Creating klines table (simplified for services)${NC}"
sudo -u postgres psql -d market_data <<EOF
-- Create klines table that services expect
CREATE TABLE IF NOT EXISTS klines (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    timestamp BIGINT NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    quote_volume DECIMAL(20, 8),
    trades_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, interval, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_klines_symbol_timestamp ON klines(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_klines_interval ON klines(interval, timestamp DESC);

-- Grant permissions to cryptobot user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cryptobot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cryptobot;
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Klines table created successfully${NC}"
else
    echo -e "${RED}❌ Failed to create klines table${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 6: Testing database connection${NC}"
sudo -u postgres psql -d market_data -c "SELECT COUNT(*) FROM klines;" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Database connection test passed${NC}"
else
    echo -e "${RED}❌ Database connection test failed${NC}"
    exit 1
fi

echo ""
echo "======================================"
echo -e "${GREEN}✅ Database Setup Complete!${NC}"
echo "======================================"
echo ""
echo "Database Credentials:"
echo "  User: cryptobot"
echo "  Password: cryptobot2024"
echo "  Databases: market_data, cryptobot"
echo ""
echo "You can now test the connection:"
echo "  psql -h localhost -U cryptobot -d market_data"
echo ""
echo "Next steps:"
echo "  1. Restart services (they will auto-connect)"
echo "  2. Collect market data"
echo "  3. Start trading bot"
echo ""
