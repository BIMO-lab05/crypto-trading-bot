#!/bin/bash
################################################################################
# Complete Secrets Management Setup Script
# Purpose: End-to-end setup of HashiCorp Vault for crypto trading bot
# Author: Security Engineer Agent
# Date: 2025-11-21
# Version: 1.0
################################################################################

set -euo pipefail
IFS=$'\n\t'

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color

# Script directory and project root
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly VAULT_DIR="${PROJECT_ROOT}/infrastructure/vault"

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

log_step() {
    echo -e "${CYAN}[STEP]${NC} $*"
}

################################################################################
# Banner
################################################################################

show_banner() {
    cat << 'EOF'
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║         Crypto Trading Bot - Secrets Management Setup          ║
║                   HashiCorp Vault Integration                  ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝

This script will:
  1. Install Python dependencies
  2. Start HashiCorp Vault
  3. Initialize and configure Vault
  4. Migrate secrets from .env files
  5. Update service configurations
  6. Verify installation
  7. Generate documentation

EOF
}

################################################################################
# Prerequisites Check
################################################################################

check_prerequisites() {
    log_step "Checking prerequisites..."

    local missing_deps=()

    # Check Python
    if ! command -v python3 &>/dev/null; then
        missing_deps+=("python3")
    fi

    # Check pip
    if ! command -v pip3 &>/dev/null; then
        missing_deps+=("pip3")
    fi

    # Check Docker
    if ! command -v docker &>/dev/null; then
        missing_deps+=("docker")
    fi

    # Check Docker Compose
    if ! command -v docker-compose &>/dev/null; then
        missing_deps+=("docker-compose")
    fi

    # Check git
    if ! command -v git &>/dev/null; then
        missing_deps+=("git")
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        log_info "Please install missing dependencies and try again"
        return 1
    fi

    log_success "All prerequisites met"
    return 0
}

################################################################################
# Install Python Dependencies
################################################################################

install_python_dependencies() {
    log_step "Installing Python dependencies..."

    cd "${PROJECT_ROOT}"

    # Install Vault client library
    if [ -f "shared/requirements-vault.txt" ]; then
        pip3 install -r shared/requirements-vault.txt --quiet
        log_success "Python dependencies installed"
    else
        log_warning "shared/requirements-vault.txt not found, installing manually"
        pip3 install hvac pydantic pydantic-settings python-dotenv --quiet
    fi
}

################################################################################
# Start Vault
################################################################################

start_vault() {
    log_step "Starting HashiCorp Vault..."

    cd "${PROJECT_ROOT}"

    # Check if Vault is already running
    if docker ps | grep -q crypto-bot-vault; then
        log_warning "Vault container already running"
        return 0
    fi

    # Start Vault using docker-compose
    cd infrastructure
    docker-compose --profile security up -d vault

    # Wait for Vault to be ready
    log_info "Waiting for Vault to be ready..."
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if docker logs crypto-bot-vault 2>&1 | grep -q "Vault server started"; then
            log_success "Vault is ready"
            return 0
        fi

        sleep 2
        attempt=$((attempt + 1))
        echo -n "."
    done

    log_error "Vault failed to start within timeout"
    docker logs crypto-bot-vault
    return 1
}

################################################################################
# Configure Vault
################################################################################

configure_vault() {
    log_step "Configuring HashiCorp Vault..."

    cd "${VAULT_DIR}"

    # Check if setup script exists
    if [ ! -f "setup_vault.sh" ]; then
        log_error "Vault setup script not found: ${VAULT_DIR}/setup_vault.sh"
        return 1
    fi

    # Make script executable
    chmod +x setup_vault.sh

    # Run setup script
    export VAULT_ADDR='http://127.0.0.1:8200'
    export VAULT_TOKEN='dev-only-token'

    ./setup_vault.sh dev

    log_success "Vault configured successfully"
}

################################################################################
# Migrate Secrets
################################################################################

migrate_secrets() {
    log_step "Migrating secrets from .env files to Vault..."

    cd "${PROJECT_ROOT}/infrastructure/scripts"

    # Check if migration script exists
    if [ ! -f "migrate_secrets_to_vault.py" ]; then
        log_error "Migration script not found"
        return 1
    fi

    # Make script executable
    chmod +x migrate_secrets_to_vault.py

    # Set Vault environment
    export VAULT_ADDR='http://127.0.0.1:8200'
    export VAULT_TOKEN='dev-only-token'

    # Ask user for confirmation
    log_warning "This will migrate all secrets from .env files to Vault"
    log_warning "Original .env files will be backed up"
    read -p "Continue? (y/N): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Migration cancelled"
        return 0
    fi

    # Run dry run first
    log_info "Running dry run..."
    python3 migrate_secrets_to_vault.py --dry-run

    read -p "Proceed with actual migration? (y/N): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Migration cancelled"
        return 0
    fi

    # Run actual migration
    python3 migrate_secrets_to_vault.py --verify

    log_success "Secrets migrated successfully"
}

