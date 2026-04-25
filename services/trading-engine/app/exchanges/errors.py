"""
Exchange Errors Module - Phase 6: Multi-Exchange Support
Purpose: Unified exception hierarchy for all exchange adapters

This module defines a comprehensive exception hierarchy that provides:
- Exchange-agnostic error handling across all supported exchanges
- Detailed error context including exchange-specific error codes
- Rate limiting and retry information
- Error categorization for automated recovery decisions

Exception Hierarchy:
    ExchangeError (base)
    +-- ConnectionError
    |   +-- TimeoutError
    |   +-- NetworkError
    +-- AuthenticationError
    |   +-- InvalidAPIKeyError
    |   +-- InvalidSignatureError
    |   +-- PermissionDeniedError
    +-- RateLimitError
    +-- ValidationError
    |   +-- InvalidSymbolError
    |   +-- InvalidQuantityError
    |   +-- InvalidPriceError
    +-- OrderError
    |   +-- OrderNotFoundError
    |   +-- OrderAlreadyCancelledError
    |   +-- InsufficientBalanceError
    |   +-- OrderRejectedError
    +-- MarketDataError
    |   +-- SymbolNotFoundError
    |   +-- DataUnavailableError
    +-- ExchangeMaintenanceError

Created: 2025-12-11
Author: Backend Developer Agent
"""

from typing import Optional, Dict, Any
from enum import Enum


# ============================================================================
# ERROR CODES ENUMERATION
# ============================================================================

class ExchangeErrorCode(str, Enum):
    """
    Standardized error codes across all exchanges

    Each exchange adapter maps its native error codes to these unified codes
    for consistent error handling throughout the trading engine.
    """
    # Connection Errors (1xxx)
    CONNECTION_FAILED = "ERR_1001"
    CONNECTION_TIMEOUT = "ERR_1002"
    NETWORK_ERROR = "ERR_1003"
    WEBSOCKET_ERROR = "ERR_1004"

    # Authentication Errors (2xxx)
    AUTH_FAILED = "ERR_2001"
    INVALID_API_KEY = "ERR_2002"
    INVALID_SIGNATURE = "ERR_2003"
    EXPIRED_TIMESTAMP = "ERR_2004"
    PERMISSION_DENIED = "ERR_2005"
    IP_NOT_WHITELISTED = "ERR_2006"

    # Rate Limiting (3xxx)
    RATE_LIMIT_EXCEEDED = "ERR_3001"
    ORDER_RATE_LIMIT = "ERR_3002"
    REQUEST_WEIGHT_EXCEEDED = "ERR_3003"

    # Validation Errors (4xxx)
    INVALID_PARAMETER = "ERR_4001"
    INVALID_SYMBOL = "ERR_4002"
    INVALID_QUANTITY = "ERR_4003"
    INVALID_PRICE = "ERR_4004"
    INVALID_SIDE = "ERR_4005"
    INVALID_ORDER_TYPE = "ERR_4006"
    QUANTITY_TOO_SMALL = "ERR_4007"
    QUANTITY_TOO_LARGE = "ERR_4008"
    PRICE_OUT_OF_RANGE = "ERR_4009"

    # Order Errors (5xxx)
    ORDER_NOT_FOUND = "ERR_5001"
    ORDER_ALREADY_CANCELLED = "ERR_5002"
    ORDER_ALREADY_FILLED = "ERR_5003"
    ORDER_REJECTED = "ERR_5004"
    INSUFFICIENT_BALANCE = "ERR_5005"
    POSITION_NOT_FOUND = "ERR_5006"
    REDUCE_ONLY_VIOLATION = "ERR_5007"
    POST_ONLY_WOULD_TAKE = "ERR_5008"

    # Market Data Errors (6xxx)
    SYMBOL_NOT_FOUND = "ERR_6001"
    DATA_UNAVAILABLE = "ERR_6002"
    INVALID_INTERVAL = "ERR_6003"
    HISTORICAL_DATA_LIMIT = "ERR_6004"

    # Exchange System Errors (7xxx)
    EXCHANGE_MAINTENANCE = "ERR_7001"
    EXCHANGE_OVERLOADED = "ERR_7002"
    TRADING_HALTED = "ERR_7003"
    MARKET_CLOSED = "ERR_7004"

    # Internal Errors (9xxx)
    UNKNOWN_ERROR = "ERR_9001"
    ADAPTER_ERROR = "ERR_9002"
    SERIALIZATION_ERROR = "ERR_9003"


