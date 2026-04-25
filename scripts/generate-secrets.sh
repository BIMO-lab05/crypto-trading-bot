#!/bin/bash
# ============================================================================
# Secure Secrets Generator for Crypto Trading Bot
# ============================================================================
# This script generates cryptographically secure secrets for deployment
#
# Usage:
#   ./scripts/generate-secrets.sh [environment]
#
# Environment:
#   development (default) - Generates secrets for local development
#   staging              - Generates secrets for staging environment
#   production           - Generates secrets for production environment
#
# Output:
#   - Prints secrets to stdout (save securely!)
#   - Optionally creates .env file for development
#   - Optionally creates secrets.yaml for Kubernetes
#
# Requirements:
#   - openssl (for cryptographic random generation)
#   - base64 (for Kubernetes secret encoding)
#
# SECURITY NOTICE:
#   - Store generated secrets in a secure password manager
#   - Never commit generated secrets to version control
#   - Rotate secrets regularly (recommended: every 90 days)
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Environment (default: development)
ENVIRONMENT="${1:-development}"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(development|staging|production)$ ]]; then
    echo -e "${RED}Error: Invalid environment '$ENVIRONMENT'${NC}"
    echo "Valid options: development, staging, production"
    exit 1
fi

echo -e "${BLUE}============================================================================${NC}"
echo -e "${BLUE}Secure Secrets Generator - Environment: ${GREEN}$ENVIRONMENT${NC}"
echo -e "${BLUE}============================================================================${NC}"
echo ""

# Check for openssl
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}Error: openssl is required but not installed${NC}"
    exit 1
fi

# Function to generate random password
generate_password() {
    local length="${1:-32}"
    openssl rand -base64 "$length" | tr -d '\n'
}

# Function to generate hex secret
generate_hex_secret() {
    local length="${1:-32}"
    openssl rand -hex "$length" | tr -d '\n'
}

# Function to base64 encode
base64_encode() {
    echo -n "$1" | base64 | tr -d '\n'
}

echo -e "${YELLOW}Generating secure credentials...${NC}"
echo ""

# Generate all secrets
JWT_SECRET_KEY=$(generate_hex_secret 64)
INTERNAL_API_KEY=$(generate_hex_secret 32)
POSTGRES_PASSWORD=$(generate_password 32)
TIMESCALE_PASSWORD=$(generate_password 32)
REDIS_PASSWORD=$(generate_password 32)
RABBITMQ_PASSWORD=$(generate_password 32)
ENCRYPTION_KEY=$(generate_password 32)
SIGNING_KEY=$(generate_password 32)
GRAFANA_PASSWORD=$(generate_password 24)
PGADMIN_PASSWORD=$(generate_password 24)

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}GENERATED SECRETS - SAVE THESE SECURELY!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""

echo -e "${BLUE}# JWT Authentication${NC}"
echo "JWT_SECRET_KEY=$JWT_SECRET_KEY"
echo ""

echo -e "${BLUE}# Internal API Authentication${NC}"
echo "INTERNAL_API_KEY=$INTERNAL_API_KEY"
echo ""

echo -e "${BLUE}# PostgreSQL${NC}"
echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
echo ""

echo -e "${BLUE}# TimescaleDB${NC}"
echo "TIMESCALE_PASSWORD=$TIMESCALE_PASSWORD"
echo ""

echo -e "${BLUE}# Redis${NC}"
echo "REDIS_PASSWORD=$REDIS_PASSWORD"
echo ""

echo -e "${BLUE}# RabbitMQ${NC}"
echo "RABBITMQ_PASSWORD=$RABBITMQ_PASSWORD"
echo ""

echo -e "${BLUE}# Trading Engine${NC}"
echo "ENCRYPTION_KEY=$ENCRYPTION_KEY"
echo "SIGNING_KEY=$SIGNING_KEY"
echo ""

echo -e "${BLUE}# Monitoring${NC}"
echo "GRAFANA_PASSWORD=$GRAFANA_PASSWORD"
echo ""

echo -e "${BLUE}# Development Tools${NC}"
echo "PGADMIN_PASSWORD=$PGADMIN_PASSWORD"
echo ""

