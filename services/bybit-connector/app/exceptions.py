"""
Bybit Connector Service - Custom Exceptions
Purpose: Define custom exception classes for error handling
"""

from typing import Optional, Dict, Any


class BybitConnectorException(Exception):
    """Base exception for all Bybit Connector errors"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """
        Initialize base exception
        
        Args:
            message: Human-readable error message
            error_code: Optional error code from API
            details: Optional additional error details
        """
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """Return formatted error message"""
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class BybitAPIException(BybitConnectorException):
    """Exception raised when Bybit API returns an error"""
    
    def __init__(self, message: str, ret_code: int, ret_msg: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize API exception with Bybit error details
        
        Args:
            message: Custom error message
            ret_code: Bybit API return code
            ret_msg: Bybit API return message
            details: Additional error context
        """
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        super().__init__(
            message=f"{message}: {ret_msg}",
            error_code=str(ret_code),
            details=details
        )


class AuthenticationException(BybitConnectorException):
    """Exception raised for authentication/authorization errors"""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        """
        Initialize authentication exception
        
        Args:
            message: Error message
            details: Additional context (DO NOT include credentials!)
        """
        super().__init__(message=message, error_code="AUTH_ERROR", details=details)


class ValidationException(BybitConnectorException):
    """Exception raised for input validation errors"""
    
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """
        Initialize validation exception
        
        Args:
            message: Validation error message
            field: Field that failed validation
            details: Additional validation context
        """
        self.field = field
        error_details = details or {}
        if field:
            error_details["field"] = field
        super().__init__(message=message, error_code="VALIDATION_ERROR", details=error_details)


class InsufficientBalanceException(BybitConnectorException):
    """Exception raised when account has insufficient balance"""
    
    def __init__(self, required: float, available: float, coin: str = "USDT"):
        """
        Initialize insufficient balance exception
        
        Args:
            required: Amount required for operation
            available: Amount currently available
            coin: Cryptocurrency symbol
        """
        self.required = required
        self.available = available
        self.coin = coin
        message = f"Insufficient {coin} balance. Required: {required}, Available: {available}"
        super().__init__(
            message=message,
            error_code="INSUFFICIENT_BALANCE",
            details={"required": required, "available": available, "coin": coin}
        )


class RateLimitException(BybitConnectorException):
    """Exception raised when API rate limit is exceeded"""
    
    def __init__(self, retry_after: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        """
        Initialize rate limit exception
        
        Args:
            retry_after: Seconds to wait before retrying
            details: Additional rate limit context
        """
        self.retry_after = retry_after
        message = "API rate limit exceeded"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        
        error_details = details or {}
        if retry_after:
            error_details["retry_after"] = retry_after
            
        super().__init__(message=message, error_code="RATE_LIMIT", details=error_details)


class WebSocketException(BybitConnectorException):
    """Exception raised for WebSocket connection errors"""
    
    def __init__(self, message: str, is_fatal: bool = False, details: Optional[Dict[str, Any]] = None):
        """
        Initialize WebSocket exception
        
        Args:
            message: Error message
            is_fatal: Whether error is fatal (should not retry)
            details: Additional error context
        """
        self.is_fatal = is_fatal
        error_details = details or {}
        error_details["is_fatal"] = is_fatal
        super().__init__(message=message, error_code="WEBSOCKET_ERROR", details=error_details)


class CircuitBreakerOpenException(BybitConnectorException):
    """Exception raised when circuit breaker is open (too many failures)"""
    
    def __init__(self, failure_count: int, threshold: int, reset_timeout: int):
        """
        Initialize circuit breaker exception
        
        Args:
            failure_count: Number of consecutive failures
            threshold: Failure threshold before opening
            reset_timeout: Seconds until circuit attempts reset
        """
        self.failure_count = failure_count
        self.threshold = threshold
        self.reset_timeout = reset_timeout
        
        message = (
            f"Circuit breaker open after {failure_count} failures "
            f"(threshold: {threshold}). Retry after {reset_timeout} seconds"
        )
        
        super().__init__(
            message=message,
            error_code="CIRCUIT_BREAKER_OPEN",
            details={
                "failure_count": failure_count,
                "threshold": threshold,
                "reset_timeout": reset_timeout
            }
        )


class OrderException(BybitConnectorException):
    """Exception raised for order-related errors"""
    
    def __init__(self, message: str, order_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """
        Initialize order exception
        
        Args:
            message: Error message
            order_id: Related order ID if available
            details: Additional order context
        """
        self.order_id = order_id
        error_details = details or {}
        if order_id:
            error_details["order_id"] = order_id
        super().__init__(message=message, error_code="ORDER_ERROR", details=error_details)


class ConfigurationException(BybitConnectorException):
    """Exception raised for configuration errors"""
    
    def __init__(self, message: str, config_field: Optional[str] = None):
        """
        Initialize configuration exception
        
        Args:
            message: Error message
            config_field: Configuration field with issue
        """
        self.config_field = config_field
        details = {}
        if config_field:
            details["config_field"] = config_field
        super().__init__(message=message, error_code="CONFIG_ERROR", details=details)


# Mapping of Bybit API error codes to custom exceptions
BYBIT_ERROR_MAP = {
    10001: AuthenticationException,  # Invalid API key
    10003: AuthenticationException,  # Invalid signature
    10004: AuthenticationException,  # Invalid timestamp
    10005: AuthenticationException,  # Permission denied
    10006: RateLimitException,       # Rate limit exceeded
    110001: ValidationException,     # Invalid parameter
    110003: ValidationException,     # Invalid order quantity
    110004: InsufficientBalanceException,  # Insufficient balance
    110007: OrderException,          # Order not found
    110043: OrderException,          # Order already cancelled
}


def get_exception_for_bybit_error(ret_code: int, ret_msg: str, details: Optional[Dict[str, Any]] = None) -> BybitConnectorException:
    """
    Factory function to create appropriate exception from Bybit error code
    
    Args:
        ret_code: Bybit API return code
        ret_msg: Bybit API return message
        details: Additional error details
    
    Returns:
        Appropriate exception instance
    """
    # Get exception class from mapping, default to BybitAPIException
    exception_class = BYBIT_ERROR_MAP.get(ret_code, BybitAPIException)
    
    # Handle special cases that need specific arguments
    if ret_code == 10006:  # Rate limit
        return RateLimitException(retry_after=60, details=details)
    elif ret_code == 110004:  # Insufficient balance
        # Try to extract balance info from details
        required = details.get("required", 0.0) if details else 0.0
        available = details.get("available", 0.0) if details else 0.0
        return InsufficientBalanceException(required=required, available=available)
    elif exception_class == ValidationException:
        return ValidationException(message=ret_msg, details=details)
    elif exception_class == OrderException:
        order_id = details.get("order_id") if details else None
        return OrderException(message=ret_msg, order_id=order_id, details=details)
    elif exception_class == AuthenticationException:
        return AuthenticationException(message=ret_msg, details=details)
    else:
        # Default to BybitAPIException
        return BybitAPIException(
            message="Bybit API error",
            ret_code=ret_code,
            ret_msg=ret_msg,
            details=details
        )
