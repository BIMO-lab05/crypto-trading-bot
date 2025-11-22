#!/bin/bash
# Database Connection Fix Script
# Purpose: Setup or fix PostgreSQL connection for trading engine

echo "🔧 Trading Engine Database Setup"
echo "=================================="
echo ""

# Check if PostgreSQL is running
echo "1. Checking PostgreSQL status..."
if systemctl is-active --quiet postgresql; then
    echo "   ✅ PostgreSQL service is running"
else
    echo "   ❌ PostgreSQL service is not running"
    echo "   Starting PostgreSQL..."
    sudo systemctl start postgresql
fi

echo ""
echo "2. Database Setup Options:"
echo "   a) Create new database user 'cryptobot'"
echo "   b) Use existing PostgreSQL user"
echo "   c) Skip database (continue in-memory mode)"
echo ""
read -p "Choose option (a/b/c): " choice

case $choice in
    a)
        echo ""
        echo "Creating database user and database..."
        echo "You'll need PostgreSQL superuser access (usually 'postgres' user)"
        echo ""

        # Create user and database
        sudo -u postgres psql << EOF
-- Create user if not exists
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'cryptobot') THEN
      CREATE USER cryptobot WITH PASSWORD 'cryptobot_secure_2024';
   END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE cryptobot OWNER cryptobot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cryptobot')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE cryptobot TO cryptobot;

-- Connect and create schema
\c cryptobot
CREATE SCHEMA IF NOT EXISTS trading AUTHORIZATION cryptobot;
ALTER USER cryptobot SET search_path TO trading,public;

\q
EOF

        if [ $? -eq 0 ]; then
            echo ""
            echo "✅ Database setup complete!"
            echo ""
            echo "Testing connection..."
            PGPASSWORD=cryptobot_secure_2024 psql -h localhost -p 5432 -U cryptobot -d cryptobot -c "SELECT 1;" > /dev/null 2>&1

            if [ $? -eq 0 ]; then
                echo "✅ Database connection successful!"
                echo ""
                echo "Next step: Run database migrations"
                echo "   cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/migrations"
                echo "   PGPASSWORD=cryptobot_secure_2024 psql -h localhost -U cryptobot -d cryptobot -f 001_initial_schema.sql"
            else
                echo "❌ Connection test failed"
                echo "Check password and user permissions"
            fi
        else
            echo "❌ Database setup failed"
        fi
        ;;

    b)
        echo ""
        read -p "Enter PostgreSQL username: " db_user
        read -sp "Enter PostgreSQL password: " db_pass
        echo ""
        read -p "Enter database name (or press Enter for 'cryptobot'): " db_name
        db_name=${db_name:-cryptobot}

        echo ""
        echo "Testing connection..."
        PGPASSWORD=$db_pass psql -h localhost -p 5432 -U $db_user -d $db_name -c "SELECT 1;" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✅ Connection successful!"
            echo ""
            echo "Update your .env file with these values:"
            echo "   DB_HOST=localhost"
            echo "   DB_PORT=5432"
            echo "   DB_NAME=$db_name"
            echo "   DB_USER=$db_user"
            echo "   DB_PASSWORD=$db_pass"
        else
            echo "❌ Connection failed"
            echo "Check username, password, and database name"
        fi
        ;;

    c)
        echo ""
        echo "✅ Continuing in in-memory mode"
        echo ""
        echo "Your system will work but trades won't be persisted."
        echo "This is perfect for testing and monitoring!"
        echo ""
        echo "To monitor signals:"
        echo "   python3 monitor_signals.py --symbol BTCUSDT --continuous"
        ;;

    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "=================================="
echo "Setup complete!"
