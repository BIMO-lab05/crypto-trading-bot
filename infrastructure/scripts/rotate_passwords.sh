#!/bin/bash
################################################################################
# Password Rotation Script for Crypto Trading Bot
# Purpose: Securely rotate all database and service passwords
# Author: Security Engineer Agent
# Date: 2025-11-19
# Version: 1.0
################################################################################

set -euo pipefail  # Exit on error, undefined vars, pipe failures
IFS=$'\n\t'        # Set safe Internal Field Separator

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly BACKUP_DIR="${PROJECT_ROOT}/infrastructure/backups/passwords"
readonly LOG_DIR="${PROJECT_ROOT}/logs/security"
readonly LOG_FILE="${LOG_DIR}/password_rotation_$(date +%Y%m%d_%H%M%S).log"
readonly ENV_FILE="${PROJECT_ROOT}/infrastructure/.env"
readonly ROLLBACK_FILE="${BACKUP_DIR}/rollback_$(date +%Y%m%d_%H%M%S).env"

# Password complexity requirements
readonly MIN_PASSWORD_LENGTH=24
readonly PASSWORD_PATTERN='^[A-Za-z0-9@#$%^&+=!]{24,}$'

# Services that need password rotation
declare -a SERVICES=(
    "POSTGRES"
    "TIMESCALE"
    "REDIS"
    "RABBITMQ"
)

################################################################################
# Logging Functions
################################################################################

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" | tee -a "${LOG_FILE}"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
    log "INFO" "$*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
    log "SUCCESS" "$*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
    log "WARNING" "$*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
    log "ERROR" "$*"
}

################################################################################
# Utility Functions
################################################################################

setup_directories() {
    log_info "Setting up required directories..."
    mkdir -p "${BACKUP_DIR}" "${LOG_DIR}"
    chmod 700 "${BACKUP_DIR}" "${LOG_DIR}"
}

generate_secure_password() {
    # Generate cryptographically secure password
    # Uses /dev/urandom for better randomness
    local password=$(LC_ALL=C tr -dc 'A-Za-z0-9@#$%^&+=!' < /dev/urandom | head -c ${MIN_PASSWORD_LENGTH})

    # Validate password meets complexity requirements
    if [[ ! $password =~ $PASSWORD_PATTERN ]]; then
        log_error "Generated password does not meet complexity requirements"
        return 1
    fi

    echo "${password}"
}

