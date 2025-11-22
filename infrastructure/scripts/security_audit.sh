#!/bin/bash
################################################################################
# Security Audit Script for Crypto Trading Bot
# Purpose: Comprehensive security checks and vulnerability scanning
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
readonly REPORT_DIR="${PROJECT_ROOT}/logs/security/audits"
readonly REPORT_FILE="${REPORT_DIR}/security_audit_$(date +%Y%m%d_%H%M%S).md"

# Audit configuration
readonly PASSWORD_MIN_LENGTH=24
readonly MAX_PASSWORD_AGE_DAYS=90
readonly MAX_FILE_AGE_DAYS=30

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Arrays to store findings
declare -a CRITICAL_FINDINGS=()
declare -a HIGH_FINDINGS=()
declare -a MEDIUM_FINDINGS=()
declare -a LOW_FINDINGS=()
declare -a INFO_FINDINGS=()

################################################################################
# Logging Functions
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $*"
    ((PASSED_CHECKS++))
    ((TOTAL_CHECKS++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $*"
    ((WARNING_CHECKS++))
    ((TOTAL_CHECKS++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $*"
    ((FAILED_CHECKS++))
    ((TOTAL_CHECKS++))
}

add_finding() {
    local severity=$1
    shift
    local finding="$*"

    case "${severity}" in
        CRITICAL)
            CRITICAL_FINDINGS+=("${finding}")
            ;;
        HIGH)
            HIGH_FINDINGS+=("${finding}")
            ;;
        MEDIUM)
            MEDIUM_FINDINGS+=("${finding}")
            ;;
        LOW)
            LOW_FINDINGS+=("${finding}")
            ;;
        INFO)
            INFO_FINDINGS+=("${finding}")
            ;;
    esac
}

################################################################################
# Setup Functions
################################################################################

setup_audit() {
    log_info "Setting up security audit..."

    mkdir -p "${REPORT_DIR}"
    chmod 700 "${REPORT_DIR}"

    # Create report header
    cat > "${REPORT_FILE}" <<EOF
# Security Audit Report

**Date:** $(date '+%Y-%m-%d %H:%M:%S')
**Auditor:** $(whoami)
**System:** $(uname -a)
**Project:** Crypto Trading Bot
**Version:** 1.0

---

## Executive Summary

This report contains the results of a comprehensive security audit of the Crypto Trading Bot infrastructure.

EOF

    log_success "Audit setup complete"
}

################################################################################
# Audit Checks
################################################################################

