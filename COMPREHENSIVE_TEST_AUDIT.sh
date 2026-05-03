#!/bin/bash
# ============================================================================
# COMPREHENSIVE PROJECT AUDIT AND TESTING SCRIPT
# Created: 2025-11-01
# Purpose: Test every component of the crypto trading bot from scratch
# TRUST NOTHING - VERIFY EVERYTHING
# ============================================================================

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Output file for detailed report
REPORT_FILE="TEST_AUDIT_REPORT_$(date +%Y%m%d_%H%M%S).md"
# Project root resolves from script location (was hardcoded WSL path).
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNING_TESTS=0

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

log_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
    echo -e "\n## $1\n" >> "$REPORT_FILE"
}

log_test() {
    local test_name="$1"
    echo -e "${YELLOW}→ Testing: ${test_name}${NC}"
    echo -e "### Test: $test_name\n" >> "$REPORT_FILE"
    ((TOTAL_TESTS++))
}

log_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    echo -e "✅ **PASS**: $1\n" >> "$REPORT_FILE"
    ((PASSED_TESTS++))
}

log_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    echo -e "❌ **FAIL**: $1\n" >> "$REPORT_FILE"
    ((FAILED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}⚠ WARNING${NC}: $1"
    echo -e "⚠️ **WARNING**: $1\n" >> "$REPORT_FILE"
    ((WARNING_TESTS++))
}

log_info() {
    echo -e "  $1"
    echo -e "$1\n" >> "$REPORT_FILE"
}

# ============================================================================
# INITIALIZE REPORT
# ============================================================================

cat > "$REPORT_FILE" << EOF
# Comprehensive Project Audit Report
**Generated:** $(date)
**Project:** Crypto Trading Bot
**Auditor:** Automated Testing Script

---

## Executive Summary

This report contains a complete audit of the crypto trading bot project, testing every component from scratch without trusting any previous implementations.

---

EOF

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  COMPREHENSIVE PROJECT AUDIT - CRYPTO TRADING BOT          ║${NC}"
echo -e "${GREEN}║  TRUST NOTHING - VERIFY EVERYTHING                         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}\n"

cd "$PROJECT_ROOT" || exit 1

# ============================================================================
# 1. PROJECT STRUCTURE AUDIT
# ============================================================================

log_header "1. PROJECT STRUCTURE AUDIT"

log_test "Project root directory exists"
if [ -d "$PROJECT_ROOT" ]; then
    log_pass "Project root exists at $PROJECT_ROOT"
else
    log_fail "Project root not found"
    exit 1
fi

log_test "Required directories"
required_dirs=("services" "frontend" "infrastructure" "docs" "tests" "scripts" "shared")
for dir in "${required_dirs[@]}"; do
    if [ -d "$PROJECT_ROOT/$dir" ]; then
        log_pass "Directory exists: $dir"
    else
        log_fail "Missing directory: $dir"
    fi
done

log_test "Services directory structure"
services=("bybit-connector" "market-data-service" "technical-analysis" "trading-engine" "portfolio-manager" "api-gateway" "notification-service")
for service in "${services[@]}"; do
    if [ -d "$PROJECT_ROOT/services/$service" ]; then
        log_pass "Service exists: $service"

        # Check for main.py
        if [ -f "$PROJECT_ROOT/services/$service/app/main.py" ]; then
            log_pass "  └─ main.py found"
        else
            log_fail "  └─ main.py missing"
        fi

        # Check for requirements.txt
        if [ -f "$PROJECT_ROOT/services/$service/requirements.txt" ]; then
            log_pass "  └─ requirements.txt found"
        else
            log_fail "  └─ requirements.txt missing"
        fi
    else
        log_fail "Service missing: $service"
    fi
done

# ============================================================================
# 2. CONFIGURATION AUDIT
# ============================================================================

log_header "2. CONFIGURATION AUDIT"

