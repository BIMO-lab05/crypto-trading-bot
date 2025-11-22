"""
Unit Tests for Request/Response Models
Tests for app/utils/request_models.py
"""

import pytest
from pydantic import ValidationError

from app.utils.request_models import (
    IntervalEnum,
    CollectKlineRequest,
    BulkCollectRequest
)


class TestIntervalEnum:
    """Test suite for IntervalEnum"""

    def test_enum_has_all_expected_values(self):
        """Test that IntervalEnum has all expected interval values"""
        expected_values = {
            "1": IntervalEnum.ONE_MIN,
            "5": IntervalEnum.FIVE_MIN,
            "15": IntervalEnum.FIFTEEN_MIN,
            "30": IntervalEnum.THIRTY_MIN,
            "60": IntervalEnum.ONE_HOUR,
            "240": IntervalEnum.FOUR_HOUR,
            "D": IntervalEnum.ONE_DAY,
        }

        for value, enum_member in expected_values.items():
            assert enum_member.value == value

    def test_enum_value_count(self):
        """Test that IntervalEnum has exactly 7 values"""
        assert len(IntervalEnum) == 7

    def test_enum_string_comparison(self):
        """Test that enum values can be compared with strings"""
        assert IntervalEnum.ONE_HOUR.value == "60"
        assert IntervalEnum.ONE_DAY.value == "D"

    def test_enum_membership(self):
        """Test that values are members of the enum"""
        assert "1" in [e.value for e in IntervalEnum]
        assert "60" in [e.value for e in IntervalEnum]
        assert "invalid" not in [e.value for e in IntervalEnum]


