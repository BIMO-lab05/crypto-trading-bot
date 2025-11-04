# Database Setup Guide
# Complete PostgreSQL + TimescaleDB Installation and Configuration

## Overview
This guide provides step-by-step instructions for setting up the database infrastructure for the Crypto Trading Bot.

## Prerequisites
- Ubuntu/Debian-based Linux system (or WSL2)
- Sudo access
- At least 2GB free disk space

## Architecture
```
┌─────────────────────────────────────────┐
│     Database Infrastructure             │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────┐  ┌───────────────┐  │
│  │ PostgreSQL   │  │  TimescaleDB  │  │
│  │   (5432)     │  │    (5433)     │  │
│  ├──────────────┤  ├───────────────┤  │
│  │ App Data     │  │ Market Data   │  │
│  │ - Trades     │  │ - OHLCV       │  │
│  │ - Portfolio  │  │ - Orderbook   │  │
│  │ - Users      │  │ - Tickers     │  │
│  └──────────────┘  └───────────────┘  │
│                                         │
│  ┌──────────────┐                      │
│  │   Redis      │                      │
│  │   (6379)     │                      │
│  ├──────────────┤                      │
│  │ Cache        │                      │
│  │ - Prices     │                      │
│  │ - Signals    │                      │
│  └──────────────┘                      │
└─────────────────────────────────────────┘
```

## Installation Steps

### Step 1: Install PostgreSQL

```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
psql --version
```

### Step 2: Install TimescaleDB

```bash
# Add TimescaleDB repository
sudo sh -c "echo 'deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main' > /etc/apt/sources.list.d/timescaledb.list"

# Import GPG key
wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | sudo apt-key add -

# Update and install
sudo apt update
sudo apt install -y timescaledb-2-postgresql-14

# Configure TimescaleDB
sudo timescaledb-tune --quiet --yes

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Step 3: Install Redis

```bash
# Install Redis
sudo apt install -y redis-server

# Start Redis service
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify installation
redis-cli ping
# Should return: PONG
```

### Step 4: Create Database Users and Databases

```bash
# Switch to postgres user
sudo -u postgres psql << 'EOF'

-- Create application user
CREATE USER cryptobot WITH PASSWORD 'change_this_secure_password';

-- Create databases
CREATE DATABASE cryptobot OWNER cryptobot;
CREATE DATABASE market_data OWNER cryptobot;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE cryptobot TO cryptobot;
GRANT ALL PRIVILEGES ON DATABASE market_data TO cryptobot;

-- Enable TimescaleDB extension on market_data database
\c market_data
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Exit
\q
EOF
```

### Step 5: Configure PostgreSQL for Remote Access (Optional)

```bash
# Edit postgresql.conf
sudo nano /etc/postgresql/14/main/postgresql.conf

# Find and modify:
listen_addresses = 'localhost'  # or '*' for all interfaces

# Edit pg_hba.conf
sudo nano /etc/postgresql/14/main/pg_hba.conf

# Add line:
host    all             cryptobot       127.0.0.1/32            md5

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Step 6: Run Database Migrations

```bash
# Navigate to project directory
cd /mnt/d/Bimo_max/crypto-trading-bot

# Run migration scripts
psql -U cryptobot -d cryptobot -f infrastructure/migrations/001_initial_schema.sql
psql -U cryptobot -d market_data -f infrastructure/migrations/002_timescale_schema.sql
```

## Database Schemas

### Application Database (cryptobot)

