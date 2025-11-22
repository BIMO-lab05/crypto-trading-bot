#!/bin/bash
# Emergency Security Hardening Script
# Fixes CRITICAL vulnerabilities immediately
# Run from project root: ./scripts/security/emergency_hardening.sh

set -e  # Exit on error

echo "==================================================================="
echo "   EMERGENCY SECURITY HARDENING - CRYPTO TRADING BOT"
echo "==================================================================="
echo ""
echo "This script will:"
echo "  1. Backup current configurations"
echo "  2. Add Redis passwords to all service .env files"
echo "  3. Generate strong passwords for infrastructure"
echo "  4. Remove dangerous port mappings"
echo "  5. Bind monitoring services to localhost"
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted by user"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure we're in project root
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}ERROR: Must run from project root${NC}"
    exit 1
fi

# Step 1: Backup current configs
echo ""
echo "=== STEP 1: Backing up configurations ==="
BACKUP_DIR="backups/security-hardening-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

cp infrastructure/docker-compose.yml "$BACKUP_DIR/" 2>/dev/null || true
cp docker-compose.yml "$BACKUP_DIR/" 2>/dev/null || true
cp .env "$BACKUP_DIR/" 2>/dev/null || true

# Backup all service .env files
for env_file in services/*/.env; do
    if [ -f "$env_file" ]; then
        service_name=$(dirname "$env_file" | xargs basename)
        cp "$env_file" "$BACKUP_DIR/${service_name}.env"
    fi
done

echo -e "${GREEN}✅ Backed up configurations to: $BACKUP_DIR${NC}"

# Step 2: Add Redis password to all .env files
echo ""
echo "=== STEP 2: Adding REDIS_PASSWORD to service .env files ==="

REDIS_PASSWORD="redis_dev_password"
UPDATED=0

for env_file in services/*/.env; do
    if [ -f "$env_file" ]; then
        if ! grep -q "REDIS_PASSWORD" "$env_file"; then
            echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> "$env_file"
            echo -e "${GREEN}✅ Added REDIS_PASSWORD to: $env_file${NC}"
            ((UPDATED++))
        else
            echo -e "${YELLOW}⚠️  REDIS_PASSWORD already exists in: $env_file${NC}"
        fi
    fi
done

echo -e "${GREEN}✅ Updated $UPDATED service .env files${NC}"

# Step 3: Generate strong passwords
echo ""
echo "=== STEP 3: Generating strong passwords ==="

mkdir -p .secrets
chmod 700 .secrets

# Generate passwords
openssl rand -base64 32 > .secrets/postgres_password
openssl rand -base64 32 > .secrets/timescale_password
openssl rand -base64 32 > .secrets/redis_password
openssl rand -base64 32 > .secrets/rabbitmq_password
openssl rand -base64 32 > .secrets/api_gateway_secret