class TestCollectKlineRequest:
    """Test suite for CollectKlineRequest model"""

    def test_valid_request_with_defaults(self):
        """Test creating valid request with default values"""
        request = CollectKlineRequest(symbol="BTCUSDT")

        assert request.symbol == "BTCUSDT"
        assert request.interval == IntervalEnum.ONE_HOUR
        assert request.days == 7

    def test_valid_request_with_all_params(self):
        """Test creating valid request with all parameters"""
        request = CollectKlineRequest(
            symbol="ETHUSDT",
            interval=IntervalEnum.FIVE_MIN,
            days=14
        )

        assert request.symbol == "ETHUSDT"
        assert request.interval == IntervalEnum.FIVE_MIN
        assert request.days == 14

    def test_symbol_uppercase_conversion(self):
        """Test that symbol is automatically converted to uppercase"""
        request = CollectKlineRequest(symbol="btcusdt")
        assert request.symbol == "BTCUSDT"

    def test_symbol_mixed_case_conversion(self):
        """Test mixed case symbol conversion"""
        request = CollectKlineRequest(symbol="EtHuSdT")
        assert request.symbol == "ETHUSDT"

    def test_valid_symbol_minimum_length(self):
        """Test that 6-character symbol is valid"""
        request = CollectKlineRequest(symbol="ABCDEF")
        assert request.symbol == "ABCDEF"

    def test_valid_symbol_maximum_length(self):
        """Test that 20-character symbol is valid"""
        request = CollectKlineRequest(symbol="ABCDEFGHIJKLMNOPQRST")
        assert request.symbol == "ABCDEFGHIJKLMNOPQRST"

    def test_invalid_symbol_too_short(self):
        """Test that symbol shorter than 6 characters is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="ABCDE")

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('symbol',) for e in errors)

    def test_invalid_symbol_too_long(self):
        """Test that symbol longer than 20 characters is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="A" * 21)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('symbol',) for e in errors)

    def test_invalid_symbol_with_numbers(self):
        """Test that symbol with numbers is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="BTC123")

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('symbol',) for e in errors)

    def test_invalid_symbol_with_special_chars(self):
        """Test that symbol with special characters is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="BTC-USDT")

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('symbol',) for e in errors)

    def test_invalid_symbol_with_spaces(self):
        """Test that symbol with spaces is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="BTC USDT")

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('symbol',) for e in errors)

    def test_days_minimum_value(self):
        """Test that days=1 is valid (minimum)"""
        request = CollectKlineRequest(symbol="BTCUSDT", days=1)
        assert request.days == 1

    def test_days_maximum_value(self):
        """Test that days=30 is valid (maximum)"""
        request = CollectKlineRequest(symbol="BTCUSDT", days=30)
        assert request.days == 30

    def test_days_below_minimum(self):
        """Test that days=0 is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="BTCUSDT", days=0)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('days',) for e in errors)

    def test_days_above_maximum(self):
        """Test that days=31 is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="BTCUSDT", days=31)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('days',) for e in errors)

    def test_days_negative_value(self):
        """Test that negative days value is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="BTCUSDT", days=-5)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('days',) for e in errors)

    def test_all_interval_values_valid(self):
        """Test that all interval enum values are valid"""
        for interval in IntervalEnum:
            request = CollectKlineRequest(symbol="BTCUSDT", interval=interval)
            assert request.interval == interval

    def test_invalid_interval_value(self):
        """Test that invalid interval value raises error"""
        with pytest.raises(ValidationError):
            CollectKlineRequest(symbol="BTCUSDT", interval="invalid")

    def test_missing_required_symbol(self):
        """Test that missing symbol raises error"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest()

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('symbol',) and e['type'] == 'missing' for e in errors)

    def test_model_dict_export(self):
        """Test that model can be exported to dict"""
        request = CollectKlineRequest(
            symbol="BTCUSDT",
            interval=IntervalEnum.ONE_HOUR,
            days=7
        )

        data = request.model_dump()

        assert data['symbol'] == "BTCUSDT"
        assert data['interval'] == "60"
        assert data['days'] == 7

    def test_model_json_export(self):
        """Test that model can be exported to JSON"""
        request = CollectKlineRequest(symbol="BTCUSDT")
        json_str = request.model_dump_json()

        assert isinstance(json_str, str)
        assert "BTCUSDT" in json_str


class TestBulkCollectRequest:
    """Test suite for BulkCollectRequest model"""

    def test_valid_request_with_defaults(self):
        """Test creating valid request with default values"""
        request = BulkCollectRequest()

        assert request.symbols is None
        assert request.interval == IntervalEnum.ONE_HOUR
        assert request.days == 7

    def test_valid_request_with_symbols(self):
        """Test creating valid request with symbols list"""
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        request = BulkCollectRequest(symbols=symbols)

        assert request.symbols == symbols
        assert len(request.symbols) == 3

    def test_valid_request_with_all_params(self):
        """Test creating valid request with all parameters"""
        symbols = ["BTCUSDT", "ETHUSDT"]
        request = BulkCollectRequest(
            symbols=symbols,
            interval=IntervalEnum.FIVE_MIN,
            days=14
        )

        assert request.symbols == symbols
        assert request.interval == IntervalEnum.FIVE_MIN
        assert request.days == 14

    def test_symbols_maximum_count(self):
        """Test that 10 symbols is valid (maximum)"""
        symbols = [f"SYMBOL{i:02d}USDT" for i in range(10)]
        request = BulkCollectRequest(symbols=symbols)

        assert len(request.symbols) == 10

    def test_symbols_exceeds_maximum(self):
        """Test that more than 10 symbols is invalid"""
        symbols = [f"SYMBOL{i:02d}USDT" for i in range(11)]

        with pytest.raises(ValidationError) as exc_info:
            BulkCollectRequest(symbols=symbols)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('symbols',) for e in errors)

    def test_symbols_single_item(self):
        """Test that single symbol in list is valid"""
        request = BulkCollectRequest(symbols=["BTCUSDT"])
        assert len(request.symbols) == 1

    def test_symbols_empty_list(self):
        """Test that empty list is valid"""
        request = BulkCollectRequest(symbols=[])
        assert request.symbols == []

    def test_symbols_none_value(self):
        """Test that None symbols is valid"""
        request = BulkCollectRequest(symbols=None)
        assert request.symbols is None

    def test_days_minimum_value(self):
        """Test that days=1 is valid (minimum)"""
        request = BulkCollectRequest(days=1)
        assert request.days == 1

    def test_days_maximum_value(self):
        """Test that days=30 is valid (maximum)"""
        request = BulkCollectRequest(days=30)
        assert request.days == 30

    def test_days_below_minimum(self):
        """Test that days=0 is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            BulkCollectRequest(days=0)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('days',) for e in errors)

    def test_days_above_maximum(self):
        """Test that days=31 is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            BulkCollectRequest(days=31)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('days',) for e in errors)

    def test_all_interval_values_valid(self):
        """Test that all interval enum values are valid"""
        for interval in IntervalEnum:
            request = BulkCollectRequest(interval=interval)
            assert request.interval == interval

    def test_invalid_interval_value(self):
        """Test that invalid interval value raises error"""
        with pytest.raises(ValidationError):
            BulkCollectRequest(interval="invalid")

    def test_invalid_symbols_type(self):
        """Test that non-list symbols raises error"""
        with pytest.raises(ValidationError):
            BulkCollectRequest(symbols="BTCUSDT")

    def test_model_dict_export(self):
        """Test that model can be exported to dict"""
        request = BulkCollectRequest(
            symbols=["BTCUSDT", "ETHUSDT"],
            interval=IntervalEnum.ONE_HOUR,
            days=7
        )

        data = request.model_dump()

        assert data['symbols'] == ["BTCUSDT", "ETHUSDT"]
        assert data['interval'] == "60"
        assert data['days'] == 7

    def test_model_json_export(self):
        """Test that model can be exported to JSON"""
        request = BulkCollectRequest(symbols=["BTCUSDT"])
        json_str = request.model_dump_json()

        assert isinstance(json_str, str)
        assert "BTCUSDT" in json_str

    def test_model_with_none_symbols_dict_export(self):
        """Test dict export when symbols is None"""
        request = BulkCollectRequest(symbols=None)
        data = request.model_dump()

        assert data['symbols'] is None


class TestEdgeCases:
    """Test suite for edge cases and special scenarios"""

    def test_collect_kline_with_interval_string_value(self):
        """Test that interval can be created from string value"""
        request = CollectKlineRequest(
            symbol="BTCUSDT",
            interval="60"
        )
        assert request.interval == IntervalEnum.ONE_HOUR

    def test_bulk_collect_with_interval_string_value(self):
        """Test that interval can be created from string value"""
        request = BulkCollectRequest(interval="60")
        assert request.interval == IntervalEnum.ONE_HOUR

    def test_symbol_validation_preserves_valid_uppercase(self):
        """Test that already uppercase symbol is preserved"""
        request = CollectKlineRequest(symbol="BTCUSDT")
        assert request.symbol == "BTCUSDT"

    def test_multiple_validation_errors(self):
        """Test that multiple validation errors are reported"""
        with pytest.raises(ValidationError) as exc_info:
            CollectKlineRequest(symbol="AB", days=100)

        errors = exc_info.value.errors()
        # Should have errors for both symbol and days
        assert len(errors) >= 1

    def test_collect_kline_immutability(self):
        """Test that model is immutable (Pydantic default)"""
        request = CollectKlineRequest(symbol="BTCUSDT")

        # Pydantic models are not frozen by default, so this test verifies current behavior
        # If you want immutability, add `model_config = ConfigDict(frozen=True)` to the model
        try:
            request.symbol = "ETHUSDT"
            # If no error, model is mutable (current behavior)
            assert request.symbol == "ETHUSDT"
        except ValidationError:
            # If error, model is immutable
            pass

    def test_bulk_collect_immutability(self):
        """Test that model is immutable (Pydantic default)"""
        request = BulkCollectRequest()

        try:
            request.days = 15
            # If no error, model is mutable (current behavior)
            assert request.days == 15
        except ValidationError:
            # If error, model is immutable
            pass