log_test "Environment configuration"
if [ -f "$PROJECT_ROOT/.env" ]; then
    log_pass ".env file exists"

    # Check for critical variables
    log_test "Critical environment variables"
    critical_vars=("BYBIT_API_KEY" "BYBIT_API_SECRET" "POSTGRES_PASSWORD" "REDIS_PASSWORD" "RABBITMQ_PASSWORD")
    for var in "${critical_vars[@]}"; do
        if grep -q "^${var}=" "$PROJECT_ROOT/.env"; then
            value=$(grep "^${var}=" "$PROJECT_ROOT/.env" | cut -d'=' -f2)
            if [[ "$value" == *"change_this"* ]] || [[ "$value" == *"your_"* ]] || [ -z "$value" ]; then
                log_warning "$var is not configured (using default/placeholder)"
            else
                log_pass "$var is configured"
            fi
        else
            log_warning "$var not found in .env"
        fi
    done
else
    log_fail ".env file not found"
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        log_info "  .env.example exists - need to copy and configure"
    fi
fi

log_test "Docker Compose configuration"
if [ -f "$PROJECT_ROOT/infrastructure/docker-compose.yml" ]; then
    log_pass "docker-compose.yml exists"

    # Check for required services
    required_services=("postgres" "redis" "rabbitmq")
    for svc in "${required_services[@]}"; do
        if grep -q "  ${svc}:" "$PROJECT_ROOT/infrastructure/docker-compose.yml"; then
            log_pass "  └─ Service defined: $svc"
        else
            log_fail "  └─ Service missing: $svc"
        fi
    done
else
    log_fail "docker-compose.yml not found"
fi

# ============================================================================
# 3. PYTHON DEPENDENCIES AUDIT
# ============================================================================

log_header "3. PYTHON DEPENDENCIES AUDIT"

log_test "Python version"
python_version=$(python3 --version 2>&1)
log_info "Detected: $python_version"
if [[ $python_version == *"3.12"* ]] || [[ $python_version == *"3.11"* ]] || [[ $python_version == *"3.10"* ]]; then
    log_pass "Python version is compatible"
else
    log_warning "Python version may not be optimal (recommended: 3.10+)"
fi

log_test "Virtual environments"
for service in "${services[@]}"; do
    service_dir="$PROJECT_ROOT/services/$service"
    if [ -d "$service_dir/venv" ]; then
        log_pass "$service: Virtual environment exists"
    else
        log_warning "$service: No virtual environment found"
    fi
done

log_test "Dependencies check (sample service: bybit-connector)"
if [ -f "$PROJECT_ROOT/services/bybit-connector/requirements.txt" ]; then
    req_file="$PROJECT_ROOT/services/bybit-connector/requirements.txt"
    log_pass "requirements.txt found"

    # Check for critical dependencies
    critical_deps=("fastapi" "uvicorn" "pybit" "httpx" "websockets")
    for dep in "${critical_deps[@]}"; do
        if grep -q "^${dep}" "$req_file"; then
            log_pass "  └─ $dep: $(grep "^${dep}" "$req_file")"
        else
            log_fail "  └─ $dep: NOT FOUND"
        fi
    done
else
    log_fail "requirements.txt not found for bybit-connector"
fi

# ============================================================================
# 4. SECURITY AUDIT
# ============================================================================

log_header "4. SECURITY AUDIT"

log_test "Git ignore configuration"
if [ -f "$PROJECT_ROOT/.gitignore" ]; then
    log_pass ".gitignore exists"

    # Check for sensitive patterns
    sensitive_patterns=(".env" "*.key" "*.pem" "__pycache__" "venv")
    for pattern in "${sensitive_patterns[@]}"; do
        if grep -q "$pattern" "$PROJECT_ROOT/.gitignore"; then
            log_pass "  └─ Ignoring: $pattern"
        else
            log_warning "  └─ Not ignoring: $pattern"
        fi
    done
else
    log_fail ".gitignore not found"
fi

