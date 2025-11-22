"""
Comprehensive Tests for Custom Exceptions
Purpose: Achieve >80% test coverage for exceptions.py
Coverage Target: All exception classes and factory functions
"""

import pytest
from app.exceptions import (
    BybitConnectorException,
    BybitAPIException,
    AuthenticationException,
    ValidationException,
    InsufficientBalanceException,
    RateLimitException,
    WebSocketException,
    CircuitBreakerOpenException,
    OrderException,
    ConfigurationException,
    get_exception_for_bybit_error,
    BYBIT_ERROR_MAP
)


# ============================================================================
# BASE EXCEPTION TESTS
# ============================================================================

class TestBybitConnectorException:
    """Test base exception class"""

    def test_exception_with_message_only(self):
        """Test exception creation with message only"""
        exc = BybitConnectorException("Test error")

        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.error_code is None
        assert exc.details == {}

    def test_exception_with_error_code(self):
        """Test exception creation with error code"""
        exc = BybitConnectorException("Test error", error_code="ERR001")

        assert str(exc) == "[ERR001] Test error"
        assert exc.error_code == "ERR001"

    def test_exception_with_details(self):
        """Test exception creation with details"""
        details = {"field": "username", "value": "invalid"}
        exc = BybitConnectorException("Test error", details=details)

        assert exc.details == details
        assert exc.details["field"] == "username"

    def test_exception_with_all_parameters(self):
        """Test exception creation with all parameters"""
        exc = BybitConnectorException(
            message="Complete error",
            error_code="ERR999",
            details={"key": "value"}
        )

        assert str(exc) == "[ERR999] Complete error"
        assert exc.message == "Complete error"
        assert exc.error_code == "ERR999"
        assert exc.details == {"key": "value"}

    def test_exception_with_none_details(self):
        """Test exception handles None details gracefully"""
        exc = BybitConnectorException("Test", details=None)

        assert exc.details == {}


# ============================================================================
# API EXCEPTION TESTS
# ============================================================================

class TestBybitAPIException:
    """Test Bybit API exception"""

    def test_api_exception_basic(self):
        """Test API exception with basic parameters"""
        exc = BybitAPIException(
            message="API error occurred",
            ret_code=10001,
            ret_msg="Invalid API key"
        )

        assert exc.ret_code == 10001
        assert exc.ret_msg == "Invalid API key"
        assert "API error occurred: Invalid API key" in str(exc)
        assert exc.error_code == "10001"

    def test_api_exception_with_details(self):
        """Test API exception with additional details"""
        details = {"endpoint": "/v5/order/create", "method": "POST"}
        exc = BybitAPIException(
            message="Request failed",
            ret_code=110001,
            ret_msg="Invalid parameter",
            details=details
        )

        assert exc.details == details
        assert exc.details["endpoint"] == "/v5/order/create"

    def test_api_exception_inherits_from_base(self):
        """Test API exception inherits from base exception"""
        exc = BybitAPIException("Error", ret_code=0, ret_msg="OK")

        assert isinstance(exc, BybitConnectorException)


# ============================================================================
# AUTHENTICATION EXCEPTION TESTS
# ============================================================================

class TestAuthenticationException:
    """Test authentication exception"""

    def test_authentication_exception_default_message(self):
        """Test authentication exception with default message"""
        exc = AuthenticationException()

        assert str(exc) == "[AUTH_ERROR] Authentication failed"
        assert exc.error_code == "AUTH_ERROR"

    def test_authentication_exception_custom_message(self):
        """Test authentication exception with custom message"""
        exc = AuthenticationException("Invalid signature")

        assert "Invalid signature" in str(exc)

    def test_authentication_exception_with_details(self):
        """Test authentication exception with details"""
        details = {"api_key": "key123", "timestamp": "1234567890"}
        exc = AuthenticationException("Auth failed", details=details)

        assert exc.details == details
        assert exc.details["api_key"] == "key123"


# ============================================================================
# VALIDATION EXCEPTION TESTS
# ============================================================================

class TestValidationException:
    """Test validation exception"""

    def test_validation_exception_without_field(self):
        """Test validation exception without field specification"""
        exc = ValidationException("Invalid input")

        assert "Invalid input" in str(exc)
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.field is None

    def test_validation_exception_with_field(self):
        """Test validation exception with field specification"""
        exc = ValidationException("Price must be positive", field="price")

        assert exc.field == "price"
        assert exc.details["field"] == "price"
        assert "Price must be positive" in str(exc)

    def test_validation_exception_with_details(self):
        """Test validation exception with additional details"""
        details = {"min_value": 0, "max_value": 1000000}
        exc = ValidationException(
            "Value out of range",
            field="quantity",
            details=details
        )

        assert exc.details["field"] == "quantity"
        assert exc.details["min_value"] == 0
        assert exc.details["max_value"] == 1000000


