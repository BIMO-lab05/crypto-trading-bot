#!/usr/bin/env python3
"""
Telegram Alert Bot for Crypto Trading Bot
Receives webhook alerts from AlertManager and sends formatted messages to Telegram

Setup:
1. Create a bot via @BotFather on Telegram
2. Get bot token
3. Start a chat with your bot
4. Run this script to get your chat_id
5. Configure environment variables

Environment Variables:
- TELEGRAM_BOT_TOKEN: Bot token from @BotFather
- TELEGRAM_CHAT_ID: Your chat ID (can be user or group)
- TELEGRAM_WEBHOOK_PORT: Port to listen on (default: 8007)
- WEBHOOK_TOKEN: Authentication token for webhooks
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse
import httpx
import uvicorn
from pydantic import BaseModel


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Configuration from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
WEBHOOK_PORT = int(os.getenv('TELEGRAM_WEBHOOK_PORT', '8007'))
WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN', 'your-secure-token-here')


# Emoji mapping for alert severity
SEVERITY_EMOJI = {
    'critical': '🚨',
    'warning': '⚠️',
    'info': 'ℹ️',
}

# Component emoji mapping
COMPONENT_EMOJI = {
    'trading-engine': '💹',
    'database': '🗄️',
    'api': '🌐',
    'risk-management': '🛡️',
    'portfolio': '💰',
    'bybit-connector': '🔗',
    'system': '💻',
    'monitoring': '📊',
}


# Pydantic models for AlertManager webhook payload
class Alert(BaseModel):
    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    startsAt: str
    endsAt: str
    generatorURL: str
    fingerprint: str


class AlertManagerPayload(BaseModel):
    version: str
    groupKey: str
    status: str
    receiver: str
    groupLabels: Dict[str, str]
    commonLabels: Dict[str, str]
    commonAnnotations: Dict[str, str]
    externalURL: str
    alerts: List[Alert]


# FastAPI app
app = FastAPI(
    title="Telegram Alert Bot",
    description="Receives AlertManager webhooks and sends to Telegram",
    version="1.0.0"
)


class TelegramBot:
    """Telegram bot client for sending alert messages"""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}"

    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True
    ) -> bool:
        """Send a message to Telegram"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": disable_web_page_preview
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                logger.info(f"Message sent successfully to chat {self.chat_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def get_chat_id(self) -> Optional[str]:
        """Get chat ID from last message (for setup purposes)"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/getUpdates",
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                if data.get('result'):
                    return str(data['result'][-1]['message']['chat']['id'])
        except Exception as e:
            logger.error(f"Failed to get chat ID: {e}")
        return None


def format_telegram_message(payload: AlertManagerPayload) -> str:
    """
    Format AlertManager payload into a Telegram message

    Args:
        payload: AlertManager webhook payload

    Returns:
        Formatted Telegram message in HTML format
    """
    # Get severity and component
    severity = payload.commonLabels.get('severity', 'info')
    component = payload.commonLabels.get('component', 'system')

    # Get emoji
    severity_emoji = SEVERITY_EMOJI.get(severity, 'ℹ️')
    component_emoji = COMPONENT_EMOJI.get(component, '🔔')

    # Build message header
    if payload.status == "firing":
        status_text = "🔴 <b>ALERT FIRING</b>"
    else:
        status_text = "🟢 <b>ALERT RESOLVED</b>"

    # Count firing and resolved alerts
    firing_count = sum(1 for alert in payload.alerts if alert.status == "firing")
    resolved_count = sum(1 for alert in payload.alerts if alert.status == "resolved")

    # Start building message
    message_parts = [
        status_text,
        f"{severity_emoji} <b>{payload.groupLabels.get('alertname', 'Unknown Alert')}</b>",
        "",
        f"<b>Severity:</b> {severity.upper()}",
        f"<b>Component:</b> {component_emoji} {component}",
    ]

    if firing_count > 0:
        message_parts.append(f"<b>Firing:</b> {firing_count} alert(s)")
    if resolved_count > 0:
        message_parts.append(f"<b>Resolved:</b> {resolved_count} alert(s)")

    message_parts.append("")

    # Add firing alerts
    if firing_count > 0:
        message_parts.append("━━━━━━━━━━━━━━━━━━━━")
        message_parts.append("<b>FIRING ALERTS:</b>")
        message_parts.append("")

        for alert in payload.alerts:
            if alert.status == "firing":
                # Alert summary
                summary = alert.annotations.get('summary', 'No summary')
                description = alert.annotations.get('description', '')

                message_parts.append(f"<b>Summary:</b> {summary}")

                if description:
                    # Truncate long descriptions for Telegram
                    if len(description) > 200:
                        description = description[:197] + "..."
                    message_parts.append(f"<i>{description}</i>")

                # Service/instance info
                if 'service' in alert.labels:
                    message_parts.append(f"<b>Service:</b> {alert.labels['service']}")
                if 'instance' in alert.labels:
                    message_parts.append(f"<b>Instance:</b> {alert.labels['instance']}")

                # Timestamp
                try:
                    starts_at = datetime.fromisoformat(alert.startsAt.replace('Z', '+00:00'))
                    message_parts.append(f"<b>Started:</b> {starts_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                except:
                    pass

                # Actions (truncated)
                action = alert.annotations.get('action', '')
                if action:
                    # Take only first action
                    first_action = action.split('\n')[0]
                    if len(first_action) > 100:
                        first_action = first_action[:97] + "..."
                    message_parts.append(f"<b>Action:</b> {first_action}")

                message_parts.append("")

    # Add resolved alerts (brief)
    if resolved_count > 0:
        message_parts.append("━━━━━━━━━━━━━━━━━━━━")
        message_parts.append("<b>RESOLVED ALERTS:</b>")
        message_parts.append("")

        for alert in payload.alerts:
            if alert.status == "resolved":
                summary = alert.annotations.get('summary', 'No summary')
                message_parts.append(f"✅ {summary}")

                # Calculate duration
                try:
                    starts_at = datetime.fromisoformat(alert.startsAt.replace('Z', '+00:00'))
                    ends_at = datetime.fromisoformat(alert.endsAt.replace('Z', '+00:00'))
                    duration = ends_at - starts_at
                    message_parts.append(f"<i>Duration: {duration}</i>")
                except:
                    pass

                message_parts.append("")

    # Add footer with links
    message_parts.append("━━━━━━━━━━━━━━━━━━━━")
    message_parts.append("<b>Quick Links:</b>")
    message_parts.append("• <a href='http://localhost:3000'>Grafana Dashboard</a>")
    message_parts.append("• <a href='http://localhost:9093'>AlertManager</a>")

    # Join all parts
    message = "\n".join(message_parts)

    # Telegram message limit is 4096 characters
    if len(message) > 4096:
        message = message[:4090] + "\n..."

    return message


def format_simple_message(severity: str, title: str, description: str) -> str:
    """Format a simple alert message"""
    severity_emoji = SEVERITY_EMOJI.get(severity, 'ℹ️')

    return f"""
{severity_emoji} <b>{severity.upper()}: {title}</b>

{description}

━━━━━━━━━━━━━━━━━━━━
<i>Crypto Trading Bot Alert System</i>
"""


# Initialize Telegram bot
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    telegram_bot = TelegramBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    logger.info("Telegram bot initialized successfully")
else:
    telegram_bot = None
    logger.warning("Telegram bot not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")


@app.post("/webhook/telegram")
async def receive_alert(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Receive alert webhook from AlertManager and forward to Telegram

    Headers:
        Authorization: Bearer <WEBHOOK_TOKEN>
    """
    # Verify authentication token
    if authorization:
        token = authorization.replace("Bearer ", "")
        if token != WEBHOOK_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
    elif WEBHOOK_TOKEN != "your-secure-token-here":
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check if Telegram bot is configured
    if not telegram_bot:
        raise HTTPException(
            status_code=500,
            detail="Telegram bot not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
        )

    try:
        # Parse request body
        body = await request.json()
        logger.info(f"Received webhook: {json.dumps(body, indent=2)}")

        # Parse with Pydantic model
        payload = AlertManagerPayload(**body)

        # Format message
        message = format_telegram_message(payload)

        # Send to Telegram
        success = await telegram_bot.send_message(message)

        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Alert sent to Telegram",
                    "alerts_count": len(payload.alerts)
                }
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to send Telegram message")

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/test")
async def send_test_alert():
    """Send a test alert to Telegram"""
    if not telegram_bot:
        raise HTTPException(status_code=500, detail="Telegram bot not configured")

    message = format_simple_message(
        severity="info",
        title="Test Alert",
        description="This is a test alert from the Crypto Trading Bot monitoring system. If you received this, the Telegram notifications are working correctly!"
    )

    success = await telegram_bot.send_message(message)

    if success:
        return {"status": "success", "message": "Test alert sent"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send test alert")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    is_configured = telegram_bot is not None

    return {
        "status": "healthy" if is_configured else "not_configured",
        "telegram_configured": is_configured,
        "chat_id": TELEGRAM_CHAT_ID if is_configured else None,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/get-chat-id")
async def get_chat_id():
    """
    Get your Telegram chat ID

    Instructions:
    1. Start a chat with your bot
    2. Send any message to the bot
    3. Call this endpoint
    """
    if not telegram_bot:
        raise HTTPException(status_code=500, detail="Telegram bot not configured")

    chat_id = await telegram_bot.get_chat_id()

    if chat_id:
        return {
            "status": "success",
            "chat_id": chat_id,
            "message": "Use this chat ID in TELEGRAM_CHAT_ID environment variable"
        }
    else:
        return {
            "status": "no_messages",
            "message": "No messages found. Send a message to your bot first."
        }


if __name__ == "__main__":
    # Run the FastAPI server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="info"
    )