```sql
-- Users table
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    api_key VARCHAR(255),
    api_secret VARCHAR(255) ENCRYPTED,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Portfolios table
CREATE TABLE portfolios (
    portfolio_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id),
    name VARCHAR(100) NOT NULL,
    initial_balance DECIMAL(20, 8) NOT NULL,
    current_balance DECIMAL(20, 8) NOT NULL,
    total_pnl DECIMAL(20, 8) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Trades table
CREATE TABLE trades (
    trade_id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(portfolio_id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'BUY' or 'SELL'
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) DEFAULT 0,
    realized_pnl DECIMAL(20, 8),
    strategy VARCHAR(50),
    signal_confidence DECIMAL(5, 4),
    executed_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_portfolio_symbol (portfolio_id, symbol),
    INDEX idx_executed_at (executed_at)
);

-- Positions table
CREATE TABLE positions (
    position_id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(portfolio_id),
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    average_entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 8),
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    opened_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    UNIQUE (portfolio_id, symbol)
);

-- Performance metrics table
CREATE TABLE performance_metrics (
    metric_id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(portfolio_id),
    date DATE NOT NULL,
    total_return DECIMAL(10, 4),
    daily_return DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    sortino_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),
    win_rate DECIMAL(5, 2),
    profit_factor DECIMAL(10, 4),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (portfolio_id, date)
);
```

### Market Data Database (market_data)

```sql
-- OHLCV data (candlesticks)
CREATE TABLE ohlcv (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    interval VARCHAR(10) NOT NULL,  -- '1m', '5m', '15m', '1h', '4h', '1d'
    PRIMARY KEY (time, symbol, interval)
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('ohlcv', 'time');

-- Create indexes
CREATE INDEX idx_ohlcv_symbol_time ON ohlcv (symbol, time DESC);
CREATE INDEX idx_ohlcv_interval ON ohlcv (interval);

-- Ticker data
CREATE TABLE tickers (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    last_price DECIMAL(20, 8) NOT NULL,
    bid_price DECIMAL(20, 8),
    ask_price DECIMAL(20, 8),
    high_24h DECIMAL(20, 8),
    low_24h DECIMAL(20, 8),
    volume_24h DECIMAL(20, 8),
    price_change_24h DECIMAL(10, 4),
    PRIMARY KEY (time, symbol)
);

SELECT create_hypertable('tickers', 'time');
CREATE INDEX idx_tickers_symbol_time ON tickers (symbol, time DESC);

-- Order book snapshots
CREATE TABLE orderbook_snapshots (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    bids JSONB NOT NULL,  -- Array of [price, quantity]
    asks JSONB NOT NULL,
    PRIMARY KEY (time, symbol)
);

SELECT create_hypertable('orderbook_snapshots', 'time');

-- Technical indicators cache
CREATE TABLE technical_indicators (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    value DECIMAL(20, 8),
    metadata JSONB,
    PRIMARY KEY (time, symbol, interval, indicator_name)
);

SELECT create_hypertable('technical_indicators', 'time');

-- Trading signals
CREATE TABLE trading_signals (
    signal_id SERIAL,
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    signal_type VARCHAR(20) NOT NULL,  -- 'BUY', 'SELL', 'HOLD'
    confidence DECIMAL(5, 4) NOT NULL,
    indicators_used JSONB,
    price_at_signal DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (signal_id, time)
);

SELECT create_hypertable('trading_signals', 'time');
CREATE INDEX idx_signals_symbol_time ON trading_signals (symbol, time DESC);
```

## Data Retention Policies

```sql
-- Keep OHLCV data for 1 year for 1m interval
SELECT add_retention_policy('ohlcv', INTERVAL '365 days',
    if_not_exists => true,
    cascade_to_materializations => true);

-- Keep ticker data for 30 days
SELECT add_retention_policy('tickers', INTERVAL '30 days');

-- Keep orderbook snapshots for 7 days
SELECT add_retention_policy('orderbook_snapshots', INTERVAL '7 days');

-- Keep signals for 90 days
SELECT add_retention_policy('trading_signals', INTERVAL '90 days');
```

## Continuous Aggregates for Performance

```sql
-- Hourly OHLCV aggregates
CREATE MATERIALIZED VIEW ohlcv_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    symbol,
    FIRST(open, time) as open,
    MAX(high) as high,
    MIN(low) as low,
    LAST(close, time) as close,
    SUM(volume) as volume
FROM ohlcv
WHERE interval = '1m'
GROUP BY bucket, symbol;

-- Daily OHLCV aggregates
CREATE MATERIALIZED VIEW ohlcv_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    symbol,
    FIRST(open, time) as open,
    MAX(high) as high,
    MIN(low) as low,
    LAST(close, time) as close,
    SUM(volume) as volume
FROM ohlcv
WHERE interval = '1h'
GROUP BY bucket, symbol;
```

