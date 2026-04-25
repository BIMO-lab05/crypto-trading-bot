"""
Input Validation Module
=======================
Comprehensive input validation for trading API requests.

Features:
- Symbol whitelist validation (BTCUSDT, ETHUSDT, etc.)
- Quantity and price bounds checking
- Request size limits
- SQL injection prevention
- Numeric input validation

Security Rules:
- Only whitelisted trading symbols allowed
- Quantity: 0.0001 - 1000000 units
- Price: $0.00000001 - $1,000,000
- Request body size: Max 1MB

Version: 1.0.0
Created: 2025-12-12
"""

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any, Set

from fastapi import HTTPException, status
from pydantic import BaseModel, field_validator, ConfigDict


# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# ALLOWED SYMBOLS WHITELIST
# ============================================================================

ALLOWED_SYMBOLS: Set[str] = {
    # Major pairs (Tier 1 - High liquidity)
    "BTCUSDT",      # Bitcoin
    "ETHUSDT",      # Ethereum
    "BNBUSDT",      # Binance Coin
    "SOLUSDT",      # Solana
    "XRPUSDT",      # XRP
    "ADAUSDT",      # Cardano
    "DOGEUSDT",     # Dogecoin
    "DOTUSDT",      # Polkadot
    "MATICUSDT",    # Polygon
    "AVAXUSDT",     # Avalanche
    "LINKUSDT",     # Chainlink
    "ATOMUSDT",     # Cosmos
    "LTCUSDT",      # Litecoin
    "UNIUSDT",      # Uniswap
    "AAVEUSDT",     # Aave

    # Popular altcoins (Tier 2)
    "ARBUSDT",      # Arbitrum
    "OPUSDT",       # Optimism
    "APTUSDT",      # Aptos
    "SUIUSDT",      # Sui
    "SEIUSDT",      # Sei
    "TIAUSDT",      # Celestia
    "NEARUSDT",     # Near Protocol
    "FTMUSDT",      # Fantom
    "ALGOUSDT",     # Algorand
    "ICPUSDT",      # Internet Computer
    "FILUSDT",      # Filecoin
    "INJUSDT",      # Injective
    "STXUSDT",      # Stacks
    "IMXUSDT",      # Immutable X
    "RENDERUSDT",   # Render
    "GRTUSDT",      # The Graph
    "SANDUSDT",     # The Sandbox
    "MANAUSDT",     # Decentraland
    "AXSUSDT",      # Axie Infinity
    "APEUSDT",      # ApeCoin

    # Perpetual futures (common)
    "BTCUSD",       # BTC inverse perpetual
    "ETHUSD",       # ETH inverse perpetual
    "BTCPERP",      # BTC perpetual
    "ETHPERP",      # ETH perpetual
}


# ============================================================================
# VALIDATION BOUNDS
# ============================================================================

@dataclass
class ValidationBounds:
    """
    Validation bounds for trading parameters.

    These limits are set to prevent erroneous orders while allowing
    legitimate trading activity across all supported pairs.
    """
    # Quantity limits (in base asset units)
    min_quantity: Decimal = Decimal("0.0001")      # 0.0001 units minimum
    max_quantity: Decimal = Decimal("1000000")     # 1M units maximum

    # Price limits (in USDT)
    min_price: Decimal = Decimal("0.00000001")     # 1 satoshi minimum
    max_price: Decimal = Decimal("1000000")        # $1M maximum

    # Percentage limits
    min_percentage: Decimal = Decimal("0.01")      # 0.01% minimum
    max_percentage: Decimal = Decimal("100")       # 100% maximum

    # String length limits
    max_symbol_length: int = 20                    # Max symbol length
    max_string_length: int = 200                   # Max general string length
    max_request_body_size: int = 1048576           # 1MB max request size

    # Integer limits
    max_limit: int = 1000                          # Max items in list requests
    max_hours: int = 8760                          # Max hours (1 year)


# Default validation bounds
DEFAULT_BOUNDS = ValidationBounds()


