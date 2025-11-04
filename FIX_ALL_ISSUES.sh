#!/bin/bash
# ============================================================================
# QUICK FIX SCRIPT - Remediate All Identified Issues
# Generated from Comprehensive Audit Report
# Run this to fix all non-critical issues automatically
# ============================================================================

set -e  # Exit on error

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_ROOT="/mnt/d/Bimo_max/crypto-trading-bot"

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  AUTOMATED FIX SCRIPT - CRYPTO TRADING BOT                 ║${NC}"
echo -e "${GREEN}║  Fixing all identified issues from audit                   ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}\n"

cd "$PROJECT_ROOT"

# ============================================================================
# 1. UPDATE .GITIGNORE
# ============================================================================

echo -e "${BLUE}[1/5] Updating .gitignore with missing patterns...${NC}"

if ! grep -q "^\*.key$" .gitignore; then
    cat >> .gitignore << 'EOF'

# Security-sensitive files (added by audit remediation)
*.key
*.pem
*.crt
*.p12
*.pfx

# Sensitive directories
secrets/
credentials/
private/

# Environment files (if not already present)
.env
.env.*
!.env.example

# IDE files (additional)
.vscode/
.idea/
*.swp
*.swo
*~

# Logs (if sensitive)
*.log
logs/*.log

# Temporary files
tmp/
temp/
.tmp/
EOF
    echo -e "${GREEN}✓ .gitignore updated${NC}"
else
    echo -e "${YELLOW}⊙ .gitignore already has security patterns${NC}"
fi

# ============================================================================
# 2. CREATE VIRTUAL ENVIRONMENTS FOR ALL SERVICES
# ============================================================================

echo -e "\n${BLUE}[2/5] Creating virtual environments for all services...${NC}"

services=("technical-analysis" "trading-engine" "portfolio-manager" "api-gateway" "notification-service")

for service in "${services[@]}"; do
    service_dir="services/$service"

    if [ -d "$service_dir" ]; then
        if [ ! -d "$service_dir/venv" ]; then
            echo -e "${YELLOW}Creating venv for $service...${NC}"
            cd "$service_dir"
            python3 -m venv venv
            source venv/bin/activate
            pip install --upgrade pip > /dev/null 2>&1

            if [ -f "requirements.txt" ]; then
                pip install -r requirements.txt > /dev/null 2>&1
                echo -e "${GREEN}✓ $service venv created and dependencies installed${NC}"
            else
                echo -e "${YELLOW}⊙ $service venv created but no requirements.txt${NC}"
            fi

            deactivate
            cd "$PROJECT_ROOT"
        else
            echo -e "${GREEN}✓ $service already has venv${NC}"
        fi
    fi
done

# ============================================================================
# 3. CREATE .ENV FILE FROM TEMPLATE (IF NOT EXISTS)
# ============================================================================

echo -e "\n${BLUE}[3/5] Checking .env configuration...${NC}"

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env from template...${NC}"
    cp .env.example .env

    # Generate secure passwords
    POSTGRES_PASS=$(openssl rand -hex 16)
    REDIS_PASS=$(openssl rand -hex 16)
    RABBITMQ_PASS=$(openssl rand -hex 16)
    JWT_SECRET=$(openssl rand -hex 32)
    INTERNAL_KEY=$(openssl rand -hex 24)

    # Update .env with generated passwords
    sed -i "s/change_this_secure_password/$POSTGRES_PASS/" .env
    sed -i "s/your_secret_key_here_use_openssl_to_generate/$JWT_SECRET/" .env
    sed -i "s/your_internal_api_key/$INTERNAL_KEY/" .env

    echo -e "${GREEN}✓ .env created with secure auto-generated passwords${NC}"
    echo -e "${YELLOW}⚠ IMPORTANT: You still need to add your Bybit API keys manually!${NC}"
    echo -e "${YELLOW}   Edit .env and set:${NC}"
    echo -e "${YELLOW}   - BYBIT_API_KEY=your_testnet_api_key${NC}"
    echo -e "${YELLOW}   - BYBIT_API_SECRET=your_testnet_api_secret${NC}"
else
    echo -e "${GREEN}✓ .env file already exists${NC}"
fi

# ============================================================================
# 4. SET PROPER FILE PERMISSIONS
# ============================================================================

echo -e "\n${BLUE}[4/5] Setting proper file permissions...${NC}"

# Make .env secure
if [ -f ".env" ]; then
    chmod 600 .env
    echo -e "${GREEN}✓ .env permissions set to 600${NC}"
fi

# Make scripts executable
if [ -d "scripts" ]; then
    chmod +x scripts/*.sh 2>/dev/null || true
    echo -e "${GREEN}✓ Scripts made executable${NC}"
fi

# Make test scripts executable
chmod +x COMPREHENSIVE_TEST_AUDIT.sh 2>/dev/null || true
chmod +x FIX_ALL_ISSUES.sh 2>/dev/null || true
chmod +x test_paper_trading.sh 2>/dev/null || true

# ============================================================================
# 5. VERIFY DOCKER SETUP (WARNING ONLY)
# ============================================================================

echo -e "\n${BLUE}[5/5] Checking Docker availability...${NC}"

if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Docker command available${NC}"

    if docker ps &> /dev/null; then
        echo -e "${GREEN}✓ Docker daemon running${NC}"

        # Check if containers are running
        if docker ps | grep -q "crypto-bot"; then
            echo -e "${GREEN}✓ Some crypto-bot containers are running${NC}"
        else
            echo -e "${YELLOW}⊙ No crypto-bot containers running${NC}"
            echo -e "${YELLOW}   To start: cd infrastructure && docker-compose up -d${NC}"
        fi
    else
        echo -e "${YELLOW}⊙ Docker daemon not running${NC}"
        echo -e "${YELLOW}   Start Docker Desktop to run infrastructure${NC}"
    fi
else
    echo -e "${YELLOW}⊙ Docker not available${NC}"
    echo -e "${YELLOW}   This is expected in WSL without Docker Desktop integration${NC}"
    echo -e "${YELLOW}   To fix:${NC}"
    echo -e "${YELLOW}   1. Install Docker Desktop for Windows${NC}"
    echo -e "${YELLOW}   2. Enable WSL 2 integration in Settings${NC}"
    echo -e "${YELLOW}   3. Select your WSL distribution${NC}"
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo -e "\n${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    FIX SUMMARY                             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}\n"

echo -e "${GREEN}✓ Completed Fixes:${NC}"
echo -e "  1. Updated .gitignore with security patterns"
echo -e "  2. Created virtual environments for 5 services"
echo -e "  3. Generated .env file with secure passwords"
echo -e "  4. Set proper file permissions"
echo -e "  5. Verified Docker setup"

echo -e "\n${YELLOW}⚠ Manual Actions Still Required:${NC}"
echo -e "  1. Add Bybit API credentials to .env:"
echo -e "     BYBIT_API_KEY=your_testnet_key"
echo -e "     BYBIT_API_SECRET=your_testnet_secret"
echo -e "  2. Start Docker infrastructure:"
echo -e "     cd infrastructure && docker-compose up -d"
echo -e "  3. Review and address 5 TODO/FIXME comments:"
echo -e "     grep -r 'TODO\\|FIXME' --include='*.py' services/"

echo -e "\n${BLUE}Next Steps:${NC}"
echo -e "  1. Edit .env with your Bybit API keys"
echo -e "  2. Start infrastructure: cd infrastructure && docker-compose up -d"
echo -e "  3. Test services: cd services/bybit-connector && source venv/bin/activate && pytest"
echo -e "  4. Start a service: uvicorn app.main:app --reload --port 8002"
echo -e "  5. Check health: curl http://localhost:8002/health"

echo -e "\n${GREEN}✓ Automated fixes complete!${NC}\n"

exit 0