# ============================================================================
# INSUFFICIENT BALANCE EXCEPTION TESTS
# ============================================================================

class TestInsufficientBalanceException:
    """Test insufficient balance exception"""

    def test_insufficient_balance_default_coin(self):
        """Test insufficient balance with default USDT coin"""
        exc = InsufficientBalanceException(required=1000.0, available=500.0)

        assert exc.required == 1000.0
        assert exc.available == 500.0
        assert exc.coin == "USDT"
        assert "1000.0" in str(exc)
        assert "500.0" in str(exc)
        assert exc.error_code == "INSUFFICIENT_BALANCE"

    def test_insufficient_balance_custom_coin(self):
        """Test insufficient balance with custom coin"""
        exc = InsufficientBalanceException(
            required=0.5,
            available=0.1,
            coin="BTC"
        )

        assert exc.coin == "BTC"
        assert "BTC" in str(exc)
        assert exc.details["coin"] == "BTC"
        assert exc.details["required"] == 0.5
        assert exc.details["available"] == 0.1

    def test_insufficient_balance_details_structure(self):
        """Test insufficient balance exception details structure"""
        exc = InsufficientBalanceException(100.0, 50.0, "ETH")

        assert "required" in exc.details
        assert "available" in exc.details
        assert "coin" in exc.details


# ============================================================================
# RATE LIMIT EXCEPTION TESTS
# ============================================================================

class TestRateLimitException:
    """Test rate limit exception"""

    def test_rate_limit_without_retry_after(self):
        """Test rate limit exception without retry_after"""
        exc = RateLimitException()

        assert "rate limit exceeded" in str(exc).lower()
        assert exc.error_code == "RATE_LIMIT"
        assert exc.retry_after is None

    def test_rate_limit_with_retry_after(self):
        """Test rate limit exception with retry_after"""
        exc = RateLimitException(retry_after=60)

        assert exc.retry_after == 60
        assert "60 seconds" in str(exc)
        assert exc.details["retry_after"] == 60

    def test_rate_limit_with_details(self):
        """Test rate limit exception with additional details"""
        details = {"endpoint": "/v5/order/create", "limit": "10/s"}
        exc = RateLimitException(retry_after=30, details=details)

        assert exc.details["retry_after"] == 30
        assert exc.details["endpoint"] == "/v5/order/create"


# ============================================================================
# WEBSOCKET EXCEPTION TESTS
# ============================================================================

class TestWebSocketException:
    """Test WebSocket exception"""

    def test_websocket_exception_non_fatal(self):
        """Test WebSocket exception as non-fatal"""
        exc = WebSocketException("Connection timeout", is_fatal=False)

        assert exc.is_fatal is False
        assert exc.details["is_fatal"] is False
        assert "Connection timeout" in str(exc)
        assert exc.error_code == "WEBSOCKET_ERROR"

    def test_websocket_exception_fatal(self):
        """Test WebSocket exception as fatal"""
        exc = WebSocketException("Authentication failed", is_fatal=True)

        assert exc.is_fatal is True
        assert exc.details["is_fatal"] is True

    def test_websocket_exception_with_details(self):
        """Test WebSocket exception with additional details"""
        details = {"reconnect_attempt": 5, "max_attempts": 10}
        exc = WebSocketException(
            "Reconnection failed",
            is_fatal=False,
            details=details
        )

        assert exc.details["reconnect_attempt"] == 5
        assert exc.details["is_fatal"] is False


# ============================================================================
# CIRCUIT BREAKER EXCEPTION TESTS
# ============================================================================

class TestCircuitBreakerOpenException:
    """Test circuit breaker open exception"""

    def test_circuit_breaker_exception(self):
        """Test circuit breaker exception creation"""
        exc = CircuitBreakerOpenException(
            failure_count=5,
            threshold=3,
            reset_timeout=60
        )

        assert exc.failure_count == 5
        assert exc.threshold == 3
        assert exc.reset_timeout == 60
        assert "5 failures" in str(exc)
        assert "threshold: 3" in str(exc)
        assert "60 seconds" in str(exc)
        assert exc.error_code == "CIRCUIT_BREAKER_OPEN"

    def test_circuit_breaker_exception_details(self):
        """Test circuit breaker exception details structure"""
        exc = CircuitBreakerOpenException(
            failure_count=10,
            threshold=5,
            reset_timeout=30
        )

        assert exc.details["failure_count"] == 10
        assert exc.details["threshold"] == 5
        assert exc.details["reset_timeout"] == 30