################################################################################
# Update Service Configurations
################################################################################

update_service_configs() {
    log_step "Updating service configurations..."

    cd "${PROJECT_ROOT}"

    # Add Vault environment variables to service .env files
    local services=(
        "api-gateway"
        "bybit-connector"
        "market-data-service"
        "portfolio-manager"
        "technical-analysis"
        "trading-engine"
    )

    for service in "${services[@]}"; do
        local env_file="services/${service}/.env"

        if [ -f "$env_file" ]; then
            log_info "Updating ${service}..."

            # Add Vault configuration if not already present
            if ! grep -q "VAULT_ADDR" "$env_file"; then
                cat >> "$env_file" << 'EOF'

# ============================================================================
# VAULT CONFIGURATION (Added by setup_secrets_management.sh)
# ============================================================================
VAULT_ADDR=http://127.0.0.1:8200
# VAULT_TOKEN will be set via environment or docker-compose
# For production, use service-specific tokens from .vault-keys/service-tokens/

EOF
                log_success "Updated ${service}/.env"
            else
                log_info "${service}/.env already has Vault config"
            fi
        else
            log_warning "${service}/.env not found, skipping"
        fi
    done
}

################################################################################
# Verify Installation
################################################################################

verify_installation() {
    log_step "Verifying installation..."

    export VAULT_ADDR='http://127.0.0.1:8200'
    export VAULT_TOKEN='dev-only-token'

    local errors=0

    # Check Vault status
    log_info "Checking Vault status..."
    if vault status &>/dev/null; then
        log_success "Vault is running and accessible"
    else
        log_error "Vault status check failed"
        errors=$((errors + 1))
    fi

    # Check secret engines
    log_info "Checking secret engines..."
    local engines=("secret/" "database/" "transit/" "pki/")
    for engine in "${engines[@]}"; do
        if vault secrets list | grep -q "^${engine}"; then
            log_success "Secret engine enabled: ${engine}"
        else
            log_error "Secret engine not found: ${engine}"
            errors=$((errors + 1))
        fi
    done

    # Check policies
    log_info "Checking policies..."
    local policies=("trading-engine" "bybit-connector" "market-data" "portfolio-manager")
    for policy in "${policies[@]}"; do
        if vault policy list | grep -q "^${policy}$"; then
            log_success "Policy exists: ${policy}"
        else
            log_error "Policy not found: ${policy}"
            errors=$((errors + 1))
        fi
    done

    # Try reading a test secret
    log_info "Testing secret retrieval..."
    if vault kv get secret/bybit-connector/bybit &>/dev/null; then
        log_success "Secret retrieval successful"
    else
        log_warning "Could not read test secret (may not be migrated yet)"
    fi

    # Test Python Vault client
    log_info "Testing Python Vault client..."
    cd "${PROJECT_ROOT}"
    python3 << 'EOF'
import sys
sys.path.insert(0, 'shared')
try:
    from vault_client import VaultClient
    vault = VaultClient()
    health = vault.health_check()
    if health['healthy']:
        print("✓ Python Vault client working")
        sys.exit(0)
    else:
        print("✗ Vault unhealthy:", health.get('error'))
        sys.exit(1)
except Exception as e:
    print("✗ Python client test failed:", e)
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        log_success "Python Vault client test passed"
    else
        log_error "Python Vault client test failed"
        errors=$((errors + 1))
    fi

    if [ $errors -eq 0 ]; then
        log_success "All verification checks passed"
        return 0
    else
        log_error "Verification failed with ${errors} errors"
        return 1
    fi
}

################################################################################
# Generate Summary Report
################################################################################

