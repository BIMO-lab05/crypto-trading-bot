#!/bin/bash
################################################################################
# HashiCorp Vault Setup Script for Crypto Trading Bot
# Purpose: Initialize and configure Vault for secrets management
# Author: Security Engineer Agent
# Date: 2025-11-19
# Version: 1.0
################################################################################

set -euo pipefail
IFS=$'\n\t'

# Color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# Configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly VAULT_CONFIG="${SCRIPT_DIR}/vault-config.hcl"
readonly VAULT_DATA_DIR="${PROJECT_ROOT}/infrastructure/vault/data"
readonly VAULT_LOGS_DIR="${PROJECT_ROOT}/logs/vault"
readonly VAULT_KEYS_DIR="${PROJECT_ROOT}/.vault-keys"
readonly VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"

# Vault configuration
readonly VAULT_DEV_ROOT_TOKEN="dev-only-token-change-in-prod"
readonly VAULT_NAMESPACE="crypto-trading-bot"

################################################################################
# Logging Functions
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

################################################################################
# Setup Functions
################################################################################

setup_directories() {
    log_info "Creating Vault directories..."

    mkdir -p "${VAULT_DATA_DIR}" "${VAULT_LOGS_DIR}" "${VAULT_KEYS_DIR}"
    chmod 700 "${VAULT_DATA_DIR}" "${VAULT_KEYS_DIR}"
    chmod 755 "${VAULT_LOGS_DIR}"

    log_success "Directories created"
}

check_vault_binary() {
    if ! command -v vault &>/dev/null; then
        log_error "Vault binary not found. Installing..."
        install_vault
    else
        local version=$(vault version | head -1 | cut -d' ' -f2)
        log_success "Vault found: ${version}"
    fi
}

install_vault() {
    log_info "Installing HashiCorp Vault..."

    # Determine OS and architecture
    local os=$(uname -s | tr '[:upper:]' '[:lower:]')
    local arch=$(uname -m)

    case "${arch}" in
        x86_64) arch="amd64" ;;
        aarch64) arch="arm64" ;;
        armv7l) arch="arm" ;;
    esac

    # Download and install Vault
    local vault_version="1.15.4"
    local vault_url="https://releases.hashicorp.com/vault/${vault_version}/vault_${vault_version}_${os}_${arch}.zip"

    log_info "Downloading Vault ${vault_version} for ${os}_${arch}..."

    cd /tmp
    curl -sSL "${vault_url}" -o vault.zip
    unzip -o vault.zip
    sudo mv vault /usr/local/bin/
    sudo chmod +x /usr/local/bin/vault

    rm vault.zip

    log_success "Vault installed successfully"
}

start_vault_dev() {
    log_info "Starting Vault in development mode..."

    export VAULT_ADDR="${VAULT_ADDR}"
    export VAULT_TOKEN="${VAULT_DEV_ROOT_TOKEN}"

    # Start Vault in background
    nohup vault server -dev \
        -dev-root-token-id="${VAULT_DEV_ROOT_TOKEN}" \
        -dev-listen-address="127.0.0.1:8200" \
        > "${VAULT_LOGS_DIR}/vault-dev.log" 2>&1 &

    local vault_pid=$!
    echo "${vault_pid}" > "${VAULT_DATA_DIR}/vault.pid"

    # Wait for Vault to be ready
    log_info "Waiting for Vault to be ready..."
    for i in {1..30}; do
        if vault status &>/dev/null; then
            log_success "Vault is ready (PID: ${vault_pid})"
            return 0
        fi
        sleep 1
    done

    log_error "Vault failed to start"
    return 1
}

start_vault_prod() {
    log_info "Starting Vault in production mode..."

    export VAULT_ADDR="${VAULT_ADDR}"

    # Check if config exists
    if [[ ! -f "${VAULT_CONFIG}" ]]; then
        log_error "Vault configuration not found: ${VAULT_CONFIG}"
        return 1
    fi

    # Start Vault server
    nohup vault server -config="${VAULT_CONFIG}" \
        > "${VAULT_LOGS_DIR}/vault-prod.log" 2>&1 &

    local vault_pid=$!
    echo "${vault_pid}" > "${VAULT_DATA_DIR}/vault.pid"

    # Wait for Vault to be ready
    log_info "Waiting for Vault to be ready..."
    for i in {1..30}; do
        if vault status &>/dev/null 2>&1; then
            log_success "Vault is ready (PID: ${vault_pid})"
            return 0
        fi
        sleep 1
    done

    log_error "Vault failed to start"
    return 1
}

