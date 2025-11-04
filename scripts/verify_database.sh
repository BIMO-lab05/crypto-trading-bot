#!/bin/bash
# Database Verification Script
# Run after database setup to verify everything works

echo "=========================================="
echo "Database Verification"
echo "=========================================="
echo ""

# Test connection
echo "Testing database connection..."
if psql -h localhost -U cryptobot -d market_data -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✅ Database connection successful"
else
    echo "❌ Database connection failed"
    echo "Please run: sudo bash scripts/setup_database.sh"
    exit 1
fi

# Check tables exist
echo ""
echo "Checking tables..."
TABLES=$(psql -h localhost -U cryptobot -d market_data -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'klines';")
if [ "$TABLES" -eq "1" ]; then
    echo "✅ Klines table exists"
else
    echo "❌ Klines table missing"
    exit 1
fi

# Check klines count
echo ""
echo "Checking data..."
COUNT=$(psql -h localhost -U cryptobot -d market_data -t -c "SELECT COUNT(*) FROM klines;")
echo "Klines in database: $COUNT"

if [ "$COUNT" -gt "0" ]; then
    echo "✅ Data exists"
    psql -h localhost -U cryptobot -d market_data -c "SELECT symbol, COUNT(*) as count FROM klines GROUP BY symbol;"
else
    echo "⚠️  No data yet (run data collection)"
fi

echo ""
echo "=========================================="
echo "✅ Database verification complete!"
echo "=========================================="