log_test "API key exposure check"
# Search for potential API keys in code
if grep -r "AKIA\|sk-\|ghp_\|gho_" --include="*.py" "$PROJECT_ROOT/services" 2>/dev/null | grep -v "example\|placeholder"; then
    log_fail "Potential hardcoded API keys found!"
else
    log_pass "No hardcoded API keys detected"
fi

log_test "Password in code check"
if grep -ri "password\s*=\s*['\"]" --include="*.py" "$PROJECT_ROOT/services" 2>/dev/null | grep -v "get_settings\|os.getenv\|env\[" | grep -v "example"; then
    log_warning "Potential hardcoded passwords found"
else
    log_pass "No hardcoded passwords detected"
fi

log_test "SQL injection vulnerability check"
# Look for string concatenation in SQL queries
if grep -r "f\".*SELECT\|f\".*INSERT\|f\".*UPDATE\|f\".*DELETE" --include="*.py" "$PROJECT_ROOT/services" 2>/dev/null; then
    log_warning "Potential SQL injection vulnerabilities (f-strings in queries)"
else
    log_pass "No obvious SQL injection patterns"
fi

# ============================================================================
# 5. CODE QUALITY AUDIT
# ============================================================================

log_header "5. CODE QUALITY AUDIT"

log_test "Python syntax check (all services)"
syntax_errors=0
for service in "${services[@]}"; do
    service_dir="$PROJECT_ROOT/services/$service"
    if [ -d "$service_dir/app" ]; then
        for py_file in $(find "$service_dir/app" -name "*.py" 2>/dev/null); do
            if ! python3 -m py_compile "$py_file" 2>/dev/null; then
                log_fail "Syntax error in: $(basename $(dirname $py_file))/$(basename $py_file)"
                ((syntax_errors++))
            fi
        done
    fi
done

if [ $syntax_errors -eq 0 ]; then
    log_pass "All Python files have valid syntax"
else
    log_fail "Found $syntax_errors files with syntax errors"
fi

log_test "Import validity check (sample: bybit-connector)"
main_file="$PROJECT_ROOT/services/bybit-connector/app/main.py"
if [ -f "$main_file" ]; then
    # Check if imports are properly defined
    if grep -q "^from\|^import" "$main_file"; then
        log_pass "Imports found in main.py"

        # Check for relative imports
        if grep -q "^from app\." "$main_file"; then
            log_pass "  └─ Using relative imports (app.)"
        fi
    else
        log_fail "No imports found in main.py"
    fi
fi

log_test "TODO/FIXME comments check"
todo_count=$(grep -r "TODO\|FIXME\|XXX\|HACK" --include="*.py" "$PROJECT_ROOT/services" 2>/dev/null | wc -l)
if [ $todo_count -gt 0 ]; then
    log_warning "Found $todo_count TODO/FIXME comments in code"
    log_info "  (Review these for incomplete features)"
else
    log_pass "No TODO/FIXME comments found"
fi

# ============================================================================
# 6. DOCUMENTATION AUDIT
# ============================================================================

log_header "6. DOCUMENTATION AUDIT"

log_test "README existence"
if [ -f "$PROJECT_ROOT/README.md" ]; then
    log_pass "README.md exists"
    lines=$(wc -l < "$PROJECT_ROOT/README.md")
    log_info "  └─ $lines lines"
    if [ $lines -gt 50 ]; then
        log_pass "  └─ Comprehensive documentation"
    else
        log_warning "  └─ README may need more content"
    fi
else
    log_fail "README.md not found"
fi

log_test "Architecture documentation"
arch_docs=("SYSTEM_OVERVIEW.md" "SERVICE_CONTRACTS.md")
for doc in "${arch_docs[@]}"; do
    if [ -f "$PROJECT_ROOT/docs/architecture/$doc" ]; then
        log_pass "$doc exists"
    else
        log_fail "$doc missing"
    fi
done