validate_password() {
    local password=$1

    if [[ ${#password} -lt ${MIN_PASSWORD_LENGTH} ]]; then
        log_error "Password must be at least ${MIN_PASSWORD_LENGTH} characters"
        return 1
    fi

    if [[ ! $password =~ $PASSWORD_PATTERN ]]; then
        log_error "Password does not meet complexity requirements"
        return 1
    fi

    return 0
}

backup_current_env() {
    log_info "Backing up current environment configuration..."

    if [[ ! -f "${ENV_FILE}" ]]; then
        log_error "Environment file not found: ${ENV_FILE}"
        return 1
    fi

    # Create encrypted backup
    cp "${ENV_FILE}" "${ROLLBACK_FILE}"
    chmod 600 "${ROLLBACK_FILE}"

    # Create audit log entry
    cat >> "${LOG_FILE}" <<EOF

=== BACKUP CREATED ===
Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Backup File: ${ROLLBACK_FILE}
Original File: ${ENV_FILE}
Checksum: $(sha256sum "${ENV_FILE}" | cut -d' ' -f1)
=====================
EOF

    log_success "Backup created: ${ROLLBACK_FILE}"
    return 0
}

################################################################################
# Database Password Rotation Functions
################################################################################

rotate_postgres_password() {
    local new_password=$1
    local service_name="PostgreSQL"

    log_info "Rotating ${service_name} password..."

    # Update password in PostgreSQL
    if docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
        -c "ALTER USER cryptobot WITH PASSWORD '${new_password}';" &>/dev/null; then
        log_success "${service_name} password updated in database"
    else
        log_error "Failed to update ${service_name} password in database"
        return 1
    fi

    # Update environment file
    sed -i.bak "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${new_password}/" "${ENV_FILE}"

    # Update service environment files
    find "${PROJECT_ROOT}/services" -name ".env" -type f | while read service_env; do
        if grep -q "POSTGRES_PASSWORD" "${service_env}"; then
            sed -i.bak "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${new_password}/" "${service_env}"
            log_info "Updated ${service_env}"
        fi
    done

    return 0
}

rotate_timescaledb_password() {
    local new_password=$1
    local service_name="TimescaleDB"

    log_info "Rotating ${service_name} password..."

    # Update password in TimescaleDB
    if docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data \
        -c "ALTER USER cryptobot WITH PASSWORD '${new_password}';" &>/dev/null; then
        log_success "${service_name} password updated in database"
    else
        log_error "Failed to update ${service_name} password in database"
        return 1
    fi

    # Update environment file
    sed -i.bak "s/^TIMESCALE_PASSWORD=.*/TIMESCALE_PASSWORD=${new_password}/" "${ENV_FILE}"

    # Update service environment files
    find "${PROJECT_ROOT}/services" -name ".env" -type f | while read service_env; do
        if grep -q "TIMESCALE_PASSWORD" "${service_env}"; then
            sed -i.bak "s/^TIMESCALE_PASSWORD=.*/TIMESCALE_PASSWORD=${new_password}/" "${service_env}"
            log_info "Updated ${service_env}"
        fi
    done

    return 0
}

rotate_redis_password() {
    local new_password=$1
    local service_name="Redis"

    log_info "Rotating ${service_name} password..."

    # Update Redis password using CONFIG SET
    if docker exec crypto-bot-redis redis-cli CONFIG SET requirepass "${new_password}" &>/dev/null; then
        log_success "${service_name} password updated"
    else
        log_error "Failed to update ${service_name} password"
        return 1
    fi

    # Persist configuration
    docker exec crypto-bot-redis redis-cli -a "${new_password}" CONFIG REWRITE &>/dev/null

    # Update environment file
    sed -i.bak "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=${new_password}/" "${ENV_FILE}"

    # Update service environment files
    find "${PROJECT_ROOT}/services" -name ".env" -type f | while read service_env; do
        if grep -q "REDIS_PASSWORD" "${service_env}"; then
            sed -i.bak "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=${new_password}/" "${service_env}"
            log_info "Updated ${service_env}"
        fi
    done

    return 0
}

rotate_rabbitmq_password() {
    local new_password=$1
    local service_name="RabbitMQ"

    log_info "Rotating ${service_name} password..."

    # Update RabbitMQ user password
    if docker exec crypto-bot-rabbitmq rabbitmqctl change_password cryptobot "${new_password}" &>/dev/null; then
        log_success "${service_name} password updated"
    else
        log_error "Failed to update ${service_name} password"
        return 1
    fi

    # Update environment file
    sed -i.bak "s/^RABBITMQ_PASSWORD=.*/RABBITMQ_PASSWORD=${new_password}/" "${ENV_FILE}"

    # Update service environment files
    find "${PROJECT_ROOT}/services" -name ".env" -type f | while read service_env; do
        if grep -q "RABBITMQ_PASSWORD" "${service_env}"; then
            sed -i.bak "s/^RABBITMQ_PASSWORD=.*/RABBITMQ_PASSWORD=${new_password}/" "${service_env}"
            log_info "Updated ${service_env}"
        fi
    done

    return 0
}

################################################################################
# Verification Functions
################################################################################

verify_postgres_connection() {
    local password=$1

    if PGPASSWORD="${password}" psql -h localhost -p 5432 -U cryptobot -d cryptobot -c "SELECT 1;" &>/dev/null; then
        log_success "PostgreSQL connection verified"
        return 0
    else
        log_error "PostgreSQL connection verification failed"
        return 1
    fi
}

verify_timescaledb_connection() {
    local password=$1

    if PGPASSWORD="${password}" psql -h localhost -p 5433 -U cryptobot -d market_data -c "SELECT 1;" &>/dev/null; then
        log_success "TimescaleDB connection verified"
        return 0
    else
        log_error "TimescaleDB connection verification failed"
        return 1
    fi
}

verify_redis_connection() {
    local password=$1

    if redis-cli -h localhost -p 6379 -a "${password}" PING &>/dev/null; then
        log_success "Redis connection verified"
        return 0
    else
        log_error "Redis connection verification failed"
        return 1
    fi
}

verify_rabbitmq_connection() {
    local password=$1

    if docker exec crypto-bot-rabbitmq rabbitmqctl authenticate_user cryptobot "${password}" &>/dev/null; then
        log_success "RabbitMQ connection verified"
        return 0
    else
        log_error "RabbitMQ connection verification failed"
        return 1
    fi
}

################################################################################
# Rollback Function
################################################################################

rollback() {
    log_warning "Initiating rollback to previous configuration..."

    if [[ ! -f "${ROLLBACK_FILE}" ]]; then
        log_error "Rollback file not found: ${ROLLBACK_FILE}"
        return 1
    fi

    # Restore environment file
    cp "${ROLLBACK_FILE}" "${ENV_FILE}"

    # Restart services with old passwords
    log_info "Restarting services with previous configuration..."
    docker-compose -f "${PROJECT_ROOT}/infrastructure/docker-compose.yml" restart

    log_success "Rollback completed successfully"
    return 0
}

################################################################################
# Main Rotation Function
################################################################################

rotate_all_passwords() {
    local mode=${1:-"automatic"}  # automatic or interactive

    log_info "Starting password rotation process (mode: ${mode})..."

    # Create backup first
    if ! backup_current_env; then
        log_error "Backup failed. Aborting rotation."
        return 1
    fi

    # Generate new passwords
    declare -A NEW_PASSWORDS

    for service in "${SERVICES[@]}"; do
        if [[ "${mode}" == "interactive" ]]; then
            echo -n "Enter new password for ${service} (or press Enter for auto-generation): "
            read -s user_password
            echo

            if [[ -n "${user_password}" ]]; then
                if validate_password "${user_password}"; then
                    NEW_PASSWORDS[${service}]="${user_password}"
                else
                    log_error "Invalid password for ${service}"
                    return 1
                fi
            else
                NEW_PASSWORDS[${service}]=$(generate_secure_password)
            fi
        else
            NEW_PASSWORDS[${service}]=$(generate_secure_password)
        fi

        log_info "Generated new password for ${service}"
    done

    # Rotate passwords
    local rotation_failed=0

    if ! rotate_postgres_password "${NEW_PASSWORDS[POSTGRES]}"; then
        rotation_failed=1
    fi

    if ! rotate_timescaledb_password "${NEW_PASSWORDS[TIMESCALE]}"; then
        rotation_failed=1
    fi

    if ! rotate_redis_password "${NEW_PASSWORDS[REDIS]}"; then
        rotation_failed=1
    fi

    if ! rotate_rabbitmq_password "${NEW_PASSWORDS[RABBITMQ]}"; then
        rotation_failed=1
    fi

    # Verify all connections
    log_info "Verifying all connections..."

    sleep 5  # Allow services to update

    verify_postgres_connection "${NEW_PASSWORDS[POSTGRES]}"
    verify_timescaledb_connection "${NEW_PASSWORDS[TIMESCALE]}"
    verify_redis_connection "${NEW_PASSWORDS[REDIS]}"
    verify_rabbitmq_connection "${NEW_PASSWORDS[RABBITMQ]}"

    if [[ ${rotation_failed} -eq 1 ]]; then
        log_error "Password rotation failed. Initiating rollback..."
        rollback
        return 1
    fi

    # Clean up backup files
    find "${PROJECT_ROOT}" -name "*.env.bak" -delete

    log_success "Password rotation completed successfully!"

    # Generate summary report
    cat >> "${LOG_FILE}" <<EOF

=== ROTATION SUMMARY ===
Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Status: SUCCESS
Services Rotated: ${#SERVICES[@]}
Services: ${SERVICES[*]}
Backup Location: ${ROLLBACK_FILE}
Next Rotation Due: $(date -d "+90 days" +"%Y-%m-%d")
========================
EOF

    return 0
}

################################################################################
# CLI Interface
################################################################################

show_usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Password Rotation Script for Crypto Trading Bot

OPTIONS:
    -a, --automatic     Automatic rotation with generated passwords (default)
    -i, --interactive   Interactive mode - prompt for passwords
    -r, --rollback      Rollback to previous passwords
    -v, --verify        Verify current password configuration
    -h, --help          Show this help message

EXAMPLES:
    $0                      # Automatic rotation
    $0 --interactive        # Interactive with custom passwords
    $0 --rollback           # Rollback to previous configuration
    $0 --verify             # Verify current setup

SECURITY NOTES:
    - All passwords must be at least ${MIN_PASSWORD_LENGTH} characters
    - Passwords must contain letters, numbers, and special characters
    - Backups are created before rotation
    - All operations are logged to ${LOG_DIR}

EOF
}

verify_current_setup() {
    log_info "Verifying current password configuration..."

    # Source current environment
    if [[ -f "${ENV_FILE}" ]]; then
        source "${ENV_FILE}"
    else
        log_error "Environment file not found"
        return 1
    fi

    verify_postgres_connection "${POSTGRES_PASSWORD}"
    verify_timescaledb_connection "${TIMESCALE_PASSWORD}"
    verify_redis_connection "${REDIS_PASSWORD}"
    verify_rabbitmq_connection "${RABBITMQ_PASSWORD}"

    log_success "All connection verifications passed"
}

################################################################################
# Main Entry Point
################################################################################

main() {
    local mode="automatic"

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -a|--automatic)
                mode="automatic"
                shift
                ;;
            -i|--interactive)
                mode="interactive"
                shift
                ;;
            -r|--rollback)
                setup_directories
                rollback
                exit $?
                ;;
            -v|--verify)
                setup_directories
                verify_current_setup
                exit $?
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Banner
    cat <<EOF
