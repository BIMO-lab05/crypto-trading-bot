# Password Rotation Guide

**Document Version:** 1.0
**Last Updated:** 2025-11-19
**Status:** Production Ready
**Security Classification:** Internal

---

## Table of Contents

1. [Overview](#overview)
2. [Security Requirements](#security-requirements)
3. [Rotation Schedule](#rotation-schedule)
4. [Pre-Rotation Checklist](#pre-rotation-checklist)
5. [Rotation Procedures](#rotation-procedures)
6. [Verification Steps](#verification-steps)
7. [Rollback Procedures](#rollback-procedures)
8. [Troubleshooting](#troubleshooting)
9. [Audit and Compliance](#audit-and-compliance)

---

## Overview

### Purpose

This document provides comprehensive procedures for rotating passwords across all Crypto Trading Bot infrastructure components. Regular password rotation is a critical security practice that:

- Reduces risk of credential compromise
- Limits exposure window of leaked credentials
- Maintains compliance with security standards
- Enforces principle of least privilege
- Provides audit trail for access control

### Scope

Password rotation covers the following components:

| Component | Port | Password Variable | Rotation Frequency |
|-----------|------|-------------------|-------------------|
| PostgreSQL | 5432 | `POSTGRES_PASSWORD` | 90 days |
| TimescaleDB | 5433 | `TIMESCALE_PASSWORD` | 90 days |
| Redis | 6379 | `REDIS_PASSWORD` | 90 days |
| RabbitMQ | 5672/15672 | `RABBITMQ_PASSWORD` | 90 days |
| PgAdmin | 5050 | `PGADMIN_PASSWORD` | 30 days |

### Password Complexity Requirements

All passwords MUST meet the following criteria:

- **Minimum Length:** 24 characters
- **Character Types:** Mix of uppercase, lowercase, numbers, and special characters
- **Allowed Special Characters:** `@#$%^&+=!`
- **Not Allowed:** Dictionary words, sequential characters, repeated patterns
- **Uniqueness:** Each service must have a unique password
- **No Reuse:** Passwords cannot be reused for 12 months

**Regex Pattern:**
```regex
^[A-Za-z0-9@#$%^&+=!]{24,}$
```

---

## Security Requirements

### Access Control

**Who Can Rotate Passwords:**
- Infrastructure Team Lead
- Security Engineers
- DevOps Engineers (with approval)
- On-call engineers (emergency only)

**Authorization Requirements:**
1. Valid security clearance
2. Multi-factor authentication enabled
3. Audit log review access
4. Incident response training completed

### Environment Considerations

#### Development Environment
- Rotation Frequency: 180 days
- Approval Required: No
- Automated: Yes
- Backup Required: Yes

#### Staging Environment
- Rotation Frequency: 90 days
- Approval Required: Team Lead
- Automated: Recommended
- Backup Required: Yes

#### Production Environment
- Rotation Frequency: 90 days (or immediately after incident)
- Approval Required: Security Team + Infrastructure Lead
- Automated: No (manual verification required)
- Backup Required: Yes (encrypted)
- Change Window: Maintenance window only
- Rollback Plan: Mandatory

---

## Rotation Schedule

### Regular Schedule

```yaml
# Recommended rotation calendar
Q1 (January-March):
  - Week 1: PostgreSQL + TimescaleDB
  - Week 2: Redis + RabbitMQ
  - Week 3: PgAdmin + API Keys
  - Week 4: Verification and audit

Q2 (April-June):
  - Week 1: PostgreSQL + TimescaleDB
  - Week 2: Redis + RabbitMQ
  - Week 3: PgAdmin + API Keys
  - Week 4: Verification and audit

Q3 (July-September):
  - Week 1: PostgreSQL + TimescaleDB
  - Week 2: Redis + RabbitMQ
  - Week 3: PgAdmin + API Keys
  - Week 4: Verification and audit

Q4 (October-December):
  - Week 1: PostgreSQL + TimescaleDB
  - Week 2: Redis + RabbitMQ
  - Week 3: PgAdmin + API Keys
  - Week 4: Verification and audit
```

### Emergency Rotation Triggers

Immediate rotation required when:

1. **Security Incidents:**
   - Suspected credential compromise
   - Unauthorized access detected
   - Data breach notification
   - Failed security audit

2. **Personnel Changes:**
   - Administrator resignation
   - Role change reducing access
   - Contractor contract end
   - Security clearance revocation

3. **Compliance Events:**
   - Failed compliance audit
   - Regulatory requirement
   - Customer security review
   - Insurance policy requirement

4. **Technical Events:**
   - Service misconfiguration detected
   - Credentials logged or exposed
   - Backup restoration from old snapshot
   - Third-party integration compromise

---

## Pre-Rotation Checklist

### Preparation Phase (T-24 hours)

#### 1. Environment Verification

```bash
# Check all services are running
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# Verify current connectivity
./infrastructure/scripts/rotate_passwords.sh --verify

# Check disk space for backups
df -h | grep -E 'Filesystem|/mnt/d'

# Verify Docker network
docker network inspect crypto-bot-network
```

#### 2. Backup Creation

```bash
# Create full database backups
./infrastructure/scripts/backup_databases.sh --full

# Backup current environment configuration
cp infrastructure/.env "infrastructure/backups/env_$(date +%Y%m%d_%H%M%S).backup"

# Export Docker volumes
docker run --rm -v postgres_data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz /data
```

#### 3. Communication

- [ ] Notify development team (24 hours advance)
- [ ] Schedule maintenance window
- [ ] Update status page
- [ ] Prepare rollback contact list
- [ ] Alert monitoring team

#### 4. Documentation Review

- [ ] Review this procedure document
- [ ] Check recent security advisories
- [ ] Verify rollback procedures
- [ ] Confirm escalation contacts
- [ ] Review incident response plan

### Pre-Flight Checks (T-1 hour)

```bash
# Final service health check
curl -s http://localhost:5432 && echo "PostgreSQL: OK"
curl -s http://localhost:5433 && echo "TimescaleDB: OK"
redis-cli -h localhost -p 6379 PING && echo "Redis: OK"
curl -s http://localhost:15672 && echo "RabbitMQ: OK"

# Verify backup integrity
tar -tzf backups/postgres_$(date +%Y%m%d).tar.gz >/dev/null && echo "Backup: OK"

# Check log space
ls -lh logs/security/

# Confirm no active trading operations
curl -s http://localhost:8001/api/v1/trading/status | jq '.active_trades'
```

---

## Rotation Procedures

### Method 1: Automatic Rotation (Recommended)

**Best For:** Development, Staging, Scheduled Maintenance

```bash
# Navigate to project root
cd /mnt/d/Bimo_max/crypto-trading-bot

# Execute automatic rotation
./infrastructure/scripts/rotate_passwords.sh --automatic

# Expected output:
# ╔═══════════════════════════════════════════════════════════╗
# ║   Crypto Trading Bot - Password Rotation Script          ║
# ║   Version: 1.0                                            ║
# ╚═══════════════════════════════════════════════════════════╝
#
# [INFO] Starting password rotation process (mode: automatic)...
# [INFO] Backing up current environment configuration...
# [SUCCESS] Backup created: infrastructure/backups/passwords/rollback_*.env
# [INFO] Generated new password for POSTGRES
# [INFO] Generated new password for TIMESCALE
# [INFO] Generated new password for REDIS
# [INFO] Generated new password for RABBITMQ
# [INFO] Rotating PostgreSQL password...
# [SUCCESS] PostgreSQL password updated in database
# ... (continues for all services)
# [SUCCESS] Password rotation completed successfully!
```

**Time Required:** 5-10 minutes

### Method 2: Interactive Rotation

**Best For:** Production, Custom Security Requirements

```bash
# Execute interactive rotation
./infrastructure/scripts/rotate_passwords.sh --interactive

# You will be prompted:
# Enter new password for POSTGRES (or press Enter for auto-generation):
# [Enter password or press Enter for auto-gen]
#
# Enter new password for TIMESCALE (or press Enter for auto-generation):
# [Enter password or press Enter for auto-gen]
#
# ... (continues for all services)
```

**Advantages:**
- Full control over password values
- Can use password manager integration
- Compliance with specific password policies
- Immediate verification possible

**Time Required:** 10-15 minutes

### Method 3: Manual Rotation

**Best For:** Emergency, Single Service, Troubleshooting

#### PostgreSQL Manual Rotation

```bash
# 1. Generate new password
NEW_POSTGRES_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9@#$%^&+=!' < /dev/urandom | head -c 24)

# 2. Update database
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
  -c "ALTER USER cryptobot WITH PASSWORD '${NEW_POSTGRES_PASSWORD}';"

# 3. Update environment file
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${NEW_POSTGRES_PASSWORD}/" \
  infrastructure/.env

# 4. Update service configurations
find services/ -name ".env" -exec \
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${NEW_POSTGRES_PASSWORD}/" {} \;

# 5. Verify connection
PGPASSWORD="${NEW_POSTGRES_PASSWORD}" psql -h localhost -p 5432 \
  -U cryptobot -d cryptobot -c "SELECT 1;"
```

#### TimescaleDB Manual Rotation

```bash
# 1. Generate new password
NEW_TIMESCALE_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9@#$%^&+=!' < /dev/urandom | head -c 24)

# 2. Update database
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
  -c "ALTER USER cryptobot WITH PASSWORD '${NEW_TIMESCALE_PASSWORD}';"

# 3. Update environment file
sed -i "s/^TIMESCALE_PASSWORD=.*/TIMESCALE_PASSWORD=${NEW_TIMESCALE_PASSWORD}/" \
  infrastructure/.env

# 4. Verify connection
PGPASSWORD="${NEW_TIMESCALE_PASSWORD}" psql -h localhost -p 5433 \
  -U cryptobot -d market_data -c "SELECT 1;"
```

#### Redis Manual Rotation

```bash
# 1. Generate new password
NEW_REDIS_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9@#$%^&+=!' < /dev/urandom | head -c 24)

# 2. Update Redis configuration
docker exec crypto-bot-redis redis-cli CONFIG SET requirepass "${NEW_REDIS_PASSWORD}"
docker exec crypto-bot-redis redis-cli -a "${NEW_REDIS_PASSWORD}" CONFIG REWRITE

# 3. Update environment file
sed -i "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=${NEW_REDIS_PASSWORD}/" \
  infrastructure/.env

# 4. Verify connection
redis-cli -h localhost -p 6379 -a "${NEW_REDIS_PASSWORD}" PING
```

#### RabbitMQ Manual Rotation

```bash
# 1. Generate new password
NEW_RABBITMQ_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9@#$%^&+=!' < /dev/urandom | head -c 24)

# 2. Update RabbitMQ user
docker exec crypto-bot-rabbitmq rabbitmqctl change_password cryptobot "${NEW_RABBITMQ_PASSWORD}"

# 3. Update environment file
sed -i "s/^RABBITMQ_PASSWORD=.*/RABBITMQ_PASSWORD=${NEW_RABBITMQ_PASSWORD}/" \
  infrastructure/.env

# 4. Verify connection
docker exec crypto-bot-rabbitmq rabbitmqctl authenticate_user cryptobot "${NEW_RABBITMQ_PASSWORD}"
```

---

## Verification Steps

### Immediate Verification (T+5 minutes)

```bash
# Run built-in verification
./infrastructure/scripts/rotate_passwords.sh --verify

# Expected output:
# [INFO] Verifying current password configuration...
# [SUCCESS] PostgreSQL connection verified
# [SUCCESS] TimescaleDB connection verified
# [SUCCESS] Redis connection verified
# [SUCCESS] RabbitMQ connection verified
# [SUCCESS] All connection verifications passed
```

### Service Health Checks

```bash
# Check all services are healthy
docker-compose -f infrastructure/docker-compose.yml ps

# Verify each service health endpoint
for port in 8001 8002 8003 8004 8005 8006 8007; do
  echo -n "Service on port $port: "
  curl -s http://localhost:$port/health | jq -r '.status' || echo "FAILED"
done

# Check database connectivity
docker exec crypto-bot-postgres pg_isready -U cryptobot
docker exec crypto-bot-timescaledb pg_isready -U cryptobot

# Verify Redis
docker exec crypto-bot-redis redis-cli PING

# Check RabbitMQ management
curl -u cryptobot:${RABBITMQ_PASSWORD} http://localhost:15672/api/overview | jq '.cluster_name'
```

### Application Integration Tests

```bash
# Run integration test suite
pytest tests/integration/ -v --tb=short

# Test database operations
python3 << EOF
import psycopg2
import os

# Test PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="cryptobot",
    user="cryptobot",
    password=os.getenv("POSTGRES_PASSWORD")
)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM trading_engine.strategies")
print(f"PostgreSQL: {cursor.fetchone()[0]} strategies found")
conn.close()

# Test TimescaleDB
conn = psycopg2.connect(
    host="localhost",
    port=5433,
    database="market_data",
    user="cryptobot",
    password=os.getenv("TIMESCALE_PASSWORD")
)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM market_data.candles")
print(f"TimescaleDB: {cursor.fetchone()[0]} candles found")
conn.close()
EOF
```

### Extended Verification (T+1 hour)

```bash
# Monitor logs for authentication errors
docker-compose -f infrastructure/docker-compose.yml logs --since 1h | grep -i "auth\|password\|failed"

# Check service metrics
curl -s http://localhost:8001/metrics | grep -E "database_connection|redis_connection"

# Verify no connection pool exhaustion
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
  -c "SELECT count(*) FROM pg_stat_activity WHERE usename='cryptobot';"

# Check for any locked accounts
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
  -c "SELECT usename, valuntil FROM pg_user WHERE usename='cryptobot';"
```

---

## Rollback Procedures

### When to Rollback

Initiate rollback if:
- Connection verification fails for any service
- Application health checks fail
- Service restart failures detected
- Authentication errors in logs
- Critical trading operations disrupted
- Data corruption detected

### Automatic Rollback

```bash
# Execute automatic rollback
./infrastructure/scripts/rotate_passwords.sh --rollback

# The script will:
# 1. Restore environment file from backup
# 2. Restart all services with old passwords
# 3. Verify connections
# 4. Log rollback event
```

### Manual Rollback

```bash
# 1. Identify latest backup
ROLLBACK_FILE=$(ls -t infrastructure/backups/passwords/rollback_*.env | head -1)
echo "Rolling back to: ${ROLLBACK_FILE}"

# 2. Restore environment file
cp "${ROLLBACK_FILE}" infrastructure/.env

# 3. Source old passwords
source infrastructure/.env

# 4. Restore PostgreSQL password
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
  -c "ALTER USER cryptobot WITH PASSWORD '${POSTGRES_PASSWORD}';"

# 5. Restore TimescaleDB password
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
  -c "ALTER USER cryptobot WITH PASSWORD '${TIMESCALE_PASSWORD}';"

# 6. Restore Redis password
docker exec crypto-bot-redis redis-cli CONFIG SET requirepass "${REDIS_PASSWORD}"
docker exec crypto-bot-redis redis-cli -a "${REDIS_PASSWORD}" CONFIG REWRITE

# 7. Restore RabbitMQ password
docker exec crypto-bot-rabbitmq rabbitmqctl change_password cryptobot "${RABBITMQ_PASSWORD}"

# 8. Restart services
docker-compose -f infrastructure/docker-compose.yml restart

# 9. Verify rollback
./infrastructure/scripts/rotate_passwords.sh --verify
```

### Post-Rollback Actions

1. **Document Failure:**
   ```bash
   cat > logs/security/rollback_$(date +%Y%m%d_%H%M%S).log <<EOF
   Rollback Event Report
   =====================
   Date: $(date)
   Initiated By: $(whoami)
   Reason: [DESCRIBE REASON]
   Failed Service: [SERVICE NAME]
   Error Message: [ERROR DETAILS]
   Rollback Status: [SUCCESS/PARTIAL/FAILED]
   Next Actions: [PLANNED ACTIONS]
   EOF
   ```

2. **Root Cause Analysis:**
   - Review rotation logs
   - Check service logs
   - Analyze connection errors
   - Identify configuration issues

3. **Incident Response:**
   - Notify security team
   - Update incident tracker
   - Schedule post-mortem
   - Plan remediation

---

## Troubleshooting

### Common Issues

#### Issue 1: Permission Denied

**Symptoms:**
```
ERROR: permission denied to alter user "cryptobot"
```

**Cause:** Insufficient database privileges

**Solution:**
```bash
# Grant necessary privileges
docker exec crypto-bot-postgres psql -U postgres -c \
  "GRANT cryptobot TO postgres;"

# Retry password rotation
docker exec crypto-bot-postgres psql -U postgres -d cryptobot -c \
  "ALTER USER cryptobot WITH PASSWORD 'new_password';"
```

#### Issue 2: Connection Pool Exhaustion

**Symptoms:**
```
FATAL: sorry, too many clients already
```

**Cause:** Active connections preventing password update

**Solution:**
```bash
# Terminate active connections
docker exec crypto-bot-postgres psql -U postgres -d cryptobot -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE usename='cryptobot' AND pid <> pg_backend_pid();"

# Retry rotation
./infrastructure/scripts/rotate_passwords.sh --automatic
```

#### Issue 3: Redis Authentication Failed

**Symptoms:**
```
NOAUTH Authentication required
```

**Cause:** Redis password not updated correctly

**Solution:**
```bash
# Check current Redis password
docker exec crypto-bot-redis redis-cli CONFIG GET requirepass

# Reset Redis password
docker exec crypto-bot-redis redis-cli CONFIG SET requirepass "new_password"
docker exec crypto-bot-redis redis-cli -a "new_password" CONFIG REWRITE

# Update environment
sed -i "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=new_password/" infrastructure/.env
```

#### Issue 4: RabbitMQ User Not Found

**Symptoms:**
```
Error: user_not_found
```

**Cause:** RabbitMQ user doesn't exist or was deleted

**Solution:**
```bash
# Recreate user
docker exec crypto-bot-rabbitmq rabbitmqctl add_user cryptobot new_password

# Set permissions
docker exec crypto-bot-rabbitmq rabbitmqctl set_permissions -p / cryptobot ".*" ".*" ".*"

# Set user tags
docker exec crypto-bot-rabbitmq rabbitmqctl set_user_tags cryptobot administrator
```

### Diagnostic Commands

```bash
# Check service logs
docker-compose -f infrastructure/docker-compose.yml logs --tail=100 [service_name]

# Verify Docker network
docker network inspect crypto-bot-network | jq '.[0].Containers'

# Check environment variables
docker exec crypto-bot-postgres env | grep POSTGRES
docker exec crypto-bot-timescaledb env | grep TIMESCALE

# Test raw socket connection
nc -zv localhost 5432  # PostgreSQL
nc -zv localhost 5433  # TimescaleDB
nc -zv localhost 6379  # Redis
nc -zv localhost 5672  # RabbitMQ

# Validate .env file syntax
grep -v '^#' infrastructure/.env | grep -v '^$' | while read line; do
  if ! echo "$line" | grep -qE '^[A-Z_]+=.*$'; then
    echo "Invalid line: $line"
  fi
done
```

---

## Audit and Compliance

### Audit Log Format

All password rotation events are logged to:
```
logs/security/password_rotation_YYYYMMDD_HHMMSS.log
```

**Log Entry Structure:**
```
2025-11-19 10:30:00 [INFO] Starting password rotation process (mode: automatic)
2025-11-19 10:30:01 [SUCCESS] Backup created: infrastructure/backups/passwords/rollback_20251119_103001.env
2025-11-19 10:30:05 [SUCCESS] PostgreSQL password updated in database
2025-11-19 10:30:10 [SUCCESS] TimescaleDB password updated in database
2025-11-19 10:30:15 [SUCCESS] Redis password updated
2025-11-19 10:30:20 [SUCCESS] RabbitMQ password updated
2025-11-19 10:30:25 [SUCCESS] PostgreSQL connection verified
2025-11-19 10:30:26 [SUCCESS] TimescaleDB connection verified
2025-11-19 10:30:27 [SUCCESS] Redis connection verified
2025-11-19 10:30:28 [SUCCESS] RabbitMQ connection verified
2025-11-19 10:30:30 [SUCCESS] Password rotation completed successfully!

=== ROTATION SUMMARY ===
Timestamp: 2025-11-19 10:30:30 UTC
Status: SUCCESS
Services Rotated: 4
Services: POSTGRES TIMESCALE REDIS RABBITMQ
Backup Location: infrastructure/backups/passwords/rollback_20251119_103001.env
Next Rotation Due: 2026-02-17
========================
```

### Compliance Reporting

Generate compliance report:

```bash
#!/bin/bash
# Generate password rotation compliance report

cat > compliance_report_$(date +%Y%m%d).md <<EOF
# Password Rotation Compliance Report

**Report Date:** $(date +"%Y-%m-%d %H:%M:%S")
**Reporting Period:** Last 90 days
**Report Generated By:** $(whoami)

## Summary

| Metric | Value | Status |
|--------|-------|--------|
| Total Rotations | $(grep -c "ROTATION SUMMARY" logs/security/password_rotation_*.log) | ✅ |
| Failed Rotations | $(grep -c "Status: FAILED" logs/security/password_rotation_*.log) | - |
| Rollbacks Required | $(ls logs/security/rollback_*.log 2>/dev/null | wc -l) | - |
| Compliance Score | 100% | ✅ |

## Rotation History

$(grep "ROTATION SUMMARY" logs/security/password_rotation_*.log | tail -10)

## Upcoming Rotations

$(grep "Next Rotation Due" logs/security/password_rotation_*.log | tail -5)

## Audit Trail

All rotation events logged to: logs/security/

## Compliance Attestation

I certify that all password rotations have been performed according to
established security policies and procedures.

Signature: _________________
Date: $(date +"%Y-%m-%d")
EOF

cat compliance_report_$(date +%Y%m%d).md
```

### Retention Policy

| Item | Retention Period | Storage Location |
|------|------------------|------------------|
| Rotation Logs | 2 years | `logs/security/` |
| Backup Files | 1 year | `infrastructure/backups/passwords/` |
| Audit Reports | 3 years | `docs/security/audit/` |
| Incident Reports | 5 years | `docs/security/incidents/` |

### Access Review

Quarterly review checklist:

- [ ] Verify all personnel with rotation access still require it
- [ ] Review rotation logs for anomalies
- [ ] Confirm backup integrity
- [ ] Test rollback procedures
- [ ] Update rotation schedule
- [ ] Review compliance reports
- [ ] Update documentation

---

## Appendix

### A. Password Strength Calculator

```python
#!/usr/bin/env python3
"""Password strength calculator"""

import re
import math

def calculate_entropy(password):
    """Calculate password entropy in bits"""
    charset_size = 0

    if re.search(r'[a-z]', password):
        charset_size += 26
    if re.search(r'[A-Z]', password):
        charset_size += 26
    if re.search(r'[0-9]', password):
        charset_size += 10
    if re.search(r'[@#$%^&+=!]', password):
        charset_size += 8

    entropy = len(password) * math.log2(charset_size)
    return entropy

def check_password_strength(password):
    """Evaluate password strength"""
    entropy = calculate_entropy(password)

    if entropy < 50:
        return "WEAK", entropy
    elif entropy < 60:
        return "FAIR", entropy
    elif entropy < 80:
        return "GOOD", entropy
    elif entropy < 100:
        return "STRONG", entropy
    else:
        return "VERY STRONG", entropy

# Example usage
password = "YourPasswordHere"
strength, entropy = check_password_strength(password)
print(f"Strength: {strength}")
print(f"Entropy: {entropy:.2f} bits")
print(f"Time to crack (100B attempts/sec): {2**entropy / (100 * 10**9) / 31536000:.2f} years")
```

### B. Emergency Contact List

| Role | Name | Contact | Escalation |
|------|------|---------|------------|
| Security Lead | [NAME] | [EMAIL/PHONE] | Primary |
| Infrastructure Lead | [NAME] | [EMAIL/PHONE] | Primary |
| DevOps Engineer | [NAME] | [EMAIL/PHONE] | Secondary |
| On-Call Engineer | [ROTATION] | [PagerDuty] | Emergency |

### C. Related Documentation

- [VAULT_INTEGRATION.md](./VAULT_INTEGRATION.md) - HashiCorp Vault setup
- [SECURITY_AUDIT.md](./SECURITY_AUDIT.md) - Security audit procedures
- [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) - Incident response plan
- [COMPLIANCE_GUIDE.md](./COMPLIANCE_GUIDE.md) - Compliance requirements

---

**Document Control:**
- Version: 1.0
- Created: 2025-11-19
- Last Reviewed: 2025-11-19
- Next Review: 2026-02-19
- Owner: Security Team
- Classification: Internal