# ============================================================================
# HELPER FUNCTION
# ============================================================================

def _get_details(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely extract details from kwargs, ensuring a dict is returned

    Args:
        kwargs: Keyword arguments dict

    Returns:
        Details dict (never None)
    """
    details = kwargs.pop("details", None)
    return details if details is not None else {}


# ============================================================================
# BASE EXCEPTION
# ============================================================================

class ExchangeError(Exception):
    """
    Base exception for all exchange-related errors

    All exchange adapters should raise exceptions that inherit from this class.
    This allows the trading engine to catch exchange errors uniformly while
    still distinguishing between different error types.

    Attributes:
        message: Human-readable error description
        error_code: Unified error code (ExchangeErrorCode)
        exchange: Name of the exchange that raised the error
        native_code: Original error code from the exchange API
        native_message: Original error message from the exchange API
        details: Additional context about the error
        retryable: Whether the operation can be retried
        retry_after: Suggested wait time before retry (seconds)

    Example:
        try:
            await exchange.place_order(order)
        except ExchangeError as e:
            logger.error(f"[{e.exchange}] {e.error_code}: {e.message}")
            if e.retryable:
                await asyncio.sleep(e.retry_after or 5)
                # Retry logic
    """

    def __init__(
        self,
        message: str,
        error_code: ExchangeErrorCode = ExchangeErrorCode.UNKNOWN_ERROR,
        exchange: Optional[str] = None,
        native_code: Optional[str] = None,
        native_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
        retry_after: Optional[int] = None
    ):
        """
        Initialize exchange exception

        Args:
            message: Human-readable error description
            error_code: Unified error code from ExchangeErrorCode enum
            exchange: Name of the exchange (e.g., "bybit", "binance")
            native_code: Original error code from exchange API
            native_message: Original error message from exchange API
            details: Additional error context dictionary
            retryable: Whether the operation can be safely retried
            retry_after: Suggested wait time in seconds before retry
        """
        # Store all error attributes
        self.message = message
        self.error_code = error_code
        self.exchange = exchange
        self.native_code = native_code
        self.native_message = native_message
        self.details = details if details is not None else {}
        self.retryable = retryable
        self.retry_after = retry_after

        # Build full error message for exception
        full_message = self._build_message()
        super().__init__(full_message)

    def _build_message(self) -> str:
        """
        Build formatted error message

        Returns:
            Formatted error string with all relevant context
        """
        # Start with basic message
        parts = []

        # Add exchange name if available
        if self.exchange:
            parts.append(f"[{self.exchange.upper()}]")

        # Add error code
        parts.append(f"[{self.error_code.value}]")

        # Add main message
        parts.append(self.message)

        # Add native error info if different from message
        if self.native_message and self.native_message != self.message:
            parts.append(f"(Native: {self.native_code}: {self.native_message})")

        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary for serialization

        Returns:
            Dictionary containing all error information
        """
        return {
            "message": self.message,
            "error_code": self.error_code.value,
            "exchange": self.exchange,
            "native_code": self.native_code,
            "native_message": self.native_message,
            "details": self.details,
            "retryable": self.retryable,
            "retry_after": self.retry_after
        }

    def __repr__(self) -> str:
        """Return detailed string representation"""
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code.value}, "
            f"exchange={self.exchange!r}, "
            f"retryable={self.retryable})"
        )


# ============================================================================
# CONNECTION ERRORS
# ============================================================================

