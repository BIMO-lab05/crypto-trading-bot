# Security Documentation

**Quick Start Guide for Production Security**

This directory contains all security documentation for the Crypto Trading Bot infrastructure.

---

## Quick Links

| Document | Purpose | Audience |
|----------|---------|----------|
| [SECURITY_IMPLEMENTATION_REPORT.md](./SECURITY_IMPLEMENTATION_REPORT.md) | Complete security implementation overview | All stakeholders |
| [PASSWORD_ROTATION.md](./PASSWORD_ROTATION.md) | Password rotation procedures | Operations team |
| [VAULT_INTEGRATION.md](./VAULT_INTEGRATION.md) | Vault setup and usage guide | Development team |

---

## Quick Start

### 1. Run Security Audit

```bash
# Full security scan
cd /mnt/d/Bimo_max/crypto-trading-bot
./infrastructure/scripts/security_audit.sh

# View report
cat logs/security/audits/security_audit_*.md
```

### 2. Setup Vault (Development)

```bash
# Quick setup for local development
./infrastructure/vault/setup_vault.sh dev

# Environment variables
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="dev-only-token"
```

### 3. Rotate Passwords

```bash
# Automatic rotation (recommended)
./infrastructure/scripts/rotate_passwords.sh --automatic

# Verify rotation
./infrastructure/scripts/rotate_passwords.sh --verify
```

---

## Security Checklist

### Development Environment

- [ ] Run security audit weekly
- [ ] Use development Vault mode
- [ ] Never commit secrets to git
- [ ] Keep dependencies updated
- [ ] Review audit findings

### Staging Environment

- [ ] Run security audit before each deployment
- [ ] Use production Vault configuration (without auto-unseal)
- [ ] Enable audit logging
- [ ] Test password rotation
- [ ] Verify backup procedures

### Production Environment

- [ ] **CRITICAL:** Enable TLS for Vault
- [ ] Configure auto-unseal (AWS KMS/Azure/GCP)
- [ ] Enable comprehensive audit logging
- [ ] Setup monitoring and alerting
- [ ] Test disaster recovery procedures
- [ ] Schedule quarterly password rotation
- [ ] Maintain security documentation
- [ ] Regular penetration testing
- [ ] Compliance reporting enabled

---

## Emergency Procedures

### Vault Sealed

```bash
# Check status
vault status

# Unseal with 3 keys
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>
```

### Password Rollback

```bash
# Emergency rollback
./infrastructure/scripts/rotate_passwords.sh --rollback

# Verify services
./infrastructure/scripts/rotate_passwords.sh --verify
```

### Security Incident

1. **Immediate Actions:**
   - Seal Vault: `vault operator seal`
   - Rotate all credentials
   - Review audit logs
   - Isolate affected services

2. **Investigation:**
   - Run security audit
   - Check access logs
   - Review recent changes
   - Document findings

3. **Recovery:**
   - Rotate compromised credentials
   - Update policies
   - Implement fixes
   - Test recovery

4. **Post-Incident:**
   - Complete incident report
   - Update procedures
   - Team review
   - Implement improvements

---

## Common Tasks

### Get Secret from Vault

```bash
# CLI
vault kv get secret/database/postgres

# Python
from utils.vault_client import VaultClient
vault = VaultClient()
secret = vault.get_secret("database/postgres")
```

### Rotate Service Token

```bash
# Create new token
vault token create -policy=trading-engine -period=24h

# Update service .env
echo "VAULT_TOKEN=<new-token>" >> services/trading-engine/.env

# Restart service
docker-compose restart trading-engine
```

### Check Audit Logs

```bash
# View recent audit events
tail -f /var/log/vault/audit.log | jq

# Search for specific secret access
grep "database/postgres" /var/log/vault/audit.log | jq
```

### Backup Vault Data