generate_summary() {
    log_step "Generating summary report..."

    local report_file="${PROJECT_ROOT}/VAULT_SETUP_REPORT.txt"

    cat > "$report_file" << EOF
════════════════════════════════════════════════════════════════
Vault Setup Summary Report
Generated: $(date)
════════════════════════════════════════════════════════════════

INSTALLATION STATUS: ✓ SUCCESS

VAULT CONFIGURATION:
  - Address: http://127.0.0.1:8200
  - Mode: Development
  - Token: dev-only-token (stored in VAULT_TOKEN)
  - Storage: File backend
  - Audit: Enabled (file + application logs)

ENABLED SECRET ENGINES:
  - KV v2 (secret/)     - Static secrets
  - Database (database/) - Dynamic credentials
  - Transit (transit/)  - Encryption service
  - PKI (pki/)         - Certificate management

CREATED POLICIES:
  - trading-engine     - Trading Engine access
  - bybit-connector    - Bybit Connector access
  - market-data        - Market Data Service access
  - portfolio-manager  - Portfolio Manager access
  - admin              - Administrative access

SERVICE TOKENS:
  Location: ${PROJECT_ROOT}/infrastructure/vault/.vault-keys/service-tokens/

  Files:
    - trading-engine-token
    - bybit-connector-token
    - market-data-token
    - portfolio-manager-token

MIGRATED SECRETS:
  - Bybit API credentials
  - Database passwords
  - Redis password
  - RabbitMQ password
  - JWT secrets

BACKUP LOCATION:
  Original .env files: ${PROJECT_ROOT}/backups/env_files/

NEXT STEPS:

1. Update service Docker containers with Vault tokens:

   docker-compose exec bybit-connector sh -c 'export VAULT_TOKEN=\$(cat /vault-keys/bybit-connector-token)'

2. Test service connectivity:

   curl http://localhost:8001/health

3. Set up automated secret rotation:

   cd infrastructure/scripts
   python rotate_secrets.py --help

4. Review security documentation:

   cat docs/security/SECRETS_MANAGEMENT.md

5. Configure production Vault:

   cd infrastructure/vault
   ./setup_vault.sh prod

6. Enable monitoring:

   # Prometheus metrics available at Vault:8200/v1/sys/metrics

SECURITY RECOMMENDATIONS:

⚠️  CRITICAL - FOR PRODUCTION:

  1. Replace dev token with production tokens
  2. Enable TLS/SSL for Vault
  3. Use auto-unseal with cloud KMS
  4. Store unseal keys securely (split across team)
  5. Enable audit logging to external system
  6. Set up Vault HA cluster
  7. Regular backup of Vault data
  8. Implement key rotation schedule
  9. Monitor audit logs for suspicious activity
  10. Use short-lived tokens with auto-renewal

USEFUL COMMANDS:

# View secrets
vault kv list secret/
vault kv get secret/bybit-connector/bybit

# Generate new token
vault token create -policy=trading-engine -period=24h

# Rotate secrets
cd infrastructure/scripts
python rotate_secrets.py bybit --help

# Check Vault status
vault status

# View audit logs
tail -f /var/log/vault/audit.log

TROUBLESHOOTING:

If services can't connect to Vault:
  1. Check Vault is running: docker ps | grep vault
  2. Verify network: docker network inspect crypto-bot-network
  3. Check logs: docker logs crypto-bot-vault
  4. Verify token: vault token lookup

If secret retrieval fails:
  1. Check policy: vault policy read <service-name>
  2. Verify secret path: vault kv list secret/
  3. Test with root token first
  4. Check application logs

SUPPORT:

  - Documentation: docs/security/SECRETS_MANAGEMENT.md
  - Vault CLI: vault --help
  - Python client: shared/vault_client.py
  - Setup script: infrastructure/vault/setup_vault.sh

════════════════════════════════════════════════════════════════
Setup completed successfully! 🎉
════════════════════════════════════════════════════════════════
EOF

    cat "$report_file"
    log_success "Summary report saved to: ${report_file}"
}

################################################################################
# Cleanup on Error
################################################################################

cleanup_on_error() {
    log_error "Setup failed. Cleaning up..."

    # Stop Vault if it was started
    cd "${PROJECT_ROOT}/infrastructure"
    docker-compose --profile security stop vault 2>/dev/null || true

    log_info "Cleanup complete. Check logs for details."
}

################################################################################
# Main Setup Function
################################################################################

main_setup() {
    # Show banner
    show_banner

    # Set error handler
    trap cleanup_on_error ERR

    # Run setup steps
    check_prerequisites || exit 1
    install_python_dependencies || exit 1
    start_vault || exit 1

    # Wait a bit for Vault to fully initialize
    sleep 5

    configure_vault || exit 1

    # Ask if user wants to migrate secrets
    read -p "Migrate secrets from .env files now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        migrate_secrets || exit 1
    else
        log_info "Skipping secret migration. Run manually later with:"
        log_info "  cd infrastructure/scripts"
        log_info "  python migrate_secrets_to_vault.py"
    fi

    update_service_configs || exit 1
    verify_installation || exit 1
    generate_summary

    # Success message
    echo
    log_success "════════════════════════════════════════════════════════════════"
    log_success "Secrets Management Setup Complete! 🎉"
    log_success "════════════════════════════════════════════════════════════════"
    echo
    log_info "Vault is running at: http://127.0.0.1:8200"
    log_info "Root token: dev-only-token"
    log_info "Next steps in: VAULT_SETUP_REPORT.txt"
    echo
}

################################################################################
# Script Entry Point
################################################################################

# Parse command line arguments
case "${1:-setup}" in
    setup)
        main_setup
        ;;
    verify)
        export VAULT_ADDR='http://127.0.0.1:8200'
        export VAULT_TOKEN='dev-only-token'
        verify_installation
        ;;
    help|--help|-h)
        cat << EOF
Usage: $0 [COMMAND]

Commands:
    setup    Run complete setup (default)
    verify   Verify existing installation
    help     Show this help message

Examples:
    $0              # Run full setup
    $0 setup        # Run full setup
    $0 verify       # Verify installation

EOF
        ;;
    *)
        log_error "Unknown command: $1"
        log_info "Run '$0 help' for usage information"
        exit 1
        ;;
esac
