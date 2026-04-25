"""
Template Engine
Handles rendering of alert templates for various channels
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from string import Template
from pathlib import Path

logger = logging.getLogger(__name__)


# ========================================
# HTML Templates
# ========================================

CRITICAL_ALERT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Critical Alert</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
        }
        .banner {
            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .banner h1 {
            margin: 0;
            font-size: 28px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        .banner .subtitle {
            margin-top: 10px;
            font-size: 16px;
            opacity: 0.9;
        }
        .content {
            padding: 30px;
        }
        .alert-box {
            background: #fdf2f2;
            border-left: 4px solid #e74c3c;
            padding: 20px;
            margin: 20px 0;
        }
        .alert-title {
            font-size: 18px;
            font-weight: bold;
            color: #c0392b;
            margin-bottom: 10px;
        }
        .alert-message {
            color: #333;
            line-height: 1.6;
        }
        .action-required {
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 5px;
            padding: 20px;
            margin: 20px 0;
        }
        .action-required h3 {
            color: #856404;
            margin-top: 0;
        }
        .metadata {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .metadata-item {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid #e9ecef;
        }
        .metadata-label {
            color: #666;
        }
        .metadata-value {
            font-weight: bold;
        }
        .footer {
            background: #2c3e50;
            color: #bdc3c7;
            padding: 20px;
            text-align: center;
            font-size: 12px;
        }
        .button {
            display: inline-block;
            background: #e74c3c;
            color: white;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 5px;
            margin-top: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="banner">
            <h1>Critical Alert</h1>
            <div class="subtitle">Immediate attention required</div>
        </div>
        <div class="content">
            <div class="alert-box">
                <div class="alert-title">${title}</div>
                <div class="alert-message">${message}</div>
            </div>

            <div class="action-required">
                <h3>Action Required</h3>
                <p>${action_required}</p>
            </div>

            <div class="metadata">
                <div class="metadata-item">
                    <span class="metadata-label">Alert ID:</span>
                    <span class="metadata-value">${alert_id}</span>
                </div>
                <div class="metadata-item">
                    <span class="metadata-label">Source:</span>
                    <span class="metadata-value">${source}</span>
                </div>
                <div class="metadata-item">
                    <span class="metadata-label">Time:</span>
                    <span class="metadata-value">${timestamp}</span>
                </div>
            </div>

            <div style="text-align: center;">
                <a href="${dashboard_url}" class="button">View Dashboard</a>
            </div>
        </div>
        <div class="footer">
            <p>This is an automated alert from your Trading Bot.</p>
            <p>Do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""

TRADE_ALERT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trade Alert</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
        }
        .header {
            background: ${header_color};
            color: white;
            padding: 25px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 24px;
        }
        .header .action-badge {
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 5px 15px;
            border-radius: 20px;
            margin-top: 10px;
            font-size: 14px;
        }
        .content {
            padding: 30px;
        }
        .trade-details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin: 20px 0;
        }
        .detail-box {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
        }
        .detail-label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }
        .detail-value {
            font-size: 20px;
            font-weight: bold;
            margin-top: 5px;
        }
        .risk-section {
            background: #fff3cd;
            border-radius: 5px;
            padding: 20px;
            margin: 20px 0;
        }
        .risk-section h3 {
            margin-top: 0;
            color: #856404;
        }
        .risk-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #ffeaa7;
        }
        .pnl-section {
            text-align: center;
            padding: 20px;
            background: ${pnl_bg_color};
            border-radius: 5px;
            margin: 20px 0;
        }
        .pnl-value {
            font-size: 32px;
            font-weight: bold;
            color: ${pnl_color};
        }
        .footer {
            background: #2c3e50;
            color: #bdc3c7;
            padding: 20px;
            text-align: center;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Trade Executed</h1>
            <div class="action-badge">${action} ${symbol}</div>
        </div>
        <div class="content">
            <div class="trade-details">
                <div class="detail-box">
                    <div class="detail-label">Quantity</div>
                    <div class="detail-value">${quantity}</div>
                </div>
                <div class="detail-box">
                    <div class="detail-label">Price</div>
                    <div class="detail-value">$${price}</div>
                </div>
                <div class="detail-box">
                    <div class="detail-label">Total Value</div>
                    <div class="detail-value">$${total_value}</div>
                </div>
                <div class="detail-box">
                    <div class="detail-label">Confidence</div>
                    <div class="detail-value">${confidence}%</div>
                </div>
            </div>

            <div class="risk-section">
                <h3>Risk Management</h3>
                <div class="risk-item">
                    <span>Stop Loss</span>
                    <span>$${stop_loss}</span>
                </div>
                <div class="risk-item">
                    <span>Take Profit</span>
                    <span>$${take_profit}</span>
                </div>
                <div class="risk-item">
                    <span>Risk/Reward</span>
                    <span>1:${risk_reward}</span>
                </div>
            </div>

            ${pnl_section}
        </div>
        <div class="footer">
            <p>Trade ID: ${trade_id} | ${timestamp}</p>
        </div>
    </div>
</body>
</html>
"""