class ConnectionError(ExchangeError):
    """
    Exception raised for connection-related issues

    This includes network failures, DNS resolution errors,
    and connection refused scenarios.
    """

    def __init__(
        self,
        message: str = "Connection to exchange failed",
        exchange: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code=ExchangeErrorCode.CONNECTION_FAILED,
            exchange=exchange,
            retryable=True,
            retry_after=5,
            **kwargs
        )


class TimeoutError(ConnectionError):
    """
    Exception raised when request times out

    Includes both connect timeouts and read timeouts.
    Generally retryable with exponential backoff.
    """

    def __init__(
        self,
        message: str = "Request timed out",
        exchange: Optional[str] = None,
        timeout_type: str = "read",  # "connect", "read", "total"
        timeout_seconds: Optional[float] = None,
        **kwargs
    ):
        # Add timeout details - use helper to safely get dict
        details = _get_details(kwargs)
        details["timeout_type"] = timeout_type
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds

        super().__init__(
            message=message,
            exchange=exchange,
            details=details,
            **kwargs
        )
        # Override error code
        self.error_code = ExchangeErrorCode.CONNECTION_TIMEOUT


class NetworkError(ConnectionError):
    """
    Exception raised for network-level errors

    Includes SSL errors, DNS failures, and other transport issues.
    """

    def __init__(
        self,
        message: str = "Network error occurred",
        exchange: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message=message, exchange=exchange, **kwargs)
        self.error_code = ExchangeErrorCode.NETWORK_ERROR


# ============================================================================
# AUTHENTICATION ERRORS
# ============================================================================

class AuthenticationError(ExchangeError):
    """
    Base exception for authentication failures

    Not retryable as credentials/signatures need to be fixed.
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        exchange: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code=ExchangeErrorCode.AUTH_FAILED,
            exchange=exchange,
            retryable=False,
            **kwargs
        )


class InvalidAPIKeyError(AuthenticationError):
    """Exception raised when API key is invalid or expired"""

    def __init__(
        self,
        message: str = "Invalid or expired API key",
        exchange: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message=message, exchange=exchange, **kwargs)
        self.error_code = ExchangeErrorCode.INVALID_API_KEY


class InvalidSignatureError(AuthenticationError):
    """Exception raised when request signature is invalid"""

    def __init__(
        self,
        message: str = "Invalid request signature",
        exchange: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message=message, exchange=exchange, **kwargs)
        self.error_code = ExchangeErrorCode.INVALID_SIGNATURE


class PermissionDeniedError(AuthenticationError):
    """Exception raised when API key lacks required permissions"""

    def __init__(
        self,
        message: str = "API key lacks required permissions",
        exchange: Optional[str] = None,
        required_permission: Optional[str] = None,
        **kwargs
    ):
        details = _get_details(kwargs)
        if required_permission:
            details["required_permission"] = required_permission

        super().__init__(message=message, exchange=exchange, details=details, **kwargs)
        self.error_code = ExchangeErrorCode.PERMISSION_DENIED


# ============================================================================
# RATE LIMITING ERRORS
# ============================================================================

class RateLimitError(ExchangeError):
    """
    Exception raised when rate limit is exceeded

    Always retryable after the specified cooldown period.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        exchange: Optional[str] = None,
        retry_after: int = 60,
        limit_type: str = "request",  # "request", "order", "weight"
        current_usage: Optional[int] = None,
        max_allowed: Optional[int] = None,
        **kwargs
    ):
        # Build details - use helper to safely get dict
        details = _get_details(kwargs)
        details["limit_type"] = limit_type
        if current_usage is not None:
            details["current_usage"] = current_usage
        if max_allowed is not None:
            details["max_allowed"] = max_allowed

        super().__init__(
            message=message,
            error_code=ExchangeErrorCode.RATE_LIMIT_EXCEEDED,
            exchange=exchange,
            retryable=True,
            retry_after=retry_after,
            details=details,
            **kwargs
        )

        # Store rate limit specific attributes
        self.limit_type = limit_type
        self.current_usage = current_usage
        self.max_allowed = max_allowed