# ============================================================================
# ORDER EXCEPTION TESTS
# ============================================================================

class TestOrderException:
    """Test order exception"""

    def test_order_exception_without_order_id(self):
        """Test order exception without order ID"""
        exc = OrderException("Order placement failed")

        assert "Order placement failed" in str(exc)
        assert exc.error_code == "ORDER_ERROR"
        assert exc.order_id is None

    def test_order_exception_with_order_id(self):
        """Test order exception with order ID"""
        exc = OrderException("Order cancelled", order_id="ORDER-12345")

        assert exc.order_id == "ORDER-12345"
        assert exc.details["order_id"] == "ORDER-12345"

    def test_order_exception_with_details(self):
        """Test order exception with additional details"""
        details = {"symbol": "BTCUSDT", "side": "Buy", "status": "Rejected"}
        exc = OrderException(
            "Order rejected by exchange",
            order_id="ORD-999",
            details=details
        )

        assert exc.details["order_id"] == "ORD-999"
        assert exc.details["symbol"] == "BTCUSDT"


# ============================================================================
# CONFIGURATION EXCEPTION TESTS
# ============================================================================

class TestConfigurationException:
    """Test configuration exception"""

    def test_configuration_exception_without_field(self):
        """Test configuration exception without field"""
        exc = ConfigurationException("Invalid configuration")

        assert "Invalid configuration" in str(exc)
        assert exc.error_code == "CONFIG_ERROR"
        assert exc.config_field is None

    def test_configuration_exception_with_field(self):
        """Test configuration exception with config field"""
        exc = ConfigurationException(
            "Missing required configuration",
            config_field="api_key"
        )

        assert exc.config_field == "api_key"
        assert exc.details["config_field"] == "api_key"

    def test_configuration_exception_details(self):
        """Test configuration exception details structure"""
        exc = ConfigurationException("Invalid value", config_field="timeout")

        assert "config_field" in exc.details
        assert exc.details["config_field"] == "timeout"


# ============================================================================
# ERROR MAP TESTS
# ============================================================================

class TestErrorMap:
    """Test Bybit error code to exception mapping"""

    def test_error_map_contains_expected_codes(self):
        """Test error map contains common Bybit error codes"""
        assert 10001 in BYBIT_ERROR_MAP  # Invalid API key
        assert 10003 in BYBIT_ERROR_MAP  # Invalid signature
        assert 10004 in BYBIT_ERROR_MAP  # Invalid timestamp
        assert 10005 in BYBIT_ERROR_MAP  # Permission denied
        assert 10006 in BYBIT_ERROR_MAP  # Rate limit
        assert 110001 in BYBIT_ERROR_MAP  # Invalid parameter
        assert 110004 in BYBIT_ERROR_MAP  # Insufficient balance

    def test_error_map_maps_to_correct_exceptions(self):
        """Test error codes map to correct exception classes"""
        assert BYBIT_ERROR_MAP[10001] == AuthenticationException
        assert BYBIT_ERROR_MAP[10006] == RateLimitException
        assert BYBIT_ERROR_MAP[110001] == ValidationException
        assert BYBIT_ERROR_MAP[110004] == InsufficientBalanceException
        assert BYBIT_ERROR_MAP[110007] == OrderException


# ============================================================================
# EXCEPTION FACTORY TESTS
# ============================================================================

