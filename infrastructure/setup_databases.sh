#!/bin/bash
# Database Setup Script for Crypto Trading Bot
# Run as: sudo bash infrastructure/setup_databases.sh

echo "=========================================="
echo "Crypto Trading Bot - Database Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run with sudo"
    echo "Usage: sudo bash infrastructure/setup_databases.sh"
    exit 1
fi

echo "Step 1: Creating database user and databases..."
sudo -u postgres psql << 'EOF'
-- Create application user
CREATE USER cryptobot WITH PASSWORD 'cryptobot2024';

-- Create databases
CREATE DATABASE cryptobot OWNER cryptobot;
CREATE DATABASE market_data OWNER cryptobot;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE cryptobot TO cryptobot;
GRANT ALL PRIVILEGES ON DATABASE market_data TO cryptobot;

-- Display created databases
\l cryptobot
\l market_data

-- Exit
\q
EOF

if [ $? -eq 0 ]; then
    echo "✅ Database user and databases created successfully"
else
    echo "❌ Error creating databases"
    exit 1
fi

echo ""
echo "Step 2: Enabling TimescaleDB extension on market_data database..."
sudo -u postgres psql -d market_data << 'EOF'
-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Verify extension
\dx timescaledb

-- Exit
\q
EOF

if [ $? -eq 0 ]; then
    echo "✅ TimescaleDB extension enabled successfully"
else
    echo "⚠️  TimescaleDB extension may not be installed. This is optional but recommended."
fi

echo ""
echo "Step 3: Testing database connections..."

# Test connection to cryptobot database
sudo -u postgres psql -d cryptobot -c "SELECT version();" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Connection to 'cryptobot' database successful"
else
    echo "❌ Failed to connect to 'cryptobot' database"
fi

# Test connection to market_data database
sudo -u postgres psql -d market_data -c "SELECT version();" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Connection to 'market_data' database successful"
else
    echo "❌ Failed to connect to 'market_data' database"
fi

echo ""
echo "=========================================="
echo "Database Setup Complete!"
echo "=========================================="
echo ""
echo "Database Credentials:"
echo "  User: cryptobot"
echo "  Password: cryptobot2024"
echo "  Databases: cryptobot, market_data"
echo "  Host: localhost"
echo "  Port: 5432"
echo ""
echo "Next Steps:"
echo "  1. Update service .env files with these credentials"
echo "  2. Restart Market Data service"
echo "  3. Verify all services are healthy"
echo ""
