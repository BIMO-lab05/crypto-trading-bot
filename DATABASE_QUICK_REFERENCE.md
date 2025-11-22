# Database Quick Reference Card

## Database Credentials

### PostgreSQL (Application DB)
```bash
Host: localhost:5432
Database: cryptobot
User: cryptobot
Password: cryptobot_dev_password
Connection String: postgresql://cryptobot:cryptobot_dev_password@localhost:5432/cryptobot
```

### TimescaleDB (Market Data)
```bash
Host: localhost:5433
Database: market_data
User: cryptobot
Password: timescale_dev_password
Connection String: postgresql://cryptobot:timescale_dev_password@localhost:5433/market_data
```

### Redis (Cache)
```bash
Host: localhost:6379
Password: redis_dev_password
Connection String: redis://:redis_dev_password@localhost:6379/0
```

### RabbitMQ (Message Broker)
```bash
Host: localhost:5672
User: cryptobot
Password: rabbitmq_dev_password
Management UI: http://localhost:15672
AMQP URL: amqp://cryptobot:rabbitmq_dev_password@localhost:5672/cryptobot
```

## Quick Commands

### Database Access
```bash
# PostgreSQL
docker exec -it crypto-bot-postgres psql -U cryptobot -d cryptobot

# TimescaleDB
docker exec -it crypto-bot-timescaledb psql -U cryptobot -d market_data

# Redis
docker exec -it crypto-bot-redis redis-cli

# RabbitMQ
docker exec -it crypto-bot-rabbitmq rabbitmqctl status
```

### Data Queries
```sql
-- PostgreSQL: View strategies
SELECT * FROM trading_engine.strategies;

-- PostgreSQL: View trades
SELECT * FROM trading_engine.trades ORDER BY created_at DESC LIMIT 10;

-- TimescaleDB: Market data summary
SELECT symbol, COUNT(*) as candles,
       MIN(time) as earliest, MAX(time) as latest
FROM market_data.candles
GROUP BY symbol;

-- TimescaleDB: Latest prices
SELECT symbol, close as price, time
FROM market_data.candles
WHERE time = (SELECT MAX(time) FROM market_data.candles)
ORDER BY symbol;
```

### Health Checks
```bash
# All databases
bash scripts/verify_databases.sh

# Individual checks
docker exec crypto-bot-postgres pg_isready -U cryptobot
docker exec crypto-bot-timescaledb pg_isready -U cryptobot
docker exec crypto-bot-redis redis-cli ping
docker exec crypto-bot-rabbitmq rabbitmq-diagnostics ping
```

### Data Collection
```bash
# Manual population (if needed)
python3 scripts/populate_database.py

# Verify data exists
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
  -c "SELECT COUNT(*) FROM market_data.candles;"

# Check scheduler status
curl http://localhost:8002/api/v1/scheduler/status | jq
```

### Backup & Restore
```bash
# Backup PostgreSQL
docker exec crypto-bot-postgres pg_dump -U cryptobot cryptobot > backup_postgres.sql

# Backup TimescaleDB
docker exec crypto-bot-timescaledb pg_dump -U cryptobot market_data > backup_timescale.sql

# Restore PostgreSQL
docker exec -i crypto-bot-postgres psql -U cryptobot cryptobot < backup_postgres.sql

# Restore TimescaleDB
docker exec -i crypto-bot-timescaledb psql -U cryptobot market_data < backup_timescale.sql
```

### Monitoring
```bash
# Database sizes
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
  -c "SELECT pg_size_pretty(pg_database_size('market_data'));"

# Active connections
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
  -c "SELECT count(*) FROM pg_stat_activity;"

# Recent queries (TimescaleDB)
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
  -c "SELECT query, calls, total_time FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

## File Locations

### Configuration Files
```
/mnt/d/Bimo_max/crypto-trading-bot/
├── .env                                  # Root environment variables
├── infrastructure/
│   ├── docker-compose.yml               # Database containers
│   ├── scripts/
│   │   ├── init-db.sql                 # PostgreSQL initialization
│   │   └── init-timescale.sql          # TimescaleDB initialization
│   └── config/
│       ├── postgresql.conf             # PostgreSQL config
│       └── redis.conf                  # Redis config
└── services/
    ├── market-data-service/.env        # Market data service env
    └── bybit-connector/.env            # Bybit connector env
```

### Database Scripts
```
/mnt/d/Bimo_max/crypto-trading-bot/scripts/
├── populate_database.py                # Initial data population
├── collect_btc_eth.py                  # BTC/ETH collection
└── verify_databases.sh                 # Health verification
```

### Documentation
```
/mnt/d/Bimo_max/crypto-trading-bot/
├── DATABASE_INITIALIZATION_COMPLETE.md # Full initialization report
├── DATABASE_STATUS_SUMMARY.txt         # Quick status overview
└── DATABASE_QUICK_REFERENCE.md         # This file
```

## Troubleshooting

### Database Not Responding
```bash
# Check container status
docker ps -a | grep crypto-bot

# Restart database
docker restart crypto-bot-postgres
docker restart crypto-bot-timescaledb

# Check logs
docker logs crypto-bot-postgres --tail 100
docker logs crypto-bot-timescaledb --tail 100
```

### Empty Database
```bash
# Re-run initialization
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
  -f /docker-entrypoint-initdb.d/init.sql

# Collect data
python3 scripts/populate_database.py
```

### Rate Limit Errors
```bash
# Check bybit connector logs
docker logs crypto-bot-bybit --tail 50 | grep 429

# Adjust rate limit in .env
# Edit: services/bybit-connector/.env
# Change: RATE_LIMIT_REQUESTS_PER_SECOND

# Restart service
docker restart crypto-bot-bybit crypto-bot-market-data
```

### Schema Errors
```bash
# Drop and recreate tables (⚠️ WARNING: Data loss!)
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
  -c "DROP TABLE IF EXISTS market_data.candles CASCADE;"

# Re-run init script
docker restart crypto-bot-timescaledb
```

## Performance Tuning

### PostgreSQL
```sql
-- Enable parallel queries
SET max_parallel_workers_per_gather = 4;

-- Adjust memory settings
SET shared_buffers = '256MB';
SET effective_cache_size = '1GB';
```

### TimescaleDB
```sql
-- Manually trigger compression
SELECT compress_chunk(i) FROM show_chunks('market_data.candles') i;

-- Refresh continuous aggregates
CALL refresh_continuous_aggregate('market_data.candles_1h', NULL, NULL);

-- Drop old chunks
SELECT drop_chunks('market_data.ticks', INTERVAL '90 days');
```

### Redis
```bash
# Clear cache
docker exec crypto-bot-redis redis-cli FLUSHDB

# Check memory usage
docker exec crypto-bot-redis redis-cli INFO memory

# Set max memory
docker exec crypto-bot-redis redis-cli CONFIG SET maxmemory 512mb
```

## Support

### Logs
```bash
# Tail all database logs
docker logs -f crypto-bot-postgres
docker logs -f crypto-bot-timescaledb
docker logs -f crypto-bot-redis
docker logs -f crypto-bot-rabbitmq
```

### Get Help
- Full Report: `DATABASE_INITIALIZATION_COMPLETE.md`
- Verification: `bash scripts/verify_databases.sh`
- Architecture: `SYSTEM_ARCHITECTURE.md`
- Troubleshooting: `docs/development/TROUBLESHOOTING.md`

---

**Last Updated:** 2025-11-19 18:47 UTC
**Status:** All databases operational with 5,040 candles loaded
