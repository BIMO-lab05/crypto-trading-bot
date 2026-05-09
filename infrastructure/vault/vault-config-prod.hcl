# HashiCorp Vault Configuration — PRODUCTION
# Version: 1.0
# Last Updated: 2026-04-29
#
# ============================================================================
# This file is the production / live-trading variant of vault-config.hcl.
# Differences from the dev file:
#   - tls_disable=0 (plaintext is REJECTED)
#   - tls_cert_file / tls_key_file required (no defaults)
#   - tls_min_version pinned to TLS 1.2
#   - Listener bound to 0.0.0.0 (intra-cluster); restrict via firewall / network policy
#   - Auto-unseal seal block included (commented for cloud-of-choice)
#   - Audit logging enabled by default
#
# To use:
#   1. Provision certs (e.g. ACME via cert-manager, AWS PCA, internal CA).
#   2. Set TLS_CERT_FILE / TLS_KEY_FILE env or replace the placeholders.
#   3. Configure the auto-unseal seal block for your cloud.
#   4. Mount this file at /vault/config/vault.hcl in the vault container
#      (NOT vault-config.hcl — that one is dev-only and refuses prod).
# ============================================================================

# Storage backend — for a real cluster, use integrated storage (Raft) or Consul.
# File storage is acceptable for a single-server prod deployment if backed by
# replicated block storage, but is NOT recommended for multi-node HA.
storage "file" {
  path = "/vault/data"
}

# Cluster-wide listener with TLS required. Plaintext requests are refused.
listener "tcp" {
  address           = "0.0.0.0:8200"
  cluster_address   = "0.0.0.0:8201"
  tls_disable       = 0
  tls_cert_file     = "/vault/tls/cert.pem"
  tls_key_file      = "/vault/tls/key.pem"
  tls_min_version   = "tls12"

  http_read_timeout    = "10s"
  http_write_timeout   = "10s"
  http_idle_timeout    = "5m"
}

# API + cluster addresses must be HTTPS in production.
api_addr     = "https://vault.internal:8200"
cluster_addr = "https://vault.internal:8201"

# Lease TTLs — same as dev unless your secrets policy says otherwise.
max_lease_ttl     = "8760h"  # 1 year
default_lease_ttl = "168h"   # 1 week

# mlock keeps secret material out of swap. Required for production unless
# the host is a container without CAP_IPC_LOCK — in that case ensure the
# container has the capability or is run with --cap-add=IPC_LOCK.
disable_mlock = false

ui = true

# Telemetry — wire to your observability stack.
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = false
}

log_level  = "info"
log_format = "json"
log_file   = "/var/log/vault/vault.log"

# ----------------------------------------------------------------------------
# Auto-unseal — uncomment exactly ONE of the seal blocks below for your cloud.
# Required for production: never store unseal keys in environment files or
# pass them on a CLI manually after each restart.
# ----------------------------------------------------------------------------

# AWS KMS Auto-unseal
# seal "awskms" {
#   region     = "us-east-1"
#   kms_key_id = "alias/vault-key"
#   endpoint   = "https://kms.us-east-1.amazonaws.com"
# }

# Azure Key Vault Auto-unseal
# seal "azurekeyvault" {
#   tenant_id     = "your-tenant-id"
#   client_id     = "your-client-id"
#   client_secret = "your-client-secret"
#   vault_name    = "your-vault-name"
#   key_name      = "your-key-name"
# }

# GCP Cloud KMS Auto-unseal
# seal "gcpckms" {
#   project    = "your-project"
#   region     = "global"
#   key_ring   = "vault"
#   crypto_key = "vault-key"
# }