# ============================================================================
# VALIDATION EXCEPTION
# ============================================================================

class ValidationError(HTTPException):
    """
    Custom exception for validation errors.

    Provides detailed error information for API responses.
    """

    def __init__(
        self,
        field: str,
        message: str,
        value: Any = None,
        allowed_values: Optional[List[Any]] = None
    ):
        """
        Initialize validation error.

        Args:
            field: Name of the field that failed validation
            message: Human-readable error message
            value: The invalid value (sanitized for logging)
            allowed_values: List of allowed values if applicable
        """
        detail = {
            "error": "validation_error",
            "field": field,
            "message": message,
        }

        if value is not None:
            # Sanitize value for logging (truncate long strings)
            str_value = str(value)[:100]
            detail["provided_value"] = str_value

        if allowed_values is not None:
            # Limit shown values for large lists
            if len(allowed_values) > 10:
                detail["allowed_values"] = allowed_values[:10] + ["..."]
            else:
                detail["allowed_values"] = allowed_values

        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

        # Log validation failure
        logger.warning(
            f"Validation failed: field={field}, message={message}, "
            f"value={str(value)[:50] if value else 'None'}"
        )


# ============================================================================
# SQL INJECTION PREVENTION
# ============================================================================

# Patterns that indicate potential SQL injection attempts
SQL_INJECTION_PATTERNS: List[str] = [
    r"(\s|;|'|\"|--|\bOR\b|\bAND\b|\bUNION\b|\bSELECT\b|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b)",
    r"(;|\-\-|\/\*|\*\/|xp_|sp_|0x)",
    r"(\%27|\%22|\%3B|\%2D\%2D)",  # URL encoded
]


def check_sql_injection(value: str, field_name: str) -> None:
    """
    Check if a string value contains potential SQL injection patterns.

    Args:
        value: String value to check
        field_name: Name of the field for error reporting

    Raises:
        ValidationError: If SQL injection pattern is detected
    """
    if not isinstance(value, str):
        return

    value_upper = value.upper()

    # Check for common SQL keywords in suspicious patterns
    suspicious_keywords = [
        "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "DROP ",
        "UNION ", " OR ", " AND ", "--", "/*", "*/",
        "EXEC ", "EXECUTE ", "XP_", "SP_",
    ]

    for keyword in suspicious_keywords:
        if keyword in value_upper:
            logger.error(
                f"Potential SQL injection detected: field={field_name}, "
                f"pattern={keyword}, value_snippet={value[:50]}"
            )
            raise ValidationError(
                field=field_name,
                message="Invalid characters detected in input",
                value=None  # Don't expose the malicious input
            )


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_symbol(symbol: str, field_name: str = "symbol") -> str:
    """
    Validate trading symbol against whitelist.

    Args:
        symbol: Trading symbol to validate
        field_name: Field name for error messages

    Returns:
        Validated symbol (uppercase, stripped)

    Raises:
        ValidationError: If symbol is invalid or not whitelisted
    """
    if not symbol:
        raise ValidationError(
            field=field_name,
            message="Symbol is required"
        )

    if not isinstance(symbol, str):
        raise ValidationError(
            field=field_name,
            message="Symbol must be a string",
            value=type(symbol).__name__
        )

    # Normalize: uppercase and strip whitespace
    symbol = symbol.upper().strip()

    # Check length
    if len(symbol) > DEFAULT_BOUNDS.max_symbol_length:
        raise ValidationError(
            field=field_name,
            message=f"Symbol too long (max {DEFAULT_BOUNDS.max_symbol_length} characters)",
            value=symbol
        )

    # Check for SQL injection
    check_sql_injection(symbol, field_name)

    # Validate format: only alphanumeric characters
    if not re.match(r"^[A-Z0-9]+$", symbol):
        raise ValidationError(
            field=field_name,
            message="Symbol must contain only alphanumeric characters",
            value=symbol
        )

    # Check whitelist
    if symbol not in ALLOWED_SYMBOLS:
        raise ValidationError(
            field=field_name,
            message=f"Symbol '{symbol}' is not in the allowed trading pairs",
            value=symbol,
            allowed_values=sorted(list(ALLOWED_SYMBOLS))[:20]
        )

    return symbol