## Backup and Recovery

### Automated Backups

```bash
# Create backup script
cat > /usr/local/bin/backup-crypto-db.sh << 'EOF'
#!/bin/bash
# Backup script for crypto trading bot databases

BACKUP_DIR="/var/backups/crypto-bot"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup application database
pg_dump -U cryptobot cryptobot | gzip > $BACKUP_DIR/cryptobot_$DATE.sql.gz

# Backup market data database
pg_dump -U cryptobot market_data | gzip > $BACKUP_DIR/market_data_$DATE.sql.gz

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /usr/local/bin/backup-crypto-db.sh

# Add to crontab (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/backup-crypto-db.sh") | crontab -
```

### Restore from Backup

```bash
# Restore application database
gunzip -c /var/backups/crypto-bot/cryptobot_YYYYMMDD_HHMMSS.sql.gz | psql -U cryptobot cryptobot

# Restore market data database
gunzip -c /var/backups/crypto-bot/market_data_YYYYMMDD_HHMMSS.sql.gz | psql -U cryptobot market_data
```

## Environment Configuration

Create `.env` file in each service directory:

```bash
# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=cryptobot
POSTGRES_PASSWORD=change_this_secure_password
POSTGRES_DB=cryptobot

# TimescaleDB Configuration (Market Data)
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_USER=cryptobot
TIMESCALE_PASSWORD=change_this_secure_password
TIMESCALE_DB=market_data

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

## Monitoring and Maintenance

### Check Database Sizes

```sql
-- Check database sizes
SELECT
    pg_database.datname,
    pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database
ORDER BY pg_database_size(pg_database.datname) DESC;

-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;
```

### Vacuum and Analyze

```bash
# Create maintenance script
cat > /usr/local/bin/maintain-crypto-db.sh << 'EOF'
#!/bin/bash
# Maintenance script for crypto trading bot databases

# Vacuum and analyze
psql -U cryptobot -d cryptobot -c "VACUUM ANALYZE;"
psql -U cryptobot -d market_data -c "VACUUM ANALYZE;"

echo "Database maintenance completed"
EOF

chmod +x /usr/local/bin/maintain-crypto-db.sh

# Run weekly
(crontab -l 2>/dev/null; echo "0 3 * * 0 /usr/local/bin/maintain-crypto-db.sh") | crontab -
```

## Security Considerations

1. **Change Default Passwords**: Update all passwords in configuration files
2. **Enable SSL**: Configure PostgreSQL to use SSL connections
3. **Firewall Rules**: Restrict database access to localhost or specific IPs
4. **Regular Updates**: Keep PostgreSQL and TimescaleDB updated
5. **Audit Logging**: Enable audit logging for sensitive operations

## Troubleshooting

### Connection Issues

```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Check if port is listening
sudo netstat -tulpn | grep 5432

# Test connection
psql -U cryptobot -h localhost -d cryptobot
```

### Performance Issues

```sql
-- Check slow queries
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Check index usage
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 20;
```

## Next Steps

After completing the database setup:

1. Update service `.env` files with database credentials
2. Run database migrations
3. Restart all services
4. Verify connectivity with health checks
5. Start collecting market data

## Quick Start Commands

```bash
# Install everything
sudo bash infrastructure/install-databases.sh

# Create databases
sudo bash infrastructure/create-databases.sh

# Run migrations
bash infrastructure/run-migrations.sh

# Start services
bash scripts/start-all-services.sh
```

---

**Note**: This setup is for development/testing. For production deployment, consider:
- High availability setup with replication
- Connection pooling (PgBouncer)
- Monitoring (Prometheus + Grafana)
- Encrypted backups
- Dedicated database server