# Generate Kubernetes-ready secrets (base64 encoded)
if [[ "$ENVIRONMENT" != "development" ]]; then
    echo -e "${GREEN}============================================================================${NC}"
    echo -e "${GREEN}KUBERNETES SECRETS (Base64 Encoded)${NC}"
    echo -e "${GREEN}============================================================================${NC}"
    echo ""

    echo -e "${BLUE}# For secrets.yaml - db-secrets${NC}"
    echo "POSTGRES_PASSWORD: $(base64_encode "$POSTGRES_PASSWORD")"
    echo "TIMESCALE_PASSWORD: $(base64_encode "$TIMESCALE_PASSWORD")"
    echo "REDIS_PASSWORD: $(base64_encode "$REDIS_PASSWORD")"
    echo "RABBITMQ_PASSWORD: $(base64_encode "$RABBITMQ_PASSWORD")"
    echo ""

    echo -e "${BLUE}# For secrets.yaml - api-secrets${NC}"
    echo "JWT_SECRET_KEY: $(base64_encode "$JWT_SECRET_KEY")"
    echo "INTERNAL_API_KEY: $(base64_encode "$INTERNAL_API_KEY")"
    echo ""

    echo -e "${BLUE}# For secrets.yaml - trading-engine-secrets${NC}"
    echo "ENCRYPTION_KEY: $(base64_encode "$ENCRYPTION_KEY")"
    echo "SIGNING_KEY: $(base64_encode "$SIGNING_KEY")"
    echo ""

    echo -e "${BLUE}# For secrets.yaml - prometheus-secrets${NC}"
    echo "GRAFANA_ADMIN_PASSWORD: $(base64_encode "$GRAFANA_PASSWORD")"
    echo ""
fi

# Offer to create .env file for development
if [[ "$ENVIRONMENT" == "development" ]]; then
    echo ""
    read -p "Create .env file with these secrets? (y/N): " create_env

    if [[ "$create_env" =~ ^[Yy]$ ]]; then
        ENV_FILE=".env"
        if [[ -f "$ENV_FILE" ]]; then
            read -p ".env already exists. Backup and overwrite? (y/N): " overwrite
            if [[ "$overwrite" =~ ^[Yy]$ ]]; then
                cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
                echo -e "${YELLOW}Backed up existing .env file${NC}"
            else
                echo -e "${YELLOW}Skipping .env creation${NC}"
                create_env="n"
            fi
        fi

        if [[ "$create_env" =~ ^[Yy]$ ]]; then
            # Copy from template and replace placeholders
            if [[ -f ".env.example" ]]; then
                cp .env.example "$ENV_FILE"

                # Replace placeholders with generated secrets
                sed -i "s|<generate_with_openssl_rand_hex_64>|$JWT_SECRET_KEY|g" "$ENV_FILE"
                sed -i "s|<generate_with_openssl_rand_hex_32>|$INTERNAL_API_KEY|g" "$ENV_FILE"
                sed -i "s|<generate_with_openssl_rand_base64_32>|$POSTGRES_PASSWORD|g" "$ENV_FILE"
                sed -i "s|<generate_secure_password>|$PGADMIN_PASSWORD|g" "$ENV_FILE"

                # Update passwords in .env
                sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|g" "$ENV_FILE"
                sed -i "s|TIMESCALE_PASSWORD=.*|TIMESCALE_PASSWORD=$TIMESCALE_PASSWORD|g" "$ENV_FILE"
                sed -i "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=$REDIS_PASSWORD|g" "$ENV_FILE"
                sed -i "s|RABBITMQ_PASSWORD=.*|RABBITMQ_PASSWORD=$RABBITMQ_PASSWORD|g" "$ENV_FILE"
                sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET_KEY|g" "$ENV_FILE"
                sed -i "s|INTERNAL_API_KEY=.*|INTERNAL_API_KEY=$INTERNAL_API_KEY|g" "$ENV_FILE"
                sed -i "s|PGADMIN_PASSWORD=.*|PGADMIN_PASSWORD=$PGADMIN_PASSWORD|g" "$ENV_FILE"

                echo -e "${GREEN}Created .env file with secure secrets${NC}"
            else
                echo -e "${RED}Error: .env.example not found${NC}"
            fi
        fi
    fi
fi

echo ""
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}SECURITY REMINDERS${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo -e "${YELLOW}1. Store these secrets in a secure password manager${NC}"
echo -e "${YELLOW}2. Never commit secrets to version control${NC}"
echo -e "${YELLOW}3. Use different secrets for each environment${NC}"
echo -e "${YELLOW}4. Rotate secrets every 90 days${NC}"
echo -e "${YELLOW}5. Enable audit logging for secret access${NC}"
echo ""

if [[ "$ENVIRONMENT" == "production" ]]; then
    echo -e "${RED}============================================================================${NC}"
    echo -e "${RED}PRODUCTION DEPLOYMENT CHECKLIST${NC}"
    echo -e "${RED}============================================================================${NC}"
    echo ""
    echo -e "${RED}[ ] Secrets stored in HashiCorp Vault or cloud secrets manager${NC}"
    echo -e "${RED}[ ] Network access restricted to secrets manager${NC}"
    echo -e "${RED}[ ] Secret rotation policy implemented${NC}"
    echo -e "${RED}[ ] Audit logging enabled${NC}"
    echo -e "${RED}[ ] Backup encryption keys stored separately${NC}"
    echo -e "${RED}[ ] Incident response plan documented${NC}"
    echo ""
fi

echo -e "${BLUE}Script completed at: $(date)${NC}"
