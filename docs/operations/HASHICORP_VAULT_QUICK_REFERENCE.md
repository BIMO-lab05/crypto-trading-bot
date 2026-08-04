# HashiCorp Vault - Quick Reference Guide

**Quick access guide for daily operations**

---

## Quick Start

### Start Vault

```bash
cd infrastructure
docker-compose --profile security up -d vault
```

### Set Environment

```bash
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='dev-only-token'
```

### Verify Running

```bash
vault status
```

---

## Common Operations

### Read Secrets

```bash
# List all secrets
vault kv list secret/

# Read specific secret
vault kv get secret/bybit-connector/bybit

# Read as JSON
vault kv get -format=json secret/bybit-connector/bybit | jq

# Get specific key
vault kv get -field=BYBIT_API_KEY secret/bybit-connector/bybit
```

### Write Secrets

```bash
# Write new secret
vault kv put secret/my-service/config \
  api_key=abc123 \
  api_secret=xyz789

# Update existing secret
vault kv patch secret/my-service/config \
  new_key=new_value
```

### Delete Secrets

```bash
# Soft delete (can be recovered)
vault kv delete secret/my-service/config

# Permanent delete
vault kv destroy -versions=1,2,3 secret/my-service/config
vault kv metadata delete secret/my-service/config
```

---

## Python Usage

### Basic Usage

```python
from shared.vault_client import VaultClient

# Initialize client
vault = VaultClient()

# Read secret
creds = vault.read_secret('bybit-connector/bybit')
api_key = creds['BYBIT_API_KEY']

# Write secret
vault.write_secret('my-service/config', {
    'api_key': 'abc123',
    'api_secret': 'xyz789'
})
```

### Using with Configuration

```python
from shared.vault_config import VaultAwareSettings
from pydantic import Field

class MyServiceConfig(VaultAwareSettings):
    service_name: str = Field(default="my-service")

    @property
    def api_key(self) -> str:
        return self.get_vault_secret(
            path=f"{self.service_name}/config",
            key="api_key",
            fallback_env="API_KEY"
        )

# Usage
config = MyServiceConfig()
print(config.api_key)  # Loaded from Vault
```

---

## Secret Rotation

### Rotate Bybit API Keys

```bash
# 1. Generate new key at https://testnet.bybit.com/
# 2. Run rotation script

cd infrastructure/scripts
python rotate_secrets.py bybit \
  --bybit-api-key "NEW_KEY" \
  --bybit-api-secret "NEW_SECRET" \
  --testnet
```

### Rotate Database Credentials

```bash
# Automatic rotation (uses dynamic credentials)
python rotate_secrets.py database
```

### Rotate JWT Secret

```bash
# Rotate JWT signing secret
python rotate_secrets.py jwt
```

---

## Troubleshooting

### Vault Not Responding

```bash
# Check if running
docker ps | grep vault

# Check logs
docker logs crypto-bot-vault

# Restart Vault
docker-compose restart vault
```

### Permission Denied

```bash
# Check token
vault token lookup

# Check policy
vault policy read my-service

# Verify token has correct policy
vault token capabilities secret/path/to/secret
```

### Secret Not Found

```bash
# List secrets in path
vault kv list secret/my-service/

# Check path spelling
vault kv get secret/my-service/config

# Verify secret was migrated
cat backups/env_files/*/migration_report.json
```

---

## Token Management

### Create Service Token

```bash
# Create token with policy
vault token create \
  -policy=trading-engine \
  -period=24h \
  -format=json
```

### Renew Token

```bash
# Renew current token
vault token renew

# Renew specific token
vault token renew <token-id>
```

### Revoke Token

```bash
# Revoke specific token
vault token revoke <token-id>

# Revoke all tokens for a service
vault token revoke -accessor <accessor-id>
```

---

## Policies

### List Policies

```bash
vault policy list
```

### Read Policy

```bash
vault policy read trading-engine
```

### Create/Update Policy

```bash
# Write policy from file
vault policy write my-policy policy.hcl

# Example policy content (policy.hcl):
cat > policy.hcl << EOF
path "secret/data/my-service/*" {
  capabilities = ["read", "list"]
}
EOF
```

---

## Audit Logs

### View Audit Log

```bash
# Real-time monitoring
tail -f /var/log/vault/audit.log | jq

# Search for specific service
jq 'select(.auth.display_name == "trading-engine")' \
  /var/log/vault/audit.log

# Find failed operations
jq 'select(.response.auth.error != null)' \
  /var/log/vault/audit.log
```

### Analyze Access Patterns

```bash
# Count accesses by service
jq -r '.auth.display_name' /var/log/vault/audit.log | \
  sort | uniq -c | sort -rn

# List accessed secrets
jq -r 'select(.request.operation == "read") | .request.path' \
  /var/log/vault/audit.log | sort | uniq -c
```