# ============================================================================
# VALIDATION ERRORS
# ============================================================================

class ValidationError(ExchangeError):
    """
    Base exception for input validation failures

    Not automatically retryable as parameters need correction.
    """

    def __init__(
        self,
        message: str = "Validation failed",
        exchange: Optional[str] = None,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs
    ):
        details = _get_details(kwargs)
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)

        super().__init__(
            message=message,
            error_code=ExchangeErrorCode.INVALID_PARAMETER,
            exchange=exchange,
            retryable=False,
            details=details,
            **kwargs
        )

        self.field = field
        self.value = value


class InvalidSymbolError(ValidationError):
    """Exception raised when trading symbol is invalid"""

    def __init__(
        self,
        symbol: str,
        exchange: Optional[str] = None,
        available_symbols: Optional[list] = None,
        **kwargs
    ):
        message = f"Invalid trading symbol: {symbol}"
        details = _get_details(kwargs)
        if available_symbols:
            details["available_symbols"] = available_symbols[:10]  # Limit to first 10

        super().__init__(
            message=message,
            exchange=exchange,
            field="symbol",
            value=symbol,
            details=details,
            **kwargs
        )
        self.error_code = ExchangeErrorCode.INVALID_SYMBOL


class InvalidQuantityError(ValidationError):
    """Exception raised when order quantity is invalid"""

    def __init__(
        self,
        quantity: Any,
        exchange: Optional[str] = None,
        min_quantity: Optional[float] = None,
        max_quantity: Optional[float] = None,
        step_size: Optional[float] = None,
        **kwargs
    ):
        message = f"Invalid quantity: {quantity}"
        details = _get_details(kwargs)
        if min_quantity is not None:
            details["min_quantity"] = min_quantity
        if max_quantity is not None:
            details["max_quantity"] = max_quantity
        if step_size is not None:
            details["step_size"] = step_size

        super().__init__(
            message=message,
            exchange=exchange,
            field="quantity",
            value=quantity,
            details=details,
            **kwargs
        )
        self.error_code = ExchangeErrorCode.INVALID_QUANTITY


class InvalidPriceError(ValidationError):
    """Exception raised when order price is invalid"""

    def __init__(
        self,
        price: Any,
        exchange: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        tick_size: Optional[float] = None,
        **kwargs
    ):
        message = f"Invalid price: {price}"
        details = _get_details(kwargs)
        if min_price is not None:
            details["min_price"] = min_price
        if max_price is not None:
            details["max_price"] = max_price
        if tick_size is not None:
            details["tick_size"] = tick_size

        super().__init__(
            message=message,
            exchange=exchange,
            field="price",
            value=price,
            details=details,
            **kwargs
        )
        self.error_code = ExchangeErrorCode.INVALID_PRICE


# ============================================================================
# ORDER ERRORS
# ============================================================================

class OrderError(ExchangeError):
    """Base exception for order-related errors"""

    def __init__(
        self,
        message: str = "Order error",
        exchange: Optional[str] = None,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        **kwargs
    ):
        details = _get_details(kwargs)
        if order_id:
            details["order_id"] = order_id
        if client_order_id:
            details["client_order_id"] = client_order_id

        super().__init__(
            message=message,
            error_code=ExchangeErrorCode.ORDER_REJECTED,
            exchange=exchange,
            retryable=False,
            details=details,
            **kwargs
        )

        self.order_id = order_id
        self.client_order_id = client_order_id


class OrderNotFoundError(OrderError):
    """Exception raised when order cannot be found"""

    def __init__(
        self,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        exchange: Optional[str] = None,
        **kwargs
    ):
        identifier = order_id or client_order_id or "unknown"
        message = f"Order not found: {identifier}"

        super().__init__(
            message=message,
            exchange=exchange,
            order_id=order_id,
            client_order_id=client_order_id,
            **kwargs
        )
        self.error_code = ExchangeErrorCode.ORDER_NOT_FOUND


