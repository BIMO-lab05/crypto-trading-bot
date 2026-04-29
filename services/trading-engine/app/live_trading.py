"""
Live Trading Engine
Purpose: Execute real trades on Bybit through bybit-connector service

This engine replaces paper trading with actual exchange orders.
Use with caution - real money at risk!

IMPORTANT:
- Only use with properly configured API keys
- Test thoroughly with small amounts first
- Monitor positions actively
"""

import asyncio
import logging
import time
import httpx
from decimal import Decimal
from typing import Optional, Tuple
from uuid import UUID

from app.config import get_settings
from app.models import Order, OrderCreate, OrderStatus, OrderSide, OrderType, PositionSide
from app.position_manager import get_position_manager
from app.risk_manager import get_risk_manager

logger = logging.getLogger(__name__)


_MAKER_POLL_INTERVAL_SECONDS = 2.0


class LiveTradingEngine:
    """
    Execute real trades via Bybit connector API

    Features:
    1. Real order execution on Bybit exchange
    2. Position tracking synced with exchange
    3. Commission from actual exchange fees
    4. Risk management integration
    """

    def __init__(self):
        """Initialize live trading engine"""
        self.settings = get_settings()
        self.bybit_url = self.settings.bybit_connector_url
        self.position_manager = get_position_manager()
        self.risk_manager = get_risk_manager()
        self.client = httpx.AsyncClient(timeout=30.0)

        logger.info("=" * 60)
        logger.info("LIVE TRADING ENGINE INITIALIZED")
        logger.info("=" * 60)
        logger.info(f"  Bybit Connector URL: {self.bybit_url}")
        logger.info(f"  Mode: LIVE (REAL MONEY)")
        logger.info("  WARNING: Real trades will be executed!")
        logger.info("=" * 60)

    async def get_balance(self) -> Decimal:
        """Get actual account balance from Bybit"""
        try:
            response = await self.client.get(f"{self.bybit_url}/api/v1/account/balance")
            response.raise_for_status()
            data = response.json()

            # Extract USDT balance from Bybit response
            # Response format: {"success": true, "data": {"list": [{"totalEquity": "...", ...}]}}
            if data.get("data"):
                result = data["data"]
                account_list = result.get("list", [])
                if account_list:
                    account = account_list[0]
                    # Try different balance fields
                    balance = account.get("totalAvailableBalance") or \
                             account.get("totalEquity") or \
                             account.get("totalWalletBalance") or \
                             "0"
                    logger.info(f"[LIVE] Bybit balance extracted: {balance}")
                    return Decimal(str(balance))

            # Fallback: try result structure
            if data.get("result"):
                result = data["result"]
                balance = result.get("totalAvailableBalance") or \
                         result.get("availableBalance") or \
                         result.get("totalWalletBalance") or \
                         "0"
                return Decimal(str(balance))

            logger.warning(f"Could not extract balance from Bybit response: {data}")
            return Decimal("0")

        except Exception as e:
            logger.error(f"Failed to get balance from Bybit: {e}")
            return Decimal("0")

    async def get_total_equity(self) -> Decimal:
        """Get total equity (balance + positions value)"""
        try:
            response = await self.client.get(f"{self.bybit_url}/api/v1/account/balance")
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                result = data["result"]
                equity = result.get("totalEquity") or \
                        result.get("totalWalletBalance") or \
                        "0"
                return Decimal(str(equity))

            return await self.get_balance()

        except Exception as e:
            logger.error(f"Failed to get equity from Bybit: {e}")
            return Decimal("0")

    async def execute_market_order(
        self,
        order: OrderCreate,
        current_price: Decimal
    ) -> Tuple[Optional[Order], Optional[str]]:
        """
        Execute a real market order on Bybit

        Args:
            order: Order to execute
            current_price: Current market price (for reference)

        Returns:
            Tuple of (executed_order, error_message)
        """
        try:
            # Risk check first
            if not self.risk_manager.can_open_position(
                order.symbol,
                current_price * order.quantity
            ):
                error = "Risk manager rejected: exposure limit reached"
                logger.warning(f"[LIVE] {error}")
                return None, error

            # Map order side to Bybit format
            side = "Buy" if order.side == OrderSide.BUY else "Sell"

            # Build order request
            order_request = {
                "category": "linear",  # USDT perpetual
                "symbol": order.symbol,
                "side": side,
                "order_type": "Market",
                "qty": str(order.quantity),
                "time_in_force": "GTC",
                "reduce_only": False
            }

            logger.info("=" * 60)
            logger.info(f"[LIVE] PLACING REAL ORDER ON BYBIT")
            logger.info("=" * 60)
            logger.info(f"  Symbol: {order.symbol}")
            logger.info(f"  Side: {side}")
            logger.info(f"  Quantity: {order.quantity}")
            logger.info(f"  Price (reference): {current_price}")
            logger.info("=" * 60)

            # Send order to Bybit
            response = await self.client.post(
                f"{self.bybit_url}/api/v1/order/place",
                json=order_request
            )
            response.raise_for_status()
            result = response.json()

            logger.info(f"[LIVE] Bybit response: {result}")

            # Check for errors
            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"[LIVE] Order rejected by Bybit: {error_msg}")
                return None, error_msg

            # Extract order details
            order_result = result.get("result", {})
            order_id = order_result.get("orderId", "")

            # Create executed order record
            executed_order = Order(
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                quantity=order.quantity,
                price=current_price,  # Will be updated with fill price
                status=OrderStatus.FILLED,
                strategy=order.strategy
            )
            executed_order.order_id = order_id

            # Create position in position manager
            position_side = PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT

            # Get stop loss and take profit from risk manager
            stop_loss = self.risk_manager.calculate_stop_loss(current_price, position_side)
            take_profit = self.risk_manager.calculate_take_profit(current_price, position_side)

            position = self.position_manager.create_position(
                symbol=order.symbol,
                side=position_side,
                entry_price=current_price,
                quantity=order.quantity,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=order.strategy or "live_trading",
                # CRITICAL FIX 2025-12-07: Save entry signal confidence
                entry_signal_confidence=order.entry_signal_confidence
            )

            logger.info("=" * 60)
            logger.info(f"[LIVE] ORDER FILLED SUCCESSFULLY")
            logger.info(f"  Bybit Order ID: {order_id}")
            logger.info(f"  Position ID: {position.id}")
            logger.info(f"  Entry: ${current_price}")
            logger.info(f"  Stop Loss: ${stop_loss}")
            logger.info(f"  Take Profit: ${take_profit}")
            logger.info("=" * 60)

            return executed_order, None

        except httpx.HTTPStatusError as e:
            error = f"HTTP error placing order: {e.response.status_code}"
            logger.error(f"[LIVE] {error}")
            return None, error
        except Exception as e:
            error = f"Failed to execute order: {str(e)}"
            logger.error(f"[LIVE] {error}", exc_info=True)
            return None, error

    async def _get_best_quote(self, symbol: str) -> Optional[Tuple[Decimal, Decimal]]:
        """Return (best_bid, best_ask) for the linear perp, or None on error."""
        try:
            response = await self.client.get(
                f"{self.bybit_url}/api/v1/market/orderbook",
                params={"category": "linear", "symbol": symbol, "limit": 1},
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or payload.get("result") or {}
            bids = data.get("b") or data.get("bids") or []
            asks = data.get("a") or data.get("asks") or []
            if not bids or not asks:
                return None
            return Decimal(str(bids[0][0])), Decimal(str(asks[0][0]))
        except Exception as e:
            logger.warning(f"[LIVE] Orderbook fetch failed for {symbol}: {e}")
            return None

    async def _is_order_open(self, symbol: str, order_id: str) -> bool:
        """Return True iff order_id is still on the book (not filled/cancelled)."""
        try:
            response = await self.client.get(
                f"{self.bybit_url}/api/v1/order/open",
                params={"category": "linear", "symbol": symbol},
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or payload.get("result") or {}
            open_orders = data.get("list") or data
            if isinstance(open_orders, list):
                return any(o.get("orderId") == order_id for o in open_orders)
            return False
        except Exception as e:
            logger.warning(f"[LIVE] Open-order check failed for {order_id}: {e}")
            return True  # Conservative: assume still open so we don't double-place

    async def execute_maker_order_with_fallback(
        self,
        order: OrderCreate,
        current_price: Decimal,
    ) -> Tuple[Optional[Order], Optional[str]]:
        """
        Place a PostOnly limit order at best bid (BUY) or best ask (SELL).
        If unfilled within `maker_quote_timeout_seconds`, cancel and either
        fall back to a taker market order or abort, per `maker_fallback_to_taker`.

        Falls back to `execute_market_order` immediately if the orderbook is
        unreachable — better to take liquidity than to silently skip a signal.
        """
        if not self.risk_manager.can_open_position(
            order.symbol, current_price * order.quantity
        ):
            return None, "Risk manager rejected: exposure limit reached"

        quote = await self._get_best_quote(order.symbol)
        if quote is None:
            logger.warning(
                f"[LIVE][MAKER] No orderbook for {order.symbol}; falling back to taker"
            )
            return await self.execute_market_order(order, current_price)
        best_bid, best_ask = quote

        side = "Buy" if order.side == OrderSide.BUY else "Sell"
        # PostOnly side: BUY → bid (don't cross); SELL → ask
        limit_price = best_bid if order.side == OrderSide.BUY else best_ask

        order_request = {
            "category": "linear",
            "symbol": order.symbol,
            "side": side,
            "order_type": "Limit",
            "qty": str(order.quantity),
            "price": str(limit_price),
            "time_in_force": "PostOnly",
            "reduce_only": False,
        }

        logger.info(
            f"[LIVE][MAKER] PostOnly {side} {order.symbol} qty={order.quantity} "
            f"@ {limit_price} (bid={best_bid}, ask={best_ask}, ref={current_price})"
        )

        try:
            place_resp = await self.client.post(
                f"{self.bybit_url}/api/v1/order/place", json=order_request
            )
            place_resp.raise_for_status()
            place_result = place_resp.json()
        except Exception as e:
            logger.error(f"[LIVE][MAKER] Place failed: {e}")
            if self.settings.maker_fallback_to_taker:
                return await self.execute_market_order(order, current_price)
            return None, f"Maker place failed: {e}"

        if place_result.get("retCode") not in (0, None):
            err = place_result.get("retMsg", "Unknown error")
            logger.warning(f"[LIVE][MAKER] Bybit rejected PostOnly: {err}")
            if self.settings.maker_fallback_to_taker:
                return await self.execute_market_order(order, current_price)
            return None, f"PostOnly rejected: {err}"

        place_data = place_result.get("data") or place_result.get("result") or {}
        order_id = place_data.get("orderId", "")
        if not order_id:
            logger.error(f"[LIVE][MAKER] No orderId returned: {place_result}")
            if self.settings.maker_fallback_to_taker:
                return await self.execute_market_order(order, current_price)
            return None, "PostOnly: no orderId returned"

        timeout_s = self.settings.maker_quote_timeout_seconds
        deadline = time.monotonic() + timeout_s
        filled = False
        while time.monotonic() < deadline:
            await asyncio.sleep(_MAKER_POLL_INTERVAL_SECONDS)
            still_open = await self._is_order_open(order.symbol, order_id)
            if not still_open:
                filled = True
                break

        if not filled:
            logger.info(
                f"[LIVE][MAKER] Timeout after {timeout_s}s — cancelling {order_id}"
            )
            try:
                await self.client.post(
                    f"{self.bybit_url}/api/v1/order/cancel",
                    json={
                        "category": "linear",
                        "symbol": order.symbol,
                        "order_id": order_id,
                    },
                )
            except Exception as e:
                logger.warning(f"[LIVE][MAKER] Cancel failed for {order_id}: {e}")
            if self.settings.maker_fallback_to_taker:
                logger.info(f"[LIVE][MAKER] Falling back to taker market order")
                return await self.execute_market_order(order, current_price)
            return None, "Maker quote timed out; taker fallback disabled"

        # Filled at limit_price → record position
        executed_order = Order(
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            quantity=order.quantity,
            price=limit_price,
            status=OrderStatus.FILLED,
            strategy=order.strategy,
            bybit_order_id=order_id,
            filled_price=limit_price,
            filled_quantity=order.quantity,
        )

        position_side = (
            PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT
        )
        stop_loss = self.risk_manager.calculate_stop_loss(limit_price, position_side)
        take_profit = self.risk_manager.calculate_take_profit(limit_price, position_side)

        self.position_manager.create_position(
            symbol=order.symbol,
            side=position_side,
            entry_price=limit_price,
            quantity=order.quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=order.strategy or "live_trading",
            entry_signal_confidence=order.entry_signal_confidence,
        )

        logger.info(
            f"[LIVE][MAKER] FILLED {order.symbol} {side} qty={order.quantity} "
            f"@ {limit_price} (id={order_id})"
        )
        return executed_order, None

    async def close_position(
        self,
        position_id: UUID,
        close_price: Decimal,
        reason: str = "manual"
    ) -> Tuple[bool, Optional[str]]:
        """
        Close a position by placing opposite order on Bybit

        Args:
            position_id: Position ID to close
            close_price: Current price for closing
            reason: Reason for closing

        Returns:
            Tuple of (success, error_message)
        """
        try:
            position = self.position_manager.get_position(position_id)
            if not position:
                return False, "Position not found"

            # Determine close side (opposite of position)
            close_side = "Sell" if position.side == PositionSide.LONG else "Buy"

            # Build close order
            close_request = {
                "category": "linear",
                "symbol": position.symbol,
                "side": close_side,
                "order_type": "Market",
                "qty": str(position.remaining_quantity),
                "time_in_force": "GTC",
                "reduce_only": True  # Only reduce position
            }

            logger.info("=" * 60)
            logger.info(f"[LIVE] CLOSING POSITION ON BYBIT")
            logger.info("=" * 60)
            logger.info(f"  Position ID: {position_id}")
            logger.info(f"  Symbol: {position.symbol}")
            logger.info(f"  Side: {close_side}")
            logger.info(f"  Quantity: {position.remaining_quantity}")
            logger.info(f"  Reason: {reason}")
            logger.info("=" * 60)

            # Send close order
            response = await self.client.post(
                f"{self.bybit_url}/api/v1/order/place",
                json=close_request
            )
            response.raise_for_status()
            result = response.json()

            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"[LIVE] Close order rejected: {error_msg}")
                return False, error_msg

            # Update position manager
            self.position_manager.close_position(position_id, close_price, reason)

            logger.info(f"[LIVE] Position closed successfully: {position_id}")
            return True, None

        except Exception as e:
            error = f"Failed to close position: {str(e)}"
            logger.error(f"[LIVE] {error}", exc_info=True)
            return False, error

    async def sync_positions_with_exchange(self):
        """
        Sync local positions with actual exchange positions

        This should be called on startup to reconcile state.
        """
        try:
            response = await self.client.get(f"{self.bybit_url}/api/v1/account/positions")
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                positions = data["result"].get("list", [])
                logger.info(f"[LIVE] Found {len(positions)} positions on exchange")

                for pos in positions:
                    if float(pos.get("size", 0)) > 0:
                        logger.info(
                            f"[LIVE] Exchange position: {pos['symbol']} "
                            f"{pos['side']} {pos['size']} @ {pos['avgPrice']}"
                        )

        except Exception as e:
            logger.error(f"[LIVE] Failed to sync positions: {e}")

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Global live trading engine instance
_live_engine: Optional[LiveTradingEngine] = None


def get_live_engine() -> LiveTradingEngine:
    """Get or create live trading engine instance"""
    global _live_engine
    if _live_engine is None:
        _live_engine = LiveTradingEngine()
    return _live_engine


async def close_live_engine():
    """Close the live trading engine"""
    global _live_engine
    if _live_engine:
        await _live_engine.close()
        _live_engine = None