initialize_vault() {
    log_info "Initializing Vault..."

    # Check if already initialized
    if vault status 2>&1 | grep -q "Initialized.*true"; then
        log_warning "Vault is already initialized"
        return 0
    fi

    # Initialize with 5 key shares and 3 required for unsealing
    local init_output=$(vault operator init \
        -key-shares=5 \
        -key-threshold=3 \
        -format=json)

    # Save keys securely
    echo "${init_output}" > "${VAULT_KEYS_DIR}/init-keys.json"
    chmod 600 "${VAULT_KEYS_DIR}/init-keys.json"

    # Extract root token
    local root_token=$(echo "${init_output}" | jq -r '.root_token')
    echo "${root_token}" > "${VAULT_KEYS_DIR}/root-token"
    chmod 600 "${VAULT_KEYS_DIR}/root-token"

    log_success "Vault initialized successfully"
    log_warning "CRITICAL: Save the keys from ${VAULT_KEYS_DIR}/init-keys.json to a secure location"

    export VAULT_TOKEN="${root_token}"
}

unseal_vault() {
    log_info "Unsealing Vault..."

    if ! vault status 2>&1 | grep -q "Sealed.*true"; then
        log_warning "Vault is already unsealed"
        return 0
    fi

    # Read unseal keys
    if [[ ! -f "${VAULT_KEYS_DIR}/init-keys.json" ]]; then
        log_error "Unseal keys not found. Cannot unseal Vault."
        return 1
    fi

    local unseal_keys=($(jq -r '.unseal_keys_b64[]' "${VAULT_KEYS_DIR}/init-keys.json"))

    # Unseal using first 3 keys (threshold)
    for i in 0 1 2; do
        vault operator unseal "${unseal_keys[$i]}" > /dev/null
        log_info "Unseal progress: $((i+1))/3"
    done

    log_success "Vault unsealed successfully"
}

################################################################################
# Vault Configuration Functions
################################################################################

enable_secret_engines() {
    log_info "Enabling secret engines..."

    export VAULT_ADDR="${VAULT_ADDR}"

    # Enable KV v2 secret engine for application secrets
    if ! vault secrets list | grep -q "^secret/"; then
        vault secrets enable -path=secret -version=2 kv
        log_success "Enabled KV v2 secret engine at secret/"
    fi

    # Enable database secret engine for dynamic credentials
    if ! vault secrets list | grep -q "^database/"; then
        vault secrets enable database
        log_success "Enabled database secret engine"
    fi

    # Enable transit engine for encryption as a service
    if ! vault secrets list | grep -q "^transit/"; then
        vault secrets enable transit
        log_success "Enabled transit secret engine"
    fi

    # Enable PKI for certificate management
    if ! vault secrets list | grep -q "^pki/"; then
        vault secrets enable pki
        vault secrets tune -max-lease-ttl=87600h pki
        log_success "Enabled PKI secret engine"
    fi
}