class OrderAlreadyCancelledError(OrderError):
    """Exception raised when trying to cancel an already cancelled order"""

    def __init__(
        self,
        order_id: Optional[str] = None,
        exchange: Optional[str] = None,
        **kwargs
    ):
        message = f"Order already cancelled: {order_id or 'unknown'}"

        super().__init__(
            message=message,
            exchange=exchange,
            order_id=order_id,
            **kwargs
        )
        self.error_code = ExchangeErrorCode.ORDER_ALREADY_CANCELLED


class InsufficientBalanceError(OrderError):
    """Exception raised when account has insufficient balance"""

    def __init__(
        self,
        exchange: Optional[str] = None,
        required: Optional[float] = None,
        available: Optional[float] = None,
        asset: str = "USDT",
        **kwargs
    ):
        message = f"Insufficient {asset} balance"
        if required is not None and available is not None:
            message = f"Insufficient {asset} balance. Required: {required}, Available: {available}"

        details = _get_details(kwargs)
        details["asset"] = asset
        if required is not None:
            details["required"] = required
        if available is not None:
            details["available"] = available

        super().__init__(
            message=message,
            exchange=exchange,
            details=details,
            **kwargs
        )
        self.error_code = ExchangeErrorCode.INSUFFICIENT_BALANCE

        self.required = required
        self.available = available
        self.asset = asset


class OrderRejectedError(OrderError):
    """Exception raised when order is rejected by exchange"""

    def __init__(
        self,
        reason: str = "Order rejected by exchange",
        exchange: Optional[str] = None,
        order_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=reason,
            exchange=exchange,
            order_id=order_id,
            **kwargs
        )
        self.error_code = ExchangeErrorCode.ORDER_REJECTED


# ============================================================================
# MARKET DATA ERRORS
# ============================================================================

class MarketDataError(ExchangeError):
    """Base exception for market data retrieval errors"""

    def __init__(
        self,
        message: str = "Market data error",
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        **kwargs
    ):
        details = _get_details(kwargs)
        if symbol:
            details["symbol"] = symbol

        super().__init__(
            message=message,
            error_code=ExchangeErrorCode.DATA_UNAVAILABLE,
            exchange=exchange,
            retryable=True,
            retry_after=5,
            details=details,
            **kwargs
        )

        self.symbol = symbol


class SymbolNotFoundError(MarketDataError):
    """Exception raised when symbol is not found on exchange"""

    def __init__(
        self,
        symbol: str,
        exchange: Optional[str] = None,
        **kwargs
    ):
        message = f"Symbol not found: {symbol}"

        super().__init__(
            message=message,
            exchange=exchange,
            symbol=symbol,
            retryable=False,
            **kwargs
        )
        self.error_code = ExchangeErrorCode.SYMBOL_NOT_FOUND


class DataUnavailableError(MarketDataError):
    """Exception raised when market data is temporarily unavailable"""

    def __init__(
        self,
        data_type: str = "market data",
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        **kwargs
    ):
        message = f"{data_type.capitalize()} temporarily unavailable"
        if symbol:
            message += f" for {symbol}"

        details = _get_details(kwargs)
        details["data_type"] = data_type

        super().__init__(
            message=message,
            exchange=exchange,
            symbol=symbol,
            details=details,
            **kwargs
        )


# ============================================================================
# EXCHANGE SYSTEM ERRORS
# ============================================================================

class ExchangeMaintenanceError(ExchangeError):
    """Exception raised when exchange is under maintenance"""

    def __init__(
        self,
        exchange: Optional[str] = None,
        estimated_end: Optional[str] = None,
        maintenance_type: str = "scheduled",
        **kwargs
    ):
        message = "Exchange is under maintenance"
        if estimated_end:
            message += f". Estimated end: {estimated_end}"

        details = _get_details(kwargs)
        details["maintenance_type"] = maintenance_type
        if estimated_end:
            details["estimated_end"] = estimated_end

        super().__init__(
            message=message,
            error_code=ExchangeErrorCode.EXCHANGE_MAINTENANCE,
            exchange=exchange,
            retryable=True,
            retry_after=300,  # 5 minutes default
            details=details,
            **kwargs
        )


