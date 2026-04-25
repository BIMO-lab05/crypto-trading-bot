"""
Security Module Tests
====================
Tests for rate limiting, input validation, and security headers.

Run with: pytest tests/test_security.py -v
"""

import pytest
from decimal import Decimal
from fastapi import HTTPException

# Import validation functions
from app.security.input_validation import (
    validate_symbol,
    validate_quantity,
    validate_price,
    validate_interval,
    validate_limit,
    validate_string,
    ValidationError,
    ALLOWED_SYMBOLS,
    check_sql_injection,
)

from app.security.rate_limiter import (
    RateLimitConfig,
    RateLimiter,
    get_client_identifier,
)

from app.security.security_headers import (
    SecurityHeadersConfig,
    CORSConfig,
    get_cors_config,
)


# ============================================================================
# INPUT VALIDATION TESTS
# ============================================================================

class TestSymbolValidation:
    """Tests for symbol validation."""

    def test_valid_symbols(self):
        """Test validation of allowed symbols."""
        valid_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
        for symbol in valid_symbols:
            result = validate_symbol(symbol)
            assert result == symbol

    def test_lowercase_symbol_normalized(self):
        """Test that lowercase symbols are normalized to uppercase."""
        result = validate_symbol("btcusdt")
        assert result == "BTCUSDT"

    def test_whitespace_stripped(self):
        """Test that whitespace is stripped from symbols."""
        result = validate_symbol("  BTCUSDT  ")
        assert result == "BTCUSDT"

    def test_invalid_symbol_rejected(self):
        """Test that symbols not in whitelist are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_symbol("INVALID123")
        assert exc_info.value.status_code == 400
        assert "not in the allowed" in str(exc_info.value.detail)

    def test_empty_symbol_rejected(self):
        """Test that empty symbol is rejected."""
        with pytest.raises(ValidationError):
            validate_symbol("")

    def test_none_symbol_rejected(self):
        """Test that None symbol is rejected."""
        with pytest.raises(ValidationError):
            validate_symbol(None)

    def test_special_characters_rejected(self):
        """Test that symbols with special characters are rejected."""
        with pytest.raises(ValidationError):
            validate_symbol("BTC-USDT")

    def test_symbol_too_long_rejected(self):
        """Test that overly long symbols are rejected."""
        with pytest.raises(ValidationError):
            validate_symbol("A" * 50)


class TestQuantityValidation:
    """Tests for quantity validation."""

    def test_valid_quantity(self):
        """Test validation of valid quantities."""
        result = validate_quantity("0.001")
        assert result == Decimal("0.001")

    def test_quantity_from_float(self):
        """Test validation from float value."""
        result = validate_quantity(0.5)
        assert result == Decimal("0.5")

    def test_quantity_from_int(self):
        """Test validation from integer value."""
        result = validate_quantity(10)
        assert result == Decimal("10")

    def test_quantity_too_small_rejected(self):
        """Test that quantities below minimum are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_quantity("0.00000001")
        assert "too small" in str(exc_info.value.detail)

    def test_quantity_too_large_rejected(self):
        """Test that quantities above maximum are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_quantity("10000000")
        assert "too large" in str(exc_info.value.detail)

    def test_negative_quantity_rejected(self):
        """Test that negative quantities are rejected."""
        with pytest.raises(ValidationError):
            validate_quantity("-1")

    def test_zero_quantity_rejected(self):
        """Test that zero quantity is rejected."""
        with pytest.raises(ValidationError):
            validate_quantity("0")

    def test_invalid_format_rejected(self):
        """Test that invalid formats are rejected."""
        with pytest.raises(ValidationError):
            validate_quantity("abc")


class TestPriceValidation:
    """Tests for price validation."""

    def test_valid_price(self):
        """Test validation of valid prices."""
        result = validate_price("50000.50")
        assert result == Decimal("50000.50")

    def test_price_minimum_allowed(self):
        """Test minimum allowed price."""
        result = validate_price("0.00000001")
        assert result == Decimal("0.00000001")

    def test_price_maximum_allowed(self):
        """Test maximum allowed price."""
        result = validate_price("999999")
        assert result == Decimal("999999")

    def test_price_too_large_rejected(self):
        """Test that prices above maximum are rejected."""
        with pytest.raises(ValidationError):
            validate_price("2000000")

    def test_negative_price_rejected(self):
        """Test that negative prices are rejected."""
        with pytest.raises(ValidationError):
            validate_price("-100")


class TestIntervalValidation:
    """Tests for interval validation."""

    def test_valid_intervals(self):
        """Test validation of valid intervals."""
        valid_intervals = ["1", "5", "15", "60", "240", "D", "W"]
        for interval in valid_intervals:
            result = validate_interval(interval)
            assert result == interval.upper()

    def test_invalid_interval_rejected(self):
        """Test that invalid intervals are rejected."""
        with pytest.raises(ValidationError):
            validate_interval("999")

    def test_empty_interval_default(self):
        """Test that empty interval returns default."""
        result = validate_interval("")
        assert result == "60"


class TestLimitValidation:
    """Tests for limit validation."""

    def test_valid_limit(self):
        """Test validation of valid limits."""
        result = validate_limit(50)
        assert result == 50

    def test_limit_default_value(self):
        """Test default value when limit is None."""
        result = validate_limit(None, default=25)
        assert result == 25

    def test_limit_too_large_rejected(self):
        """Test that limits above maximum are rejected."""
        with pytest.raises(ValidationError):
            validate_limit(5000, max_limit=1000)

    def test_limit_zero_rejected(self):
        """Test that zero limit is rejected."""
        with pytest.raises(ValidationError):
            validate_limit(0)

    def test_negative_limit_rejected(self):
        """Test that negative limits are rejected."""
        with pytest.raises(ValidationError):
            validate_limit(-10)


class TestSQLInjectionPrevention:
    """Tests for SQL injection prevention."""

    def test_sql_select_blocked(self):
        """Test that SELECT keyword is blocked."""
        with pytest.raises(ValidationError):
            check_sql_injection("SELECT * FROM users", "test_field")

    def test_sql_drop_blocked(self):
        """Test that DROP keyword is blocked."""
        with pytest.raises(ValidationError):
            check_sql_injection("DROP TABLE users", "test_field")

    def test_sql_union_blocked(self):
        """Test that UNION keyword is blocked."""
        with pytest.raises(ValidationError):
            check_sql_injection("UNION SELECT password", "test_field")

    def test_sql_comment_blocked(self):
        """Test that SQL comments are blocked."""
        with pytest.raises(ValidationError):
            check_sql_injection("admin'--", "test_field")

    def test_clean_string_allowed(self):
        """Test that clean strings pass."""
        # Should not raise
        check_sql_injection("BTCUSDT", "symbol")
        check_sql_injection("valid_input", "field")


# ============================================================================
# RATE LIMITER TESTS
# ============================================================================

class TestRateLimitConfig:
    """Tests for rate limit configuration."""

    def test_default_config(self):
        """Test default rate limit configuration."""
        config = RateLimitConfig()
        assert config.trading_limit == 10
        assert config.auth_limit == 5
        assert config.health_limit == 60
        assert config.general_limit == 30
        assert config.enabled is True

    def test_custom_config(self):
        """Test custom rate limit configuration."""
        config = RateLimitConfig(
            trading_limit=20,
            auth_limit=10,
            enabled=False
        )
        assert config.trading_limit == 20
        assert config.auth_limit == 10
        assert config.enabled is False


class TestRateLimiter:
    """Tests for rate limiter."""

    def test_limiter_initialization(self):
        """Test rate limiter initialization."""
        config = RateLimitConfig(redis_url=None)
        limiter = RateLimiter(config)
        assert limiter.enabled is True
        assert limiter.limiter is not None

    def test_limiter_disabled(self):
        """Test rate limiter when disabled."""
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(config)
        assert limiter.enabled is False


# ============================================================================
# SECURITY HEADERS TESTS
# ============================================================================

class TestSecurityHeadersConfig:
    """Tests for security headers configuration."""

    def test_default_config(self):
        """Test default security headers configuration."""
        config = SecurityHeadersConfig()
        assert config.csp_enabled is True
        assert config.frame_options == "DENY"
        assert config.hsts_enabled is True
        assert config.hsts_max_age == 31536000

    def test_custom_frame_options(self):
        """Test custom frame options."""
        config = SecurityHeadersConfig(frame_options="SAMEORIGIN")
        assert config.frame_options == "SAMEORIGIN"


class TestCORSConfig:
    """Tests for CORS configuration."""

    def test_default_origins(self):
        """Test default CORS origins."""
        config = CORSConfig()
        assert "http://localhost:3000" in config.allow_origins
        assert "http://localhost:8000" in config.allow_origins

    def test_get_cors_config_with_additional(self):
        """Test getting CORS config with additional origins."""
        config = get_cors_config(
            additional_origins=["https://example.com"]
        )
        assert "https://example.com" in config.allow_origins
        assert "http://localhost:3000" in config.allow_origins

    def test_invalid_origin_ignored(self):
        """Test that invalid origins are ignored."""
        config = get_cors_config(
            additional_origins=["not-a-valid-url"]
        )
        assert "not-a-valid-url" not in config.allow_origins


# ============================================================================
# ALLOWED SYMBOLS WHITELIST TESTS
# ============================================================================

class TestAllowedSymbols:
    """Tests for allowed symbols whitelist."""

    def test_major_symbols_in_whitelist(self):
        """Test that major symbols are in whitelist."""
        major_symbols = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
            "XRPUSDT", "ADAUSDT", "DOGEUSDT"
        ]
        for symbol in major_symbols:
            assert symbol in ALLOWED_SYMBOLS

    def test_whitelist_not_empty(self):
        """Test that whitelist is not empty."""
        assert len(ALLOWED_SYMBOLS) > 0

    def test_all_symbols_uppercase(self):
        """Test that all symbols in whitelist are uppercase."""
        for symbol in ALLOWED_SYMBOLS:
            assert symbol == symbol.upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
