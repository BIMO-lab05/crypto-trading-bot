"""
Tests for Input Validation Models
Comprehensive tests for all Pydantic models and validators
"""

import pytest
from pydantic import ValidationError

from app.models import (
    SymbolValidator,
    IntervalValidator,
    KlineRequest,
    RSIRequest,
    TradeRequest,
    VaRRequest
)


class TestSymbolValidator:
    """Test SymbolValidator model"""

    def test_valid_symbol(self):
        """Test valid USDT trading pair"""
        validator = SymbolValidator(symbol="BTCUSDT")
        assert validator.symbol == "BTCUSDT"

    def test_symbol_uppercase_conversion(self):
        """Test symbol is converted to uppercase"""
        validator = SymbolValidator(symbol="btcusdt")
        assert validator.symbol == "BTCUSDT"

    def test_valid_eth_symbol(self):
        """Test valid ETH pair"""
        validator = SymbolValidator(symbol="ETHUSDT")
        assert validator.symbol == "ETHUSDT"

    def test_invalid_symbol_non_usdt(self):
        """Test that non-USDT pairs are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SymbolValidator(symbol="BTCBUSD")

        assert "Only USDT pairs are supported" in str(exc_info.value)

    def test_invalid_symbol_with_numbers(self):
        """Test that symbols with numbers are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SymbolValidator(symbol="BTC1USDT")

        assert "must be alphabetic" in str(exc_info.value)

    def test_invalid_symbol_too_short(self):
        """Test that too short symbols are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SymbolValidator(symbol="BTUS")

        # Should fail min_length validation
        assert "at least 5 characters" in str(exc_info.value)

    def test_invalid_symbol_too_long(self):
        """Test that too long symbols are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SymbolValidator(symbol="VERYLONGSYMBOLNAMEUSDT")

        # Should fail max_length validation
        assert "at most 20 characters" in str(exc_info.value)

    def test_invalid_symbol_special_characters(self):
        """Test that symbols with special characters are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SymbolValidator(symbol="BTC-USDT")

        assert "must be alphabetic" in str(exc_info.value)


class TestIntervalValidator:
    """Test IntervalValidator model"""

    def test_valid_interval_60(self):
        """Test valid 60 minute interval"""
        validator = IntervalValidator(interval="60")
        assert validator.interval == "60"

    def test_default_interval(self):
        """Test default interval is 60"""
        validator = IntervalValidator()
        assert validator.interval == "60"

    def test_valid_interval_1_minute(self):
        """Test 1 minute interval"""
        validator = IntervalValidator(interval="1")
        assert validator.interval == "1"

    def test_valid_interval_daily(self):
        """Test daily interval"""
        validator = IntervalValidator(interval="D")
        assert validator.interval == "D"

    def test_all_valid_intervals(self):
        """Test all valid interval values"""
        valid_intervals = ["1", "5", "15", "30", "60", "240", "D"]

        for interval in valid_intervals:
            validator = IntervalValidator(interval=interval)
            assert validator.interval == interval

    def test_invalid_interval(self):
        """Test that invalid intervals are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            IntervalValidator(interval="90")

        assert "Invalid interval" in str(exc_info.value)

    def test_invalid_interval_string(self):
        """Test that non-numeric intervals (except D) are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            IntervalValidator(interval="hourly")

        assert "Invalid interval" in str(exc_info.value)


class TestKlineRequest:
    """Test KlineRequest model"""

    def test_valid_kline_request(self):
        """Test valid kline request with all parameters"""
        request = KlineRequest(symbol="BTCUSDT", interval="60", limit=100)

        assert request.symbol == "BTCUSDT"
        assert request.interval == "60"
        assert request.limit == 100

    def test_kline_request_defaults(self):
        """Test kline request with default values"""
        request = KlineRequest(symbol="ETHUSDT")

        assert request.symbol == "ETHUSDT"
        assert request.interval == "60"
        assert request.limit == 100

    def test_kline_request_uppercase_symbol(self):
        """Test symbol is converted to uppercase"""
        request = KlineRequest(symbol="btcusdt", interval="15", limit=50)

        assert request.symbol == "BTCUSDT"

    def test_kline_request_invalid_symbol(self):
        """Test invalid symbol is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            KlineRequest(symbol="BTCBUSD")

        assert "Only USDT pairs supported" in str(exc_info.value)

    def test_kline_request_invalid_interval(self):
        """Test invalid interval is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            KlineRequest(symbol="BTCUSDT", interval="120")

        assert "Invalid interval" in str(exc_info.value)

    def test_kline_request_limit_too_low(self):
        """Test that limit below 1 is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            KlineRequest(symbol="BTCUSDT", interval="60", limit=0)

        assert "greater than or equal to 1" in str(exc_info.value)

    def test_kline_request_limit_too_high(self):
        """Test that limit above 1000 is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            KlineRequest(symbol="BTCUSDT", interval="60", limit=1001)

        assert "less than or equal to 1000" in str(exc_info.value)

    def test_kline_request_valid_limit_range(self):
        """Test valid limit values"""
        request_min = KlineRequest(symbol="BTCUSDT", limit=1)
        assert request_min.limit == 1

        request_max = KlineRequest(symbol="BTCUSDT", limit=1000)
        assert request_max.limit == 1000


class TestRSIRequest:
    """Test RSIRequest model"""

    def test_valid_rsi_request(self):
        """Test valid RSI request"""
        request = RSIRequest(symbol="BTCUSDT", interval="60", period=14)

        assert request.symbol == "BTCUSDT"
        assert request.interval == "60"
        assert request.period == 14

    def test_rsi_request_defaults(self):
        """Test RSI request with default values"""
        request = RSIRequest(symbol="ETHUSDT")

        assert request.symbol == "ETHUSDT"
        assert request.interval == "60"
        assert request.period == 14

    def test_rsi_request_uppercase_conversion(self):
        """Test symbol is converted to uppercase"""
        request = RSIRequest(symbol="btcusdt")
        assert request.symbol == "BTCUSDT"

    def test_rsi_request_period_boundaries(self):
        """Test period boundary validation"""
        # Minimum valid period
        request_min = RSIRequest(symbol="BTCUSDT", period=2)
        assert request_min.period == 2

        # Maximum valid period
        request_max = RSIRequest(symbol="BTCUSDT", period=100)
        assert request_max.period == 100

    def test_rsi_request_period_too_low(self):
        """Test that period below 2 is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            RSIRequest(symbol="BTCUSDT", period=1)

        assert "greater than or equal to 2" in str(exc_info.value)

    def test_rsi_request_period_too_high(self):
        """Test that period above 100 is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            RSIRequest(symbol="BTCUSDT", period=101)

        assert "less than or equal to 100" in str(exc_info.value)

    def test_rsi_request_custom_interval(self):
        """Test RSI request with custom interval"""
        request = RSIRequest(symbol="BTCUSDT", interval="5", period=20)

        assert request.interval == "5"
        assert request.period == 20


class TestTradeRequest:
    """Test TradeRequest model"""

    def test_valid_trade_request(self):
        """Test valid trade request"""
        request = TradeRequest(
            portfolio_id="default",
            symbol="BTCUSDT",
            quantity="1.5",
            price="45000.00"
        )

        assert request.portfolio_id == "default"
        assert request.symbol == "BTCUSDT"
        assert request.quantity == "1.5"
        assert request.price == "45000.00"

    def test_trade_request_default_portfolio(self):
        """Test trade request with default portfolio"""
        request = TradeRequest(
            symbol="ETHUSDT",
            quantity="10",
            price="3000"
        )

        assert request.portfolio_id == "default"

    def test_trade_request_uppercase_symbol(self):
        """Test symbol is converted to uppercase"""
        request = TradeRequest(
            symbol="btcusdt",
            quantity="1.0",
            price="45000"
        )

        assert request.symbol == "BTCUSDT"

    def test_trade_request_valid_quantity_formats(self):
        """Test various valid quantity formats"""
        # Integer
        request1 = TradeRequest(symbol="BTCUSDT", quantity="1", price="45000")
        assert request1.quantity == "1"

        # Decimal
        request2 = TradeRequest(symbol="BTCUSDT", quantity="0.5", price="45000")
        assert request2.quantity == "0.5"

        # Large number
        request3 = TradeRequest(symbol="BTCUSDT", quantity="1000.123", price="45000")
        assert request3.quantity == "1000.123"

    def test_trade_request_invalid_quantity_negative(self):
        """Test that negative quantity is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(symbol="BTCUSDT", quantity="-1", price="45000")

        assert "Must be a valid positive number" in str(exc_info.value)

    def test_trade_request_invalid_quantity_zero(self):
        """Test that zero quantity is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(symbol="BTCUSDT", quantity="0", price="45000")

        assert "Must be a valid positive number" in str(exc_info.value)

    def test_trade_request_invalid_quantity_non_numeric(self):
        """Test that non-numeric quantity is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(symbol="BTCUSDT", quantity="abc", price="45000")

        assert "Must be a valid positive number" in str(exc_info.value)

    def test_trade_request_invalid_price_negative(self):
        """Test that negative price is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(symbol="BTCUSDT", quantity="1", price="-45000")

        assert "Must be a valid positive number" in str(exc_info.value)

    def test_trade_request_invalid_price_zero(self):
        """Test that zero price is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(symbol="BTCUSDT", quantity="1", price="0")

        assert "Must be a valid positive number" in str(exc_info.value)

    def test_trade_request_invalid_price_non_numeric(self):
        """Test that non-numeric price is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(symbol="BTCUSDT", quantity="1", price="expensive")

        assert "Must be a valid positive number" in str(exc_info.value)


class TestVaRRequest:
    """Test VaRRequest model"""

    def test_valid_var_request(self):
        """Test valid VaR request"""
        request = VaRRequest(confidence_level=0.95, time_horizon_days=1)

        assert request.confidence_level == 0.95
        assert request.time_horizon_days == 1

    def test_var_request_defaults(self):
        """Test VaR request with default values"""
        request = VaRRequest()

        assert request.confidence_level == 0.95
        assert request.time_horizon_days == 1

    def test_var_request_valid_confidence_levels(self):
        """Test various valid confidence levels"""
        # Minimum
        request_min = VaRRequest(confidence_level=0.9)
        assert request_min.confidence_level == 0.9

        # Mid-range
        request_mid = VaRRequest(confidence_level=0.95)
        assert request_mid.confidence_level == 0.95

        # Maximum
        request_max = VaRRequest(confidence_level=0.99)
        assert request_max.confidence_level == 0.99

    def test_var_request_confidence_level_too_low(self):
        """Test that confidence level below 0.9 is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            VaRRequest(confidence_level=0.89)

        assert "greater than or equal to 0.9" in str(exc_info.value)

    def test_var_request_confidence_level_too_high(self):
        """Test that confidence level above 0.99 is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            VaRRequest(confidence_level=1.0)

        assert "less than or equal to 0.99" in str(exc_info.value)

    def test_var_request_valid_time_horizons(self):
        """Test various valid time horizons"""
        # Minimum
        request_min = VaRRequest(time_horizon_days=1)
        assert request_min.time_horizon_days == 1

        # Mid-range
        request_mid = VaRRequest(time_horizon_days=7)
        assert request_mid.time_horizon_days == 7

        # Maximum
        request_max = VaRRequest(time_horizon_days=30)
        assert request_max.time_horizon_days == 30

    def test_var_request_time_horizon_too_low(self):
        """Test that time horizon below 1 is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            VaRRequest(time_horizon_days=0)

        assert "greater than or equal to 1" in str(exc_info.value)

    def test_var_request_time_horizon_too_high(self):
        """Test that time horizon above 30 is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            VaRRequest(time_horizon_days=31)

        assert "less than or equal to 30" in str(exc_info.value)

    def test_var_request_custom_values(self):
        """Test VaR request with custom values"""
        request = VaRRequest(confidence_level=0.97, time_horizon_days=14)

        assert request.confidence_level == 0.97
        assert request.time_horizon_days == 14
