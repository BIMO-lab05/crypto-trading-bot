"""
Notification Service Client
Sends trade notifications to the notification service for Telegram/Email alerts
"""

import aiohttp
import logging
from typing import Dict, Optional, Any
from datetime import datetime

from ..config import get_settings

logger = logging.getLogger(__name__)


class NotificationClient:
    """Client for sending notifications via the notification service"""

    def __init__(self, base_url: Optional[str] = None):
        settings = get_settings()
        self.base_url = base_url or settings.notification_service_url
        self.enabled = settings.enable_notifications
        self.notify_on_trade_open = settings.notify_on_trade_open
        self.notify_on_trade_close = settings.notify_on_trade_close
        self.notify_on_daily_summary = settings.notify_on_daily_summary
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request to notification service"""
        if not self.enabled:
            logger.debug("Notifications disabled, skipping")
            return {"success": False, "reason": "disabled"}

        try:
            session = await self._get_session()
            url = f"{self.base_url}{endpoint}"
            async with session.post(url, json=data) as response:
                result = await response.json()
                if response.status == 200:
                    logger.info(f"Notification sent: {endpoint}")
                    return result
                else:
                    logger.warning(f"Notification failed: {response.status} - {result}")
                    return {"success": False, "error": result}
        except aiohttp.ClientError as e:
            logger.error(f"Notification service connection error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Notification error: {e}")
            return {"success": False, "error": str(e)}

    async def notify_trade_open(
        self,
        symbol: str,
        action: str,
        quantity: float,
        price: float,
        confidence: float = 0.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """Send notification when a trade is opened"""
        if not self.notify_on_trade_open:
            return {"success": False, "reason": "trade_open_notifications_disabled"}

        data = {
            "action": action,
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "timestamp": datetime.utcnow().isoformat(),
            "signal_confidence": confidence
        }

        logger.info(f"[NOTIFY] Trade opened: {action} {quantity} {symbol} @ ${price:.2f}")
        return await self._post("/api/v1/notify/trade", data)

    async def notify_trade_close(
        self,
        symbol: str,
        action: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float
    ) -> Dict[str, Any]:
        """Send notification when a trade is closed"""
        if not self.notify_on_trade_close:
            return {"success": False, "reason": "trade_close_notifications_disabled"}

        trade_data = {
            "action": action,
            "symbol": symbol,
            "quantity": quantity,
            "price": exit_price,
            "timestamp": datetime.utcnow().isoformat(),
            "signal_confidence": 0.0
        }

        data = {
            "trade": trade_data,
            "pnl": pnl
        }

        profit_emoji = "+" if pnl >= 0 else ""
        logger.info(f"[NOTIFY] Trade closed: {symbol} PnL: {profit_emoji}${pnl:.2f} ({profit_emoji}{pnl_pct:.2f}%)")
        return await self._post("/api/v1/notify/pnl", data)

    async def notify_error(
        self,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send error notification"""
        data = {
            "error_message": error_message,
            "context": context or {}
        }

        logger.warning(f"[NOTIFY] Error: {error_message}")
        return await self._post("/api/v1/notify/error", data)

    async def notify_startup(
        self,
        mode: str,
        symbols: list,
        interval_minutes: int,
        capital: float,
        max_position_pct: float,
        daily_loss_limit: float,
        stop_loss_pct: float
    ) -> Dict[str, Any]:
        """Send startup notification"""
        data = {
            "mode": mode,
            "symbols": symbols,
            "interval_minutes": interval_minutes,
            "capital": capital,
            "max_position_pct": max_position_pct,
            "daily_loss_limit": daily_loss_limit,
            "stop_loss_pct": stop_loss_pct
        }

        logger.info(f"[NOTIFY] Bot started in {mode} mode with {len(symbols)} symbols")
        return await self._post("/api/v1/notify/startup", data)

    async def notify_daily_summary(
        self,
        total_pnl: float,
        total_trades: int,
        win_rate: float,
        best_trade: float,
        worst_trade: float,
        balance: float,
        open_positions: int
    ) -> Dict[str, Any]:
        """Send daily summary notification"""
        if not self.notify_on_daily_summary:
            return {"success": False, "reason": "daily_summary_notifications_disabled"}

        data = {
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "balance": balance,
            "open_positions": open_positions
        }

        profit_emoji = "+" if total_pnl >= 0 else ""
        logger.info(f"[NOTIFY] Daily summary: {profit_emoji}${total_pnl:.2f}, {total_trades} trades, {win_rate:.1f}% win rate")
        return await self._post("/api/v1/notify/daily-summary", data)

    async def test_notification(self, message: str = "Test notification") -> Dict[str, Any]:
        """Send test notification"""
        data = {"message": message}
        return await self._post("/api/v1/test", data)


# Singleton instance
_notification_client: Optional[NotificationClient] = None


def get_notification_client() -> NotificationClient:
    """Get or create notification client singleton"""
    global _notification_client
    if _notification_client is None:
        _notification_client = NotificationClient()
    return _notification_client


async def close_notification_client():
    """Close notification client session"""
    global _notification_client
    if _notification_client:
        await _notification_client.close()
        _notification_client = None