RISK_ALERT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Risk Alert</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
        }
        .header {
            background: ${header_color};
            color: white;
            padding: 25px;
            text-align: center;
        }
        .severity-badge {
            display: inline-block;
            background: rgba(0,0,0,0.2);
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            text-transform: uppercase;
        }
        .content {
            padding: 30px;
        }
        .metric-display {
            display: flex;
            justify-content: space-around;
            margin: 30px 0;
        }
        .metric {
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            min-width: 120px;
        }
        .metric-value {
            font-size: 28px;
            font-weight: bold;
            color: ${metric_color};
        }
        .metric-label {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
        .threshold-bar {
            background: #e9ecef;
            height: 20px;
            border-radius: 10px;
            overflow: hidden;
            margin: 20px 0;
        }
        .threshold-fill {
            height: 100%;
            background: ${fill_color};
            width: ${fill_percentage}%;
        }
        .message-box {
            background: #f8f9fa;
            border-left: 4px solid ${header_color};
            padding: 20px;
            margin: 20px 0;
        }
        .footer {
            background: #2c3e50;
            color: #bdc3c7;
            padding: 20px;
            text-align: center;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Risk Alert</h1>
            <div class="severity-badge">${severity}</div>
        </div>
        <div class="content">
            <h2>${title}</h2>

            <div class="metric-display">
                <div class="metric">
                    <div class="metric-value">${current_value}</div>
                    <div class="metric-label">Current</div>
                </div>
                <div class="metric">
                    <div class="metric-value">${threshold}</div>
                    <div class="metric-label">Threshold</div>
                </div>
            </div>

            <div class="threshold-bar">
                <div class="threshold-fill"></div>
            </div>

            <div class="message-box">
                ${message}
            </div>
        </div>
        <div class="footer">
            <p>Risk Management System | ${timestamp}</p>
        </div>
    </div>
</body>
</html>
"""

DAILY_SUMMARY_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Summary</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
        }
        .header {
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .pnl-hero {
            font-size: 48px;
            font-weight: bold;
            color: ${pnl_color};
            margin: 20px 0;
        }
        .content {
            padding: 30px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin: 20px 0;
        }
        .stat-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
        }
        .stat-label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            margin-top: 5px;
        }
        .trades-section {
            margin: 30px 0;
        }
        .trade-row {
            display: flex;
            justify-content: space-between;
            padding: 10px;
            border-bottom: 1px solid #e9ecef;
        }
        .trade-row.best {
            background: #d4edda;
        }
        .trade-row.worst {
            background: #f8d7da;
        }
        .balance-section {
            background: #e8f4fd;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            margin: 20px 0;
        }
        .balance-value {
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
        }
        .footer {
            background: #2c3e50;
            color: #bdc3c7;
            padding: 20px;
            text-align: center;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Daily Trading Summary</h1>
            <p>${date}</p>
            <div class="pnl-hero">$${total_pnl}</div>
        </div>
        <div class="content">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${total_trades}</div>
                    <div class="stat-label">Total Trades</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${win_rate}%</div>
                    <div class="stat-label">Win Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${winning_trades}</div>
                    <div class="stat-label">Winning</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${losing_trades}</div>
                    <div class="stat-label">Losing</div>
                </div>
            </div>

            <div class="trades-section">
                <h3>Trade Highlights</h3>
                <div class="trade-row best">
                    <span>Best Trade</span>
                    <span>+$${best_trade}</span>
                </div>
                <div class="trade-row worst">
                    <span>Worst Trade</span>
                    <span>$${worst_trade}</span>
                </div>
            </div>

            <div class="balance-section">
                <div class="stat-label">Current Balance</div>
                <div class="balance-value">$${balance}</div>
            </div>
        </div>
        <div class="footer">
            <p>Keep trading smart. Stay disciplined.</p>
            <p>Generated on ${timestamp}</p>
        </div>
    </div>
</body>
</html>
"""

# ========================================
# Telegram Markdown Templates
# ========================================

TELEGRAM_TRADE_MD = """
{emoji} <b>Trade Executed</b>

<b>Action:</b> {action}
<b>Symbol:</b> {symbol}
<b>Quantity:</b> {quantity}
<b>Entry Price:</b> ${price}
<b>Total Value:</b> ${total_value}

<b>Risk Management:</b>
- Stop Loss: ${stop_loss} ({sl_pct}%)
- Take Profit: ${take_profit} ({tp_pct}%)
- Risk/Reward: 1:{risk_reward}

<b>Confidence:</b> {confidence}%
<b>Time:</b> {timestamp}
"""

TELEGRAM_RISK_MD = """
{emoji} <b>Risk Alert: {severity}</b>

<b>Alert Type:</b> {alert_type}
<b>Current Value:</b> {current_value}
<b>Threshold:</b> {threshold}

{message}

<b>Time:</b> {timestamp}
"""

TELEGRAM_SYSTEM_MD = """
{emoji} <b>System Alert</b>

<b>Service:</b> {service_name}
<b>Status:</b> {status}

{error_section}

<b>Time:</b> {timestamp}
"""

# ========================================
# Slack Block Templates
# ========================================

SLACK_SYSTEM_BLOCKS = {
    "type": "section",
    "fields": [
        {
            "type": "mrkdwn",
            "text": "*Service:*\n{service_name}"
        },
        {
            "type": "mrkdwn",
            "text": "*Status:*\n{status_emoji} {status}"
        }
    ]
}


class TemplateEngine:
    """Template rendering engine"""

    # Template registry
    HTML_TEMPLATES = {
        "critical_alert": CRITICAL_ALERT_HTML,
        "trade_alert": TRADE_ALERT_HTML,
        "risk_alert": RISK_ALERT_HTML,
        "daily_summary": DAILY_SUMMARY_HTML,
    }

    TELEGRAM_TEMPLATES = {
        "trade": TELEGRAM_TRADE_MD,
        "risk": TELEGRAM_RISK_MD,
        "system": TELEGRAM_SYSTEM_MD,
    }

    @classmethod
    def render_html(cls, template_name: str, **kwargs) -> str:
        """
        Render an HTML template

        Args:
            template_name: Name of the template
            **kwargs: Template variables

        Returns:
            Rendered HTML string
        """
        template_str = cls.HTML_TEMPLATES.get(template_name)
        if not template_str:
            logger.warning(f"Unknown HTML template: {template_name}")
            return f"<p>{kwargs.get('message', 'No content')}</p>"

        # Add default values
        defaults = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "dashboard_url": "http://localhost:3000",
            "action_required": "Please review this alert and take appropriate action.",
        }
        defaults.update(kwargs)

        try:
            template = Template(template_str)
            return template.safe_substitute(defaults)
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            return f"<p>Error rendering template: {e}</p>"

    @classmethod
    def render_telegram(cls, template_name: str, **kwargs) -> str:
        """
        Render a Telegram Markdown template

        Args:
            template_name: Name of the template
            **kwargs: Template variables

        Returns:
            Rendered Markdown string
        """
        template_str = cls.TELEGRAM_TEMPLATES.get(template_name)
        if not template_str:
            logger.warning(f"Unknown Telegram template: {template_name}")
            return kwargs.get("message", "No content")

        # Add defaults
        defaults = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "emoji": "i",
            "error_section": "",
        }
        defaults.update(kwargs)

        try:
            return template_str.format(**defaults)
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            return f"Template error: missing {e}"

    @classmethod
    def get_trade_html(
        cls,
        action: str,
        symbol: str,
        quantity: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        confidence: float = 0.0,
        pnl: Optional[float] = None,
        **kwargs
    ) -> str:
        """Generate trade alert HTML"""
        is_buy = action.upper() == "BUY"

        # Calculate risk/reward
        risk_reward = "N/A"
        if stop_loss and take_profit:
            if is_buy:
                risk = abs(price - stop_loss)
                reward = abs(take_profit - price)
            else:
                risk = abs(stop_loss - price)
                reward = abs(price - take_profit)
            if risk > 0:
                risk_reward = f"{reward/risk:.2f}"

        # PNL section
        pnl_section = ""
        if pnl is not None:
            pnl_color = "#27ae60" if pnl >= 0 else "#e74c3c"
            pnl_bg = "#d4edda" if pnl >= 0 else "#f8d7da"
            pnl_section = f"""
            <div class="pnl-section" style="background: {pnl_bg};">
                <div style="font-size: 14px; color: #666;">Realized P&L</div>
                <div class="pnl-value" style="color: {pnl_color};">${pnl:,.2f}</div>
            </div>
            """

        return cls.render_html(
            "trade_alert",
            action=action.upper(),
            symbol=symbol,
            quantity=f"{quantity:.6f}",
            price=f"{price:,.2f}",
            total_value=f"{quantity * price:,.2f}",
            stop_loss=f"{stop_loss:,.2f}" if stop_loss else "N/A",
            take_profit=f"{take_profit:,.2f}" if take_profit else "N/A",
            risk_reward=risk_reward,
            confidence=f"{confidence * 100:.1f}",
            header_color="#27ae60" if is_buy else "#e74c3c",
            pnl_section=pnl_section,
            pnl_color="#27ae60" if (pnl or 0) >= 0 else "#e74c3c",
            pnl_bg_color="#d4edda" if (pnl or 0) >= 0 else "#f8d7da",
            trade_id=kwargs.get("trade_id", "N/A"),
            **kwargs
        )

    @classmethod
    def get_daily_summary_html(
        cls,
        total_pnl: float,
        total_trades: int,
        win_rate: float,
        best_trade: float,
        worst_trade: float,
        balance: float,
        **kwargs
    ) -> str:
        """Generate daily summary HTML"""
        winning = int(total_trades * win_rate)
        losing = total_trades - winning

        return cls.render_html(
            "daily_summary",
            total_pnl=f"{total_pnl:,.2f}",
            pnl_color="#27ae60" if total_pnl >= 0 else "#e74c3c",
            total_trades=total_trades,
            win_rate=f"{win_rate * 100:.1f}",
            winning_trades=winning,
            losing_trades=losing,
            best_trade=f"{best_trade:,.2f}",
            worst_trade=f"{worst_trade:,.2f}",
            balance=f"{balance:,.2f}",
            date=datetime.utcnow().strftime("%B %d, %Y"),
            **kwargs
        )


def get_template(template_name: str) -> Optional[str]:
    """
    Get raw template string by name

    Args:
        template_name: Name of the template

    Returns:
        Template string or None
    """
    all_templates = {
        **TemplateEngine.HTML_TEMPLATES,
        **TemplateEngine.TELEGRAM_TEMPLATES,
    }
    return all_templates.get(template_name)
