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
from app.models import (
    Order,
    OrderCreate,
    OrderStatus,
    OrderSide,
    PositionSide,
)
from app.models.enums import ExitKind
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
        raise RuntimeError(
            "LIVE trading path is fenced off (2026-08-17): LiveTradingEngine "
            "records fills at the reference price with zero fees and zero "
            "posted margin, and its closes write the PAPER cash ledger "
            "(position_manager.close_position -> get_paper_engine()"
            ".get_balance() -> portfolio row 'paper_trading'). LIVE is also "
            "not mechanically viable at the $100 account: the 2% LIVE cap is "
            "$2, below the ~$5 venue min-notional. Repair the accounting and "
            "remove this fence deliberately before any LIVE build-out."
        )
        self.settings = get_settings()
        self.bybit_url = self.settings.bybit_connector_url
        self.position_manager = get_position_manager()
        self.risk_manager = get_risk_manager()
        self.client = httpx.AsyncClient(timeout=30.0)

        logger.info("=" * 60)
        logger.info("LIVE TRADING ENGINE INITIALIZED")
        logger.info("=" * 60)
        logger.info(f"  Bybit Connector URL: {self.bybit_url}")
        logger.info("  Mode: LIVE (REAL MONEY)")
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
                    balance = (
                        account.get("totalAvailableBalance")
                        or account.get("totalEquity")
                        or account.get("totalWalletBalance")
                        or "0"
                    )
                    logger.info(f"[LIVE] Bybit balance extracted: {balance}")
                    return Decimal(str(balance))

            # Fallback: try result structure
            if data.get("result"):
                result = data["result"]
                balance = (
                    result.get("totalAvailableBalance")
                    or result.get("availableBalance")
                    or result.get("totalWalletBalance")
                    or "0"
                )
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
            payload = response.json()

            data = payload.get("data") or {}
            account_list = data.get("list") or []
            if account_list:
                account = account_list[0]
                equity = (
                    account.get("totalEquity")
                    or account.get("totalWalletBalance")
                    or "0"
                )
                return Decimal(str(equity))

            return await self.get_balance()

        except Exception as e:
            logger.error(f"Failed to get equity from Bybit: {e}")
            return Decimal("0")

    async def execute_market_order(
        self, order: OrderCreate, current_price: Decimal
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
            # Risk check first.
            # FIX (audit 2026-05-01): RiskManager has no can_open_position
            # method — calling this in LIVE mode raised AttributeError before
            # an order was ever placed, so LIVE has been silently broken at
            # this gate. The existing API is check_position_limits(positions,
            # balance), so wire that.
            open_positions = self.position_manager.get_open_positions()
            balance_for_check = await self.get_balance()
            allowed, reason = self.risk_manager.check_position_limits(
                open_positions, balance_for_check
            )
            if not allowed:
                error = f"Risk manager rejected: {reason}"
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
                "reduce_only": False,
            }

            logger.info("=" * 60)
            logger.info("[LIVE] PLACING REAL ORDER ON BYBIT")
            logger.info("=" * 60)
            logger.info(f"  Symbol: {order.symbol}")
            logger.info(f"  Side: {side}")
            logger.info(f"  Quantity: {order.quantity}")
            logger.info(f"  Price (reference): {current_price}")
            logger.info("=" * 60)

            # Send order to Bybit. The bybit-connector raises HTTP 400 on Bybit
            # API errors and wraps the success payload as
            # {"success": True, "data": <bybit_result>}, so we extract orderId
            # from response["data"]["orderId"] and rely on raise_for_status
            # plus the broad except below for error handling.
            response = await self.client.post(
                f"{self.bybit_url}/api/v1/order/place", json=order_request
            )
            response.raise_for_status()
            payload = response.json()

            logger.info(f"[LIVE] Bybit response: {payload}")

            # Do NOT trust HTTP 200 alone. The connector signals failure by
            # raising (non-2xx), but an explicit {"success": false, ...} body
            # or a response carrying no orderId must never be recorded as a
            # fill: the code below stamps OrderStatus.FILLED and opens a
            # position, so accepting either shape invents a phantom position
            # against an order the exchange never accepted.
            if payload.get("success") is False:
                error = payload.get("detail") or payload.get("error") or "Order rejected by connector"
                logger.error(f"[LIVE] Order rejected: {error}")
                return None, error

            order_result = payload.get("data") or {}
            order_id = order_result.get("orderId", "")

            if not order_id:
                error = (
                    "Connector returned no orderId; refusing to record a fill "
                    f"for {order.symbol}. Payload: {payload}"
                )
                logger.error(f"[LIVE] {error}")
                return None, error

            # Create executed order record
            executed_order = Order(
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                quantity=order.quantity,
                price=current_price,
                status=OrderStatus.FILLED,
                strategy=order.strategy,
                bybit_order_id=order_id,
                filled_price=current_price,
                filled_quantity=order.quantity,
            )

            # Create position in position manager
            position_side = (
                PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT
            )

            # Get stop loss and take profit from risk manager
            stop_loss = self.risk_manager.calculate_stop_loss(
                current_price, position_side
            )
            take_profit = self.risk_manager.calculate_take_profit(
                current_price, position_side
            )

            position = self.position_manager.create_position(
                symbol=order.symbol,
                side=position_side,
                entry_price=current_price,
                quantity=order.quantity,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=order.strategy or "live_trading",
                # CRITICAL FIX 2025-12-07: Save entry signal confidence
                entry_signal_confidence=order.entry_signal_confidence,
            )

            logger.info("=" * 60)
            logger.info("[LIVE] ORDER FILLED SUCCESSFULLY")
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
        # FIX (audit 2026-05-01): same broken can_open_position call as in
        # execute_market_order — replaced with the real check_position_limits
        # so the maker entry path doesn't raise AttributeError.
        open_positions = self.position_manager.get_open_positions()
        balance_for_check = await self.get_balance()
        allowed, reason = self.risk_manager.check_position_limits(
            open_positions, balance_for_check
        )
        if not allowed:
            return None, f"Risk manager rejected: {reason}"

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

        # The bybit-connector raises HTTP 4xx on Bybit rejection (caught
        # above as `Exception`), so a 2xx success response carries
        # `{"success": True, "data": <bybit_inner>}` and we just need to
        # extract orderId. PostOnly-would-cross specifically returns 4xx
        # from Bybit and is therefore handled by the except block above.
        place_data = place_result.get("data") or {}
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
                logger.info("[LIVE][MAKER] Falling back to taker market order")
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
        take_profit = self.risk_manager.calculate_take_profit(
            limit_price, position_side
        )

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
        reason: str = "manual",
        exit_kind: Optional[ExitKind] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Close a position by placing opposite order on Bybit

        Args:
            position_id: Position ID to close
            close_price: Current price for closing
            reason: Reason for closing (prose)
            exit_kind: Structured close reason (Stage 0, 2026-08-07). PAPER
                and LIVE previously wrote structurally different values for
                the same event — LIVE had no channel at all. None for
                legacy callers; Task 6 wires actual values in from
                auto_trader.py.

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
                "reduce_only": True,  # Only reduce position
            }

            logger.info("=" * 60)
            logger.info("[LIVE] CLOSING POSITION ON BYBIT")
            logger.info("=" * 60)
            logger.info(f"  Position ID: {position_id}")
            logger.info(f"  Symbol: {position.symbol}")
            logger.info(f"  Side: {close_side}")
            logger.info(f"  Quantity: {position.remaining_quantity}")
            logger.info(f"  Reason: {reason}")
            logger.info("=" * 60)

            # Send close order. The bybit-connector raises HTTP 400 on Bybit
            # rejection, so a 2xx here means the close was accepted.
            response = await self.client.post(
                f"{self.bybit_url}/api/v1/order/place", json=close_request
            )
            response.raise_for_status()

            # Update position manager
            self.position_manager.close_position(
                position_id, close_price, reason, exit_kind=exit_kind
            )

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
            response = await self.client.get(
                f"{self.bybit_url}/api/v1/account/positions"
            )
            response.raise_for_status()
            payload = response.json()

            # Connector returns {"success": True, "data": [pos, ...]}
            positions = payload.get("data") or []
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
