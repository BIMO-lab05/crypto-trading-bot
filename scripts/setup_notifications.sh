#!/bin/bash
# Quick setup script for notification service

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

clear

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     📧 Notification Service Setup Wizard              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Navigate to notification service directory
cd /mnt/d/Bimo_max/crypto-trading-bot/services/notification-service

# Step 1: Check if .env exists
if [ -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file already exists${NC}"
    echo ""
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}Keeping existing .env file${NC}"
        echo "You can edit it manually at: services/notification-service/.env"
        exit 0
    fi
fi

# Step 2: Copy .env.example
echo -e "${BLUE}Creating .env file...${NC}"
cp .env.example .env
echo -e "${GREEN}✓ .env file created${NC}"
echo ""

# Step 3: Ask about notification methods
echo -e "${YELLOW}Which notification method do you want to use?${NC}"
echo "1) Telegram (Recommended - Easy & Free)"
echo "2) Email (Gmail)"
echo "3) Both"
echo "4) Skip for now"
echo ""
read -p "Enter choice (1-4): " -n 1 -r
echo ""

CHOICE=$REPLY

# Step 4: Configure based on choice
case $CHOICE in
    1|3)
        # Telegram setup
        echo ""
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${YELLOW}📱 Telegram Setup${NC}"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo "To get your Telegram Bot Token:"
        echo "1. Open Telegram and search for @BotFather"
        echo "2. Send /newbot and follow instructions"
        echo "3. Copy the token (looks like: 123456789:ABCdef...)"
        echo ""
        read -p "Enter your Telegram Bot Token: " BOT_TOKEN
        echo ""
        echo "To get your Chat ID:"
        echo "1. Send a message to your bot"
        echo "2. Visit: https://api.telegram.org/bot${BOT_TOKEN}/getUpdates"
        echo "3. Find 'chat':{'id':123456789} in the response"
        echo ""
        read -p "Enter your Telegram Chat ID: " CHAT_ID

        # Update .env file
        sed -i "s/TELEGRAM_ENABLED=false/TELEGRAM_ENABLED=true/" .env
        sed -i "s|TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${BOT_TOKEN}|" .env
        sed -i "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=${CHAT_ID}/" .env

        echo -e "${GREEN}✓ Telegram configured${NC}"
        ;;
esac

case $CHOICE in
    2|3)
        # Email setup
        echo ""
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${YELLOW}📧 Email Setup${NC}"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo "For Gmail, you need an App Password:"
        echo "1. Go to: https://myaccount.google.com/apppasswords"
        echo "2. Create new app password for 'Trading Bot'"
        echo "3. Copy the 16-character password"
        echo ""
        read -p "Enter your Gmail address: " EMAIL
        echo ""
        read -p "Enter your Gmail App Password: " APP_PASSWORD

        # Update .env file
        sed -i "s/EMAIL_ENABLED=false/EMAIL_ENABLED=true/" .env
        sed -i "s/SMTP_USERNAME=.*/SMTP_USERNAME=${EMAIL}/" .env
        sed -i "s/SMTP_PASSWORD=.*/SMTP_PASSWORD=${APP_PASSWORD}/" .env
        sed -i "s/EMAIL_FROM=.*/EMAIL_FROM=${EMAIL}/" .env
        sed -i "s/EMAIL_TO=.*/EMAIL_TO=${EMAIL}/" .env

        echo -e "${GREEN}✓ Email configured${NC}"
        ;;
esac

# Step 5: Install requirements
echo ""
echo -e "${BLUE}Installing requirements...${NC}"
pip3 install -r requirements.txt > /dev/null 2>&1
echo -e "${GREEN}✓ Requirements installed${NC}"

# Step 6: Start service
echo ""
echo -e "${BLUE}Starting notification service...${NC}"

# Kill any existing instance
lsof -ti:8007 | xargs kill -9 2>/dev/null || true

# Start in background
nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8007 > /tmp/notification-service.log 2>&1 &
sleep 2

# Check if started
if curl -s -f "http://localhost:8007/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Notification service started${NC}"
else
    echo -e "${RED}✗ Failed to start notification service${NC}"
    echo "Check logs: /tmp/notification-service.log"
    exit 1
fi

# Step 7: Test
if [ "$CHOICE" != "4" ]; then
    echo ""
    echo -e "${YELLOW}Testing notifications...${NC}"
    sleep 1

    RESULT=$(curl -s -X POST "http://localhost:8007/api/v1/test")

    if echo "$RESULT" | grep -q "success.*true"; then
        echo -e "${GREEN}✓ Test notification sent!${NC}"
        echo ""
        echo "Check your:"
        case $CHOICE in
            1) echo "  • Telegram bot chat" ;;
            2) echo "  • Email inbox (and spam folder)" ;;
            3) echo "  • Telegram bot chat"
               echo "  • Email inbox (and spam folder)" ;;
        esac
    else
        echo -e "${YELLOW}⚠️  Test may have failed - check service logs${NC}"
    fi
fi

# Step 8: Summary
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Service Status:"
echo "  • API Endpoint: http://localhost:8007"
echo "  • Documentation: http://localhost:8007/docs"
echo "  • Health Check: http://localhost:8007/health"
echo ""
echo "Configuration:"
echo "  • Config File: services/notification-service/.env"
echo "  • Log File: /tmp/notification-service.log"
echo ""
echo "Next Steps:"
echo "  1. Verify you received test notifications"
echo "  2. Customize alert settings in .env if needed"
echo "  3. Restart service after config changes:"
echo "     pkill -f 'port 8007' && python3 -m uvicorn app.main:app --port 8007"
echo ""
echo "For detailed setup instructions, see:"
echo "  NOTIFICATION_SETUP_GUIDE.md"
echo ""
echo -e "${GREEN}Happy Trading! 🚀${NC}"