╔═══════════════════════════════════════════════════════════╗
║   Crypto Trading Bot - Password Rotation Script          ║
║   Version: 1.0                                            ║
║   Date: $(date +"%Y-%m-%d %H:%M:%S")                                 ║
╚═══════════════════════════════════════════════════════════╝

EOF

    # Setup
    setup_directories

    # Check if running as root (not recommended)
    if [[ $EUID -eq 0 ]]; then
        log_warning "Running as root is not recommended"
        echo -n "Continue anyway? (y/N): "
        read -r response
        if [[ ! "${response}" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # Check if Docker is running
    if ! docker info &>/dev/null; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi

    # Check if services are running
    local required_containers=("crypto-bot-postgres" "crypto-bot-timescaledb" "crypto-bot-redis" "crypto-bot-rabbitmq")
    for container in "${required_containers[@]}"; do
        if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
            log_error "Container ${container} is not running"
            exit 1
        fi
    done

    # Confirm rotation
    if [[ "${mode}" == "automatic" ]]; then
        log_warning "This will rotate ALL service passwords automatically"
        echo -n "Continue? (y/N): "
        read -r response
        if [[ ! "${response}" =~ ^[Yy]$ ]]; then
            log_info "Password rotation cancelled by user"
            exit 0
        fi
    fi

    # Execute rotation
    if rotate_all_passwords "${mode}"; then
        log_success "Password rotation completed successfully!"
        log_info "Backup saved to: ${ROLLBACK_FILE}"
        log_info "Logs saved to: ${LOG_FILE}"
        exit 0
    else
        log_error "Password rotation failed. Check logs: ${LOG_FILE}"
        exit 1
    fi
}

# Execute main function
main "$@"