configure_database_secrets() {
    log_info "Configuring database secret engine..."

    # Source environment variables
    if [[ -f "${PROJECT_ROOT}/infrastructure/.env" ]]; then
        source "${PROJECT_ROOT}/infrastructure/.env"
    fi

    # Configure PostgreSQL connection
    vault write database/config/postgres \
        plugin_name=postgresql-database-plugin \
        allowed_roles="trading-bot-role" \
        connection_url="postgresql://{{username}}:{{password}}@localhost:5432/cryptobot?sslmode=disable" \
        username="cryptobot" \
        password="${POSTGRES_PASSWORD:-cryptobot_dev_password}"

    log_success "Configured PostgreSQL database connection"

    # Configure TimescaleDB connection
    vault write database/config/timescaledb \
        plugin_name=postgresql-database-plugin \
        allowed_roles="market-data-role" \
        connection_url="postgresql://{{username}}:{{password}}@localhost:5433/market_data?sslmode=disable" \
        username="cryptobot" \
        password="${TIMESCALE_PASSWORD:-timescale_dev_password}"

    log_success "Configured TimescaleDB database connection"

    # Create database roles
    vault write database/roles/trading-bot-role \
        db_name=postgres \
        creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}' INHERIT; \
                            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA trading_engine TO \"{{name}}\"; \
                            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA portfolio TO \"{{name}}\";" \
        default_ttl="1h" \
        max_ttl="24h"

    vault write database/roles/market-data-role \
        db_name=timescaledb \
        creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}' INHERIT; \
                            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA market_data TO \"{{name}}\";" \
        default_ttl="1h" \
        max_ttl="24h"

    log_success "Created database roles"
}

store_initial_secrets() {
    log_info "Storing initial secrets..."

    # Source environment variables
    if [[ -f "${PROJECT_ROOT}/infrastructure/.env" ]]; then
        source "${PROJECT_ROOT}/infrastructure/.env"
    fi

    # Store database credentials
    vault kv put secret/database/postgres \
        username="cryptobot" \
        password="${POSTGRES_PASSWORD:-cryptobot_dev_password}" \
        host="localhost" \
        port="5432" \
        database="cryptobot"

    vault kv put secret/database/timescaledb \
        username="cryptobot" \
        password="${TIMESCALE_PASSWORD:-timescale_dev_password}" \
        host="localhost" \
        port="5433" \
        database="market_data"

    # Store Redis credentials
    vault kv put secret/redis \
        password="${REDIS_PASSWORD:-redis_dev_password}" \
        host="localhost" \
        port="6379"

    # Store RabbitMQ credentials
    vault kv put secret/rabbitmq \
        username="cryptobot" \
        password="${RABBITMQ_PASSWORD:-rabbitmq_dev_password}" \
        host="localhost" \
        port="5672" \
        vhost="cryptobot"

    # Store API keys (if available)
    if [[ -n "${BYBIT_API_KEY:-}" ]]; then
        vault kv put secret/bybit \
            api_key="${BYBIT_API_KEY}" \
            api_secret="${BYBIT_API_SECRET}" \
            testnet="${BYBIT_TESTNET:-true}"
    fi

    log_success "Initial secrets stored"
}

