# HashiCorp Vault Configuration for Crypto Trading Bot
# Version: 1.0
# Last Updated: 2025-11-19
# Environment: Production

# Storage backend - File storage for single-server deployment
# For production cluster, use Consul or integrated storage (Raft)
storage "file" {
  path = "/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/vault/data"
}

# TCP listener configuration
listener "tcp" {
  address       = "127.0.0.1:8200"
  tls_disable   = 1  # WARNING: Enable TLS in production!

  # For production, use TLS:
  # tls_disable     = 0
  # tls_cert_file   = "/path/to/cert.pem"
  # tls_key_file    = "/path/to/key.pem"
  # tls_min_version = "tls12"

  # Enable HTTP/2 for better performance
  http_read_timeout    = "10s"
  http_write_timeout   = "10s"
  http_idle_timeout    = "5m"
}

# API address
api_addr = "http://127.0.0.1:8200"

# Cluster address (for multi-node setup)
# cluster_addr = "https://127.0.0.1:8201"

# Maximum lease TTL
max_lease_ttl = "8760h"  # 1 year

# Default lease TTL
default_lease_ttl = "168h"  # 1 week

# Disable mlock (required for containers, not recommended for bare metal)
disable_mlock = true

# UI configuration
ui = true

# Telemetry configuration for monitoring
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = false

  # Uncomment to send metrics to statsd/statsite
  # statsd_address = "127.0.0.1:8125"

  # Uncomment to send metrics to Datadog
  # dogstatsd_addr = "127.0.0.1:8125"
  # dogstatsd_tags = ["env:production", "service:vault"]
}

# Log level: "trace", "debug", "info", "warn", "error"
log_level = "info"

# Log format: "standard" or "json"
log_format = "json"

# Log to file
# log_file = "/var/log/vault/vault.log"

# Seal configuration - Auto-unseal with cloud KMS (production)
# Uncomment and configure for your cloud provider:

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
#   project     = "your-project"
#   region      = "global"
#   key_ring    = "vault"
#   crypto_key  = "vault-key"
# }

# Audit device configuration
# Enable after initial setup using: vault audit enable file file_path=/var/log/vault/audit.log
# This will log all Vault operations for compliance and security

# High Availability configuration (multi-node cluster)
# Uncomment for HA setup:
# ha_storage "consul" {
#   address = "127.0.0.1:8500"
#   path    = "vault/"
# }

# Performance tuning
# cache_size = "131072"  # 128MB cache

# Plugin directory
# plugin_directory = "/etc/vault/plugins"

# Service registration (for load balancing)
# service_registration "consul" {
#   address = "127.0.0.1:8500"
#   service = "vault"
# }

# Entropy augmentation (HSM or external entropy source)
# entropy "seal" {
#   mode = "augmentation"
# }