check_hardcoded_secrets() {
    log_info "Checking for hardcoded secrets in code..."

    local secret_patterns=(
        "password\s*=\s*['\"][^'\"]{8,}"
        "api[_-]?key\s*=\s*['\"][^'\"]{8,}"
        "secret\s*=\s*['\"][^'\"]{8,}"
        "token\s*=\s*['\"][^'\"]{8,}"
        "aws[_-]?access[_-]?key"
        "private[_-]?key"
        "-----BEGIN.*PRIVATE KEY-----"
    )

    local found_secrets=0

    for pattern in "${secret_patterns[@]}"; do
        local matches=$(find "${PROJECT_ROOT}" \
            -type f \
            -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.yml" -o -name "*.yaml" \
            ! -path "*/node_modules/*" \
            ! -path "*/.venv/*" \
            ! -path "*/venv/*" \
            ! -path "*/.git/*" \
            -exec grep -l -E "${pattern}" {} \; 2>/dev/null || true)

        if [[ -n "${matches}" ]]; then
            while IFS= read -r file; do
                log_error "Potential hardcoded secret in: ${file}"
                add_finding "CRITICAL" "Hardcoded secret found in ${file}"
                ((found_secrets++))
            done <<< "${matches}"
        fi
    done

    if [[ ${found_secrets} -eq 0 ]]; then
        log_success "No hardcoded secrets found"
    else
        log_error "Found ${found_secrets} potential hardcoded secrets"
    fi
}

check_env_files() {
    log_info "Checking for exposed .env files..."

    local env_files=$(find "${PROJECT_ROOT}" \
        -type f \
        -name ".env" \
        ! -path "*/.git/*" \
        ! -path "*/node_modules/*")

    local exposed_count=0

    if [[ -n "${env_files}" ]]; then
        while IFS= read -r env_file; do
            # Check if .env is in .gitignore
            if git check-ignore "${env_file}" &>/dev/null; then
                log_success ".env file properly ignored: ${env_file}"
            else
                log_error ".env file NOT in .gitignore: ${env_file}"
                add_finding "HIGH" ".env file not properly ignored: ${env_file}"
                ((exposed_count++))
            fi

            # Check file permissions
            local perms=$(stat -c "%a" "${env_file}" 2>/dev/null || stat -f "%A" "${env_file}" 2>/dev/null)
            if [[ "${perms}" != "600" ]] && [[ "${perms}" != "400" ]]; then
                log_warning "Insecure permissions (${perms}) on: ${env_file}"
                add_finding "MEDIUM" "Insecure file permissions on ${env_file}"
            fi

            # Check for sensitive data
            if grep -qE "(password|secret|key|token)" "${env_file}"; then
                log_info "Contains sensitive data: ${env_file}"
            fi
        done <<< "${env_files}"
    fi

    if [[ ${exposed_count} -eq 0 ]]; then
        log_success "All .env files properly protected"
    fi
}

check_vault_connectivity() {
    log_info "Checking Vault connectivity..."

    if ! command -v vault &>/dev/null; then
        log_warning "Vault CLI not installed"
        add_finding "MEDIUM" "Vault CLI not available"
        return
    fi

    local vault_addr="${VAULT_ADDR:-http://127.0.0.1:8200}"

    if vault status &>/dev/null; then
        log_success "Vault is accessible at ${vault_addr}"

        # Check if Vault is sealed
        if vault status 2>&1 | grep -q "Sealed.*false"; then
            log_success "Vault is unsealed"
        else
            log_error "Vault is SEALED"
            add_finding "CRITICAL" "Vault is sealed - services cannot access secrets"
        fi

        # Check if authenticated
        if vault token lookup &>/dev/null; then
            log_success "Vault authentication valid"
        else
            log_warning "Vault authentication not configured"
            add_finding "HIGH" "Vault token not configured or expired"
        fi
    else
        log_error "Cannot connect to Vault at ${vault_addr}"
        add_finding "HIGH" "Vault is not accessible"
    fi
}

check_password_complexity() {
    log_info "Checking password complexity..."

    local env_file="${PROJECT_ROOT}/infrastructure/.env"

    if [[ ! -f "${env_file}" ]]; then
        log_warning "Environment file not found: ${env_file}"
        return
    fi

    local passwords=$(grep -E "_PASSWORD=" "${env_file}" | cut -d'=' -f2 || true)

    local weak_passwords=0

    while IFS= read -r password; do
        if [[ -z "${password}" ]]; then
            continue
        fi

        local length=${#password}

        if [[ ${length} -lt ${PASSWORD_MIN_LENGTH} ]]; then
            log_error "Password too short (${length} chars, minimum ${PASSWORD_MIN_LENGTH})"
            add_finding "HIGH" "Password does not meet minimum length requirement"
            ((weak_passwords++))
        else
            # Check for complexity (letters, numbers, special chars)
            if [[ "${password}" =~ [a-z] ]] && \
               [[ "${password}" =~ [A-Z] ]] && \
               [[ "${password}" =~ [0-9] ]] && \
               [[ "${password}" =~ [^a-zA-Z0-9] ]]; then
                log_success "Password meets complexity requirements"
            else
                log_warning "Password lacks complexity (missing uppercase, lowercase, numbers, or special characters)"
                add_finding "MEDIUM" "Password lacks sufficient complexity"
                ((weak_passwords++))
            fi
        fi
    done <<< "${passwords}"

    if [[ ${weak_passwords} -eq 0 ]]; then
        log_success "All passwords meet complexity requirements"
    fi
}

check_file_permissions() {
    log_info "Checking file permissions..."

    # Check critical files
    local critical_files=(
        "infrastructure/.env"
        "infrastructure/vault/vault-config.hcl"
        ".vault-keys/root-token"
        ".vault-keys/init-keys.json"
    )

    for file in "${critical_files[@]}"; do
        local filepath="${PROJECT_ROOT}/${file}"

        if [[ ! -f "${filepath}" ]]; then
            continue
        fi

        local perms=$(stat -c "%a" "${filepath}" 2>/dev/null || stat -f "%A" "${filepath}" 2>/dev/null)

        if [[ "${perms}" == "600" ]] || [[ "${perms}" == "400" ]]; then
            log_success "Secure permissions (${perms}) on ${file}"
        else
            log_error "Insecure permissions (${perms}) on ${file}"
            add_finding "HIGH" "Insecure file permissions on ${file}"
        fi
    done

    # Check script executability
    local scripts=$(find "${PROJECT_ROOT}/infrastructure/scripts" -type f -name "*.sh")

    while IFS= read -r script; do
        if [[ -x "${script}" ]]; then
            log_success "Script is executable: $(basename ${script})"
        else
            log_warning "Script not executable: $(basename ${script})"
            add_finding "LOW" "Script should be executable: ${script}"
        fi
    done <<< "${scripts}"
}

check_docker_security() {
    log_info "Checking Docker security configuration..."

    if ! command -v docker &>/dev/null; then
        log_warning "Docker not installed or not in PATH"
        return
    fi

    # Check if Docker daemon is running
    if ! docker info &>/dev/null; then
        log_error "Docker daemon not running"
        add_finding "HIGH" "Docker daemon is not accessible"
        return
    fi

    log_success "Docker daemon is running"

    # Check for containers running as root
    local root_containers=$(docker ps --format '{{.Names}}' --filter "label=com.docker.compose.project=crypto-bot" | \
        while read container; do
            if docker exec "${container}" id -u 2>/dev/null | grep -q "^0$"; then
                echo "${container}"
            fi
        done || true)

    if [[ -n "${root_containers}" ]]; then
        while IFS= read -r container; do
            log_warning "Container running as root: ${container}"
            add_finding "MEDIUM" "Container ${container} running as root user"
        done <<< "${root_containers}"
    else
        log_success "No containers running as root"
    fi

    # Check for exposed ports
    local exposed_ports=$(docker ps --format '{{.Names}}: {{.Ports}}' --filter "label=com.docker.compose.project=crypto-bot" | \
        grep -E "0\.0\.0\.0|:::" || true)

    if [[ -n "${exposed_ports}" ]]; then
        log_info "Exposed ports detected:"
        echo "${exposed_ports}"
        add_finding "INFO" "Review exposed Docker ports for necessity"
    fi

    # Check for privileged containers
    local privileged=$(docker ps --format '{{.Names}}' --filter "label=com.docker.compose.project=crypto-bot" | \
        while read container; do
            if docker inspect "${container}" --format '{{.HostConfig.Privileged}}' 2>/dev/null | grep -q "true"; then
                echo "${container}"
            fi
        done || true)

    if [[ -n "${privileged}" ]]; then
        while IFS= read -r container; do
            log_error "Privileged container detected: ${container}"
            add_finding "CRITICAL" "Container ${container} running in privileged mode"
        done <<< "${privileged}"
    else
        log_success "No privileged containers"
    fi
}

check_ssl_certificates() {
    log_info "Checking SSL/TLS configuration..."

    # Check if TLS is disabled in Vault config
    local vault_config="${PROJECT_ROOT}/infrastructure/vault/vault-config.hcl"

    if [[ -f "${vault_config}" ]]; then
        if grep -q "tls_disable\s*=\s*1" "${vault_config}"; then
            log_warning "TLS is disabled in Vault configuration"
            add_finding "HIGH" "Vault TLS is disabled - not suitable for production"
        else
            log_success "Vault TLS configuration looks secure"
        fi
    fi

    # Check certificate expiry (if certificates exist)
    local cert_dir="${PROJECT_ROOT}/infrastructure/certs"

    if [[ -d "${cert_dir}" ]]; then
        local certs=$(find "${cert_dir}" -name "*.crt" -o -name "*.pem")

        while IFS= read -r cert; do
            if [[ -z "${cert}" ]]; then
                continue
            fi

            local expiry=$(openssl x509 -enddate -noout -in "${cert}" 2>/dev/null | cut -d'=' -f2)

            if [[ -n "${expiry}" ]]; then
                local expiry_epoch=$(date -d "${expiry}" +%s 2>/dev/null || date -j -f "%b %d %H:%M:%S %Y %Z" "${expiry}" +%s 2>/dev/null)
                local now_epoch=$(date +%s)
                local days_until_expiry=$(( (expiry_epoch - now_epoch) / 86400 ))

                if [[ ${days_until_expiry} -lt 0 ]]; then
                    log_error "Certificate EXPIRED: ${cert}"
                    add_finding "CRITICAL" "Expired certificate: ${cert}"
                elif [[ ${days_until_expiry} -lt 30 ]]; then
                    log_warning "Certificate expires soon (${days_until_expiry} days): ${cert}"
                    add_finding "MEDIUM" "Certificate expiring soon: ${cert}"
                else
                    log_success "Certificate valid (${days_until_expiry} days): $(basename ${cert})"
                fi
            fi
        done <<< "${certs}"
    fi
}

check_database_security() {
    log_info "Checking database security..."

    # Check PostgreSQL connections
    if docker ps --format '{{.Names}}' | grep -q "crypto-bot-postgres"; then
        # Check for password authentication
        local pg_hba=$(docker exec crypto-bot-postgres cat /var/lib/postgresql/data/pg_hba.conf 2>/dev/null || true)

        if echo "${pg_hba}" | grep -q "trust"; then
            log_error "PostgreSQL allows trust authentication"
            add_finding "CRITICAL" "PostgreSQL trust authentication enabled"
        else
            log_success "PostgreSQL requires password authentication"
        fi

        # Check SSL mode
        if docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SHOW ssl;" 2>/dev/null | grep -q "off"; then
            log_warning "PostgreSQL SSL is disabled"
            add_finding "MEDIUM" "PostgreSQL SSL disabled"
        fi
    fi

    # Check Redis authentication
    if docker ps --format '{{.Names}}' | grep -q "crypto-bot-redis"; then
        if docker exec crypto-bot-redis redis-cli CONFIG GET requirepass 2>/dev/null | grep -q '""'; then
            log_error "Redis password not configured"
            add_finding "CRITICAL" "Redis authentication disabled"
        else
            log_success "Redis password authentication enabled"
        fi
    fi
}

check_git_security() {
    log_info "Checking Git security..."

    cd "${PROJECT_ROOT}"

    # Check for committed secrets
    local sensitive_files=$(git ls-files | grep -E "\.(env|pem|key|p12|pfx)$" || true)

    if [[ -n "${sensitive_files}" ]]; then
        while IFS= read -r file; do
            log_error "Sensitive file in Git: ${file}"
            add_finding "CRITICAL" "Sensitive file committed to Git: ${file}"
        done <<< "${sensitive_files}"
    else
        log_success "No obvious sensitive files in Git"
    fi

    # Check .gitignore
    if [[ -f ".gitignore" ]]; then
        local important_patterns=(".env" "*.pem" "*.key" ".vault-keys" "vault-keys.txt")

        for pattern in "${important_patterns[@]}"; do
            if grep -q "^${pattern}" .gitignore; then
                log_success ".gitignore contains: ${pattern}"
            else
                log_warning ".gitignore missing: ${pattern}"
                add_finding "LOW" ".gitignore should include ${pattern}"
            fi
        done
    else
        log_error ".gitignore file not found"
        add_finding "HIGH" "No .gitignore file present"
    fi

    # Check for large files (potential data leaks)
    local large_files=$(find . -type f -size +10M ! -path "*/.git/*" ! -path "*/node_modules/*" || true)

    if [[ -n "${large_files}" ]]; then
        log_warning "Large files detected (potential data exposure):"
        echo "${large_files}"
        add_finding "INFO" "Review large files for sensitive data"
    fi
}

check_network_security() {
    log_info "Checking network security..."

    # Check Docker network isolation
    if docker network ls | grep -q "crypto-bot-network"; then
        log_success "Isolated Docker network exists"

        # Check network driver
        local driver=$(docker network inspect crypto-bot-network --format '{{.Driver}}' 2>/dev/null)

        if [[ "${driver}" == "bridge" ]]; then
            log_success "Using bridge network driver"
        else
            log_info "Network driver: ${driver}"
        fi
    else
        log_warning "Isolated Docker network not found"
        add_finding "MEDIUM" "Services should use isolated Docker network"
    fi

    # Check exposed ports
    log_info "Checking for unnecessary exposed ports..."

    local exposed=$(docker ps --format '{{.Names}}: {{.Ports}}' | grep "0.0.0.0" || true)

    if [[ -n "${exposed}" ]]; then
        echo "${exposed}"
        add_finding "INFO" "Review exposed ports - minimize external access"
    fi
}

check_backup_security() {
    log_info "Checking backup security..."

    local backup_dir="${PROJECT_ROOT}/infrastructure/backups"

    if [[ -d "${backup_dir}" ]]; then
        # Check backup encryption
        local unencrypted=$(find "${backup_dir}" -type f ! -name "*.gpg" ! -name "*.enc" || true)

        if [[ -n "${unencrypted}" ]]; then
            log_warning "Unencrypted backup files found"
            add_finding "MEDIUM" "Backups should be encrypted"
        else
            log_success "All backups appear to be encrypted"
        fi

        # Check backup age
        local old_backups=$(find "${backup_dir}" -type f -mtime +${MAX_FILE_AGE_DAYS} || true)

        if [[ -n "${old_backups}" ]]; then
            log_info "Old backup files detected (>30 days)"
            add_finding "INFO" "Review backup retention policy"
        fi
    else
        log_warning "Backup directory not found"
        add_finding "LOW" "No backup directory found"
    fi
}

check_logging_security() {
    log_info "Checking logging security..."

    local log_dir="${PROJECT_ROOT}/logs"

    if [[ -d "${log_dir}" ]]; then
        # Check for secrets in logs
        local log_files=$(find "${log_dir}" -type f -name "*.log" | head -10)

        local secrets_in_logs=0

        while IFS= read -r log_file; do
            if [[ -z "${log_file}" ]]; then
                continue
            fi

            if grep -qE "(password|secret|token|api[_-]?key)[:=]\s*['\"]?[a-zA-Z0-9]{8,}" "${log_file}" 2>/dev/null; then
                log_warning "Potential secrets in log: ${log_file}"
                add_finding "HIGH" "Possible secrets logged in ${log_file}"
                ((secrets_in_logs++))
            fi
        done <<< "${log_files}"

        if [[ ${secrets_in_logs} -eq 0 ]]; then
            log_success "No obvious secrets found in logs"
        fi

        # Check log permissions
        local insecure_logs=$(find "${log_dir}" -type f -not -perm -600 || true)

        if [[ -n "${insecure_logs}" ]]; then
            log_warning "Insecure log file permissions"
            add_finding "LOW" "Log files should have restrictive permissions"
        fi
    else
        log_info "Log directory not found"
    fi
}

check_dependency_vulnerabilities() {
    log_info "Checking for vulnerable dependencies..."

    # Check Python dependencies
    if command -v pip &>/dev/null; then
        local vulnerable_packages=$(pip list --outdated --format=json 2>/dev/null | \
            jq -r '.[] | select(.latest_version != .version) | .name' || true)

        if [[ -n "${vulnerable_packages}" ]]; then
            log_warning "Outdated Python packages detected"
            add_finding "MEDIUM" "Update outdated Python packages"
        else
            log_success "Python packages are up to date"
        fi
    fi

    # Check for known vulnerable packages
    if command -v safety &>/dev/null; then
        if ! safety check &>/dev/null; then
            log_error "Vulnerable Python packages detected"
            add_finding "HIGH" "Known vulnerabilities in Python dependencies"
        else
            log_success "No known vulnerabilities in Python packages"
        fi
    else
        log_info "Install 'safety' for dependency vulnerability scanning"
    fi
}

################################################################################
# Report Generation
################################################################################

generate_report() {
    log_info "Generating security audit report..."

    # Add findings summary
    cat >> "${REPORT_FILE}" <<EOF

## Findings Summary

| Severity | Count |
|----------|-------|
| Critical | ${#CRITICAL_FINDINGS[@]} |
| High     | ${#HIGH_FINDINGS[@]} |
| Medium   | ${#MEDIUM_FINDINGS[@]} |
| Low      | ${#LOW_FINDINGS[@]} |
| Info     | ${#INFO_FINDINGS[@]} |

**Total Checks:** ${TOTAL_CHECKS}
**Passed:** ${PASSED_CHECKS}
**Failed:** ${FAILED_CHECKS}
**Warnings:** ${WARNING_CHECKS}

**Overall Score:** $(( (PASSED_CHECKS * 100) / TOTAL_CHECKS ))%

---

## Critical Findings

EOF

    if [[ ${#CRITICAL_FINDINGS[@]} -eq 0 ]]; then
        echo "✅ No critical findings" >> "${REPORT_FILE}"
    else
        for finding in "${CRITICAL_FINDINGS[@]}"; do
            echo "- ❌ ${finding}" >> "${REPORT_FILE}"
        done
    fi

    cat >> "${REPORT_FILE}" <<EOF

## High Severity Findings

EOF

    if [[ ${#HIGH_FINDINGS[@]} -eq 0 ]]; then
        echo "✅ No high severity findings" >> "${REPORT_FILE}"
    else
        for finding in "${HIGH_FINDINGS[@]}"; do
            echo "- ⚠️  ${finding}" >> "${REPORT_FILE}"
        done
    fi

    cat >> "${REPORT_FILE}" <<EOF

## Medium Severity Findings

EOF

    if [[ ${#MEDIUM_FINDINGS[@]} -eq 0 ]]; then
        echo "✅ No medium severity findings" >> "${REPORT_FILE}"
    else
        for finding in "${MEDIUM_FINDINGS[@]}"; do
            echo "- ⚠️  ${finding}" >> "${REPORT_FILE}"
        done
    fi

    cat >> "${REPORT_FILE}" <<EOF

## Recommendations

### Immediate Actions (Critical/High)

EOF

    if [[ ${#CRITICAL_FINDINGS[@]} -gt 0 ]] || [[ ${#HIGH_FINDINGS[@]} -gt 0 ]]; then
        cat >> "${REPORT_FILE}" <<EOF
1. Address all critical and high severity findings immediately
2. Rotate any exposed credentials
3. Review and update security policies
4. Implement additional monitoring

EOF
    else
        echo "✅ No immediate actions required" >> "${REPORT_FILE}"
    fi

    cat >> "${REPORT_FILE}" <<EOF

### Short-term Actions (Medium)

1. Review and address medium severity findings within 30 days
2. Update documentation for security procedures
3. Schedule regular security audits
4. Implement automated security scanning

### Long-term Improvements

1. Enable all security features in production
2. Implement comprehensive monitoring and alerting
3. Regular penetration testing
4. Security awareness training for team

---

## Audit Details

**Auditor:** $(whoami)
**Hostname:** $(hostname)
**Audit Duration:** $SECONDS seconds
**Report Location:** ${REPORT_FILE}

---

**Next Audit Due:** $(date -d "+30 days" '+%Y-%m-%d')

EOF

    log_success "Report generated: ${REPORT_FILE}"
}

################################################################################
# Main Execution
################################################################################

main() {
    cat <<'EOF'
╔═══════════════════════════════════════════════════════════╗
║   Crypto Trading Bot - Security Audit                    ║
║   Comprehensive Security Assessment                      ║
╚═══════════════════════════════════════════════════════════╝

EOF

    setup_audit

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Running security checks..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    check_hardcoded_secrets
    echo ""

    check_env_files
    echo ""

    check_vault_connectivity
    echo ""

    check_password_complexity
    echo ""

    check_file_permissions
    echo ""

    check_docker_security
    echo ""

    check_ssl_certificates
    echo ""

    check_database_security
    echo ""

    check_git_security
    echo ""

    check_network_security
    echo ""

    check_backup_security
    echo ""

    check_logging_security
    echo ""

    check_dependency_vulnerabilities
    echo ""

    generate_report

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Audit Summary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Total Checks: ${TOTAL_CHECKS}"
    echo -e "${GREEN}Passed: ${PASSED_CHECKS}${NC}"
    echo -e "${RED}Failed: ${FAILED_CHECKS}${NC}"
    echo -e "${YELLOW}Warnings: ${WARNING_CHECKS}${NC}"
    echo ""
    echo "Findings:"
    echo -e "${RED}Critical: ${#CRITICAL_FINDINGS[@]}${NC}"
    echo -e "${YELLOW}High: ${#HIGH_FINDINGS[@]}${NC}"
    echo -e "Medium: ${#MEDIUM_FINDINGS[@]}"
    echo -e "Low: ${#LOW_FINDINGS[@]}"
    echo ""
    echo "Report: ${REPORT_FILE}"
    echo ""

    # Exit code based on findings
    if [[ ${#CRITICAL_FINDINGS[@]} -gt 0 ]]; then
        return 2  # Critical findings
    elif [[ ${#HIGH_FINDINGS[@]} -gt 0 ]]; then
        return 1  # High findings
    else
        return 0  # All good
    fi
}

main "$@"