chmod 600 .secrets/*

echo -e "${GREEN}✅ Generated strong passwords in .secrets/${NC}"
echo -e "${YELLOW}⚠️  MANUAL ACTION REQUIRED:${NC}"
echo "    Update infrastructure/docker-compose.yml with new passwords from .secrets/"
echo "    Update .env files with new passwords"

# Step 4: Update infrastructure docker-compose.yml
echo ""
echo "=== STEP 4: Removing dangerous port mappings ==="

INFRA_COMPOSE="infrastructure/docker-compose.yml"

if [ -f "$INFRA_COMPOSE" ]; then
    # Remove PostgreSQL port mapping
    sed -i.bak 's/- "5432:5432"/# - "5432:5432"  # REMOVED FOR SECURITY - Access via Docker network only/' "$INFRA_COMPOSE"

    # Remove TimescaleDB port mapping
    sed -i.bak 's/- "5433:5432"/# - "5433:5432"  # REMOVED FOR SECURITY - Access via Docker network only/' "$INFRA_COMPOSE"

    # Remove Redis port mapping
    sed -i.bak 's/- "6379:6379"/# - "6379:6379"  # REMOVED FOR SECURITY - Access via Docker network only/' "$INFRA_COMPOSE"

    # Bind RabbitMQ management to localhost
    sed -i.bak 's/- "0.0.0.0:15672:15672"/- "127.0.0.1:15672:15672"  # Bound to localhost for security/' "$INFRA_COMPOSE"
    sed -i.bak 's/- "15672:15672"/- "127.0.0.1:15672:15672"  # Bound to localhost for security/' "$INFRA_COMPOSE"

    echo -e "${GREEN}✅ Updated infrastructure/docker-compose.yml${NC}"
else
    echo -e "${YELLOW}⚠️  File not found: $INFRA_COMPOSE${NC}"
fi

# Step 5: Update main docker-compose.yml for monitoring
echo ""
echo "=== STEP 5: Securing monitoring services ==="

MAIN_COMPOSE="docker-compose.yml"

if [ -f "$MAIN_COMPOSE" ]; then
    # Bind Prometheus to localhost
    sed -i.bak 's/- "0.0.0.0:9090:9090"/- "127.0.0.1:9090:9090"  # Bound to localhost for security/' "$MAIN_COMPOSE"
    sed -i.bak 's/- "9090:9090"/- "127.0.0.1:9090:9090"  # Bound to localhost for security/' "$MAIN_COMPOSE"

    # Bind Grafana to localhost
    sed -i.bak 's/- "0.0.0.0:3001:3000"/- "127.0.0.1:3001:3000"  # Bound to localhost for security/' "$MAIN_COMPOSE"
    sed -i.bak 's/- "3001:3000"/- "127.0.0.1:3001:3000"  # Bound to localhost for security/' "$MAIN_COMPOSE"

    echo -e "${GREEN}✅ Updated docker-compose.yml (monitoring services)${NC}"
else
    echo -e "${YELLOW}⚠️  File not found: $MAIN_COMPOSE${NC}"
fi

# Step 6: Create .secrets/.gitignore
echo ""
echo "=== STEP 6: Protecting secrets directory ==="

cat > .secrets/.gitignore << 'EOF'
# Ignore all secrets
*
!.gitignore
EOF

echo -e "${GREEN}✅ Created .secrets/.gitignore${NC}"

# Step 7: Verify .env files are in .gitignore
echo ""
echo "=== STEP 7: Verifying .gitignore configuration ==="

if grep -q "^\.env$" .gitignore && grep -q "^\.secrets/$" .gitignore; then
    echo -e "${GREEN}✅ .env and .secrets/ are in .gitignore${NC}"
else
    echo -e "${YELLOW}⚠️  Adding .env and .secrets/ to .gitignore${NC}"
    echo "" >> .gitignore
    echo "# Security - Never commit secrets" >> .gitignore
    echo ".env" >> .gitignore
    echo ".secrets/" >> .gitignore
    echo "*.secret" >> .gitignore
fi

# Summary
echo ""
echo "==================================================================="
echo "   HARDENING COMPLETE"
echo "==================================================================="
echo ""
echo -e "${GREEN}✅ Completed Steps:${NC}"
echo "  1. Backed up configurations to: $BACKUP_DIR"
echo "  2. Added REDIS_PASSWORD to $UPDATED service .env files"
echo "  3. Generated strong passwords in .secrets/"
echo "  4. Removed PostgreSQL, TimescaleDB, Redis port mappings"
echo "  5. Bound RabbitMQ management to localhost"
echo "  6. Bound Prometheus and Grafana to localhost"
echo "  7. Protected .secrets directory"
echo ""
echo -e "${YELLOW}⚠️  MANUAL ACTIONS REQUIRED:${NC}"
echo ""
echo "  1. Update passwords in infrastructure/docker-compose.yml:"
echo "     POSTGRES_PASSWORD: $(cat .secrets/postgres_password)"
echo "     TIMESCALE_PASSWORD: $(cat .secrets/timescale_password)"
echo "     REDIS_PASSWORD: $(cat .secrets/redis_password)"
echo "     RABBITMQ_PASSWORD: $(cat .secrets/rabbitmq_password)"
echo ""
echo "  2. Update .env files with new passwords"
echo ""
echo "  3. Restart services:"
echo "     docker-compose down"
echo "     docker-compose -f infrastructure/docker-compose.yml down"
echo "     docker-compose -f infrastructure/docker-compose.yml up -d"
echo "     docker-compose up -d"
echo ""
echo "  4. Validate security:"
echo "     ./scripts/security/validate_security.sh"
echo ""
echo "  5. Test all services:"
echo "     ./scripts/health_check.sh"
echo ""
echo -e "${YELLOW}  6. Review full audit report:${NC}"
echo "     SECURITY_AUDIT_REPORT.md"
echo ""
echo "==================================================================="
echo ""
echo -e "${GREEN}Backup location: $BACKUP_DIR${NC}"
echo -e "${YELLOW}Keep this backup until you verify everything works!${NC}"
echo ""
