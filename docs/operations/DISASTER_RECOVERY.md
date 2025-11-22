# Disaster Recovery Procedures
**Crypto Trading Bot - DR Playbook**
**Version:** 1.0
**Last Updated:** 2025-11-16

---

## Table of Contents

1. [Overview](#overview)
2. [Backup Procedures](#backup-procedures)
3. [Recovery Procedures](#recovery-procedures)
4. [Failover Procedures](#failover-procedures)
5. [Emergency Contacts](#emergency-contacts)
6. [Testing Schedule](#testing-schedule)

---

## Overview

### Recovery Time Objective (RTO)
**Target:** 30 minutes maximum downtime

### Recovery Point Objective (RPO)
**Target:** 5 minutes maximum data loss

### Critical Systems Priority

| Priority | System | RTO | RPO |
|----------|--------|-----|-----|
| P1 | Trading Engine | 5 min | 1 min |
| P1 | Bybit Connector | 5 min | 1 min |
| P2 | Market Data Service | 15 min | 5 min |
| P2 | Portfolio Manager | 15 min | 5 min |
| P3 | Technical Analysis | 30 min | 15 min |
| P3 | Risk Metrics | 30 min | 15 min |

---

## Backup Procedures

### 1. Database Backups

#### PostgreSQL Backup (Automated)

**Schedule:** Every 6 hours + before each deployment

```bash
#!/bin/bash
# Location: scripts/backup/postgres_backup.sh

# Configuration
BACKUP_DIR="/backups/postgres"
RETENTION_DAYS=30
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="cryptobot"
DB_USER="cryptobot"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Create backup directory
mkdir -p ${BACKUP_DIR}

# Perform backup
pg_dump -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} -d ${DB_NAME} \
    -F c -b -v -f "${BACKUP_DIR}/cryptobot_${TIMESTAMP}.dump"

# Compress backup
gzip "${BACKUP_DIR}/cryptobot_${TIMESTAMP}.dump"

# Verify backup integrity
pg_restore --list "${BACKUP_DIR}/cryptobot_${TIMESTAMP}.dump.gz" > /dev/null
if [ $? -eq 0 ]; then
    echo "✅ Backup verified: cryptobot_${TIMESTAMP}.dump.gz"
else
    echo "❌ Backup verification failed!"
    exit 1
fi

# Upload to S3/Cloud Storage
aws s3 cp "${BACKUP_DIR}/cryptobot_${TIMESTAMP}.dump.gz" \
    s3://crypto-bot-backups/postgres/ \
    --storage-class STANDARD_IA

# Cleanup old backups (keep last 30 days)
find ${BACKUP_DIR} -name "cryptobot_*.dump.gz" -mtime +${RETENTION_DAYS} -delete

# Log backup
echo "$(date): Backup completed - cryptobot_${TIMESTAMP}.dump.gz" >> /var/log/backups.log
```

**Cron Schedule:**
```cron
0 */6 * * * /scripts/backup/postgres_backup.sh
```

#### TimescaleDB Backup (Market Data)

**Schedule:** Every 12 hours

```bash
#!/bin/bash
# Location: scripts/backup/timescale_backup.sh

BACKUP_DIR="/backups/timescale"
DB_NAME="market_data"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p ${BACKUP_DIR}

# Backup with compression
pg_dump -h localhost -p 5432 -U cryptobot -d ${DB_NAME} \
    -F c -Z 9 -f "${BACKUP_DIR}/market_data_${TIMESTAMP}.dump"

# Upload to cloud
aws s3 cp "${BACKUP_DIR}/market_data_${TIMESTAMP}.dump" \
    s3://crypto-bot-backups/timescale/

# Cleanup (keep last 7 days for market data)
find ${BACKUP_DIR} -name "market_data_*.dump" -mtime +7 -delete
```

### 2. Redis Backup

**Schedule:** Every hour + before deployments

```bash
#!/bin/bash
# Location: scripts/backup/redis_backup.sh

BACKUP_DIR="/backups/redis"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p ${BACKUP_DIR}

# Trigger BGSAVE
redis-cli BGSAVE

# Wait for save to complete
while [ $(redis-cli LASTSAVE) -eq $(redis-cli LASTSAVE) ]; do
    sleep 1
done

# Copy RDB file
cp /var/lib/redis/dump.rdb "${BACKUP_DIR}/dump_${TIMESTAMP}.rdb"

# Compress and upload
gzip "${BACKUP_DIR}/dump_${TIMESTAMP}.rdb"
aws s3 cp "${BACKUP_DIR}/dump_${TIMESTAMP}.rdb.gz" \
    s3://crypto-bot-backups/redis/

# Cleanup (keep last 24 backups)
ls -t ${BACKUP_DIR}/dump_*.rdb.gz | tail -n +25 | xargs rm -f
```

### 3. Configuration Backup

**Schedule:** On every change + daily

```bash
#!/bin/bash
# Location: scripts/backup/config_backup.sh

BACKUP_DIR="/backups/config"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
CONFIG_FILES=(
    "/etc/crypto-bot/*.conf"
    "/mnt/d/Bimo_max/crypto-trading-bot/.env"
    "/mnt/d/Bimo_max/crypto-trading-bot/services/*/.env"
    "/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/docker-compose.yml"
)

mkdir -p ${BACKUP_DIR}

# Create tarball
tar -czf "${BACKUP_DIR}/config_${TIMESTAMP}.tar.gz" ${CONFIG_FILES[@]}

# Upload to S3
aws s3 cp "${BACKUP_DIR}/config_${TIMESTAMP}.tar.gz" \
    s3://crypto-bot-backups/config/

# Keep last 90 days
find ${BACKUP_DIR} -name "config_*.tar.gz" -mtime +90 -delete
```

### 4. Trade History Archive

**Schedule:** Daily at 00:00 UTC

```bash
#!/bin/bash
# Location: scripts/backup/archive_trades.sh

ARCHIVE_DIR="/backups/archives/trades"
DAYS_TO_ARCHIVE=7
TIMESTAMP=$(date +"%Y%m%d")

mkdir -p ${ARCHIVE_DIR}

# Export trades older than 7 days to CSV
psql -h localhost -U cryptobot -d cryptobot -c \
    "COPY (SELECT * FROM trades WHERE created_at < NOW() - INTERVAL '${DAYS_TO_ARCHIVE} days')
     TO STDOUT WITH CSV HEADER" \
    > "${ARCHIVE_DIR}/trades_${TIMESTAMP}.csv"

# Compress
gzip "${ARCHIVE_DIR}/trades_${TIMESTAMP}.csv"

# Upload to cold storage
aws s3 cp "${ARCHIVE_DIR}/trades_${TIMESTAMP}.csv.gz" \
    s3://crypto-bot-backups/archives/trades/ \
    --storage-class GLACIER

# Archive to permanent storage
mv "${ARCHIVE_DIR}/trades_${TIMESTAMP}.csv.gz" \
    /archives/permanent/trades/

echo "Archived trades up to $(date -d "${DAYS_TO_ARCHIVE} days ago" +"%Y-%m-%d")"
```

---

## Recovery Procedures

### 1. Database Recovery

#### PostgreSQL Full Recovery

**Estimated Time:** 10-15 minutes

```bash
#!/bin/bash
# Location: scripts/recovery/restore_postgres.sh

# STOP TRADING FIRST!
docker-compose stop trading-engine

# Get latest backup
LATEST_BACKUP=$(aws s3 ls s3://crypto-bot-backups/postgres/ | sort | tail -n 1 | awk '{print $4}')

echo "Restoring from: ${LATEST_BACKUP}"

# Download backup
aws s3 cp "s3://crypto-bot-backups/postgres/${LATEST_BACKUP}" /tmp/

# Decompress
gunzip "/tmp/${LATEST_BACKUP}"

# Drop existing database (CAREFUL!)
read -p "WARNING: This will drop the existing database. Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled"
    exit 1
fi

# Drop and recreate database
psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS cryptobot;"
psql -h localhost -U postgres -c "CREATE DATABASE cryptobot OWNER cryptobot;"

# Restore from backup
pg_restore -h localhost -U cryptobot -d cryptobot -v \
    "/tmp/${LATEST_BACKUP%.gz}"

# Verify restoration
TRADE_COUNT=$(psql -h localhost -U cryptobot -d cryptobot -t -c "SELECT COUNT(*) FROM trades;")
echo "✅ Restored database with ${TRADE_COUNT} trades"

# Restart services
docker-compose start trading-engine

echo "✅ Database recovery complete"
```

#### Point-in-Time Recovery (PITR)

**Use Case:** Recover to specific timestamp before corruption

```bash
#!/bin/bash
# Location: scripts/recovery/pitr_postgres.sh

TARGET_TIME="2025-11-16 15:30:00"  # Set target recovery time

# Stop services
docker-compose stop

# Restore base backup
pg_restore -h localhost -U cryptobot -d cryptobot /backups/postgres/base.dump

# Replay WAL files up to target time
pg_wal_replay_wait_for_lsn \
    --dbname=cryptobot \
    --target-time="${TARGET_TIME}"

# Start services
docker-compose start

echo "✅ PITR recovery to ${TARGET_TIME} complete"
```

### 2. Redis Recovery

**Estimated Time:** 5 minutes

```bash
#!/bin/bash
# Location: scripts/recovery/restore_redis.sh

# Stop Redis
docker-compose stop redis

# Get latest backup
LATEST_BACKUP=$(aws s3 ls s3://crypto-bot-backups/redis/ | sort | tail -n 1 | awk '{print $4}')

# Download and decompress
aws s3 cp "s3://crypto-bot-backups/redis/${LATEST_BACKUP}" /tmp/
gunzip "/tmp/${LATEST_BACKUP}"

# Replace dump.rdb
cp "/tmp/${LATEST_BACKUP%.gz}" /var/lib/redis/dump.rdb
chown redis:redis /var/lib/redis/dump.rdb

# Start Redis
docker-compose start redis

# Verify
REDIS_KEYS=$(redis-cli DBSIZE)
echo "✅ Redis restored with ${REDIS_KEYS} keys"
```

### 3. Configuration Recovery

```bash
#!/bin/bash
# Location: scripts/recovery/restore_config.sh

# Get latest config backup
LATEST_CONFIG=$(aws s3 ls s3://crypto-bot-backups/config/ | sort | tail -n 1 | awk '{print $4}')

# Download
aws s3 cp "s3://crypto-bot-backups/config/${LATEST_CONFIG}" /tmp/

# Extract
tar -xzf "/tmp/${LATEST_CONFIG}" -C /

echo "✅ Configuration restored"
echo "⚠️  Review .env files and restart services"
```

### 4. Full System Recovery

**Complete disaster recovery from scratch**

**Estimated Time:** 30-45 minutes

```bash
#!/bin/bash
# Location: scripts/recovery/full_system_recovery.sh

echo "🚨 FULL SYSTEM RECOVERY INITIATED"
echo "================================="

# Step 1: Infrastructure
echo "Step 1/5: Setting up infrastructure..."
docker-compose -f infrastructure/docker-compose.yml up -d postgres redis rabbitmq
sleep 30

# Step 2: Restore databases
echo "Step 2/5: Restoring databases..."
./scripts/recovery/restore_postgres.sh
./scripts/recovery/restore_redis.sh

# Step 3: Restore configuration
echo "Step 3/5: Restoring configuration..."
./scripts/recovery/restore_config.sh

# Step 4: Start services in order
echo "Step 4/5: Starting services..."
docker-compose up -d bybit-connector
sleep 10
docker-compose up -d market-data-service
sleep 10
docker-compose up -d technical-analysis
sleep 10
docker-compose up -d portfolio-manager
sleep 10
docker-compose up -d trading-engine
sleep 10
docker-compose up -d api-gateway

# Step 5: Health checks
echo "Step 5/5: Verifying system health..."
for service in api-gateway trading-engine market-data-service; do
    HEALTH=$(curl -s http://localhost:8000/health | jq -r '.status')
    echo "${service}: ${HEALTH}"
done

echo "✅ FULL SYSTEM RECOVERY COMPLETE"
echo "⚠️  MANUAL VERIFICATION REQUIRED:"
echo "   1. Check all service health endpoints"
echo "   2. Verify database integrity"
echo "   3. Review recent trades for consistency"
echo "   4. Test one manual trade"
echo "   5. Re-enable automated trading ONLY after verification"
```

---

## Failover Procedures

### 1. Database Failover (PostgreSQL)

**Automatic Failover with Patroni**

```yaml
# patroni.yml
scope: crypto-bot-cluster
namespace: /service/
name: postgres-primary

restapi:
  listen: 0.0.0.0:8008
  connect_address: postgres-primary:8008

postgresql:
  listen: 0.0.0.0:5432
  connect_address: postgres-primary:5432
  data_dir: /var/lib/postgresql/data
  authentication:
    replication:
      username: replicator
      password: ${REPLICATION_PASSWORD}
    superuser:
      username: postgres
      password: ${POSTGRES_PASSWORD}

  parameters:
    wal_level: replica
    hot_standby: "on"
    max_wal_senders: 10
    max_replication_slots: 10
    wal_keep_segments: 8

patroni:
  ttl: 30
  loop_wait: 10
  retry_timeout: 10
  maximum_lag_on_failover: 1048576
```

**Manual Failover:**

```bash
# Promote replica to primary
patronictl -c /etc/patroni/patroni.yml failover crypto-bot-cluster

# Update service DNS/connection strings
# (Automatic with HAProxy or pgBouncer)
```

### 2. Redis Failover (Sentinel)

**Automatic Failover with Redis Sentinel**

```bash
# sentinel.conf
sentinel monitor crypto-bot-redis redis-master 6379 2
sentinel down-after-milliseconds crypto-bot-redis 5000
sentinel parallel-syncs crypto-bot-redis 1
sentinel failover-timeout crypto-bot-redis 10000
```

**Manual Failover:**

```bash
# Force failover to replica
redis-cli -p 26379 SENTINEL failover crypto-bot-redis

# Verify new master
redis-cli -p 26379 SENTINEL get-master-addr-by-name crypto-bot-redis
```

### 3. Service Failover (Kubernetes/Docker Swarm)

**Automatic with health checks:**

```yaml
# docker-compose.yml
services:
  trading-engine:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      replicas: 3
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
```

---

## Emergency Contacts

### Escalation Matrix

| Level | Role | Contact | Response Time |
|-------|------|---------|---------------|
| L1 | On-Call Engineer | [Phone/Slack] | 15 minutes |
| L2 | Lead DevOps | [Phone/Slack] | 30 minutes |
| L3 | CTO | [Phone] | 1 hour |
| External | Bybit Support | support@bybit.com | 2-4 hours |
| External | AWS Support | Premium Support | 15 minutes |

### Emergency Procedures Checklist

#### P1 Incident (Trading Down)

- [ ] **Immediate:** Stop all automated trading
- [ ] **0-5 min:** Alert on-call engineer
- [ ] **5-10 min:** Assess impact (open positions, pending orders)
- [ ] **10-15 min:** Decide: recover or failover
- [ ] **15-30 min:** Execute recovery/failover
- [ ] **30-45 min:** Verify system integrity
- [ ] **45-60 min:** Resume trading (manual approval required)
- [ ] **Post-incident:** Write RCA document

#### P2 Incident (Degraded Performance)

- [ ] Alert relevant team
- [ ] Identify bottleneck
- [ ] Scale resources if needed
- [ ] Monitor for escalation to P1
- [ ] Plan maintenance window if required

---

## Testing Schedule

### Monthly DR Drills

**First Friday of each month - 10:00 UTC**

```bash
# Monthly DR drill script
#!/bin/bash
# Location: scripts/testing/monthly_dr_drill.sh

echo "🧪 MONTHLY DR DRILL - $(date)"
echo "================================"

# Test 1: Database backup/restore (non-production)
echo "Test 1: Database backup/restore..."
./scripts/backup/postgres_backup.sh
./scripts/recovery/restore_postgres.sh --test-environment

# Test 2: Service failover
echo "Test 2: Service failover..."
docker-compose stop trading-engine
sleep 30
# Verify automatic restart
HEALTH=$(curl -s http://localhost:8000/health)
echo "Failover result: ${HEALTH}"

# Test 3: Configuration restore
echo "Test 3: Configuration restore..."
./scripts/recovery/restore_config.sh --dry-run

# Test 4: Communication test
echo "Test 4: Testing alert channels..."
./scripts/alerting/test_alerts.sh

echo "✅ DR DRILL COMPLETE"
echo "📋 Review results and update procedures if needed"
```

### Quarterly Full Recovery Test

**Last Sunday of each quarter - 02:00 UTC**

- Complete system shutdown
- Full recovery from backups
- Data integrity verification
- Performance benchmarking
- Document time taken vs RTO

### Annual DR Exercise

**Last weekend of January - Full day**

- Simulate complete datacenter failure
- Recover in alternate region
- Test all runbooks
- Update all documentation
- Train all team members

---

## Backup Verification

### Automated Verification Script

```bash
#!/bin/bash
# Location: scripts/testing/verify_backups.sh
# Run daily to ensure backups are valid

echo "🔍 BACKUP VERIFICATION - $(date)"

# Test PostgreSQL backup
LATEST_PG=$(ls -t /backups/postgres/*.dump.gz | head -1)
pg_restore --list ${LATEST_PG} > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PostgreSQL backup valid: ${LATEST_PG}"
else
    echo "❌ PostgreSQL backup CORRUPT: ${LATEST_PG}"
    # Send alert
    ./scripts/alerting/send_alert.sh "CRITICAL: PostgreSQL backup verification failed"
fi

# Test Redis backup
LATEST_REDIS=$(ls -t /backups/redis/*.rdb.gz | head -1)
gunzip -t ${LATEST_REDIS} 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Redis backup valid: ${LATEST_REDIS}"
else
    echo "❌ Redis backup CORRUPT: ${LATEST_REDIS}"
    ./scripts/alerting/send_alert.sh "CRITICAL: Redis backup verification failed"
fi

# Test S3 replication
S3_COUNT=$(aws s3 ls s3://crypto-bot-backups/postgres/ | wc -l)
if [ ${S3_COUNT} -gt 0 ]; then
    echo "✅ S3 backups replicated: ${S3_COUNT} files"
else
    echo "❌ S3 replication FAILED"
    ./scripts/alerting/send_alert.sh "CRITICAL: S3 backup replication failed"
fi
```

**Cron Schedule:**
```cron
0 4 * * * /scripts/testing/verify_backups.sh
```

---

## Recovery Metrics

### Track Recovery Performance

```bash
# /var/log/recovery_metrics.log
Date,Incident_Type,Detection_Time,Recovery_Time,Data_Loss,RTO_Met,RPO_Met
2025-11-16,DB_Failure,5min,18min,0records,Yes,Yes
2025-11-15,Service_Crash,2min,45sec,0records,Yes,Yes
```

### Monthly Report

```bash
#!/bin/bash
# Generate monthly DR metrics report
# Location: scripts/reporting/dr_monthly_report.sh

MONTH=$(date +"%Y-%m")
echo "Disaster Recovery Report - ${MONTH}"
echo "===================================="

# Count incidents
INCIDENTS=$(grep "^${MONTH}" /var/log/recovery_metrics.log | wc -l)
echo "Total Incidents: ${INCIDENTS}"

# Average recovery time
AVG_RECOVERY=$(awk -F',' '{sum+=$4; count++} END {print sum/count}' /var/log/recovery_metrics.log)
echo "Average Recovery Time: ${AVG_RECOVERY} minutes"

# RTO/RPO compliance
RTO_MET=$(grep "Yes" /var/log/recovery_metrics.log | wc -l)
TOTAL=$(wc -l < /var/log/recovery_metrics.log)
COMPLIANCE=$((RTO_MET * 100 / TOTAL))
echo "RTO/RPO Compliance: ${COMPLIANCE}%"
```

---

## Appendix A: Recovery Scripts Reference

All recovery scripts located in: `/scripts/recovery/`

| Script | Purpose | Runtime |
|--------|---------|---------|
| `restore_postgres.sh` | Full PostgreSQL recovery | ~15min |
| `restore_redis.sh` | Redis recovery | ~5min |
| `restore_config.sh` | Configuration recovery | ~2min |
| `pitr_postgres.sh` | Point-in-time recovery | ~20min |
| `full_system_recovery.sh` | Complete system recovery | ~45min |

---

## Appendix B: Validation Checklist

After any recovery, complete this checklist:

- [ ] All services reporting healthy (`/health`)
- [ ] Database connections working
- [ ] Redis cache accessible
- [ ] Message queue functional
- [ ] Recent trade data visible
- [ ] Portfolio balances correct
- [ ] API Gateway responding
- [ ] Bybit connection established
- [ ] Logs being generated
- [ ] Metrics being collected
- [ ] No error spikes in logs
- [ ] Execute one test trade successfully
- [ ] Verify websocket connections
- [ ] Check backup jobs still scheduled

**Sign-off required before resuming automated trading**

---

**Document Version:** 1.0
**Next Review:** 2025-12-16
**Owner:** DevOps Team
**Approved By:** CTO

*This is a living document. Update after each DR drill and incident.*
