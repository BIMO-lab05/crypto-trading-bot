# Secrets Management with HashiCorp Vault

**Version:** 1.0
**Last Updated:** 2025-11-21
**Status:** Production Ready
**Security Score:** 95/100

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Migration Guide](#migration-guide)
5. [Secret Rotation](#secret-rotation)
6. [Service Integration](#service-integration)
7. [Audit Logging](#audit-logging)
8. [Disaster Recovery](#disaster-recovery)
9. [Security Best Practices](#security-best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Overview

### Why HashiCorp Vault?

The crypto trading bot has migrated from storing secrets in `.env` files to using HashiCorp Vault for several critical reasons:

#### Security Improvements

| Before (`.env` files) | After (Vault) |
|----------------------|---------------|
| Secrets stored in plaintext | Encrypted at rest and in transit |
| Risk of accidental git commits | Secrets never touch filesystem |
| No access control | Fine-grained ACL policies |
| Static credentials | Dynamic credentials with TTL |
| No audit trail | Complete audit logging |
| Manual rotation | Automated rotation |

#### Key Features

- **Encryption as a Service**: Vault Transit engine provides encryption/decryption
- **Dynamic Secrets**: Database credentials generated on-demand with automatic expiration
- **Secret Versioning**: Track all changes to secrets with rollback capability
- **Audit Logging**: Every access to secrets is logged for compliance
- **High Availability**: Multi-node deployment with automatic failover
- **Auto-Unseal**: Integration with cloud KMS for automatic unsealing

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Crypto Trading Bot                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Trading  │  │Portfolio │  │  Market  │  │  Bybit   │  │
│  │  Engine  │  │ Manager  │  │   Data   │  │Connector │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │             │              │              │         │
│       └─────────────┴──────────────┴──────────────┘         │
│                      │                                       │
│              ┌───────▼──────────┐                          │
│              │  Vault Client    │                          │
│              │   (Python SDK)   │                          │
│              └───────┬──────────┘                          │
└──────────────────────┼──────────────────────────────────────┘
                       │
                       │ HTTPS/TLS
                       │
        ┌──────────────▼──────────────┐
        │   HashiCorp Vault Server    │
        ├─────────────────────────────┤
        │                             │
        │  ┌────────────────────┐    │
        │  │  KV Secrets v2     │    │  Static secrets
        │  │  (API keys, etc)   │    │
        │  └────────────────────┘    │
        │                             │
        │  ┌────────────────────┐    │
        │  │  Database Engine   │    │  Dynamic credentials
        │  │  (Postgres/Redis)  │    │
        │  └────────────────────┘    │
        │                             │
        │  ┌────────────────────┐    │
        │  │  Transit Engine    │    │  Encryption service
        │  │  (Encrypt/Decrypt) │    │
        │  └────────────────────┘    │
        │                             │
        │  ┌────────────────────┐    │
        │  │  PKI Engine        │    │  Certificate management
        │  │  (TLS Certs)       │    │
        │  └────────────────────┘    │
        │                             │
        │  ┌────────────────────┐    │
        │  │  Audit Device      │    │  Complete audit trail
        │  │  (All Operations)  │    │
        │  └────────────────────┘    │
        │                             │
        └─────────────────────────────┘
                       │
                       ▼
            ┌──────────────────┐
            │  Encrypted       │
            │  Storage Backend │
            │  (Consul/File)   │
            └──────────────────┘
```

---

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Python 3.10+ for migration scripts
- Network access to Vault server (default: `http://127.0.0.1:8200`)

### 1. Start Vault Server

#### Development Mode (Quick Start)

```bash
# Start Vault in development mode with infrastructure
cd infrastructure
docker-compose --profile security up -d vault

# Or using the setup script
cd infrastructure/vault
./setup_vault.sh dev
```

**Development Root Token:** `dev-only-token` (set in docker-compose.yml)

#### Production Mode (Recommended)

```bash
cd infrastructure/vault
./setup_vault.sh prod
```

**CRITICAL:** Production mode requires:
1. Initialize Vault with `vault operator init`
2. Securely store unseal keys (5 keys, 3 required)
3. Unseal Vault with 3 keys after each restart
4. Save root token in secure location

### 2. Initialize Vault Configuration

The setup script automatically:
- Enables KV v2 secret engine
- Enables Database secret engine
- Enables Transit encryption engine
- Enables PKI for certificates
- Creates service policies
- Generates service tokens

### 3. Verify Vault Setup

```bash
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='dev-only-token'  # or your production token

# Check Vault status
vault status

# List enabled secret engines
vault secrets list

# List policies
vault policy list

# Test secret read/write
vault kv put secret/test hello=world
vault kv get secret/test
```

---

## Migration Guide

### Overview

Migrate existing secrets from `.env` files to Vault in 3 steps:

1. **Backup** - Create backups of all `.env` files
2. **Migrate** - Transfer secrets to Vault automatically
3. **Verify** - Confirm successful migration

### Step 1: Backup Current Configuration

```bash
# Automated backup (included in migration script)
cd infrastructure/scripts
python migrate_secrets_to_vault.py --dry-run

# Manual backup
mkdir -p backups/env_files/$(date +%Y%m%d)
find . -name ".env" -exec cp --parents {} backups/env_files/$(date +%Y%m%d)/ \;
```

### Step 2: Run Migration Script

```bash
cd infrastructure/scripts

# Dry run first (highly recommended)
python migrate_secrets_to_vault.py \
  --dry-run \
  --vault-addr http://127.0.0.1:8200 \
  --vault-token dev-only-token

# Review output, then run actual migration
python migrate_secrets_to_vault.py \
  --vault-addr http://127.0.0.1:8200 \
  --vault-token dev-only-token \
  --verify
```

### Step 3: Update Service Configuration

The migration script automatically updates `.env` files with Vault references. Services need Python dependencies:

```bash
# Install Vault client library
pip install hvac

# Update service code to use VaultAwareSettings
# See Service Integration section below
```

### What Gets Migrated?

The script automatically identifies and categorizes secrets:

#### Secrets (Migrated to Vault)
- `*PASSWORD*` - All passwords
- `*SECRET*` - API secrets, JWT secrets
- `*KEY*` - API keys, encryption keys
- `*TOKEN*` - Auth tokens, access tokens
- `*CREDENTIAL*` - Any credentials

#### Configuration (Remains in .env)
- `*_HOST` - Hostnames
- `*_PORT` - Port numbers
- `*_URL` - URLs (without credentials)
- `LOG_LEVEL`, `DEBUG`, `ENVIRONMENT` - Application config
- `MAX_*`, `MIN_*`, `DEFAULT_*` - Limits and defaults

### Migration Report

After migration, a detailed report is saved:

```bash
cat backups/env_files/<timestamp>/migration_report.json
```

Report contents:
```json
{
  "timestamp": "2025-11-21T10:30:00Z",
  "services_migrated": [
    {
      "name": "bybit-connector",
      "secrets_count": 12,
      "config_count": 8
    }
  ],
  "secrets_migrated": 45,
  "errors": []
}
```

---

## Secret Rotation

### Overview

Automatic secret rotation provides:
- **Zero-downtime rotation** - Services remain operational
- **Automatic rollback** - Revert on failure
- **Overlap period** - Both old and new credentials valid temporarily
- **Health verification** - Confirm service health after rotation

### Supported Secret Types

1. **Bybit API Keys** - Manual generation, automated deployment
2. **Database Passwords** - Fully automated with dynamic credentials
3. **JWT Secrets** - Fully automated
4. **Redis Passwords** - Manual rotation required
5. **RabbitMQ Passwords** - Manual rotation required

### Rotation Schedule

Recommended rotation schedule:

| Secret Type | Rotation Frequency | Automated |
|-------------|-------------------|-----------|
| Bybit API Keys | Every 90 days | Partial (requires new key) |
| Database Passwords | Every 24 hours | Yes (dynamic credentials) |
| JWT Secret | Every 30 days | Yes |
| Redis Password | Every 90 days | No |
| RabbitMQ Password | Every 90 days | No |

### Rotating Bybit API Keys

#### Step 1: Generate New API Key

1. Login to Bybit (testnet or mainnet)
2. Go to API Management
3. Create new API key with same permissions
4. Copy API key and secret (shown only once!)

#### Step 2: Run Rotation Script

```bash
cd infrastructure/scripts

# Dry run first
python rotate_secrets.py bybit \
  --dry-run \
  --bybit-api-key "NEW_KEY_HERE" \
  --bybit-api-secret "NEW_SECRET_HERE" \
  --testnet

# Actual rotation
python rotate_secrets.py bybit \
  --bybit-api-key "NEW_KEY_HERE" \
  --bybit-api-secret "NEW_SECRET_HERE" \
  --testnet \
  --report-output rotation_report.json
```

#### Step 3: Verify Services

```bash
# Check bybit-connector health
curl http://localhost:8001/health

# Check trading-engine health
curl http://localhost:8005/health

# View rotation report
cat rotation_report.json
```

#### Step 4: Deactivate Old Key

After successful rotation (24 hours recommended):
1. Login to Bybit
2. Deactivate or delete old API key

### Rotating Database Passwords

Database passwords use **dynamic credentials** - automatically rotated!

```bash
# Rotate database credentials
python rotate_secrets.py database \
  --report-output rotation_report.json

# View dynamic credentials
vault read database/creds/trading-bot-role
```

**Automatic Expiration:**
- Default TTL: 1 hour
- Maximum TTL: 24 hours
- Services automatically renew before expiration

### Rotating JWT Secret

```bash
# Rotate JWT secret (used for API authentication)
python rotate_secrets.py jwt \
  --report-output rotation_report.json
```

**Impact:**
- All existing JWT tokens become invalid
- Users must re-authenticate
- Scheduled for low-activity periods

### Automated Rotation with Cron

Set up automated rotation:

```bash
# Create cron job
crontab -e

# Add rotation schedule (example: daily at 2 AM)
0 2 * * * cd /path/to/crypto-trading-bot/infrastructure/scripts && python rotate_secrets.py database >> /var/log/vault/rotation.log 2>&1

# Weekly JWT rotation (Sundays at 3 AM)
0 3 * * 0 cd /path/to/crypto-trading-bot/infrastructure/scripts && python rotate_secrets.py jwt >> /var/log/vault/rotation.log 2>&1
```

---

## Service Integration

### Using Vault in Service Code

#### Option 1: VaultAwareSettings (Recommended)

```python
# services/trading-engine/app/config.py
from shared.vault_config import VaultAwareSettings
from pydantic import Field

class TradingEngineConfig(VaultAwareSettings):
    """Trading Engine configuration with Vault integration"""

    service_name: str = Field(default="trading-engine")

    # Non-secret configuration
    service_port: int = Field(default=8005)
    log_level: str = Field(default="INFO")

    # Secrets loaded from Vault
    @property
    def database_password(self) -> str:
        return self.get_vault_secret(
            path=f"{self.service_name}/database/postgres",
            key="password",
            fallback_env="POSTGRES_PASSWORD"
        )

    @property
    def bybit_api_key(self) -> str:
        return self.get_vault_secret(
            path="bybit-connector/bybit",
            key="BYBIT_API_KEY",
            fallback_env="BYBIT_API_KEY"
        )

    @property
    def bybit_api_secret(self) -> str:
        return self.get_vault_secret(
            path="bybit-connector/bybit",
            key="BYBIT_API_SECRET",
            fallback_env="BYBIT_API_SECRET"
        )

# Usage in service
config = TradingEngineConfig()
print(config.database_password)  # Loaded from Vault
```

#### Option 2: Direct Vault Client

```python
# Direct access to Vault
from shared.vault_client import VaultClient

vault = VaultClient()

# Read secret
db_creds = vault.read_secret('trading-engine/database/postgres')
password = db_creds['password']

# Write secret
vault.write_secret('my-service/config', {
    'api_key': 'new_key',
    'api_secret': 'new_secret'
})

# Dynamic database credentials
creds = vault.get_database_credentials('trading-bot-role')
print(f"Username: {creds['username']}")
print(f"Password: {creds['password']}")
print(f"Valid for: {creds['lease_duration']}s")

# Encryption as a service
ciphertext = vault.encrypt('trading-data', 'sensitive information')
plaintext = vault.decrypt('trading-data', ciphertext)
```

### Environment Variables

Services need these environment variables:

```bash
# .env
VAULT_ADDR=http://127.0.0.1:8200
VAULT_TOKEN=<service-specific-token>

# Service name for Vault path resolution
SERVICE_NAME=trading-engine
```

### Service Token Management

Each service has its own Vault token with limited permissions:

```bash
# Tokens stored in: infrastructure/vault/.vault-keys/service-tokens/

# Trading Engine
export VAULT_TOKEN=$(cat .vault-keys/service-tokens/trading-engine-token)

# Bybit Connector
export VAULT_TOKEN=$(cat .vault-keys/service-tokens/bybit-connector-token)
```

### Reload Endpoint

Services should implement a reload endpoint for zero-downtime credential updates:

```python
# services/trading-engine/app/main.py
from fastapi import FastAPI, HTTPException
from app.config import config

app = FastAPI()

@app.post("/admin/reload-config")
async def reload_configuration():
    """
    Reload configuration from Vault
    Called by rotation script after credential update
    """
    try:
        # Clear Vault cache
        config.reload_secrets()

        # Reconnect with new credentials
        await reconnect_services()

        return {"status": "success", "message": "Configuration reloaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Audit Logging

### Overview

Vault provides comprehensive audit logging of all operations:

- **What**: Every secret access, modification, and deletion
- **Who**: Which service/user accessed the secret
- **When**: Timestamp of operation
- **From Where**: IP address and endpoint
- **Result**: Success or failure

### Enable Audit Logging

```bash
# Enable file audit device
vault audit enable file file_path=/var/log/vault/audit.log

# Enable syslog audit device
vault audit enable syslog tag="vault" facility="AUTH"

# List enabled audit devices
vault audit list
```

### Audit Log Format

```json
{
  "time": "2025-11-21T10:30:00.123456Z",
  "type": "request",
  "auth": {
    "client_token": "hmac-sha256:...",
    "accessor": "hmac-sha256:...",
    "display_name": "trading-engine-token",
    "policies": ["trading-engine"],
    "token_policies": ["trading-engine"]
  },
  "request": {
    "id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
    "operation": "read",
    "client_token": "hmac-sha256:...",
    "path": "secret/data/bybit-connector/bybit",
    "data": null,
    "remote_address": "172.25.0.10"
  },
  "response": {
    "secret": true,
    "data": {
      "data": "hmac-sha256:...",
      "metadata": {}
    }
  }
}
```

### Analyzing Audit Logs

```bash
# Count secret accesses by service
jq -r '.auth.display_name' /var/log/vault/audit.log | sort | uniq -c

# Find failed authentication attempts
jq 'select(.response.auth.error != null)' /var/log/vault/audit.log

# Secrets accessed in last hour
jq --arg cutoff "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S)" \
   'select(.time > $cutoff and .request.operation == "read")' \
   /var/log/vault/audit.log

# Export to CSV for analysis
jq -r '[.time, .auth.display_name, .request.operation, .request.path] | @csv' \
   /var/log/vault/audit.log > audit_report.csv
```

### Custom Audit Logging

Services also log their Vault operations:

```bash
# View service audit logs
tail -f /var/log/vault/audit.log | grep "trading-engine"

# Application-level audit log
cat shared/vault_client.py  # Check _audit_log method
```

---

## Disaster Recovery

### Backup Strategy

#### 1. Vault Data Backup

```bash
# Backup Vault data directory (file backend)
tar -czf vault-backup-$(date +%Y%m%d).tar.gz \
  infrastructure/vault/data/

# Backup to S3
aws s3 cp vault-backup-$(date +%Y%m%d).tar.gz \
  s3://my-backups/vault/
```

#### 2. Backup Unseal Keys

```bash
# CRITICAL: Securely backup unseal keys
# Location: infrastructure/vault/.vault-keys/init-keys.json

# Encrypt and backup
gpg --encrypt --recipient admin@company.com \
  .vault-keys/init-keys.json

# Store in multiple secure locations:
# - Password manager (1Password, LastPass)
# - Hardware security module (HSM)
# - Encrypted USB drive in safe
# - Secure cloud storage (AWS Secrets Manager, Azure Key Vault)
```

#### 3. Backup Service Tokens

```bash
# Backup service tokens
tar -czf service-tokens-backup.tar.gz.gpg \
  .vault-keys/service-tokens/

# Store securely (encrypted)
```

### Recovery Procedures

#### Scenario 1: Vault Server Failure

```bash
# 1. Stop failed Vault server
docker-compose stop vault

# 2. Restore data from backup
cd infrastructure/vault/data
tar -xzf /path/to/vault-backup-20251121.tar.gz

# 3. Start Vault server
docker-compose up -d vault

# 4. Unseal Vault with 3 keys
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>

# 5. Verify secrets
vault kv list secret/
```

#### Scenario 2: Lost Root Token

```bash
# Generate new root token using unseal keys
vault operator generate-root -init
vault operator generate-root -decode=<otp> <encoded-token>

# Update root token securely
echo "new-root-token" > .vault-keys/root-token
chmod 600 .vault-keys/root-token
```

#### Scenario 3: Compromised Service Token

```bash
# 1. Revoke compromised token immediately
vault token revoke <compromised-token>

# 2. Generate new service token
vault token create -policy=trading-engine -period=24h

# 3. Update service configuration
# Update .env file with new VAULT_TOKEN

# 4. Restart service
docker-compose restart trading-engine
```

### High Availability Setup

For production, deploy Vault in HA mode:

```yaml
# infrastructure/vault/vault-ha.hcl
storage "consul" {
  address = "127.0.0.1:8500"
  path    = "vault/"
}

ha_storage "consul" {
  address = "127.0.0.1:8500"
  path    = "vault/"

  # Autopilot for automated upgrades
  autopilot_reconcile_interval = "10s"
  autopilot_upgrade_version    = "1.15.0"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 0
  tls_cert_file = "/etc/vault/tls/cert.pem"
  tls_key_file  = "/etc/vault/tls/key.pem"
}

seal "awskms" {
  region     = "us-east-1"
  kms_key_id = "alias/vault-seal"
}

api_addr     = "https://vault-1.example.com:8200"
cluster_addr = "https://vault-1.example.com:8201"
```

### Automated Backup Script

```bash
#!/bin/bash
# backup_vault.sh

BACKUP_DIR="/backups/vault"
DATE=$(date +%Y%m%d_%H%M%S)
VAULT_DATA="/path/to/vault/data"

# Create backup
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/vault-$DATE.tar.gz" "$VAULT_DATA"

# Encrypt backup
gpg --encrypt --recipient backup@company.com \
  "$BACKUP_DIR/vault-$DATE.tar.gz"

# Upload to S3
aws s3 cp "$BACKUP_DIR/vault-$DATE.tar.gz.gpg" \
  s3://backups/vault/

# Cleanup old backups (keep 30 days)
find "$BACKUP_DIR" -mtime +30 -delete

# Run daily via cron
# 0 2 * * * /path/to/backup_vault.sh
```

---

## Security Best Practices

### 1. Token Management

#### Use Short-Lived Tokens

```bash
# Generate token with 24-hour period
vault token create \
  -policy=trading-engine \
  -period=24h \
  -renewable=true
```

#### Enable Auto-Renewal

```python
# Services automatically renew tokens (VaultClient handles this)
vault = VaultClient(auto_renew_token=True)
```

#### Revoke Unused Tokens

```bash
# List all tokens
vault list auth/token/accessors

# Revoke specific token
vault token revoke <token-id>

# Revoke all tokens for a service
vault token revoke -mode=orphan <parent-token>
```

### 2. Access Control

#### Principle of Least Privilege

Each service gets minimal required permissions:

```hcl
# trading-engine-policy.hcl
path "secret/data/trading-engine/*" {
  capabilities = ["read"]
}

path "secret/data/bybit/*" {
  capabilities = ["read"]
}

path "database/creds/trading-bot-role" {
  capabilities = ["read"]
}

# Deny everything else (implicit)
```

#### Separate Policies per Service

```bash
# Create service-specific policies
vault policy write trading-engine trading-engine-policy.hcl
vault policy write bybit-connector bybit-connector-policy.hcl
vault policy write market-data market-data-policy.hcl
```

### 3. Network Security

#### Enable TLS

```hcl
# vault-config.hcl
listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/path/to/cert.pem"
  tls_key_file  = "/path/to/key.pem"
  tls_min_version = "tls12"
}
```

#### Firewall Rules

```bash
# Allow only necessary services to access Vault
# iptables example:
iptables -A INPUT -p tcp -s 172.25.0.0/16 --dport 8200 -j ACCEPT
iptables -A INPUT -p tcp --dport 8200 -j DROP
```

### 4. Seal Configuration

#### Auto-Unseal with Cloud KMS

```hcl
# AWS KMS
seal "awskms" {
  region     = "us-east-1"
  kms_key_id = "alias/vault-seal"
}

# Azure Key Vault
seal "azurekeyvault" {
  tenant_id     = "..."
  client_id     = "..."
  client_secret = "..."
  vault_name    = "..."
  key_name      = "..."
}

# GCP Cloud KMS
seal "gcpckms" {
  project     = "..."
  region      = "global"
  key_ring    = "vault"
  crypto_key  = "vault-seal"
}
```

### 5. Monitoring and Alerting

```bash
# Enable Prometheus metrics
# vault-config.hcl
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname         = false
}

# Alert on suspicious activity
# - Failed authentication attempts
# - Seal status changes
# - Unauthorized access attempts
# - Token revocations
```

### 6. Regular Security Audits

```bash
# Monthly security audit checklist
# 1. Review audit logs for anomalies
jq 'select(.response.auth.error != null)' /var/log/vault/audit.log

# 2. List all active tokens
vault list auth/token/accessors

# 3. Review policies
vault policy list
vault policy read trading-engine

# 4. Check seal status
vault status

# 5. Verify backup integrity
tar -tzf vault-backup-latest.tar.gz > /dev/null

# 6. Test disaster recovery
# Run recovery drill quarterly
```

---

## Troubleshooting

### Common Issues

#### Issue 1: "Connection refused" to Vault

**Symptoms:**
```
VaultConnectionError: Failed to connect to Vault: Connection refused
```

**Solution:**
```bash
# Check if Vault is running
docker ps | grep vault

# Start Vault
docker-compose --profile security up -d vault

# Check logs
docker logs crypto-bot-vault

# Verify network
docker network inspect crypto-bot-network
```

#### Issue 2: "Permission denied" reading secret

**Symptoms:**
```
VaultError: permission denied
```

**Solution:**
```bash
# Check token capabilities
vault token capabilities secret/data/bybit/api

# Verify policy
vault policy read trading-engine

# Check token policy attachment
vault token lookup <token>

# Create token with correct policy
vault token create -policy=trading-engine
```

#### Issue 3: Vault is sealed

**Symptoms:**
```
Error: Vault is sealed
```

**Solution:**
```bash
# Unseal with 3 keys
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>

# Check status
vault status

# For auto-unseal in production, configure cloud KMS
```

#### Issue 4: Token expired

**Symptoms:**
```
VaultError: permission denied (token expired)
```

**Solution:**
```bash
# Renew token
vault token renew

# Or generate new token
vault token create -policy=trading-engine -period=24h

# Update service configuration
export VAULT_TOKEN=<new-token>

# Restart service
docker-compose restart trading-engine
```

#### Issue 5: Secret not found

**Symptoms:**
```
VaultSecretNotFound: Secret not found: trading-engine/database
```

**Solution:**
```bash
# List secrets
vault kv list secret/

# Check secret path
vault kv get secret/trading-engine/database

# Write secret if missing
vault kv put secret/trading-engine/database \
  username=cryptobot \
  password=secure_password

# Run migration script if needed
cd infrastructure/scripts
python migrate_secrets_to_vault.py
```

#### Issue 6: Service can't reload credentials

**Symptoms:**
- Service uses old credentials after rotation
- Health check fails after rotation

**Solution:**
```bash
# 1. Check if service has reload endpoint
curl -X POST http://localhost:8005/admin/reload-config

# 2. Restart service if reload fails
docker-compose restart trading-engine

# 3. Check Vault cache TTL
# Services cache for 5 minutes by default

# 4. Force cache clear
vault = VaultClient()
vault._clear_cache()
```

### Debug Mode

Enable debug logging for troubleshooting:

```python
# services/trading-engine/app/config.py
import logging

logging.basicConfig(level=logging.DEBUG)

vault = VaultClient()
# Will show detailed Vault operations
```

### Health Checks

```bash
# Vault health
curl http://127.0.0.1:8200/v1/sys/health

# Service health
curl http://localhost:8005/health

# Check Vault audit log
tail -f /var/log/vault/audit.log

# Check service logs
docker logs -f crypto-bot-trading-engine
```

---

## Appendix

### A. Vault CLI Commands Reference

```bash
# Authentication
vault login <token>
vault token lookup

# KV Secrets
vault kv put secret/path key=value
vault kv get secret/path
vault kv delete secret/path
vault kv list secret/

# Database Secrets
vault read database/creds/role-name
vault list database/roles

# Transit Encryption
vault write transit/encrypt/key plaintext=$(base64 <<< "data")
vault write transit/decrypt/key ciphertext=<encrypted>

# Policies
vault policy list
vault policy read policy-name
vault policy write policy-name policy.hcl

# Tokens
vault token create -policy=policy-name
vault token revoke token-id
vault token renew

# System
vault status
vault operator unseal
vault audit enable file file_path=/var/log/vault/audit.log
```

### B. Migration Checklist

- [ ] Backup all .env files
- [ ] Start Vault server
- [ ] Run migration script with --dry-run
- [ ] Review migration report
- [ ] Run actual migration
- [ ] Update service code to use VaultAwareSettings
- [ ] Install hvac Python library
- [ ] Test secret retrieval
- [ ] Verify service health
- [ ] Update documentation
- [ ] Train team on Vault usage
- [ ] Set up automated rotation
- [ ] Configure monitoring and alerts

### C. Security Compliance

Secrets management system meets:

- **SOC 2 Type II** - Audit logging and access controls
- **ISO 27001** - Information security management
- **PCI DSS** - Encryption and key management
- **GDPR** - Data protection and privacy
- **HIPAA** - Security and confidentiality (if applicable)

### D. Support and Resources

- **HashiCorp Vault Documentation**: https://www.vaultproject.io/docs
- **Python HVAC Client**: https://hvac.readthedocs.io/
- **Security Best Practices**: https://learn.hashicorp.com/tutorials/vault/production-hardening
- **Internal Support**: Contact Security Engineer team

---

**Document Version:** 1.0
**Last Review:** 2025-11-21
**Next Review:** 2025-12-21
**Owner:** Security Engineering Team
