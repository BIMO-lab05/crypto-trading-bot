#!/bin/bash
# Setup Alerting System for Crypto Trading Bot
# This script helps configure email and Telegram notifications

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_section() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

echo ""
echo "=========================================="
echo "  Crypto Trading Bot Alerting Setup      "
echo "=========================================="
echo ""

# Check if running from correct directory
if [ ! -f "docker-compose.monitoring.yml" ]; then
    log_error "Please run this script from infrastructure/monitoring/ directory"
    exit 1
fi

log_section "Step 1: Telegram Bot Setup"
echo ""
echo "To receive Telegram notifications, you need to create a Telegram bot:"
echo ""
echo "1. Open Telegram and search for @BotFather"
echo "2. Send command: /newbot"
echo "3. Follow prompts to create your bot"
echo "4. Copy the bot token (looks like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)"
echo ""
read -p "Do you have a Telegram bot token? (y/n): " has_telegram

if [ "$has_telegram" = "y" ]; then
    read -p "Enter your Telegram bot token: " telegram_token
    TELEGRAM_BOT_TOKEN="$telegram_token"
    log_info "Telegram bot token saved"
else
    log_warn "Skipping Telegram setup. You can configure it later in telegram-bot/.env"
    TELEGRAM_BOT_TOKEN=""
fi

echo ""
log_section "Step 2: Email Configuration"
echo ""
echo "Configure email notifications (using Gmail SMTP):"
echo ""
echo "Note: For Gmail, you need an App-Specific Password:"
echo "1. Enable 2-factor authentication in your Google Account"
echo "2. Go to: https://myaccount.google.com/apppasswords"
echo "3. Create an App-Specific Password for 'Mail'"
echo ""
read -p "Enter your Gmail address: " smtp_username
read -sp "Enter your App-Specific Password: " smtp_password
echo ""
read -p "Enter alert recipient email: " alert_email

echo ""
log_section "Step 3: Webhook Security"
echo ""
log_info "Generating secure webhook token..."
WEBHOOK_TOKEN=$(openssl rand -hex 32)
log_info "Webhook token generated"

echo ""
log_section "Step 4: Creating Configuration Files"
echo ""

# Create .env file for Telegram bot
ENV_FILE="telegram-bot/.env"
log_info "Creating $ENV_FILE..."

cat > "$ENV_FILE" <<EOF
# Telegram Bot Configuration
# Generated: $(date)

# Telegram bot token from @BotFather
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}

# Your Telegram chat ID (will be filled after first message to bot)
TELEGRAM_CHAT_ID=

# Webhook configuration
TELEGRAM_WEBHOOK_PORT=8007
WEBHOOK_TOKEN=${WEBHOOK_TOKEN}

# Email configuration
SMTP_USERNAME=${smtp_username}
SMTP_PASSWORD=${smtp_password}
ALERT_EMAIL=${alert_email}

# Optional: Slack webhooks (uncomment and configure if using Slack)
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
# SLACK_WEBHOOK_URL_CRITICAL=https://hooks.slack.com/services/YOUR/CRITICAL/URL
# SLACK_WEBHOOK_URL_DATABASE=https://hooks.slack.com/services/YOUR/DATABASE/URL

# Optional: PagerDuty (uncomment and configure if using PagerDuty)
# PAGERDUTY_SERVICE_KEY=your-pagerduty-service-key
EOF

log_info "Configuration file created: $ENV_FILE"

# Create AlertManager env file
ALERTMANAGER_ENV="alertmanager/.env"
log_info "Creating $ALERTMANAGER_ENV..."

cat > "$ALERTMANAGER_ENV" <<EOF
# AlertManager Configuration
# Generated: $(date)

SMTP_USERNAME=${smtp_username}
SMTP_PASSWORD=${smtp_password}
ALERT_EMAIL=${alert_email}
WEBHOOK_TOKEN=${WEBHOOK_TOKEN}
EOF

log_info "Configuration file created: $ALERTMANAGER_ENV"

echo ""
log_section "Step 5: Update Docker Compose"
echo ""

# Check if telegram-bot is in docker-compose
if grep -q "telegram-bot:" docker-compose.monitoring.yml; then
    log_info "Telegram bot already configured in docker-compose.monitoring.yml"
else
    log_warn "Adding Telegram bot service to docker-compose.monitoring.yml"

    cat >> docker-compose.monitoring.yml <<EOF

  # Telegram Alert Bot
  telegram-bot:
    build: ./telegram-bot
    container_name: crypto-bot-telegram-alerts
    ports:
      - "8007:8007"
    env_file:
      - ./telegram-bot/.env
    networks:
      - crypto-bot-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8007/health"]
      interval: 30s
      timeout: 10s
      retries: 3