```bash
# Snapshot (Raft only)
vault operator raft snapshot save vault-backup.snap

# Export KV secrets
vault kv export -format=json secret/ > secrets-backup.json

# Encrypt backup
gpg -c vault-backup.snap
```

---

## Monitoring

### Key Metrics

| Metric | Threshold | Action |
|--------|-----------|--------|
| Vault Sealed | Always unsealed | Immediate unseal |
| Token Expiry | < 1 hour | Renew token |
| Failed Logins | > 5 in 1 hour | Investigate |
| Audit Log Size | > 1GB | Rotate logs |
| Backup Age | > 24 hours | Create backup |

### Health Checks

```bash
# Vault health
curl http://localhost:8200/v1/sys/health | jq

# Service connectivity
for service in postgres timescaledb redis rabbitmq; do
    echo -n "$service: "
    docker exec crypto-bot-$service echo "OK" 2>/dev/null || echo "FAILED"
done
```

---

## Compliance

### SOC 2 Requirements

- [x] Encryption at rest (Vault storage)
- [x] Encryption in transit (TLS configured)
- [x] Access control (RBAC policies)
- [x] Audit logging (Vault audit device)
- [x] Password rotation (Automated)
- [x] Credential management (Centralized)

### ISO 27001 Requirements

- [x] Information security policy
- [x] Access control policy
- [x] Cryptography controls
- [x] Audit logging and monitoring
- [x] Incident management procedures
- [x] Business continuity planning

### GDPR Compliance

- [x] Data encryption
- [x] Access controls
- [x] Audit trail
- [x] Data retention policies
- [x] Right to erasure support

---

## Training Resources

### For Developers

1. **Getting Started:**
   - Read [VAULT_INTEGRATION.md](./VAULT_INTEGRATION.md)
   - Setup local Vault environment
   - Practice secret retrieval
   - Implement VaultClient in service

2. **Best Practices:**
   - Never log secrets
   - Use environment variables
   - Implement token renewal
   - Handle errors gracefully

3. **Code Examples:**
   - See `/shared/utils/vault_client.py`
   - Check service integration examples
   - Review test cases

### For Operations

1. **Day 1:**
   - Read [PASSWORD_ROTATION.md](./PASSWORD_ROTATION.md)
   - Understand rotation procedures
   - Practice rollback procedures

2. **Week 1:**
   - Learn Vault CLI
   - Practice token management
   - Test backup/restore

3. **Month 1:**
   - Master troubleshooting
   - Understand monitoring
   - Practice incident response

### For Security Team

1. **Initial Setup:**
   - Review architecture
   - Configure policies
   - Setup monitoring
   - Enable audit logging

2. **Ongoing:**
   - Weekly security audits
   - Monthly policy reviews
   - Quarterly penetration tests
   - Annual security assessments

---

## Support

### Documentation

- **Full Implementation Report:** [SECURITY_IMPLEMENTATION_REPORT.md](./SECURITY_IMPLEMENTATION_REPORT.md)
- **Password Procedures:** [PASSWORD_ROTATION.md](./PASSWORD_ROTATION.md)
- **Vault Guide:** [VAULT_INTEGRATION.md](./VAULT_INTEGRATION.md)
- **Official Vault Docs:** https://www.vaultproject.io/docs

### Contact

- **Security Team:** security@cryptobot.local
- **Infrastructure:** infra@cryptobot.local
- **On-Call:** oncall@cryptobot.local
- **Emergency:** +1-555-SECURITY

### Escalation

1. **Level 1:** Team lead review
2. **Level 2:** Security team investigation
3. **Level 3:** Executive escalation
4. **Level 4:** External security consultant

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-11-19 | Initial security implementation | Security Engineer Agent |

---

## License

Internal Use Only - Confidential

Copyright (c) 2025 Crypto Trading Bot Team. All rights reserved.

---

**Last Updated:** 2025-11-19
**Maintained By:** Security Team
**Review Cycle:** Quarterly