def validate_quantity(
    quantity: Any,
    field_name: str = "quantity",
    min_qty: Optional[Decimal] = None,
    max_qty: Optional[Decimal] = None
) -> Decimal:
    """
    Validate trade quantity.

    Args:
        quantity: Quantity value to validate
        field_name: Field name for error messages
        min_qty: Minimum allowed quantity (default: 0.0001)
        max_qty: Maximum allowed quantity (default: 1,000,000)

    Returns:
        Validated quantity as Decimal

    Raises:
        ValidationError: If quantity is invalid
    """
    min_qty = min_qty or DEFAULT_BOUNDS.min_quantity
    max_qty = max_qty or DEFAULT_BOUNDS.max_quantity

    if quantity is None:
        raise ValidationError(
            field=field_name,
            message="Quantity is required"
        )

    # Convert to Decimal
    try:
        if isinstance(quantity, str):
            # Check for SQL injection in string input
            check_sql_injection(quantity, field_name)
            qty = Decimal(quantity.strip())
        elif isinstance(quantity, (int, float)):
            qty = Decimal(str(quantity))
        elif isinstance(quantity, Decimal):
            qty = quantity
        else:
            raise ValidationError(
                field=field_name,
                message="Quantity must be a number",
                value=type(quantity).__name__
            )
    except InvalidOperation:
        raise ValidationError(
            field=field_name,
            message="Invalid quantity format",
            value=str(quantity)[:50]
        )

    # Check for negative or zero
    if qty <= 0:
        raise ValidationError(
            field=field_name,
            message="Quantity must be positive",
            value=str(qty)
        )

    # Check bounds
    if qty < min_qty:
        raise ValidationError(
            field=field_name,
            message=f"Quantity too small (minimum: {min_qty})",
            value=str(qty)
        )

    if qty > max_qty:
        raise ValidationError(
            field=field_name,
            message=f"Quantity too large (maximum: {max_qty})",
            value=str(qty)
        )

    # Check decimal places (max 8 decimal places for crypto)
    if qty.as_tuple().exponent < -8:
        raise ValidationError(
            field=field_name,
            message="Quantity has too many decimal places (max 8)",
            value=str(qty)
        )

    return qty


def validate_price(
    price: Any,
    field_name: str = "price",
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None
) -> Decimal:
    """
    Validate trade price.

    Args:
        price: Price value to validate
        field_name: Field name for error messages
        min_price: Minimum allowed price (default: 0.00000001)
        max_price: Maximum allowed price (default: 1,000,000)

    Returns:
        Validated price as Decimal

    Raises:
        ValidationError: If price is invalid
    """
    min_price = min_price or DEFAULT_BOUNDS.min_price
    max_price = max_price or DEFAULT_BOUNDS.max_price

    if price is None:
        raise ValidationError(
            field=field_name,
            message="Price is required"
        )

    # Convert to Decimal
    try:
        if isinstance(price, str):
            # Check for SQL injection in string input
            check_sql_injection(price, field_name)
            p = Decimal(price.strip())
        elif isinstance(price, (int, float)):
            p = Decimal(str(price))
        elif isinstance(price, Decimal):
            p = price
        else:
            raise ValidationError(
                field=field_name,
                message="Price must be a number",
                value=type(price).__name__
            )
    except InvalidOperation:
        raise ValidationError(
            field=field_name,
            message="Invalid price format",
            value=str(price)[:50]
        )

    # Check for negative or zero
    if p <= 0:
        raise ValidationError(
            field=field_name,
            message="Price must be positive",
            value=str(p)
        )

    # Check bounds
    if p < min_price:
        raise ValidationError(
            field=field_name,
            message=f"Price too small (minimum: {min_price})",
            value=str(p)
        )

    if p > max_price:
        raise ValidationError(
            field=field_name,
            message=f"Price too large (maximum: {max_price})",
            value=str(p)
        )

    return p