EOF

    log_info "Telegram bot service added to docker-compose"
fi

echo ""
log_section "Step 6: Starting Services"
echo ""

log_info "Building Telegram bot..."
docker-compose -f docker-compose.monitoring.yml build telegram-bot

log_info "Starting monitoring stack..."
docker-compose -f docker-compose.monitoring.yml up -d

# Wait for services to be ready
log_info "Waiting for services to start..."
sleep 10

echo ""
log_section "Step 7: Get Telegram Chat ID"
echo ""

if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "To get your Telegram chat ID:"
    echo "1. Open Telegram and find your bot"
    echo "2. Send any message to your bot (e.g., 'Hello')"
    echo "3. Wait 5 seconds, then press Enter to retrieve your chat ID"
    echo ""
    read -p "Press Enter after sending a message to your bot..."

    log_info "Retrieving chat ID..."
    sleep 2

    CHAT_ID=$(curl -s http://localhost:8007/get-chat-id | jq -r '.chat_id // empty')

    if [ -n "$CHAT_ID" ] && [ "$CHAT_ID" != "null" ]; then
        log_info "Chat ID retrieved: $CHAT_ID"

        # Update .env file
        sed -i "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=${CHAT_ID}/" "$ENV_FILE"

        log_info "Chat ID saved to $ENV_FILE"

        # Restart Telegram bot
        log_info "Restarting Telegram bot..."
        docker-compose -f docker-compose.monitoring.yml restart telegram-bot
        sleep 5
    else
        log_warn "Could not retrieve chat ID automatically"
        echo ""
        echo "Manual steps:"
        echo "1. Send a message to your bot in Telegram"
        echo "2. Run: curl http://localhost:8007/get-chat-id"
        echo "3. Copy the chat_id value"
        echo "4. Edit $ENV_FILE and set TELEGRAM_CHAT_ID"
        echo "5. Restart: docker-compose -f docker-compose.monitoring.yml restart telegram-bot"
    fi
else
    log_warn "Telegram not configured. Skipping chat ID retrieval."
fi

echo ""
log_section "Step 8: Testing Alerts"
echo ""

log_info "Running alert tests..."
cd scripts

if [ -f "test_alerts.sh" ]; then
    chmod +x test_alerts.sh

    echo ""
    echo "Would you like to run test alerts now? (y/n)"
    read -p "> " run_tests

    if [ "$run_tests" = "y" ]; then
        ./test_alerts.sh telegram
        echo ""
        log_info "Check your Telegram and email for test notifications"
    else
        log_info "You can run tests later with: ./scripts/test_alerts.sh all"
    fi
else
    log_warn "Test script not found at scripts/test_alerts.sh"
fi

cd ..

echo ""
log_section "Setup Complete!"
echo ""

log_info "Configuration Summary:"
echo ""
echo "  Telegram Bot Token: ${TELEGRAM_BOT_TOKEN:0:20}..."
echo "  Telegram Chat ID: ${CHAT_ID:-'(not set)'}"
echo "  SMTP Username: ${smtp_username}"
echo "  Alert Email: ${alert_email}"
echo "  Webhook Token: ${WEBHOOK_TOKEN:0:16}..."
echo ""

log_info "Services Running:"
echo ""
docker-compose -f docker-compose.monitoring.yml ps
echo ""

log_info "Next Steps:"
echo ""
echo "1. Verify services are healthy:"
echo "   docker-compose -f docker-compose.monitoring.yml ps"
echo ""
echo "2. Check AlertManager:"
echo "   http://localhost:9093"
echo ""
echo "3. Check Prometheus alerts:"
echo "   http://localhost:9090/alerts"
echo ""
echo "4. Test notifications:"
echo "   cd scripts && ./test_alerts.sh all"
echo ""
echo "5. Review configuration:"
echo "   - Email templates: alertmanager/templates/email.tmpl"
echo "   - Alert rules: rules/trading-alerts.yml"
echo "   - AlertManager config: alertmanager/alertmanager.yml"
echo ""

log_info "Documentation:"
echo ""
echo "  - ALERTING_GUIDE.md: ../../docs/operations/ALERTING_GUIDE.md"
echo "  - ALERT_RUNBOOKS.md: ../../docs/operations/ALERT_RUNBOOKS.md"
echo "  - MONITORING_GUIDE.md: ../../docs/MONITORING_GUIDE.md"
echo ""

log_info "Setup complete! Happy monitoring!"
echo ""
