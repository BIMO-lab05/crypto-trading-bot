"""
Trading Service - Business Logic Layer
Extracted from main.py - Responsibility: Core trading execution logic

This service contains the core trading logic isolated from HTTP concerns.
It can be tested independently and reused across different contexts.
"""

import logging
from decimal import Decimal
from typing import Tuple, Optional

from app.models import OrderCreate, OrderSide, OrderType, SignalAction
from app.paper_trading import get_paper_engine
from app.risk_manager import get_risk_manager
from app.position_manager import get_position_manager

logger = logging.getLogger(__name__)


class TradingService:
    """
    Core trading execution service

    Handles signal-to-trade conversion with proper risk management,
    position sizing, and execution logic.
    """

    @staticmethod
    async def execute_signal_trade(signal) -> str:
        """
        Execute trade based on signal (paper trading mode)

        Args:
            signal: Trading signal object with action, symbol, and indicators

        Returns:
            str: Execution result message

        Process:
            1. Validate signal action (BUY/SELL only)
            2. Extract current price from signal indicators
            3. Calculate position size using risk management
            4. Execute market order via paper trading engine
        """
        # Skip HOLD signals
        if signal.action not in [SignalAction.BUY, SignalAction.SELL]:
            return f"No trade executed: signal is {signal.action.value}"

        paper_engine = get_paper_engine()
        risk_manager = get_risk_manager()

        # Extract current price from signal indicators
        current_price = TradingService._extract_current_price(signal)

        # Validate price availability
        if not current_price or current_price == 0:
            return "Cannot execute trade: current price not available in signal"

        # Execute based on signal action
        if signal.action == SignalAction.BUY:
            return await TradingService._execute_buy(
                signal, current_price, paper_engine, risk_manager
            )
        elif signal.action == SignalAction.SELL:
            return await TradingService._execute_sell(
                signal, current_price, paper_engine
            )

    @staticmethod
    def _extract_current_price(signal) -> Optional[Decimal]:
        """
        Extract current price from signal indicators or metadata

        Tries multiple sources in order:
        1. Indicator metadata (EMA, SMA, RSI, MACD, Bollinger)
        2. Signal-level metadata

        Returns:
            Decimal: Current price or None if not found
        """
        # Try to extract from indicators
        for indicator_name in ["EMA", "SMA", "RSI", "MACD", "Bollinger"]:
            indicator = signal.indicators.get(indicator_name)
            if indicator and hasattr(indicator, 'metadata') and indicator.metadata:
                price = indicator.metadata.get("current_price")
                if price:
                    return Decimal(str(price))

        # Fallback: Try signal-level metadata
        if signal.metadata:
            price = signal.metadata.get("current_price") or signal.metadata.get("price")
            if price:
                return Decimal(str(price))

        return None

    @staticmethod
    async def _execute_buy(
        signal,
        current_price: Decimal,
        paper_engine,
        risk_manager
    ) -> str:
        """
        Execute BUY order with risk management

        Steps:
        1. Calculate position size based on account equity
        2. Validate position can be opened
        3. Execute market buy order

        Returns:
            str: Execution result message
        """
        # Calculate position size with risk management
        quantity = risk_manager.calculate_position_size(
            paper_engine.get_total_equity(),
            current_price
        )

        # Validate position opening
        can_open, reason = paper_engine.can_open_position(
            signal.symbol, quantity, current_price
        )
        if not can_open:
            return f"Cannot open position: {reason}"

        # Create and execute buy order
        order = OrderCreate(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=quantity,
            strategy=signal.strategy
        )

        executed_order, error = await paper_engine.execute_market_order(
            order, current_price
        )

        if error:
            return f"Order failed: {error}"

        return f"BUY order executed: {quantity} {signal.symbol} @ {current_price}"

    @staticmethod
    async def _execute_sell(
        signal,
        current_price: Decimal,
        paper_engine
    ) -> str:
        """
        Execute SELL order to close existing position

        Steps:
        1. Find open position for symbol
        2. Create market sell order for position quantity
        3. Execute order to close position

        Returns:
            str: Execution result message
        """
        # Find open position to close
        position_manager = get_position_manager()
        open_positions = [
            pos for pos in position_manager.get_open_positions()
            if pos.symbol == signal.symbol
        ]

        if not open_positions:
            return f"No open position for {signal.symbol} to close"

        # Close first open position
        position = open_positions[0]
        order = OrderCreate(
            symbol=signal.symbol,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=position.quantity,
            position_id=position.id,
            strategy=signal.strategy
        )

        executed_order, error = await paper_engine.execute_market_order(
            order, current_price
        )

        if error:
            return f"Order failed: {error}"

        return f"SELL order executed: {position.quantity} {signal.symbol} @ {current_price}"
