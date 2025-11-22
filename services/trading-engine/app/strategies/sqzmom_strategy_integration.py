"""
SQZMOM Strategy Integration for Trading Engine
Purpose: Connects to Technical Analysis service for SQZMOM signals and executes trades

This module integrates the highly profitable SQZMOM strategy with the Trading Engine,
enabling automated or manual trading on optimized symbols with backtested parameters.

Flow:
1. Get signal from Technical Analysis service
2. Validate signal meets confidence threshold
3. Calculate position size based on risk management
4. Check trading constraints (max positions, risk limits)
5. Execute trade (paper or live)
"""

import httpx
import logging
from typing import Dict, Optional, List
from decimal import Decimal
from datetime import datetime

from app.strategies.sqzmom_config import sqzmom_config

logger = logging.getLogger(__name__)


class SQZMOMStrategy:
    """
    SQZMOM Strategy Implementation for Trading Engine

    This strategy fetches signals from the Technical Analysis service
    and executes trades according to optimized parameters discovered
    through backtesting.

    Key Features:
    - Symbol whitelisting (only profitable symbols)
    - Confidence-based filtering
    - Position size calculation with risk management
    - Max position limits
    - Paper/live trading modes
    - Manual approval option

    Attributes:
        ta_url: Technical Analysis service URL
        config: SQZMOM configuration with optimized parameters
        http_client: Async HTTP client for service communication
    """

    def __init__(self, technical_analysis_url: Optional[str] = None):
        """
        Initialize SQZMOM strategy

        Args:
            technical_analysis_url: Override Technical Analysis service URL
                                  (defaults to config value)
        """
        # Use provided URL or get from config
        self.ta_url = technical_analysis_url or sqzmom_config.technical_analysis_url
        self.config = sqzmom_config

        # Initialize HTTP client with reasonable timeout
        self.http_client = httpx.AsyncClient(timeout=10.0)

        logger.info(
            f"SQZMOM Strategy initialized for symbols: {self.config.enabled_symbols}"
        )
        logger.info(
            f"Parameters: min_momentum={self.config.min_momentum_threshold}, "
            f"SL={self.config.stop_loss_pct}%, TP={self.config.take_profit_pct}%"
        )
        logger.info(
            f"Mode: paper_trading={self.config.paper_trading}, "
            f"auto_trading={self.config.auto_trading}"
        )

    async def get_signal(
        self,
        symbol: str,
        interval: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Get SQZMOM trading signal from Technical Analysis service

        This method fetches a complete trading signal including:
        - Action (BUY/SELL/HOLD)
        - Confidence score
        - Entry price
        - Stop loss price
        - Take profit price
        - Reasoning

        Args:
            symbol: Trading pair (e.g., SOLUSDT)
            interval: Timeframe in minutes (default: from config, typically 60)

        Returns:
            Signal dictionary:
            {
                'symbol': str,
                'interval': str,
                'timestamp': int,
                'action': 'BUY'|'SELL'|'HOLD',
                'confidence': float (0-1),
                'entry_price': float,
                'stop_loss': float,
                'take_profit': float,
                'reason': str,
                'momentum': float,
                'squeeze_state': str,
                'momentum_color': str,
                'strategy_config': dict
            }

            Returns None if:
            - Symbol not in whitelist
            - Service unavailable
            - Error occurred
        """
        # Check if symbol is enabled in whitelist
        if symbol not in self.config.enabled_symbols:
            logger.warning(
                f"Symbol {symbol} not in SQZMOM whitelist {self.config.enabled_symbols}, "
                f"skipping signal fetch"
            )
            return None

        # Use provided interval or default from config
        if interval is None:
            interval = self.config.default_interval

        try:
            # Get symbol-specific config for parameters
            symbol_params = self.config.symbol_config.get(symbol, {})

            # Build request URL with optimized parameters
            url = f"{self.ta_url}/api/v1/strategies/sqzmom/signal/{symbol}"

            # Build query parameters
            params = {
                "interval": interval,
                "min_momentum": self.config.min_momentum_threshold,
                "stop_loss_pct": symbol_params.get(
                    "stop_loss_pct",
                    self.config.stop_loss_pct
                ),
                "take_profit_pct": symbol_params.get(
                    "take_profit_pct",
                    self.config.take_profit_pct
                ),
                "require_squeeze_release": self.config.require_squeeze_release,
                "require_volume": self.config.require_volume_confirmation
            }

            logger.info(f"Fetching SQZMOM signal for {symbol} ({interval}m)")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Request params: {params}")

            # Make HTTP request to Technical Analysis service
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()

            # Parse response
            signal = response.json()

            logger.info(
                f"SQZMOM signal for {symbol}: {signal['action']} "
                f"(confidence: {signal['confidence']:.2f}, "
                f"momentum: {signal.get('momentum', 0):.4f})"
            )
            logger.debug(f"Full signal: {signal}")

            return signal

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching SQZMOM signal for {symbol}: "
                f"{e.response.status_code} - {e.response.text}"
            )
            return None
        except httpx.RequestError as e:
            logger.error(
                f"Request error fetching SQZMOM signal for {symbol}: {e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error fetching SQZMOM signal for {symbol}: {e}",
                exc_info=True
            )
            return None

    async def get_all_signals(self) -> Dict[str, Dict]:
        """
        Get SQZMOM signals for all enabled symbols

        Returns:
            Dictionary mapping symbol to signal:
            {
                'SOLUSDT': {...signal...},
                'DOGEUSDT': {...signal...},
                'BNBUSDT': {...signal...}
            }
        """
        signals = {}

        for symbol in self.config.enabled_symbols:
            signal = await self.get_signal(symbol)
            if signal:
                signals[symbol] = signal
            else:
                logger.warning(f"Failed to get signal for {symbol}")

        logger.info(
            f"Retrieved {len(signals)}/{len(self.config.enabled_symbols)} signals"
        )

        return signals

    async def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        account_balance: float
    ) -> Decimal:
        """
        Calculate position size based on risk management rules

        Uses symbol-specific position size % or default from config.
        Position size is determined as a percentage of total capital,
        not based on risk amount.

        Args:
            symbol: Trading symbol
            entry_price: Entry price for the trade
            stop_loss: Stop loss price
            account_balance: Current account balance

        Returns:
            Decimal: Position quantity in base asset

        Example:
            balance = $10,000
            position_size_pct = 2%
            entry_price = $100
            -> position_value = $200
            -> quantity = 2.0 units
        """
        # Get symbol-specific position size or use default
        symbol_config = self.config.symbol_config.get(symbol, {})
        position_pct = symbol_config.get(
            "position_size_pct",
            self.config.position_size_pct
        )

        # Calculate position value (% of capital)
        position_value = account_balance * (position_pct / 100.0)

        # Calculate quantity
        quantity = Decimal(str(position_value / entry_price))

        # Calculate risk amount and percentage
        risk_per_unit = abs(entry_price - stop_loss)
        risk_amount = float(quantity) * risk_per_unit
        risk_pct = (risk_amount / account_balance) * 100

        logger.info(
            f"Position size calculated for {symbol}:"
        )
        logger.info(f"  Account balance: ${account_balance:,.2f}")
        logger.info(f"  Position size: {position_pct}% = ${position_value:,.2f}")
        logger.info(f"  Entry price: ${entry_price:,.2f}")
        logger.info(f"  Quantity: {quantity}")
        logger.info(f"  Stop loss: ${stop_loss:,.2f}")
        logger.info(f"  Risk amount: ${risk_amount:,.2f} ({risk_pct:.2f}%)")

        return quantity

    async def should_execute_trade(
        self,
        signal: Dict,
        current_positions: int
    ) -> tuple[bool, str]:
        """
        Validate if trade should be executed based on risk rules

        Checks:
        1. Auto-trading enabled
        2. Max positions not exceeded
        3. Signal confidence meets threshold
        4. Action is BUY or SELL (not HOLD)
        5. Symbol-specific confidence threshold

        Args:
            signal: SQZMOM signal dictionary
            current_positions: Number of current open positions

        Returns:
            Tuple of (should_execute: bool, reason: str)
        """
        symbol = signal.get('symbol', 'UNKNOWN')

        # Check if trading is enabled
        if not self.config.auto_trading:
            return False, "Auto-trading disabled, manual approval required"

        # Check max positions
        if current_positions >= self.config.max_positions:
            return False, (
                f"Max positions reached ({current_positions}/"
                f"{self.config.max_positions})"
            )

        # Check action is BUY or SELL (not HOLD)
        action = signal.get('action', 'HOLD')
        if action == 'HOLD':
            return False, "Signal action is HOLD"

        # Check signal confidence (symbol-specific or default)
        confidence = signal.get('confidence', 0.0)
        symbol_config = self.config.symbol_config.get(symbol, {})
        min_confidence = symbol_config.get(
            'min_confidence',
            self.config.min_confidence
        )

        if confidence < min_confidence:
            return False, (
                f"Signal confidence too low: {confidence:.2f} < "
                f"{min_confidence:.2f}"
            )

        # All checks passed
        return True, "All validation checks passed"

    def get_symbol_config(self, symbol: str) -> Dict:
        """
        Get complete configuration for a specific symbol

        Merges default config with symbol-specific overrides.

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with all config parameters for the symbol
        """
        # Start with defaults
        config = {
            'position_size_pct': self.config.position_size_pct,
            'stop_loss_pct': self.config.stop_loss_pct,
            'take_profit_pct': self.config.take_profit_pct,
            'min_confidence': self.config.min_confidence,
            'description': f"Default SQZMOM configuration"
        }

        # Override with symbol-specific config if exists
        symbol_config = self.config.symbol_config.get(symbol, {})
        config.update(symbol_config)

        return config

    def get_enabled_symbols(self) -> List[str]:
        """Get list of enabled symbols"""
        return self.config.enabled_symbols.copy()

    def is_symbol_enabled(self, symbol: str) -> bool:
        """Check if symbol is enabled for trading"""
        return symbol in self.config.enabled_symbols

    def get_strategy_info(self) -> Dict:
        """
        Get complete strategy information

        Returns:
            Dictionary with strategy configuration, enabled symbols,
            and current state
        """
        return {
            'name': 'SQZMOM',
            'description': 'Squeeze Momentum strategy with optimized parameters',
            'version': '1.0.0',
            'enabled_symbols': self.config.enabled_symbols,
            'paper_trading': self.config.paper_trading,
            'auto_trading': self.config.auto_trading,
            'max_positions': self.config.max_positions,
            'parameters': {
                'bb_length': self.config.bb_length,
                'kc_length': self.config.kc_length,
                'min_momentum_threshold': self.config.min_momentum_threshold,
                'stop_loss_pct': self.config.stop_loss_pct,
                'take_profit_pct': self.config.take_profit_pct,
                'require_squeeze_release': self.config.require_squeeze_release,
                'require_volume_confirmation': self.config.require_volume_confirmation,
                'min_confidence': self.config.min_confidence
            },
            'symbol_configs': self.config.symbol_config,
            'backtesting_results': {
                'SOLUSDT': '+2,706% (22% WR, 4.76 Sharpe)',
                'DOGEUSDT': '+630% (28% WR, 5.41 Sharpe)',
                'BNBUSDT': '+330% (31% WR)'
            }
        }

    async def close(self):
        """Close HTTP client and cleanup resources"""
        await self.http_client.aclose()
        logger.info("SQZMOM Strategy closed")


# Initialize singleton strategy instance
sqzmom_strategy = SQZMOMStrategy()