---

## Database Dynamic Credentials

### Generate Credentials

```bash
# Generate new database credentials
vault read database/creds/trading-bot-role

# Output:
# Key                Value
# ---                -----
# lease_id           database/creds/trading-bot-role/abc123...
# lease_duration     1h
# username           v-token-trading-bot-abc123
# password           A1b2C3d4E5f6G7h8
```

### Revoke Credentials

```bash
# Revoke specific lease
vault lease revoke database/creds/trading-bot-role/abc123...

# Revoke all for role
vault lease revoke -prefix database/creds/trading-bot-role/
```

---

## Migration

### Migrate Secrets

```bash
cd infrastructure/scripts

# Dry run first
python migrate_secrets_to_vault.py --dry-run

# Actual migration
python migrate_secrets_to_vault.py --verify

# Check migration report
cat backups/env_files/*/migration_report.json
```

### Restore from Backup

```bash
# Restore .env files from backup
cd backups/env_files/
ls -la  # Find backup date

# Copy back
cp -r 20251121_120000/.env ../../services/bybit-connector/
```

---

## Health Checks

### Vault Health

```bash
# HTTP check
curl http://localhost:8200/v1/sys/health

# CLI check
vault status

# Python check
python3 << EOF
from shared.vault_client import VaultClient
vault = VaultClient()
print(vault.health_check())
EOF
```

### Service Health

```bash
# Check service can connect to Vault
curl http://localhost:8001/health

# View service logs
docker logs -f crypto-bot-bybit-connector
```

---

## Emergency Procedures

### Vault Sealed

```bash
# Unseal with 3 keys (production only)
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>

# Verify unsealed
vault status
```

### Token Expired

```bash
# Use root token
export VAULT_TOKEN='<root-token>'

# Generate new service token
vault token create -policy=trading-engine -period=24h

# Update service .env
echo "VAULT_TOKEN=<new-token>" >> services/trading-engine/.env

# Restart service
docker-compose restart trading-engine
```

### Compromised Secret

```bash
# 1. Rotate immediately
python rotate_secrets.py <type>

# 2. Review audit logs
jq 'select(.request.path == "secret/data/compromised/path")' \
  /var/log/vault/audit.log

# 3. Revoke related tokens
vault token revoke <token>

# 4. Update access policies
vault policy write service-name updated-policy.hcl
```

---

## Useful Aliases

Add to your `.bashrc` or `.zshrc`:

```bash
# Vault aliases
alias v='vault'
alias vs='vault status'
alias vl='vault kv list secret/'
alias vg='vault kv get'
alias vp='vault kv put'

# Export Vault env
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='dev-only-token'

# Quick functions
vsecret() { vault kv get secret/$1; }
vread() { vault kv get -field=$2 secret/$1; }
vwrite() { vault kv put secret/$1 $2; }

# Example usage:
# vsecret bybit-connector/bybit
# vread bybit-connector/bybit BYBIT_API_KEY
# vwrite my-service/test key=value
```

---

## Important Paths

### Project Files

```
/mnt/d/Bimo_max/crypto-trading-bot/
├── infrastructure/vault/          # Vault config
├── infrastructure/scripts/        # Management scripts
├── shared/vault_*.py              # Python libraries
├── docs/security/                 # Documentation
└── backups/env_files/            # .env backups
```

### Vault Paths

```
secret/                            # KV v2 secrets
├── bybit-connector/
├── trading-engine/
├── portfolio-manager/
└── market-data-service/

database/                          # Dynamic DB creds
├── config/postgres
├── config/timescaledb
└── creds/<role-name>

transit/                           # Encryption
└── encrypt/<key-name>

pki/                              # Certificates
└── cert/<cert-name>
```

---

## Quick Commands Cheat Sheet

| Task | Command |
|------|---------|
| Start Vault | `docker-compose --profile security up -d vault` |
| Stop Vault | `docker-compose stop vault` |
| Vault status | `vault status` |
| List secrets | `vault kv list secret/` |
| Read secret | `vault kv get secret/path` |
| Write secret | `vault kv put secret/path key=value` |
| Create token | `vault token create -policy=name` |
| Rotate DB creds | `python rotate_secrets.py database` |
| View audit log | `tail -f /var/log/vault/audit.log \| jq` |
| Health check | `curl localhost:8200/v1/sys/health` |
| Migration | `python migrate_secrets_to_vault.py` |

---

## Support

- **Documentation:** `docs/security/SECRETS_MANAGEMENT.md`
- **Report:** `SECRETS_MANAGEMENT_IMPLEMENTATION_REPORT.md`
- **Vault Docs:** https://www.vaultproject.io/docs
- **HVAC Client:** https://hvac.readthedocs.io/
- **Security Team:** security@company.com

---

**Last Updated:** 2025-11-21
**Version:** 1.0