def validate_interval(interval: str, field_name: str = "interval") -> str:
    """
    Validate candlestick interval.

    Args:
        interval: Interval string (e.g., "1", "5", "15", "60", "240", "D")
        field_name: Field name for error messages

    Returns:
        Validated interval string

    Raises:
        ValidationError: If interval is invalid
    """
    # Allowed intervals (in minutes or special values)
    ALLOWED_INTERVALS = {
        "1", "3", "5", "15", "30",      # Minutes
        "60", "120", "240", "360", "720", # Hours (in minutes)
        "D", "W", "M",                    # Day, Week, Month
    }

    if not interval:
        return "60"  # Default to 1 hour

    interval = str(interval).strip().upper()

    # Check for SQL injection
    check_sql_injection(interval, field_name)

    if interval not in ALLOWED_INTERVALS:
        raise ValidationError(
            field=field_name,
            message=f"Invalid interval '{interval}'",
            value=interval,
            allowed_values=sorted(list(ALLOWED_INTERVALS))
        )

    return interval


def validate_limit(
    limit: Any,
    field_name: str = "limit",
    default: int = 50,
    max_limit: Optional[int] = None
) -> int:
    """
    Validate limit parameter for list endpoints.

    Args:
        limit: Limit value
        field_name: Field name for error messages
        default: Default value if limit is None
        max_limit: Maximum allowed limit (default: 1000)

    Returns:
        Validated limit as integer

    Raises:
        ValidationError: If limit is invalid
    """
    max_limit = max_limit or DEFAULT_BOUNDS.max_limit

    if limit is None:
        return default

    try:
        limit_int = int(limit)
    except (ValueError, TypeError):
        raise ValidationError(
            field=field_name,
            message="Limit must be an integer",
            value=str(limit)[:50]
        )

    if limit_int < 1:
        raise ValidationError(
            field=field_name,
            message="Limit must be at least 1",
            value=str(limit_int)
        )

    if limit_int > max_limit:
        raise ValidationError(
            field=field_name,
            message=f"Limit too large (maximum: {max_limit})",
            value=str(limit_int)
        )

    return limit_int


def validate_string(
    value: str,
    field_name: str,
    max_length: Optional[int] = None,
    pattern: Optional[str] = None,
    allowed_chars: Optional[str] = None
) -> str:
    """
    Validate a general string parameter.

    Args:
        value: String value to validate
        field_name: Field name for error messages
        max_length: Maximum allowed length
        pattern: Regex pattern to match
        allowed_chars: String of allowed characters

    Returns:
        Validated string (stripped)

    Raises:
        ValidationError: If string is invalid
    """
    max_length = max_length or DEFAULT_BOUNDS.max_string_length

    if not isinstance(value, str):
        raise ValidationError(
            field=field_name,
            message="Value must be a string",
            value=type(value).__name__
        )

    value = value.strip()

    if len(value) > max_length:
        raise ValidationError(
            field=field_name,
            message=f"Value too long (maximum {max_length} characters)",
            value=f"{value[:50]}..."
        )

    # Check for SQL injection
    check_sql_injection(value, field_name)

    # Check pattern if provided
    if pattern and not re.match(pattern, value):
        raise ValidationError(
            field=field_name,
            message="Value does not match expected format",
            value=value[:50]
        )

    # Check allowed characters if provided
    if allowed_chars:
        invalid_chars = set(value) - set(allowed_chars)
        if invalid_chars:
            raise ValidationError(
                field=field_name,
                message=f"Value contains invalid characters: {list(invalid_chars)[:5]}",
                value=value[:50]
            )

    return value


# ============================================================================
# REQUEST VALIDATION
# ============================================================================

