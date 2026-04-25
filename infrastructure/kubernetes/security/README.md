# Kubernetes Security Configuration

## Overview

This directory contains comprehensive security hardening for the Crypto Trading Bot Kubernetes deployments. The configuration implements defense-in-depth security following Kubernetes best practices.

**Version**: 1.0
**Created**: 2025-12-12
**Last Updated**: 2025-12-12

## Table of Contents

1. [Security Architecture](#security-architecture)
2. [Components](#components)
3. [Quick Start](#quick-start)
4. [Secrets Management](#secrets-management)
5. [Pod Security](#pod-security)
6. [Network Policies](#network-policies)
7. [RBAC Configuration](#rbac-configuration)
8. [Deployment Instructions](#deployment-instructions)
9. [Rollback Procedures](#rollback-procedures)
10. [Security Validation](#security-validation)
11. [Troubleshooting](#troubleshooting)

## Security Architecture

```
+------------------------------------------------------------------+
|                        SECURITY LAYERS                            |
+------------------------------------------------------------------+
|                                                                   |
|  [1] SECRETS MANAGEMENT                                          |
|      +------------------+     +------------------+                |
|      | External Secrets |---->| HashiCorp Vault  |                |
|      | Operator         |     | (Secret Store)   |                |
|      +------------------+     +------------------+                |
|                                                                   |
|  [2] POD SECURITY STANDARDS                                      |
|      +------------------+     +------------------+                |
|      | Namespace Labels |---->| Restricted PSS   |                |
|      | (Enforcement)    |     | (Production)     |                |
|      +------------------+     +------------------+                |
|                                                                   |
|  [3] NETWORK POLICIES                                            |
|      +------------------+     +------------------+                |
|      | Default Deny     |---->| Allow Rules      |                |
|      | (Ingress/Egress) |     | (Per Service)    |                |
|      +------------------+     +------------------+                |
|                                                                   |
|  [4] RBAC                                                        |
|      +------------------+     +------------------+                |
|      | ServiceAccounts  |---->| Roles/Bindings   |                |
|      | (Per Service)    |     | (Least Privilege)|                |
|      +------------------+     +------------------+                |
|                                                                   |
+------------------------------------------------------------------+
```

## Components

### Directory Structure

```
security/
├── external-secrets/
│   ├── external-secrets-operator.yaml   # ESO configuration
│   ├── external-secret-templates.yaml   # Secret sync definitions
│   └── vault-setup.yaml                 # Vault configuration
├── pod-security/
│   ├── pod-security-standards.yaml      # Namespace PSS labels
│   └── security-context-template.yaml   # SecurityContext templates
├── network-policies/
│   ├── default-deny.yaml                # Default deny all traffic
│   ├── microservices-policies.yaml      # Service-to-service rules
│   └── database-policies.yaml           # Database access rules
├── rbac/
│   ├── service-accounts.yaml            # Per-service accounts
│   └── roles-and-bindings.yaml          # RBAC definitions
├── staging/
│   └── hardened-deployments.yaml        # Staging deployments
├── production/
│   └── hardened-deployments.yaml        # Production deployments
├── scripts/
│   ├── validate-security.sh             # Security validation
│   ├── apply-security.sh                # Apply configuration
│   └── rollback-security.sh             # Rollback script
└── README.md                            # This documentation
```

## Quick Start

### Prerequisites

1. Kubernetes cluster (v1.25+)
2. kubectl configured
3. Network CNI supporting Network Policies (Calico, Cilium)
4. (Optional) External Secrets Operator
5. (Optional) HashiCorp Vault

### Deploy Security Configuration

```bash
# Validate configuration
./scripts/validate-security.sh staging

# Apply to staging (dry-run first)
./scripts/apply-security.sh staging --dry-run

# Apply to staging
./scripts/apply-security.sh staging

# Apply to production
./scripts/apply-security.sh production
```

## Secrets Management

### External Secrets Operator

We use External Secrets Operator (ESO) to sync secrets from HashiCorp Vault to Kubernetes.

**Benefits:**
- Secrets never stored in Git
- Automatic secret rotation
- Centralized secret management
- Audit trail for secret access

### Setup Vault

1. Install Vault:
```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm install vault hashicorp/vault -n vault-system --create-namespace
```

2. Configure Vault for crypto-bot:
```bash
# Initialize and unseal Vault
kubectl exec -it vault-0 -n vault-system -- vault operator init

# Run setup script (from vault-setup.yaml)
kubectl exec -it vault-0 -n vault-system -- /bin/sh
# Then run the setup-crypto-bot.sh script contents
```

3. Install External Secrets Operator:
```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets-system --create-namespace
```

### Secret Paths in Vault

| Environment | Path | Description |
|-------------|------|-------------|
| Staging | `secret/crypto-bot/staging/database` | Database credentials |
| Staging | `secret/crypto-bot/staging/api` | API secrets |
| Staging | `secret/crypto-bot/staging/bybit` | Bybit testnet keys |
| Production | `secret/crypto-bot/production/database` | Database credentials |
| Production | `secret/crypto-bot/production/api` | API secrets |
| Production | `secret/crypto-bot/production/bybit` | Bybit mainnet keys |

### Generate Secrets

Use the provided script to generate secure random secrets:

```bash
# Generate random passwords
openssl rand -base64 32  # For passwords
openssl rand -base64 64  # For JWT secrets
openssl rand -hex 32     # For API tokens
```

## Pod Security

### Pod Security Standards (PSS)

We enforce Pod Security Standards at the namespace level:

| Environment | Enforce | Warn | Audit |
|-------------|---------|------|-------|
| Staging | baseline | restricted | restricted |
| Production | restricted | restricted | restricted |

### Security Context Requirements

All containers must have:

```yaml
securityContext:
  allowPrivilegeEscalation: false
  runAsNonRoot: true
  runAsUser: 10000
  runAsGroup: 10000
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL
  seccompProfile:
    type: RuntimeDefault
```

### Writable Directories

For containers with readOnlyRootFilesystem, use emptyDir volumes:

```yaml
volumeMounts:
  - name: tmp-volume
    mountPath: /tmp
  - name: cache-volume
    mountPath: /app/.cache

volumes:
  - name: tmp-volume
    emptyDir:
      sizeLimit: 100Mi
  - name: cache-volume
    emptyDir:
      sizeLimit: 200Mi
```

## Network Policies

### Default Deny Strategy

All namespaces have default deny policies for both ingress and egress:

```yaml
# Default deny ingress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
spec:
  podSelector: {}
  policyTypes:
    - Ingress
```

### Service Communication Matrix

| Service | Ingress From | Egress To |
|---------|--------------|-----------|
| api-gateway | Ingress Controller | All internal services, Redis |
| trading-engine | api-gateway | bybit-connector, portfolio-manager, technical-analysis, PostgreSQL, Redis, RabbitMQ |
| bybit-connector | trading-engine, portfolio-manager | External (Bybit API), Redis, RabbitMQ |
| market-data-service | technical-analysis, ml-prediction | bybit-connector, TimescaleDB, Redis |
| portfolio-manager | trading-engine, risk-metrics | bybit-connector, PostgreSQL, Redis |
| technical-analysis | trading-engine | market-data-service, Redis |

### External Access

Only specific services can access external networks:
- **bybit-connector**: Bybit API (api.bybit.com, api-testnet.bybit.com)
- **notification-service**: SMTP, Telegram API
- **sentiment-analysis-service**: Twitter API, NewsAPI

## RBAC Configuration

### Service Accounts

Each microservice has a dedicated ServiceAccount:

| Service | ServiceAccount | Token Mount |
|---------|----------------|-------------|
| api-gateway | api-gateway-sa | No |
| trading-engine | trading-engine-sa | Yes (audit) |
| bybit-connector | bybit-connector-sa | Yes (audit) |
| portfolio-manager | portfolio-manager-sa | No |
| technical-analysis | technical-analysis-sa | No |
| market-data-service | market-data-sa | No |

### Roles

| Role | Permissions | Bound To |
|------|-------------|----------|
| configmap-reader | Get/List ConfigMaps | api-gateway, trading-engine |
| event-creator | Create Events | trading-engine, bybit-connector |
| secret-reader | Get specific Secrets | (when needed) |

## Deployment Instructions

### Staging Deployment

```bash
# 1. Validate security configuration
./scripts/validate-security.sh staging

# 2. Apply security configuration
./scripts/apply-security.sh staging

# 3. Verify deployment
kubectl get pods -n trading-bot-staging
kubectl get networkpolicies -n trading-bot-staging
kubectl get serviceaccounts -n trading-bot-staging

# 4. Check for security violations
kubectl get events -n trading-bot-staging --field-selector reason=FailedCreate
```

### Production Deployment

```bash
# 1. Validate (mandatory for production)
./scripts/validate-security.sh production

# 2. Apply with dry-run first
./scripts/apply-security.sh production --dry-run

# 3. Apply to production
./scripts/apply-security.sh production

# 4. Verify all pods are running
kubectl get pods -n crypto-bot -w

# 5. Verify network policies are effective
kubectl describe networkpolicy -n crypto-bot
```

## Rollback Procedures

### Full Rollback

```bash
# Rollback all security configurations
./scripts/rollback-security.sh staging all

# Or for production
./scripts/rollback-security.sh production all
```

### Partial Rollback

```bash
# Rollback network policies only
./scripts/rollback-security.sh staging network

# Rollback RBAC only
./scripts/rollback-security.sh staging rbac

# Rollback deployments only
./scripts/rollback-security.sh staging deployments
```

### Emergency Rollback

If pods fail to start due to security constraints:

```bash
# 1. Remove network policies (immediate)
kubectl delete networkpolicy -n trading-bot-staging --all

# 2. Relax PSS (namespace labels)
kubectl label namespace trading-bot-staging \
  pod-security.kubernetes.io/enforce=privileged --overwrite

# 3. Restore original deployments
kubectl apply -f ../staging/microservices.yaml
```

## Security Validation

### Pre-deployment Checks

The validation script checks:
- YAML syntax
- Pod Security Standards labels
- SecurityContext configurations
- ServiceAccount settings
- Network Policy coverage
- RBAC least-privilege compliance
- Resource limits

### Run Validation

```bash
./scripts/validate-security.sh staging   # For staging
./scripts/validate-security.sh production # For production
```

### Continuous Validation

Consider integrating with CI/CD:

```yaml
# GitHub Actions example
- name: Validate Security
  run: |
    ./infrastructure/kubernetes/security/scripts/validate-security.sh production
```

## Troubleshooting

### Pod Fails to Start

**Symptom**: Pod stuck in `CreateContainerConfigError`

**Cause**: SecurityContext violations

**Solution**:
```bash
# Check pod events
kubectl describe pod <pod-name> -n <namespace>

# Common fixes:
# 1. Ensure image runs as non-root
# 2. Add emptyDir for writable directories
# 3. Check capabilities requirements
```

### Network Policy Blocking Traffic

**Symptom**: Service cannot reach dependencies

**Solution**:
```bash
# Test connectivity
kubectl exec -it <pod> -n <namespace> -- nc -zv <service> <port>

# Check network policies
kubectl describe networkpolicy <policy-name> -n <namespace>

# Temporarily allow all traffic for debugging
kubectl delete networkpolicy <policy-name> -n <namespace>
```

### External Secrets Not Syncing

**Symptom**: Kubernetes secrets not created

**Solution**:
```bash
# Check ExternalSecret status
kubectl get externalsecret -n <namespace>
kubectl describe externalsecret <name> -n <namespace>

# Check SecretStore connectivity
kubectl get secretstore -n <namespace>
kubectl describe secretstore <name> -n <namespace>

# Verify Vault access
kubectl logs -n external-secrets-system -l app.kubernetes.io/name=external-secrets
```

### RBAC Permission Denied

**Symptom**: Pod cannot access Kubernetes API

**Solution**:
```bash
# Check service account
kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.serviceAccountName}'

# Check role bindings
kubectl get rolebinding -n <namespace> -l app=crypto-trading-bot

# Verify permissions
kubectl auth can-i get configmaps -n <namespace> --as system:serviceaccount:<namespace>:<sa-name>
```

## Security Checklist

### Before Deployment

- [ ] All secrets stored in Vault (not Git)
- [ ] Security validation passes
- [ ] Network policies reviewed
- [ ] RBAC permissions verified
- [ ] Resource limits set
- [ ] Pod Security Standards enforced

### After Deployment

- [ ] All pods running successfully
- [ ] Network policies effective
- [ ] No security events in logs
- [ ] Monitoring configured
- [ ] Audit logging enabled

## Contact

For security-related issues, contact the DevOps team or raise a security incident.

---

*This security configuration follows OWASP, CIS Kubernetes Benchmark, and NSA/CISA Kubernetes Hardening Guidelines.*
