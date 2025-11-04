#!/bin/bash
# Helper script to get Telegram Chat ID

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   📱 Telegram Chat ID Finder                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""

# Ask for bot token
echo -e "${YELLOW}Enter your Telegram Bot Token:${NC}"
echo "(Looks like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)"
read -r BOT_TOKEN

echo ""
echo -e "${YELLOW}Step 1: Send a message to your bot${NC}"
echo "  1. Open Telegram"
echo "  2. Search for your bot"
echo "  3. Click START or send any message"
echo ""
read -p "Press Enter after you've sent a message to your bot..."

echo ""
echo -e "${BLUE}Fetching chat ID...${NC}"
echo ""

# Fetch updates
RESPONSE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates")

# Check if response contains chat ID
if echo "$RESPONSE" | grep -q '"chat"'; then
    echo -e "${GREEN}✅ Success! Found your chat information:${NC}"
    echo ""
    echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data['ok'] and len(data['result']) > 0:
        chat = data['result'][-1]['message']['chat']
        chat_id = chat['id']
        first_name = chat.get('first_name', 'Unknown')
        username = chat.get('username', 'No username')

        print('Chat Details:')
        print(f'  • Chat ID: {chat_id}')
        print(f'  • First Name: {first_name}')
        print(f'  • Username: @{username}' if username != 'No username' else f'  • Username: {username}')
        print('')
        print('─' * 50)
        print('')
        print('✨ Your Chat ID is: \033[1;32m' + str(chat_id) + '\033[0m')
        print('')
        print('Copy this number and use it in your .env file:')
        print(f'TELEGRAM_CHAT_ID={chat_id}')
    else:
        print('No messages found. Please send a message to your bot first.')
except Exception as e:
    print(f'Error parsing response: {e}')
" 2>/dev/null || echo "$RESPONSE"

    echo ""
    echo -e "${BLUE}────────────────────────────────────────────────${NC}"
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "1. Copy your Chat ID (the number above)"
    echo "2. Edit your .env file:"
    echo "   nano services/notification-service/.env"
    echo "3. Set:"
    echo "   TELEGRAM_ENABLED=true"
    echo "   TELEGRAM_BOT_TOKEN=${BOT_TOKEN}"
    echo "   TELEGRAM_CHAT_ID=<YOUR_CHAT_ID>"
    echo "4. Restart notification service"
    echo "5. Test: curl -X POST http://localhost:8007/api/v1/test"
else
    echo -e "${RED}❌ No messages found${NC}"
    echo ""
    echo "Possible issues:"
    echo "  1. You haven't sent a message to your bot yet"
    echo "  2. Bot token is incorrect"
    echo "  3. Network connection issue"
    echo ""
    echo "Please:"
    echo "  • Make sure you sent a message to your bot"
    echo "  • Double-check your bot token"
    echo "  • Try again"
    echo ""
    echo -e "${YELLOW}Raw response:${NC}"
    echo "$RESPONSE"
fi

echo ""