class TradingRequestValidator(BaseModel):
    """
    Pydantic model for validating trading request parameters.

    Usage:
        validated = TradingRequestValidator(
            symbol="BTCUSDT",
            quantity="0.001",
            price="50000"
        )
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str
    quantity: Optional[str] = None
    price: Optional[str] = None
    side: Optional[str] = None
    order_type: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol_field(cls, v: str) -> str:
        """Validate symbol against whitelist."""
        return validate_symbol(v)

    @field_validator("quantity")
    @classmethod
    def validate_quantity_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate quantity if provided."""
        if v is not None:
            validate_quantity(v)
        return v

    @field_validator("price")
    @classmethod
    def validate_price_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate price if provided."""
        if v is not None:
            validate_price(v)
        return v

    @field_validator("side")
    @classmethod
    def validate_side_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate order side."""
        if v is not None:
            v = v.upper().strip()
            if v not in {"BUY", "SELL"}:
                raise ValidationError(
                    field="side",
                    message="Side must be 'BUY' or 'SELL'",
                    value=v,
                    allowed_values=["BUY", "SELL"]
                )
        return v

    @field_validator("order_type")
    @classmethod
    def validate_order_type_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate order type."""
        if v is not None:
            v = v.upper().strip()
            allowed_types = {"MARKET", "LIMIT", "STOP_LOSS", "STOP_LIMIT", "TAKE_PROFIT"}
            if v not in allowed_types:
                raise ValidationError(
                    field="order_type",
                    message=f"Invalid order type",
                    value=v,
                    allowed_values=list(allowed_types)
                )
        return v


def validate_trading_request(
    symbol: Optional[str] = None,
    quantity: Optional[Any] = None,
    price: Optional[Any] = None,
    side: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Validate a complete trading request.

    Args:
        symbol: Trading symbol
        quantity: Trade quantity
        price: Trade price
        side: Trade side (BUY/SELL)
        **kwargs: Additional parameters to pass through

    Returns:
        Dictionary of validated parameters

    Raises:
        ValidationError: If any parameter is invalid
    """
    result = {}

    # Validate symbol (required)
    if symbol is not None:
        result["symbol"] = validate_symbol(symbol)

    # Validate quantity (optional but validate if provided)
    if quantity is not None:
        result["quantity"] = validate_quantity(quantity)

    # Validate price (optional but validate if provided)
    if price is not None:
        result["price"] = validate_price(price)

    # Validate side (optional but validate if provided)
    if side is not None:
        side = side.upper().strip()
        if side not in {"BUY", "SELL"}:
            raise ValidationError(
                field="side",
                message="Side must be 'BUY' or 'SELL'",
                value=side,
                allowed_values=["BUY", "SELL"]
            )
        result["side"] = side

    # Pass through other parameters (validated individually if needed)
    for key, value in kwargs.items():
        if isinstance(value, str):
            # Basic sanitization for string parameters
            check_sql_injection(value, key)
        result[key] = value

    return result


class InputValidator:
    """
    Centralized input validator for API requests.

    Provides methods for validating all input types with
    consistent error handling and logging.

    Usage:
        validator = InputValidator()

        # In endpoint
        symbol = validator.symbol(request_symbol)
        quantity = validator.quantity(request_quantity)
    """

    @staticmethod
    def symbol(value: str) -> str:
        """Validate trading symbol."""
        return validate_symbol(value)

    @staticmethod
    def quantity(value: Any) -> Decimal:
        """Validate trade quantity."""
        return validate_quantity(value)

    @staticmethod
    def price(value: Any) -> Decimal:
        """Validate trade price."""
        return validate_price(value)

    @staticmethod
    def interval(value: str) -> str:
        """Validate candlestick interval."""
        return validate_interval(value)

    @staticmethod
    def limit(value: Any, default: int = 50) -> int:
        """Validate limit parameter."""
        return validate_limit(value, default=default)

    @staticmethod
    def string(
        value: str,
        field_name: str,
        max_length: int = 200,
        pattern: Optional[str] = None
    ) -> str:
        """Validate general string."""
        return validate_string(value, field_name, max_length, pattern)

    @staticmethod
    def trading_request(**kwargs) -> Dict[str, Any]:
        """Validate complete trading request."""
        return validate_trading_request(**kwargs)