create_policies() {
    log_info "Creating Vault policies..."

    # Trading Engine Policy
    cat > /tmp/trading-engine-policy.hcl <<'EOF'
# Trading Engine Policy
path "secret/data/database/postgres" {
  capabilities = ["read"]
}

path "secret/data/redis" {
  capabilities = ["read"]
}

path "secret/data/rabbitmq" {
  capabilities = ["read"]
}

path "secret/data/bybit" {
  capabilities = ["read"]
}

path "database/creds/trading-bot-role" {
  capabilities = ["read"]
}

path "transit/encrypt/trading-data" {
  capabilities = ["update"]
}

path "transit/decrypt/trading-data" {
  capabilities = ["update"]
}
EOF

    vault policy write trading-engine /tmp/trading-engine-policy.hcl
    log_success "Created trading-engine policy"

    # Market Data Service Policy
    cat > /tmp/market-data-policy.hcl <<'EOF'
# Market Data Service Policy
path "secret/data/database/timescaledb" {
  capabilities = ["read"]
}

path "secret/data/redis" {
  capabilities = ["read"]
}

path "database/creds/market-data-role" {
  capabilities = ["read"]
}
EOF

    vault policy write market-data /tmp/market-data-policy.hcl
    log_success "Created market-data policy"

    # Portfolio Manager Policy
    cat > /tmp/portfolio-policy.hcl <<'EOF'
# Portfolio Manager Policy
path "secret/data/database/postgres" {
  capabilities = ["read"]
}

path "secret/data/redis" {
  capabilities = ["read"]
}

path "database/creds/trading-bot-role" {
  capabilities = ["read"]
}

path "transit/encrypt/portfolio-data" {
  capabilities = ["update"]
}

path "transit/decrypt/portfolio-data" {
  capabilities = ["update"]
}
EOF

    vault policy write portfolio-manager /tmp/portfolio-policy.hcl
    log_success "Created portfolio-manager policy"

    # Bybit Connector Policy
    cat > /tmp/bybit-policy.hcl <<'EOF'
# Bybit Connector Policy
path "secret/data/bybit" {
  capabilities = ["read"]
}

path "secret/data/redis" {
  capabilities = ["read"]
}
EOF

    vault policy write bybit-connector /tmp/bybit-policy.hcl
    log_success "Created bybit-connector policy"

    # Admin Policy
    cat > /tmp/admin-policy.hcl <<'EOF'
# Admin Policy - Full access
path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "database/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "transit/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "sys/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
EOF

    vault policy write admin /tmp/admin-policy.hcl
    log_success "Created admin policy"

    # Cleanup
    rm -f /tmp/*-policy.hcl
}

create_service_tokens() {
    log_info "Creating service tokens..."

    # Create tokens for each service
    local token_dir="${VAULT_KEYS_DIR}/service-tokens"
    mkdir -p "${token_dir}"
    chmod 700 "${token_dir}"

    # Trading Engine Token
    local trading_token=$(vault token create \
        -policy=trading-engine \
        -period=24h \
        -format=json | jq -r '.auth.client_token')
    echo "${trading_token}" > "${token_dir}/trading-engine-token"
    log_success "Created trading-engine token"

    # Market Data Token
    local market_token=$(vault token create \
        -policy=market-data \
        -period=24h \
        -format=json | jq -r '.auth.client_token')
    echo "${market_token}" > "${token_dir}/market-data-token"
    log_success "Created market-data token"

    # Portfolio Manager Token
    local portfolio_token=$(vault token create \
        -policy=portfolio-manager \
        -period=24h \
        -format=json | jq -r '.auth.client_token')
    echo "${portfolio_token}" > "${token_dir}/portfolio-manager-token"
    log_success "Created portfolio-manager token"

    # Bybit Connector Token
    local bybit_token=$(vault token create \
        -policy=bybit-connector \
        -period=24h \
        -format=json | jq -r '.auth.client_token')
    echo "${bybit_token}" > "${token_dir}/bybit-connector-token"
    log_success "Created bybit-connector token"

    chmod 600 "${token_dir}"/*
    log_success "Service tokens created and saved to ${token_dir}"
}

configure_transit_keys() {
    log_info "Creating transit encryption keys..."

    # Create encryption keys for different data types
    vault write -f transit/keys/trading-data
    vault write -f transit/keys/portfolio-data
    vault write -f transit/keys/api-credentials

    log_success "Transit encryption keys created"
}

################################################################################
# Health Check Functions
################################################################################

verify_vault_setup() {
    log_info "Verifying Vault setup..."

    export VAULT_ADDR="${VAULT_ADDR}"

    # Check Vault status
    if ! vault status &>/dev/null; then
        log_error "Vault is not accessible"
        return 1
    fi

    # Check secret engines
    local engines=("secret/" "database/" "transit/" "pki/")
    for engine in "${engines[@]}"; do
        if vault secrets list | grep -q "^${engine}"; then
            log_success "Secret engine enabled: ${engine}"
        else
            log_error "Secret engine not found: ${engine}"
            return 1
        fi
    done

    # Check policies
    local policies=("trading-engine" "market-data" "portfolio-manager" "bybit-connector" "admin")
    for policy in "${policies[@]}"; do
        if vault policy list | grep -q "^${policy}$"; then
            log_success "Policy exists: ${policy}"
        else
            log_error "Policy not found: ${policy}"
            return 1
        fi
    done

    # Test secret retrieval
    if vault kv get secret/database/postgres &>/dev/null; then
        log_success "Secret retrieval test passed"
    else
        log_error "Failed to retrieve secrets"
        return 1
    fi

    log_success "Vault setup verification complete"
}

################################################################################
# Main Setup Function
################################################################################

setup_vault() {
    local mode=${1:-"dev"}  # dev or prod

    cat <<'EOF'
╔═══════════════════════════════════════════════════════════╗
║   HashiCorp Vault Setup for Crypto Trading Bot          ║
║   Secrets Management & Dynamic Credentials               ║
╚═══════════════════════════════════════════════════════════╝

EOF

    log_info "Setting up Vault in ${mode} mode..."

    # Setup directories
    setup_directories

    # Check/Install Vault
    check_vault_binary

    # Start Vault based on mode
    if [[ "${mode}" == "dev" ]]; then
        start_vault_dev
        export VAULT_TOKEN="${VAULT_DEV_ROOT_TOKEN}"
    else
        start_vault_prod
        initialize_vault
        unseal_vault
    fi

    # Configure Vault
    enable_secret_engines
    create_policies
    store_initial_secrets
    configure_database_secrets
    configure_transit_keys
    create_service_tokens

    # Verify setup
    verify_vault_setup

    # Print summary
    cat <<EOF

╔═══════════════════════════════════════════════════════════╗
║   Vault Setup Complete                                    ║
╚═══════════════════════════════════════════════════════════╝

Vault Address: ${VAULT_ADDR}
Mode: ${mode}

$(if [[ "${mode}" == "dev" ]]; then
    echo "Root Token: ${VAULT_DEV_ROOT_TOKEN}"
    echo "⚠️  WARNING: Development mode only! Do not use in production."
else
    echo "Root Token: Saved in ${VAULT_KEYS_DIR}/root-token"
    echo "Unseal Keys: Saved in ${VAULT_KEYS_DIR}/init-keys.json"
    echo ""
    echo "🔒 CRITICAL: Secure these files immediately!"
fi)

Service Tokens: ${VAULT_KEYS_DIR}/service-tokens/

Next Steps:
1. Update service .env files with VAULT_ADDR and VAULT_TOKEN
2. Test secret retrieval from services
3. Enable automatic token renewal in services
4. Set up monitoring and audit logging
5. Schedule regular backup of Vault data

View secrets: vault kv get secret/database/postgres
View logs: tail -f ${VAULT_LOGS_DIR}/vault-${mode}.log

EOF

    return 0
}

################################################################################
# CLI Interface
################################################################################

show_usage() {
    cat <<EOF
Usage: $0 [MODE]

HashiCorp Vault Setup Script

MODES:
    dev     Setup Vault in development mode (default)
    prod    Setup Vault in production mode
    stop    Stop running Vault server
    status  Check Vault status
    help    Show this help message

EXAMPLES:
    $0                  # Setup in development mode
    $0 dev              # Setup in development mode
    $0 prod             # Setup in production mode
    $0 status           # Check Vault status
    $0 stop             # Stop Vault server

ENVIRONMENT VARIABLES:
    VAULT_ADDR          Vault server address (default: http://127.0.0.1:8200)

EOF
}

stop_vault() {
    log_info "Stopping Vault server..."

    if [[ -f "${VAULT_DATA_DIR}/vault.pid" ]]; then
        local pid=$(cat "${VAULT_DATA_DIR}/vault.pid")
        if kill "${pid}" 2>/dev/null; then
            log_success "Vault stopped (PID: ${pid})"
            rm "${VAULT_DATA_DIR}/vault.pid"
        else
            log_warning "Vault process not found (PID: ${pid})"
        fi
    else
        log_warning "Vault PID file not found"
    fi
}

show_status() {
    export VAULT_ADDR="${VAULT_ADDR}"

    log_info "Vault Status:"
    vault status || log_error "Vault is not running"

    if [[ -f "${VAULT_DATA_DIR}/vault.pid" ]]; then
        local pid=$(cat "${VAULT_DATA_DIR}/vault.pid")
        log_info "Vault PID: ${pid}"
    fi
}

################################################################################
# Main Entry Point
################################################################################

main() {
    local mode="${1:-dev}"

    case "${mode}" in
        dev|prod)
            setup_vault "${mode}"
            ;;
        stop)
            stop_vault
            ;;
        status)
            show_status
            ;;
        help|--help|-h)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown mode: ${mode}"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
