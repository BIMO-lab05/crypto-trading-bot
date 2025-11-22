# HashiCorp Vault Integration Guide

**Document Version:** 1.0
**Last Updated:** 2025-11-19
**Status:** Production Ready
**Security Classification:** Internal

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Service Integration](#service-integration)
6. [Migration from .env](#migration-from-env)
7. [Operations](#operations)
8. [Troubleshooting](#troubleshooting)
9. [Best Practices](#best-practices)

---

## Overview

### Why Vault?

HashiCorp Vault provides centralized secrets management for the Crypto Trading Bot, offering:

**Security Benefits:**
- Centralized secret storage with encryption at rest
- Dynamic secret generation (database credentials)
- Automatic secret rotation
- Detailed audit logging
- Fine-grained access control (policies)
- Encryption as a service (Transit engine)

**Operational Benefits:**
- No hardcoded secrets in code
- Automatic credential renewal
- Secret versioning and rollback
- Multi-environment support (dev/staging/prod)
- Compliance and audit trail
- High availability support

### Current State vs. Target State

| Aspect | Before Vault | With Vault |
|--------|--------------|------------|
| Secret Storage | `.env` files | Encrypted Vault storage |
| Database Passwords | Static, manually rotated | Dynamic, auto-rotating |
| API Keys | Environment variables | Vault KV store |
| Encryption Keys | Application-managed | Vault Transit engine |
| Access Control | File permissions | Vault policies |
| Audit Trail | None | Complete audit log |
| Rotation | Manual (90 days) | Automatic (1-24 hours) |

---

## Architecture

### Vault Deployment Topology

```
┌─────────────────────────────────────────────────────────────┐
│                    Crypto Trading Bot                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │Trading Engine│  │Market Data   │  │Portfolio Mgr │    │
│  │              │  │Service       │  │              │    │
│  │ Token: TE-1  │  │ Token: MD-1  │  │ Token: PM-1  │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │                                │
├────────────────────────────┼────────────────────────────────┤
│                            ▼                                │
│              ┌─────────────────────────┐                   │
│              │   Vault Client Library   │                   │
│              │   (vault_client.py)      │                   │
│              └─────────────┬────────────┘                   │
│                            │                                │
└────────────────────────────┼────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   HashiCorp Vault        │
              │   127.0.0.1:8200         │
              ├──────────────────────────┤
              │ ┌────────────────────┐   │
              │ │  KV Secrets v2     │   │
              │ ├────────────────────┤   │
              │ │ secret/database/*  │   │
              │ │ secret/redis       │   │
              │ │ secret/rabbitmq    │   │
              │ │ secret/bybit       │   │
              │ └────────────────────┘   │
              │                          │
              │ ┌────────────────────┐   │
              │ │  Database Engine   │   │
              │ ├────────────────────┤   │
              │ │ Dynamic Postgres   │   │
              │ │ Dynamic Timescale  │   │
              │ └────────────────────┘   │
              │                          │
              │ ┌────────────────────┐   │
              │ │  Transit Engine    │   │
              │ ├────────────────────┤   │
              │ │ trading-data key   │   │
              │ │ portfolio-data key │   │
              │ └────────────────────┘   │
              └──────────────────────────┘
```

### Secret Hierarchy

```
secret/
├── database/
│   ├── postgres          # PostgreSQL connection details
│   └── timescaledb       # TimescaleDB connection details
├── redis                 # Redis connection details
├── rabbitmq              # RabbitMQ connection details
├── bybit                 # Bybit API credentials
├── api/
│   ├── jwt-secret        # JWT signing key
│   └── encryption-key    # Application encryption key
└── monitoring/
    ├── prometheus        # Prometheus credentials
    └── grafana           # Grafana admin credentials
```

### Access Control Matrix

| Service | Policies | Secrets Access | Database Roles | Transit Keys |
|---------|----------|----------------|----------------|--------------|
| Trading Engine | `trading-engine` | postgres, redis, rabbitmq, bybit | `trading-bot-role` | trading-data |
| Market Data | `market-data` | timescaledb, redis | `market-data-role` | - |
| Portfolio Manager | `portfolio-manager` | postgres, redis | `trading-bot-role` | portfolio-data |
| Bybit Connector | `bybit-connector` | bybit, redis | - | - |
| Technical Analysis | `technical-analysis` | redis, timescaledb | `market-data-role` | - |
| API Gateway | `api-gateway` | jwt-secret, redis | - | - |
| Admin | `admin` | ALL | ALL | ALL |

---

## Installation

### Prerequisites

- Docker and Docker Compose (for containerized deployment)
- OR Vault binary installed (for standalone deployment)
- Network access to Vault server (port 8200)
- Sufficient disk space for Vault data (minimum 1GB)

### Method 1: Automatic Setup (Recommended)

```bash
# Navigate to infrastructure directory
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure

# Run Vault setup script (development mode)
./vault/setup_vault.sh dev

# Expected output:
# ╔═══════════════════════════════════════════════════════════╗
# ║   HashiCorp Vault Setup for Crypto Trading Bot          ║
# ║   Secrets Management & Dynamic Credentials               ║
# ╚═══════════════════════════════════════════════════════════╝
#
# [INFO] Setting up Vault in dev mode...
# [SUCCESS] Vault found: v1.15.4
# [INFO] Starting Vault in development mode...
# [SUCCESS] Vault is ready (PID: 12345)
# ... (continues)
# [SUCCESS] Vault setup complete!

# Set environment variables
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="dev-only-token-change-in-prod"  # Development only!
```

### Method 2: Docker Compose Integration

```bash
# Add Vault to docker-compose.yml
docker-compose up -d vault

# Wait for Vault to be healthy
docker-compose ps vault

# Initialize Vault
docker-compose exec vault vault operator init -key-shares=5 -key-threshold=3 > vault-keys.txt

# Unseal Vault (use 3 out of 5 unseal keys)
docker-compose exec vault vault operator unseal <key1>
docker-compose exec vault vault operator unseal <key2>
docker-compose exec vault vault operator unseal <key3>

# Authenticate with root token
export VAULT_TOKEN="<root-token-from-vault-keys.txt>"

# Run configuration
./vault/setup_vault.sh prod
```

### Method 3: Production Installation

```bash
# Install Vault binary
wget https://releases.hashicorp.com/vault/1.15.4/vault_1.15.4_linux_amd64.zip
unzip vault_1.15.4_linux_amd64.zip
sudo mv vault /usr/local/bin/
sudo chmod +x /usr/local/bin/vault

# Verify installation
vault version

# Create Vault user and directories
sudo useradd --system --home /etc/vault.d --shell /bin/false vault
sudo mkdir -p /opt/vault/data /var/log/vault
sudo chown -R vault:vault /opt/vault /var/log/vault

# Create systemd service
sudo cat > /etc/systemd/system/vault.service <<'EOF'
[Unit]
Description=HashiCorp Vault
Documentation=https://www.vaultproject.io/docs/
Requires=network-online.target
After=network-online.target

[Service]
User=vault
Group=vault
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=yes
PrivateDevices=yes
SecureBits=keep-caps
AmbientCapabilities=CAP_IPC_LOCK
Capabilities=CAP_IPC_LOCK+ep
CapabilityBoundingSet=CAP_SYSLOG CAP_IPC_LOCK
NoNewPrivileges=yes
ExecStart=/usr/local/bin/vault server -config=/etc/vault.d/vault-config.hcl
ExecReload=/bin/kill --signal HUP $MAINPID
KillMode=process
KillSignal=SIGINT
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
LimitNOFILE=65536
LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
EOF

# Copy configuration
sudo cp infrastructure/vault/vault-config.hcl /etc/vault.d/

# Start Vault
sudo systemctl enable vault
sudo systemctl start vault

# Check status
sudo systemctl status vault
```

---

## Configuration

### Environment Variables

Add to service `.env` files:

```bash
# Vault Configuration
VAULT_ADDR=http://127.0.0.1:8200
VAULT_TOKEN=<service-specific-token>
VAULT_NAMESPACE=crypto-trading-bot  # Optional

# Cache settings
VAULT_CACHE_TTL=300  # Secret cache TTL in seconds

# SSL/TLS (production)
VAULT_CACERT=/path/to/ca.pem        # CA certificate
VAULT_CLIENT_CERT=/path/to/cert.pem  # Client certificate
VAULT_CLIENT_KEY=/path/to/key.pem    # Client private key
VAULT_SKIP_VERIFY=false              # Verify SSL certificates
```

### Service Token Distribution

```bash
# Extract service tokens (created during setup)
TOKEN_DIR="/mnt/d/Bimo_max/crypto-trading-bot/.vault-keys/service-tokens"

# Update service environment files
echo "VAULT_TOKEN=$(cat ${TOKEN_DIR}/trading-engine-token)" >> services/trading-engine/.env
echo "VAULT_TOKEN=$(cat ${TOKEN_DIR}/market-data-token)" >> services/market-data-service/.env
echo "VAULT_TOKEN=$(cat ${TOKEN_DIR}/portfolio-manager-token)" >> services/portfolio-manager/.env
echo "VAULT_TOKEN=$(cat ${TOKEN_DIR}/bybit-connector-token)" >> services/bybit-connector/.env
```

---

## Service Integration

### Step 1: Install Dependencies

Add to service `requirements.txt`:

```
hvac==2.1.0              # HashiCorp Vault client
requests==2.31.0         # HTTP library (hvac dependency)
urllib3==2.1.0           # URL library
```

### Step 2: Update Service Code

**Example: Trading Engine Integration**

```python
#!/usr/bin/env python3
"""
Trading Engine with Vault Integration
"""

import os
import sys
from pathlib import Path

# Add shared utilities to path
sys.path.append(str(Path(__file__).parent.parent.parent / "shared"))

from utils.vault_client import VaultClient, VaultClientError
import psycopg2
from redis import Redis
import pika

class TradingEngine:
    def __init__(self):
        """Initialize trading engine with Vault secrets"""
        self.vault = VaultClient()
        self._initialize_connections()

    def _initialize_connections(self):
        """Initialize service connections using Vault secrets"""
        try:
            # Get PostgreSQL connection details
            pg_config = self.vault.get_secret("database/postgres")

            self.pg_conn = psycopg2.connect(
                host=pg_config["host"],
                port=pg_config["port"],
                database=pg_config["database"],
                user=pg_config["username"],
                password=pg_config["password"],
            )

            # Get Redis connection details
            redis_config = self.vault.get_secret("redis")

            self.redis = Redis(
                host=redis_config["host"],
                port=int(redis_config["port"]),
                password=redis_config["password"],
                decode_responses=True,
            )

            # Get RabbitMQ connection details
            rabbitmq_config = self.vault.get_secret("rabbitmq")

            credentials = pika.PlainCredentials(
                rabbitmq_config["username"],
                rabbitmq_config["password"],
            )

            self.rabbitmq_conn = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=rabbitmq_config["host"],
                    port=int(rabbitmq_config["port"]),
                    virtual_host=rabbitmq_config["vhost"],
                    credentials=credentials,
                )
            )

            # Get Bybit API credentials
            bybit_config = self.vault.get_secret("bybit")

            self.bybit_api_key = bybit_config["api_key"]
            self.bybit_api_secret = bybit_config["api_secret"]
            self.bybit_testnet = bybit_config.get("testnet", "true") == "true"

            print("All connections initialized successfully")

        except VaultClientError as e:
            print(f"Failed to get secrets from Vault: {e}")
            raise

    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive trading data using Vault Transit"""
        return self.vault.encrypt("trading-data", data)

    def decrypt_sensitive_data(self, ciphertext: str) -> str:
        """Decrypt sensitive trading data using Vault Transit"""
        return self.vault.decrypt("trading-data", ciphertext)

# Example usage
if __name__ == "__main__":
    engine = TradingEngine()

    # Test encryption
    sensitive = "order_id_12345"
    encrypted = engine.encrypt_sensitive_data(sensitive)
    decrypted = engine.decrypt_sensitive_data(encrypted)

    assert sensitive == decrypted
    print("Encryption test passed!")
```

### Step 3: Dynamic Database Credentials

**Example: Using Dynamic Credentials**

```python
from utils.vault_client import VaultClient
import psycopg2

class DatabaseConnection:
    def __init__(self):
        self.vault = VaultClient()
        self.conn = None
        self.creds = None

    def connect(self):
        """Connect using dynamic credentials"""
        # Get fresh credentials from Vault
        self.creds = self.vault.get_database_credentials("trading-bot-role")

        # Connect to database
        self.conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="cryptobot",
            user=self.creds["username"],
            password=self.creds["password"],
        )

        print(f"Connected as: {self.creds['username']}")
        return self.conn

    def renew(self):
        """Renew credentials before expiry"""
        if self.conn:
            self.conn.close()

        self.connect()

# Usage with automatic renewal
import threading
import time

db = DatabaseConnection()
db.connect()

# Renew credentials every 30 minutes
def renew_credentials():
    while True:
        time.sleep(1800)  # 30 minutes
        db.renew()

renewal_thread = threading.Thread(target=renew_credentials, daemon=True)
renewal_thread.start()
```

### Step 4: Health Check Integration

```python
from fastapi import FastAPI
from utils.vault_client import VaultClient

app = FastAPI()

@app.get("/health")
async def health_check():
    """Health check endpoint with Vault status"""
    vault = VaultClient()
    vault_health = vault.health_check()

    return {
        "status": "healthy",
        "vault": {
            "connected": vault_health.get("authenticated", False),
            "addr": vault_health.get("vault_addr"),
            "sealed": vault_health.get("sealed", True),
        }
    }
```

---

## Migration from .env

### Pre-Migration Checklist

- [ ] Vault is installed and running
- [ ] Vault is initialized and unsealed
- [ ] Service policies are created
- [ ] Service tokens are generated
- [ ] Backup of current `.env` files created
- [ ] Test environment configured
- [ ] Rollback plan documented

### Migration Process

#### Phase 1: Parallel Operation (Week 1)

Run both .env and Vault simultaneously:

```python
# Hybrid configuration - Read from Vault, fallback to .env
import os
from utils.vault_client import VaultClient, VaultClientError

def get_config(vault_path: str, env_var: str) -> str:
    """Get config from Vault with .env fallback"""
    try:
        vault = VaultClient()
        return vault.get_secret(vault_path)
    except VaultClientError as e:
        print(f"Vault unavailable, using .env: {e}")
        return os.getenv(env_var)

# Usage
postgres_config = get_config("database/postgres", "POSTGRES_PASSWORD")
```

#### Phase 2: Vault Primary (Week 2)

Switch to Vault as primary, .env as backup:

```python
# Vault primary configuration
from utils.vault_client import VaultClient

vault = VaultClient()

# Required: Vault must be available
postgres_config = vault.get_secret("database/postgres")
```

#### Phase 3: Vault Only (Week 3)

Remove all .env files and use Vault exclusively:

```bash
# Archive old .env files
mkdir -p infrastructure/backups/env-archive
find . -name ".env" -type f -exec cp {} infrastructure/backups/env-archive/ \;

# Remove .env files from services (keep .env.example)
find services/ -name ".env" -type f -delete

# Update .gitignore to prevent future commits
echo "# All secrets now in Vault" >> .gitignore
```

### Migration Script

```bash
#!/bin/bash
# migrate_to_vault.sh - Migrate secrets from .env to Vault

set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export VAULT_ADDR

echo "Migrating secrets to Vault..."

# Read secrets from .env files
source infrastructure/.env

# Store in Vault
vault kv put secret/database/postgres \
    username="${POSTGRES_USER}" \
    password="${POSTGRES_PASSWORD}" \
    host="localhost" \
    port="5432" \
    database="${POSTGRES_DB}"

vault kv put secret/database/timescaledb \
    username="${TIMESCALE_USER}" \
    password="${TIMESCALE_PASSWORD}" \
    host="localhost" \
    port="5433" \
    database="${TIMESCALE_DB}"

vault kv put secret/redis \
    password="${REDIS_PASSWORD}" \
    host="localhost" \
    port="6379"

vault kv put secret/rabbitmq \
    username="${RABBITMQ_USER}" \
    password="${RABBITMQ_PASSWORD}" \
    host="localhost" \
    port="5672" \
    vhost="${RABBITMQ_VHOST}"

echo "Migration complete! Verify with:"
echo "vault kv get secret/database/postgres"
```

### Verification

```bash
# Test each service can retrieve secrets
for service in trading-engine market-data-service portfolio-manager; do
    echo "Testing ${service}..."
    cd services/${service}
    python3 -c "
from utils.vault_client import VaultClient
vault = VaultClient()
print(vault.get_secret('database/postgres'))
"
    echo "✓ ${service} can access Vault"
done
```

---

## Operations

### Daily Operations

#### Check Vault Status

```bash
# Vault server status
vault status

# Health check
curl http://127.0.0.1:8200/v1/sys/health | jq

# Check seal status
vault operator key-status
```

#### Read Secrets

```bash
# Get secret
vault kv get secret/database/postgres

# Get specific field
vault kv get -field=password secret/database/postgres

# List secrets
vault kv list secret/database
```

#### Update Secrets

```bash
# Update secret (creates new version)
vault kv put secret/database/postgres password="new_password"

# Patch secret (update specific fields)
vault kv patch secret/database/postgres password="new_password"

# Delete latest version
vault kv delete secret/database/postgres

# Permanently delete
vault kv destroy -versions=1,2 secret/database/postgres
```

### Token Management

#### Create Service Token

```bash
# Create token with policy
vault token create \
    -policy=trading-engine \
    -period=24h \
    -display-name="trading-engine" \
    -format=json

# Create token with TTL
vault token create \
    -policy=market-data \
    -ttl=8h \
    -renewable=true
```

#### Renew Token

```bash
# Renew own token
vault token renew

# Renew specific token
vault token renew <token-id>

# Check token info
vault token lookup
```

#### Revoke Token

```bash
# Revoke specific token
vault token revoke <token-id>

# Revoke all tokens for accessor
vault token revoke -accessor <accessor-id>
```

### Backup and Restore

#### Backup Vault Data

```bash
# Snapshot (Raft storage only)
vault operator raft snapshot save vault-backup-$(date +%Y%m%d).snap

# Export secrets (KV only)
vault kv export -format=json secret/ > secrets-backup-$(date +%Y%m%d).json

# Backup config
cp infrastructure/vault/vault-config.hcl vault-config-backup-$(date +%Y%m%d).hcl
```

#### Restore Vault Data

```bash
# Restore snapshot
vault operator raft snapshot restore vault-backup-20251119.snap

# Import secrets
vault kv import secret/ < secrets-backup-20251119.json
```

### Monitoring

#### Enable Audit Logging

```bash
# Enable file audit device
vault audit enable file file_path=/var/log/vault/audit.log

# Enable syslog audit device
vault audit enable syslog tag="vault" facility="LOCAL7"

# List audit devices
vault audit list
```

#### View Audit Logs

```bash
# Tail audit log
tail -f /var/log/vault/audit.log | jq

# Search for specific operations
grep "database/postgres" /var/log/vault/audit.log | jq

# Count operations by type
cat /var/log/vault/audit.log | jq -r '.request.operation' | sort | uniq -c
```

### Maintenance

#### Seal/Unseal Operations

```bash
# Seal Vault (requires operator privileges)
vault operator seal

# Unseal Vault (requires unseal keys)
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>

# Generate new root token
vault operator generate-root
```

#### Rotate Encryption Key

```bash
# Rotate encryption key
vault operator rotate

# Check rotation status
vault operator key-status
```

---

## Troubleshooting

### Common Issues

#### Issue 1: Vault Sealed

**Symptoms:**
```
Error: Vault is sealed
```

**Solution:**
```bash
# Check seal status
vault status

# Unseal with 3 keys
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>

# Verify
vault status | grep Sealed
```

#### Issue 2: Permission Denied

**Symptoms:**
```
Error: permission denied
```

**Solution:**
```bash
# Check token capabilities
vault token capabilities secret/database/postgres

# List token policies
vault token lookup | grep policies

# Verify policy allows operation
vault policy read trading-engine

# If needed, update policy
vault policy write trading-engine /path/to/policy.hcl
```

#### Issue 3: Connection Refused

**Symptoms:**
```
Error: dial tcp 127.0.0.1:8200: connect: connection refused
```

**Solution:**
```bash
# Check if Vault is running
ps aux | grep vault

# Check Vault logs
tail -f /var/log/vault/vault.log

# Restart Vault
systemctl restart vault

# Verify listener
netstat -tulpn | grep 8200
```

#### Issue 4: Token Expired

**Symptoms:**
```
Error: permission denied (HTTP 403)
```

**Solution:**
```bash
# Check token TTL
vault token lookup | grep ttl

# Renew token (if renewable)
vault token renew

# Create new token
vault token create -policy=<policy-name>
```

### Debug Mode

```bash
# Enable debug logging
export VAULT_LOG_LEVEL=debug

# Test connection
vault status -format=json

# Test authentication
vault token lookup -format=json

# Test secret access
vault kv get -format=json secret/database/postgres
```

### Health Checks

```python
#!/usr/bin/env python3
"""Vault health check script"""

from utils.vault_client import VaultClient
import sys

def main():
    try:
        vault = VaultClient()

        # Health check
        health = vault.health_check()
        print(f"Vault Health: {health}")

        # Test secret retrieval
        secret = vault.get_secret("database/postgres")
        print("✓ Secret retrieval successful")

        # Test encryption
        ciphertext = vault.encrypt("trading-data", "test")
        plaintext = vault.decrypt("trading-data", ciphertext)
        assert plaintext == "test"
        print("✓ Encryption/decryption successful")

        return 0

    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

---

## Best Practices

### Security

1. **Never log secrets**
   ```python
   # BAD
   logger.info(f"Password: {password}")

   # GOOD
   logger.info("Password retrieved successfully")
   ```

2. **Use least privilege policies**
   - Grant minimum required permissions
   - Use separate tokens per service
   - Regularly review and update policies

3. **Enable audit logging**
   - Log all Vault operations
   - Monitor for anomalies
   - Retain logs per compliance requirements

4. **Use TLS in production**
   - Never disable TLS verification
   - Use valid certificates
   - Enforce minimum TLS 1.2

5. **Secure token storage**
   - Never commit tokens to git
   - Use environment variables
   - Rotate tokens regularly

### Operational

1. **Implement token renewal**
   ```python
   # Automatic token renewal
   import threading
   import time

   def renew_token_periodically(vault_client):
       while True:
           time.sleep(3600)  # 1 hour
           vault_client.renew_token()

   vault = VaultClient()
   renewal_thread = threading.Thread(
       target=renew_token_periodically,
       args=(vault,),
       daemon=True
   )
   renewal_thread.start()
   ```

2. **Use secret caching wisely**
   - Cache static secrets (5 minutes)
   - Don't cache dynamic credentials
   - Invalidate cache on errors

3. **Monitor Vault health**
   - Include in service health checks
   - Alert on Vault unavailability
   - Have fallback procedures

4. **Regular backups**
   - Daily snapshots
   - Test restore procedures
   - Store backups securely offsite

5. **Document everything**
   - Keep runbooks updated
   - Document policies and access
   - Maintain change log

### Development

1. **Use development mode locally**
   ```bash
   # Local development only!
   vault server -dev -dev-root-token-id="dev-token"
   ```

2. **Never use root token in code**
   - Create service-specific tokens
   - Use appropriate policies
   - Set reasonable TTLs

3. **Test with Vault unavailable**
   ```python
   # Graceful degradation
   try:
       vault = VaultClient()
       config = vault.get_secret("database/postgres")
   except VaultConnectionError:
       # Fallback to cached config
       config = load_from_cache()
   ```

4. **Version control policies**
   ```bash
   # Store policies in git
   git add infrastructure/vault/policies/
   git commit -m "Update Vault policies"
   ```

---

## Appendix

### A. Complete Policy Examples

**Trading Engine Policy:**
```hcl
# File: infrastructure/vault/policies/trading-engine.hcl

# PostgreSQL credentials
path "secret/data/database/postgres" {
  capabilities = ["read"]
}

# Dynamic database credentials
path "database/creds/trading-bot-role" {
  capabilities = ["read"]
}

# Redis credentials
path "secret/data/redis" {
  capabilities = ["read"]
}

# RabbitMQ credentials
path "secret/data/rabbitmq" {
  capabilities = ["read"]
}

# Bybit API credentials
path "secret/data/bybit" {
  capabilities = ["read"]
}

# Encryption/decryption
path "transit/encrypt/trading-data" {
  capabilities = ["update"]
}

path "transit/decrypt/trading-data" {
  capabilities = ["update"]
}

# Allow token renewal
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Allow token lookup
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
```

### B. Vault CLI Cheat Sheet

```bash
# Authentication
vault login <token>
vault login -method=userpass username=admin

# KV Operations
vault kv put secret/path key=value
vault kv get secret/path
vault kv get -field=key secret/path
vault kv delete secret/path
vault kv list secret/

# Token Operations
vault token create -policy=policy-name
vault token renew
vault token lookup
vault token revoke <token>

# Policy Operations
vault policy write policy-name policy.hcl
vault policy read policy-name
vault policy list
vault policy delete policy-name

# Secret Engine Operations
vault secrets enable kv-v2
vault secrets enable database
vault secrets enable transit
vault secrets list
vault secrets disable <path>

# Database Operations
vault write database/config/postgres plugin_name=postgresql-database-plugin ...
vault write database/roles/role-name db_name=postgres ...
vault read database/creds/role-name

# Transit Operations
vault write transit/keys/key-name type=aes256-gcm96
vault write transit/encrypt/key-name plaintext=<base64>
vault write transit/decrypt/key-name ciphertext=<vault-cipher>

# Audit Operations
vault audit enable file file_path=/var/log/vault/audit.log
vault audit list
vault audit disable <device>

# System Operations
vault status
vault operator init
vault operator unseal <key>
vault operator seal
vault operator rotate
```

### C. Environment Setup Script

```bash
#!/bin/bash
# setup_vault_env.sh - Setup Vault environment for service

SERVICE_NAME="$1"

if [ -z "$SERVICE_NAME" ]; then
    echo "Usage: $0 <service-name>"
    exit 1
fi

# Get service token
TOKEN=$(cat .vault-keys/service-tokens/${SERVICE_NAME}-token)

# Create service .env
cat > services/${SERVICE_NAME}/.env <<EOF
# Vault Configuration
VAULT_ADDR=http://127.0.0.1:8200
VAULT_TOKEN=${TOKEN}
VAULT_CACHE_TTL=300
EOF

echo "✓ Vault environment configured for ${SERVICE_NAME}"
```

### D. Related Documentation

- [PASSWORD_ROTATION.md](./PASSWORD_ROTATION.md) - Password rotation procedures
- [SECURITY_AUDIT.md](./SECURITY_AUDIT.md) - Security audit guide
- [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) - Incident response plan
- [Vault Official Documentation](https://www.vaultproject.io/docs)

---

**Document Control:**
- Version: 1.0
- Created: 2025-11-19
- Last Reviewed: 2025-11-19
- Next Review: 2026-02-19
- Owner: Security Team
- Classification: Internal