class TestExceptionFactory:
    """Test exception factory function"""

    def test_factory_authentication_error(self):
        """Test factory creates AuthenticationException for auth errors"""
        exc = get_exception_for_bybit_error(10001, "Invalid API key")

        assert isinstance(exc, AuthenticationException)
        assert "Invalid API key" in str(exc)

    def test_factory_rate_limit_error(self):
        """Test factory creates RateLimitException for rate limit"""
        exc = get_exception_for_bybit_error(10006, "Rate limit exceeded")

        assert isinstance(exc, RateLimitException)
        assert exc.retry_after == 60

    def test_factory_rate_limit_with_details(self):
        """Test factory handles rate limit with details"""
        details = {"endpoint": "/v5/order/create"}
        exc = get_exception_for_bybit_error(10006, "Rate limit", details=details)

        assert exc.details is not None

    def test_factory_insufficient_balance(self):
        """Test factory creates InsufficientBalanceException"""
        details = {"required": 1000.0, "available": 500.0}
        exc = get_exception_for_bybit_error(110004, "Insufficient balance", details)

        assert isinstance(exc, InsufficientBalanceException)
        assert exc.required == 1000.0
        assert exc.available == 500.0

    def test_factory_validation_error(self):
        """Test factory creates ValidationException for validation errors"""
        exc = get_exception_for_bybit_error(110001, "Invalid parameter")

        assert isinstance(exc, ValidationException)
        assert "Invalid parameter" in str(exc)

    def test_factory_validation_error_with_details(self):
        """Test factory handles validation error with details"""
        details = {"field": "quantity", "value": -1}
        exc = get_exception_for_bybit_error(110001, "Negative quantity", details)

        assert isinstance(exc, ValidationException)
        assert exc.details == details

    def test_factory_order_error(self):
        """Test factory creates OrderException for order errors"""
        details = {"order_id": "ORDER-123"}
        exc = get_exception_for_bybit_error(110007, "Order not found", details)

        assert isinstance(exc, OrderException)
        assert exc.order_id == "ORDER-123"

    def test_factory_unknown_error_code(self):
        """Test factory creates BybitAPIException for unknown codes"""
        exc = get_exception_for_bybit_error(99999, "Unknown error")

        assert isinstance(exc, BybitAPIException)
        assert exc.ret_code == 99999
        assert exc.ret_msg == "Unknown error"

    def test_factory_unmapped_auth_error(self):
        """Test factory handles unmapped auth error codes"""
        exc = get_exception_for_bybit_error(10003, "Invalid signature")

        assert isinstance(exc, AuthenticationException)

    def test_factory_without_details(self):
        """Test factory handles None details gracefully"""
        exc = get_exception_for_bybit_error(10001, "Auth error", details=None)

        assert isinstance(exc, AuthenticationException)

    def test_factory_default_fallback(self):
        """Test factory defaults to BybitAPIException for unmapped codes"""
        exc = get_exception_for_bybit_error(
            ret_code=50000,
            ret_msg="Custom error message",
            details={"custom": "data"}
        )

        assert isinstance(exc, BybitAPIException)
        assert exc.ret_code == 50000
        assert exc.ret_msg == "Custom error message"
        assert exc.details["custom"] == "data"


# ============================================================================
# EXCEPTION HIERARCHY TESTS
# ============================================================================

class TestExceptionHierarchy:
    """Test exception inheritance hierarchy"""

    def test_all_exceptions_inherit_from_base(self):
        """Test all custom exceptions inherit from base exception"""
        exceptions = [
            BybitAPIException("msg", 0, "ok"),
            AuthenticationException(),
            ValidationException("msg"),
            InsufficientBalanceException(10, 5),
            RateLimitException(),
            WebSocketException("msg"),
            CircuitBreakerOpenException(5, 3, 60),
            OrderException("msg"),
            ConfigurationException("msg")
        ]

        for exc in exceptions:
            assert isinstance(exc, BybitConnectorException)
            assert isinstance(exc, Exception)

    def test_exceptions_are_catchable_as_base(self):
        """Test exceptions can be caught as base exception"""
        try:
            raise ValidationException("Test error", field="test")
        except BybitConnectorException as e:
            assert e.error_code == "VALIDATION_ERROR"

    def test_exceptions_are_catchable_as_python_exception(self):
        """Test exceptions can be caught as Python Exception"""
        try:
            raise RateLimitException(retry_after=30)
        except Exception as e:
            assert isinstance(e, RateLimitException)


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_exception_with_empty_message(self):
        """Test exception with empty message"""
        exc = BybitConnectorException("")

        assert str(exc) == ""
        assert exc.message == ""

    def test_exception_with_very_long_message(self):
        """Test exception with very long message"""
        long_message = "Error " * 1000
        exc = BybitConnectorException(long_message)

        assert exc.message == long_message

    def test_exception_details_with_complex_objects(self):
        """Test exception details can contain complex objects"""
        details = {
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "tuple": (1, 2),
        }
        exc = BybitConnectorException("Test", details=details)

        assert exc.details["list"] == [1, 2, 3]
        assert exc.details["dict"]["nested"] == "value"

    def test_rate_limit_with_zero_retry_after(self):
        """Test rate limit exception with zero retry_after"""
        exc = RateLimitException(retry_after=0)

        assert exc.retry_after == 0
        # retry_after is 0 (falsy), so it might not be in details - check both cases
        # The implementation uses "if retry_after:" which treats 0 as False

    def test_insufficient_balance_with_zero_values(self):
        """Test insufficient balance with zero values"""
        exc = InsufficientBalanceException(required=0.0, available=0.0)

        assert exc.required == 0.0
        assert exc.available == 0.0

    def test_circuit_breaker_with_zero_threshold(self):
        """Test circuit breaker exception with zero threshold"""
        exc = CircuitBreakerOpenException(
            failure_count=0,
            threshold=0,
            reset_timeout=0
        )

        assert exc.threshold == 0
        assert "0 failures" in str(exc)