log_test "Setup documentation"
if [ -f "$PROJECT_ROOT/docs/development/SETUP.md" ]; then
    log_pass "SETUP.md exists"
else
    log_fail "SETUP.md missing"
fi

log_test "API documentation"
if [ -f "$PROJECT_ROOT/docs/api/openapi.yaml" ]; then
    log_pass "OpenAPI specification exists"
else
    log_warning "OpenAPI specification not found"
fi

# ============================================================================
# 7. DATABASE AUDIT
# ============================================================================

log_header "7. DATABASE AUDIT"

log_test "Database initialization scripts"
if [ -f "$PROJECT_ROOT/infrastructure/scripts/init-db.sql" ]; then
    log_pass "PostgreSQL init script exists"
else
    log_warning "PostgreSQL init script not found"
fi

if [ -f "$PROJECT_ROOT/infrastructure/scripts/init-timescale.sql" ]; then
    log_pass "TimescaleDB init script exists"
else
    log_warning "TimescaleDB init script not found"
fi

log_test "Database connection check"
# Check if Docker is running and database is accessible
if command -v docker &> /dev/null; then
    if docker ps 2>/dev/null | grep -q "crypto-bot-postgres"; then
        log_pass "PostgreSQL container is running"
    else
        log_warning "PostgreSQL container not running"
        log_info "  └─ Run: cd infrastructure && docker-compose up -d"
    fi
else
    log_warning "Docker not available for testing"
fi

# ============================================================================
# 8. SERVICE FUNCTIONALITY AUDIT
# ============================================================================

log_header "8. SERVICE FUNCTIONALITY AUDIT"

log_test "Service endpoint availability (if running)"
service_ports=(8000 8001 8002 8003 8004 8005)
service_names=("API Gateway" "Trading Engine" "Bybit Connector" "Market Data" "Technical Analysis" "Portfolio Manager")

for i in "${!service_ports[@]}"; do
    port=${service_ports[$i]}
    name=${service_names[$i]}

    if nc -z localhost $port 2>/dev/null; then
        log_pass "$name (port $port) is accessible"

        # Try to hit health endpoint
        if command -v curl &> /dev/null; then
            response=$(curl -s "http://localhost:$port/health" 2>/dev/null)
            if [ -n "$response" ]; then
                log_pass "  └─ Health endpoint responding"
            fi
        fi
    else
        log_info "$name (port $port) not running (expected if services not started)"
    fi
done

# ============================================================================
# 9. FRONTEND AUDIT
# ============================================================================

log_header "9. FRONTEND AUDIT"

log_test "Frontend directory"
if [ -d "$PROJECT_ROOT/frontend" ]; then
    log_pass "Frontend directory exists"

    # Check for package.json
    if [ -f "$PROJECT_ROOT/frontend/package.json" ]; then
        log_pass "  └─ package.json found"
    else
        log_fail "  └─ package.json missing"
    fi

    # Check for node_modules
    if [ -d "$PROJECT_ROOT/frontend/node_modules" ]; then
        log_pass "  └─ node_modules installed"
    else
        log_warning "  └─ node_modules not installed (run npm install)"
    fi
else
    log_fail "Frontend directory not found"
fi

# ============================================================================
# 10. TESTING INFRASTRUCTURE AUDIT
# ============================================================================

log_header "10. TESTING INFRASTRUCTURE AUDIT"

log_test "Test directories"
for service in "${services[@]}"; do
    test_dir="$PROJECT_ROOT/services/$service/tests"
    if [ -d "$test_dir" ]; then
        test_count=$(find "$test_dir" -name "test_*.py" 2>/dev/null | wc -l)
        if [ $test_count -gt 0 ]; then
            log_pass "$service: $test_count test files found"
        else
            log_warning "$service: test directory exists but no test files"
        fi
    else
        log_warning "$service: no test directory"
    fi
done