# ============================================================================
# ERROR CODE MAPPING UTILITIES
# ============================================================================

# Bybit error code mapping to unified error codes
BYBIT_ERROR_MAP: Dict[int, type] = {
    # Authentication errors
    10001: InvalidAPIKeyError,
    10003: InvalidSignatureError,
    10004: AuthenticationError,  # Invalid timestamp
    10005: PermissionDeniedError,
    10006: RateLimitError,

    # Validation errors
    110001: ValidationError,
    110003: InvalidQuantityError,
    110004: InsufficientBalanceError,
    110007: OrderNotFoundError,
    110043: OrderAlreadyCancelledError,

    # Market errors
    10010: InvalidSymbolError,
    100028: SymbolNotFoundError,

    # System errors
    10016: ExchangeMaintenanceError,
}


def map_bybit_error(
    ret_code: int,
    ret_msg: str,
    details: Optional[Dict[str, Any]] = None
) -> ExchangeError:
    """
    Map Bybit error code to unified exception

    Args:
        ret_code: Bybit API return code
        ret_msg: Bybit API return message
        details: Additional context

    Returns:
        Appropriate ExchangeError subclass instance
    """
    # Ensure details is a dict
    details = details if details is not None else {}

    # Get exception class from mapping
    exception_class = BYBIT_ERROR_MAP.get(ret_code, ExchangeError)

    # Handle special cases
    if ret_code == 10006:  # Rate limit
        return RateLimitError(
            exchange="bybit",
            native_code=str(ret_code),
            native_message=ret_msg,
            details=details.copy() if details else None
        )
    elif ret_code == 110004:  # Insufficient balance
        return InsufficientBalanceError(
            exchange="bybit",
            required=details.get("required") if details else None,
            available=details.get("available") if details else None,
            native_code=str(ret_code),
            native_message=ret_msg,
            details=details.copy() if details else None
        )
    elif exception_class in (InvalidAPIKeyError, InvalidSignatureError, PermissionDeniedError):
        return exception_class(
            exchange="bybit",
            native_code=str(ret_code),
            native_message=ret_msg,
            details=details.copy() if details else None
        )
    elif exception_class == OrderNotFoundError:
        return OrderNotFoundError(
            order_id=details.get("order_id") if details else None,
            exchange="bybit",
            native_code=str(ret_code),
            native_message=ret_msg,
            details=details.copy() if details else None
        )
    else:
        # Default mapping
        return ExchangeError(
            message=ret_msg or "Unknown Bybit error",
            error_code=ExchangeErrorCode.UNKNOWN_ERROR,
            exchange="bybit",
            native_code=str(ret_code),
            native_message=ret_msg,
            details=details.copy() if details else None
        )


__all__ = [
    # Error codes
    "ExchangeErrorCode",

    # Base exception
    "ExchangeError",

    # Connection errors
    "ConnectionError",
    "TimeoutError",
    "NetworkError",

    # Authentication errors
    "AuthenticationError",
    "InvalidAPIKeyError",
    "InvalidSignatureError",
    "PermissionDeniedError",

    # Rate limiting
    "RateLimitError",

    # Validation errors
    "ValidationError",
    "InvalidSymbolError",
    "InvalidQuantityError",
    "InvalidPriceError",

    # Order errors
    "OrderError",
    "OrderNotFoundError",
    "OrderAlreadyCancelledError",
    "InsufficientBalanceError",
    "OrderRejectedError",

    # Market data errors
    "MarketDataError",
    "SymbolNotFoundError",
    "DataUnavailableError",

    # System errors
    "ExchangeMaintenanceError",

    # Mapping utilities
    "BYBIT_ERROR_MAP",
    "map_bybit_error",
]
