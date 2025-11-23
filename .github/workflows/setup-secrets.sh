#!/bin/bash
# Setup script for GitHub Actions secrets
# Run this script to configure all required secrets for CI/CD pipelines

set -e

echo "==============================================="
echo "GitHub Actions CI/CD Secrets Setup"
echo "Crypto Trading Bot Microservices"
echo "==============================================="
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed"
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Check if logged in
if ! gh auth status &> /dev/null; then
    echo "Error: Not logged in to GitHub"
    echo "Run: gh auth login"
    exit 1
fi

# Get repository information
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "Repository: $REPO"
echo ""

# Function to set secret
set_secret() {
    local name=$1
    local description=$2
    local default=$3

    echo "Setting: $name"
    echo "Description: $description"

    if [ -n "$default" ]; then
        echo "Default/Example: $default"
    fi

    read -p "Enter value (or press Enter to skip): " -s value
    echo ""

    if [ -n "$value" ]; then
        gh secret set "$name" --body "$value"
        echo "✓ Secret '$name' set successfully"
    else
        echo "⊘ Skipped '$name'"
    fi
    echo ""
}

# Function to set secret from file
set_secret_from_file() {
    local name=$1
    local description=$2
    local file_path=$3

    echo "Setting: $name"
    echo "Description: $description"
    echo "File path: $file_path"

    if [ -f "$file_path" ]; then
        read -p "Use file '$file_path'? (y/n): " use_file
        if [ "$use_file" == "y" ]; then
            gh secret set "$name" < "$file_path"
            echo "✓ Secret '$name' set from file"
        else
            echo "⊘ Skipped '$name'"
        fi
    else
        echo "File not found: $file_path"
        read -p "Enter value manually (or press Enter to skip): " -s value
        echo ""
        if [ -n "$value" ]; then
            gh secret set "$name" --body "$value"
            echo "✓ Secret '$name' set successfully"
        else
            echo "⊘ Skipped '$name'"
        fi
    fi
    echo ""
}

echo "=== Container Registry Secrets ==="
echo ""

set_secret "DOCKER_REGISTRY_URL" \
    "Container registry URL (e.g., ghcr.io)" \
    "ghcr.io"

set_secret "DOCKER_REGISTRY_USERNAME" \
    "Registry username" \
    "$USER"

set_secret "DOCKER_REGISTRY_PASSWORD" \
    "Registry password or token" \
    ""

echo ""
echo "=== Kubernetes Cluster Configurations ==="
echo ""

echo "Dev Cluster"
if [ -f "$HOME/.kube/config-dev" ]; then
    KUBE_CONFIG_DEV=$(cat "$HOME/.kube/config-dev" | base64 -w 0)
    gh secret set "KUBE_CONFIG_DEV" --body "$KUBE_CONFIG_DEV"
    echo "✓ KUBE_CONFIG_DEV set from ~/.kube/config-dev"
else
    set_secret_from_file "KUBE_CONFIG_DEV" \
        "Base64 encoded kubeconfig for dev cluster" \
        "$HOME/.kube/config"
fi
echo ""

echo "Staging Cluster"
if [ -f "$HOME/.kube/config-staging" ]; then
    KUBE_CONFIG_STAGING=$(cat "$HOME/.kube/config-staging" | base64 -w 0)
    gh secret set "KUBE_CONFIG_STAGING" --body "$KUBE_CONFIG_STAGING"
    echo "✓ KUBE_CONFIG_STAGING set from ~/.kube/config-staging"
else
    echo "⊘ Skipped KUBE_CONFIG_STAGING (file not found)"
fi
echo ""

echo "Production Cluster"
if [ -f "$HOME/.kube/config-prod" ]; then
    KUBE_CONFIG_PROD=$(cat "$HOME/.kube/config-prod" | base64 -w 0)
    gh secret set "KUBE_CONFIG_PROD" --body "$KUBE_CONFIG_PROD"
    echo "✓ KUBE_CONFIG_PROD set from ~/.kube/config-prod"
else
    echo "⊘ Skipped KUBE_CONFIG_PROD (file not found)"
fi
echo ""

echo "=== API Credentials ==="
echo ""

set_secret "BYBIT_API_KEY_DEV" \
    "Bybit testnet API key" \
    ""

set_secret "BYBIT_API_SECRET_DEV" \
    "Bybit testnet API secret" \
    ""

set_secret "BYBIT_API_KEY_PROD" \
    "Bybit production API key" \
    ""

set_secret "BYBIT_API_SECRET_PROD" \
    "Bybit production API secret" \
    ""

echo ""
echo "=== Database Passwords ==="
echo ""

set_secret "DATABASE_PASSWORD_DEV" \
    "PostgreSQL password for dev environment" \
    ""

set_secret "DATABASE_PASSWORD_STAGING" \
    "PostgreSQL password for staging environment" \
    ""

set_secret "DATABASE_PASSWORD_PROD" \
    "PostgreSQL password for production environment" \
    ""

set_secret "REDIS_PASSWORD_PROD" \
    "Redis password for production" \
    ""

set_secret "RABBITMQ_PASSWORD_PROD" \
    "RabbitMQ password for production" \
    ""

echo ""
echo "=== External Services ==="
echo ""

set_secret "CODECOV_TOKEN" \
    "Codecov.io token for coverage reporting" \
    ""

set_secret "SLACK_WEBHOOK_URL" \
    "Slack webhook URL for notifications" \
    "https://hooks.slack.com/services/..."

set_secret "GITLEAKS_LICENSE" \
    "Gitleaks license key (optional)" \
    ""

echo ""
echo "=== Production API Secrets (JSON) ==="
echo ""

echo "Creating JSON object for PROD_API_SECRETS"
echo "This should contain all production secrets in JSON format"
echo ""

read -p "Do you want to create PROD_API_SECRETS from previous values? (y/n): " create_json

if [ "$create_json" == "y" ]; then
    # This would typically be done programmatically
    echo "Please create a JSON file with the following structure:"
    echo '{'
    echo '  "bybit-api-key": "your-key",'
    echo '  "bybit-api-secret": "your-secret",'
    echo '  "database-password": "your-password",'
    echo '  "redis-password": "your-password",'
    echo '  "rabbitmq-password": "your-password"'
    echo '}'
    echo ""
    read -p "Enter path to JSON file: " json_file

    if [ -f "$json_file" ]; then
        gh secret set "PROD_API_SECRETS" < "$json_file"
        echo "✓ PROD_API_SECRETS set from file"
    else
        echo "⊘ File not found, skipping PROD_API_SECRETS"
    fi
else
    echo "⊘ Skipped PROD_API_SECRETS"
fi

echo ""
echo "==============================================="
echo "Secret Setup Complete!"
echo "==============================================="
echo ""

# List all secrets
echo "Current secrets in repository:"
gh secret list

echo ""
echo "Next steps:"
echo "1. Verify all secrets are set correctly"
echo "2. Enable GitHub Actions in repository settings"
echo "3. Configure branch protection rules"
echo "4. Create environments (development, staging, production)"
echo "5. Push code to trigger first workflow run"
echo ""
echo "Documentation: .github/workflows/README.md"
echo "Summary: .github/workflows/CICD_SUMMARY.md"
echo ""