log_test "Pytest configuration"
for service in "${services[@]}"; do
    if [ -f "$PROJECT_ROOT/services/$service/pytest.ini" ] || [ -f "$PROJECT_ROOT/services/$service/pyproject.toml" ]; then
        log_pass "$service: pytest configured"
    fi
done

# ============================================================================
# 11. GIT REPOSITORY AUDIT
# ============================================================================

log_header "11. GIT REPOSITORY AUDIT"

log_test "Git repository"
if [ -d "$PROJECT_ROOT/.git" ]; then
    log_pass "Git repository initialized"

    # Check branch
    branch=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)
    log_info "  └─ Current branch: $branch"

    # Check for uncommitted changes
    if git -C "$PROJECT_ROOT" diff --quiet 2>/dev/null; then
        log_pass "  └─ No uncommitted changes"
    else
        log_info "  └─ Uncommitted changes present"
    fi

    # Check remote
    if git -C "$PROJECT_ROOT" remote -v 2>/dev/null | grep -q origin; then
        log_pass "  └─ Remote repository configured"
    else
        log_info "  └─ No remote repository"
    fi
else
    log_fail "Git repository not initialized"
fi

# ============================================================================
# 12. MONITORING & LOGGING AUDIT
# ============================================================================

log_header "12. MONITORING & LOGGING AUDIT"

log_test "Log directories"
if [ -d "$PROJECT_ROOT/logs" ]; then
    log_pass "Logs directory exists"
    log_count=$(find "$PROJECT_ROOT/logs" -name "*.log" 2>/dev/null | wc -l)
    log_info "  └─ $log_count log files present"
else
    log_info "Logs directory not found (will be created on startup)"
fi

log_test "Monitoring configuration"
if grep -r "prometheus" --include="requirements.txt" "$PROJECT_ROOT/services" 2>/dev/null | grep -q prometheus; then
    log_pass "Prometheus client found in dependencies"
else
    log_warning "Prometheus monitoring may not be configured"
fi

# ============================================================================
# SUMMARY
# ============================================================================

log_header "AUDIT SUMMARY"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                        TEST RESULTS                            ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Total Tests:${NC}     $TOTAL_TESTS"
echo -e "${GREEN}Passed:${NC}          $PASSED_TESTS"
echo -e "${RED}Failed:${NC}          $FAILED_TESTS"
echo -e "${YELLOW}Warnings:${NC}        $WARNING_TESTS"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"

# Calculate pass rate
if [ $TOTAL_TESTS -gt 0 ]; then
    pass_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    echo -e "${GREEN}Pass Rate:${NC}       $pass_rate%\n"
fi

# Write summary to report
cat >> "$REPORT_FILE" << EOF

---

## Test Summary

- **Total Tests:** $TOTAL_TESTS
- **Passed:** $PASSED_TESTS
- **Failed:** $FAILED_TESTS
- **Warnings:** $WARNING_TESTS
- **Pass Rate:** $pass_rate%

## Recommendations

EOF

# Generate recommendations based on failures
if [ $FAILED_TESTS -gt 0 ]; then
    echo "### Critical Issues" >> "$REPORT_FILE"
    echo "- $FAILED_TESTS tests failed. Review failures above and address immediately." >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
fi

if [ $WARNING_TESTS -gt 0 ]; then
    echo "### Warnings" >> "$REPORT_FILE"
    echo "- $WARNING_TESTS warnings detected. These should be reviewed but may not be critical." >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
fi

if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "### Immediate Actions" >> "$REPORT_FILE"
    echo "1. Copy .env.example to .env and configure all variables" >> "$REPORT_FILE"
    echo "2. Generate secure passwords for databases" >> "$REPORT_FILE"
    echo "3. Configure Bybit API keys (testnet first)" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
fi

echo -e "${GREEN}✓ Audit complete!${NC}"
echo -e "${GREEN}✓ Detailed report saved to: $REPORT_FILE${NC}\n"

# Exit with appropriate code
if [ $FAILED_TESTS -gt 0 ]; then
    exit 1
else
    exit 0
fi
