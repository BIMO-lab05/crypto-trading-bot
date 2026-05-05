"""
Bybit Connector Service - Models Tests
Purpose: Comprehensive tests for Pydantic models and input validation
"""

import pytest
from pydantic import ValidationError

from app.models import (
    OrderSide,
    OrderType,
    TimeInForce,
    Category,
    PlaceOrderRequest,
    CancelOrderRequest,
    OrderResponse,
    BalanceResponse
)


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestEnums:
    """Test enum values and validation"""

    def test_order_side_enum_values(self):
        """Test OrderSide enum has correct values"""
        # Then OrderSide enum has Buy and Sell
        assert OrderSide.BUY.value == "Buy"
        assert OrderSide.SELL.value == "Sell"
        assert len(OrderSide) == 2

    def test_order_type_enum_values(self):
        """Test OrderType enum has correct values"""
        # Then OrderType enum has Market and Limit
        assert OrderType.MARKET.value == "Market"
        assert OrderType.LIMIT.value == "Limit"
        assert len(OrderType) == 2

    def test_time_in_force_enum_values(self):
        """Test TimeInForce enum has correct values"""
        # Then TimeInForce enum has all valid values
        assert TimeInForce.GTC.value == "GTC"
        assert TimeInForce.IOC.value == "IOC"
        assert TimeInForce.FOK.value == "FOK"
        assert TimeInForce.POST_ONLY.value == "PostOnly"
        assert len(TimeInForce) == 4

    def test_category_enum_values(self):
        """Test Category enum has correct values"""
        # Then Category enum has all trading categories
        assert Category.LINEAR.value == "linear"
        assert Category.INVERSE.value == "inverse"
        assert Category.OPTION.value == "option"
        assert Category.SPOT.value == "spot"
        assert len(Category) == 4


# ============================================================================
# PLACE ORDER REQUEST TESTS
# ============================================================================

class TestPlaceOrderRequestValidation:
    """Test PlaceOrderRequest model validation"""

    def test_place_order_request_valid_limit_order(self):
        """Test creating valid limit order request"""
        # Given valid limit order data
        order_data = {
            "category": Category.LINEAR,
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.LIMIT,
            "qty": "0.01",
            "price": "50000",
            "time_in_force": TimeInForce.GTC
        }

        # When creating order request
        order = PlaceOrderRequest(**order_data)

        # Then order is created successfully
        assert order.symbol == "BTCUSDT"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.qty == "0.01"
        assert order.price == "50000"
        assert order.time_in_force == TimeInForce.GTC
        assert order.reduce_only is False

    def test_place_order_request_valid_market_order(self):
        """Test creating valid market order request"""
        # Given valid market order data
        order_data = {
            "symbol": "ETHUSDT",
            "side": OrderSide.SELL,
            "order_type": OrderType.MARKET,
            "qty": "0.5"
        }

        # When creating order request
        order = PlaceOrderRequest(**order_data)

        # Then order is created with defaults
        assert order.symbol == "ETHUSDT"
        assert order.side == OrderSide.SELL
        assert order.order_type == OrderType.MARKET
        assert order.qty == "0.5"
        assert order.price is None
        assert order.category == Category.LINEAR  # default

    def test_place_order_request_symbol_uppercase(self):
        """Test symbol is converted to uppercase"""
        # Given order data with lowercase symbol
        order_data = {
            "symbol": "btcusdt",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "0.01"
        }

        # When creating order request
        order = PlaceOrderRequest(**order_data)

        # Then symbol is uppercase
        assert order.symbol == "BTCUSDT"

    def test_place_order_request_invalid_symbol_too_short(self):
        """Test validation fails with too short symbol"""
        # Given order data with short symbol
        order_data = {
            "symbol": "BTC",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "0.01"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("symbol" in str(e["loc"]) for e in errors)

    def test_place_order_request_invalid_symbol_special_chars(self):
        """Test validation fails with invalid symbol characters"""
        # Given order data with special characters
        order_data = {
            "symbol": "BTC@USDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "0.01"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("Symbol must be alphanumeric" in str(e) for e in errors)

    def test_place_order_request_negative_quantity(self):
        """Test validation fails with negative quantity"""
        # Given order data with negative quantity
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "-0.01"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("Quantity must be positive" in str(e) for e in errors)

    def test_place_order_request_zero_quantity(self):
        """Test validation fails with zero quantity"""
        # Given order data with zero quantity
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "0"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("Quantity must be positive" in str(e) for e in errors)

    def test_place_order_request_invalid_quantity_format(self):
        """Test validation fails with invalid quantity format"""
        # Given order data with invalid quantity
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "abc"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("Quantity must be a valid positive number" in str(e) for e in errors)

    def test_place_order_request_negative_price(self):
        """Test validation fails with negative price"""
        # Given order data with negative price
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.LIMIT,
            "qty": "0.01",
            "price": "-50000"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("Price must be positive" in str(e) for e in errors)

    def test_place_order_request_zero_price(self):
        """Test validation fails with zero price"""
        # Given order data with zero price
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.LIMIT,
            "qty": "0.01",
            "price": "0"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("Price must be positive" in str(e) for e in errors)

    def test_place_order_request_invalid_price_format(self):
        """Test validation fails with invalid price format"""
        # Given order data with invalid price
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.LIMIT,
            "qty": "0.01",
            "price": "fifty thousand"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("Price must be a valid positive number" in str(e) for e in errors)

    def test_place_order_request_limit_order_without_price(self):
        """Test limit order validation fails without price"""
        # Given limit order data without price
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.LIMIT,
            "qty": "0.01"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("Limit orders require a price" in str(e) for e in errors)

    def test_place_order_request_market_order_ignores_price(self):
        """Test market order can be created without price"""
        # Given market order data without price
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "0.01"
        }

        # When creating order request
        order = PlaceOrderRequest(**order_data)

        # Then order is created successfully
        assert order.price is None

    def test_place_order_request_with_order_link_id(self):
        """Test order request with custom order link ID"""
        # Given order data with order_link_id
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "0.01",
            "order_link_id": "my-order-123"
        }

        # When creating order request
        order = PlaceOrderRequest(**order_data)

        # Then order_link_id is set
        assert order.order_link_id == "my-order-123"

    def test_place_order_request_order_link_id_too_long(self):
        """Test validation fails with too long order_link_id"""
        # Given order data with long order_link_id
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "0.01",
            "order_link_id": "a" * 37  # Max is 36
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("order_link_id" in str(e["loc"]) for e in errors)

    def test_place_order_request_reduce_only_flag(self):
        """Test order request with reduce_only flag"""
        # Given order data with reduce_only
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.SELL,
            "order_type": OrderType.MARKET,
            "qty": "0.01",
            "reduce_only": True
        }

        # When creating order request
        order = PlaceOrderRequest(**order_data)

        # Then reduce_only is set
        assert order.reduce_only is True

    def test_place_order_request_all_time_in_force_values(self):
        """Test order request with different time_in_force values"""
        # Given order data with each time_in_force
        for tif in TimeInForce:
            order_data = {
                "symbol": "BTCUSDT",
                "side": OrderSide.BUY,
                "order_type": OrderType.LIMIT,
                "qty": "0.01",
                "price": "50000",
                "time_in_force": tif
            }

            # When creating order request
            order = PlaceOrderRequest(**order_data)

            # Then time_in_force is set correctly
            assert order.time_in_force == tif

    def test_place_order_request_all_categories(self):
        """Test order request with different categories"""
        # Given order data with each category
        for cat in Category:
            order_data = {
                "category": cat,
                "symbol": "BTCUSDT",
                "side": OrderSide.BUY,
                "order_type": OrderType.MARKET,
                "qty": "0.01"
            }

            # When creating order request
            order = PlaceOrderRequest(**order_data)

            # Then category is set correctly
            assert order.category == cat

    def test_place_order_request_invalid_side(self):
        """Test validation fails with invalid order side"""
        # Given order data with invalid side
        order_data = {
            "symbol": "BTCUSDT",
            "side": "InvalidSide",
            "order_type": OrderType.MARKET,
            "qty": "0.01"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("side" in str(e["loc"]) for e in errors)

    def test_place_order_request_invalid_order_type(self):
        """Test validation fails with invalid order type"""
        # Given order data with invalid order_type
        order_data = {
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "order_type": "InvalidType",
            "qty": "0.01"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        assert any("order_type" in str(e["loc"]) for e in errors)

    def test_place_order_request_missing_required_fields(self):
        """Test validation fails with missing required fields"""
        # Given order data without required fields
        order_data = {
            "symbol": "BTCUSDT"
        }

        # When/Then creating order request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            PlaceOrderRequest(**order_data)

        errors = exc_info.value.errors()
        # Should fail on missing side, order_type, qty
        assert len(errors) >= 3


# ============================================================================
# CANCEL ORDER REQUEST TESTS
# ============================================================================

class TestCancelOrderRequestValidation:
    """Test CancelOrderRequest model validation"""

    def test_cancel_order_request_with_order_id(self):
        """Test creating cancel request with order_id"""
        # Given cancel request data with order_id
        cancel_data = {
            "category": Category.LINEAR,
            "symbol": "BTCUSDT",
            "order_id": "order-123"
        }

        # When creating cancel request
        cancel = CancelOrderRequest(**cancel_data)

        # Then cancel request is created
        assert cancel.symbol == "BTCUSDT"
        assert cancel.order_id == "order-123"
        assert cancel.order_link_id is None

    def test_cancel_order_request_with_order_link_id(self):
        """Test creating cancel request with order_link_id"""
        # Given cancel request data with order_link_id
        cancel_data = {
            "symbol": "ETHUSDT",
            "order_link_id": "my-order-456"
        }

        # When creating cancel request
        cancel = CancelOrderRequest(**cancel_data)

        # Then cancel request is created
        assert cancel.symbol == "ETHUSDT"
        assert cancel.order_id is None
        assert cancel.order_link_id == "my-order-456"

    def test_cancel_order_request_with_both_ids(self):
        """Test creating cancel request with both IDs"""
        # Given cancel request data with both IDs
        cancel_data = {
            "symbol": "BTCUSDT",
            "order_id": "order-123",
            "order_link_id": "my-order-123"
        }

        # When creating cancel request
        cancel = CancelOrderRequest(**cancel_data)

        # Then both IDs are set
        assert cancel.order_id == "order-123"
        assert cancel.order_link_id == "my-order-123"

    def test_cancel_order_request_without_ids(self):
        """Test validation fails when no IDs provided"""
        # Given cancel request data without IDs
        cancel_data = {
            "symbol": "BTCUSDT"
        }

        # When/Then creating cancel request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            CancelOrderRequest(**cancel_data)

        errors = exc_info.value.errors()
        assert any("Either order_id or order_link_id must be provided" in str(e) for e in errors)

    def test_cancel_order_request_symbol_uppercase(self):
        """Test symbol is converted to uppercase"""
        # Given cancel request with lowercase symbol
        cancel_data = {
            "symbol": "btcusdt",
            "order_id": "order-123"
        }

        # When creating cancel request
        cancel = CancelOrderRequest(**cancel_data)

        # Then symbol is uppercase
        assert cancel.symbol == "BTCUSDT"

    def test_cancel_order_request_invalid_symbol_too_short(self):
        """Test validation fails with too short symbol"""
        # Given cancel request with short symbol
        cancel_data = {
            "symbol": "BTC",
            "order_id": "order-123"
        }

        # When/Then creating cancel request raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            CancelOrderRequest(**cancel_data)

        errors = exc_info.value.errors()
        assert any("symbol" in str(e["loc"]) for e in errors)

    def test_cancel_order_request_default_category(self):
        """Test cancel request uses default category"""
        # Given cancel request without category
        cancel_data = {
            "symbol": "BTCUSDT",
            "order_id": "order-123"
        }

        # When creating cancel request
        cancel = CancelOrderRequest(**cancel_data)

        # Then default category is used
        assert cancel.category == Category.LINEAR

    def test_cancel_order_request_all_categories(self):
        """Test cancel request with different categories"""
        # Given cancel request data with each category
        for cat in Category:
            cancel_data = {
                "category": cat,
                "symbol": "BTCUSDT",
                "order_id": "order-123"
            }

            # When creating cancel request
            cancel = CancelOrderRequest(**cancel_data)

            # Then category is set correctly
            assert cancel.category == cat


# ============================================================================
# RESPONSE MODEL TESTS
# ============================================================================

class TestOrderResponse:
    """Test OrderResponse model"""

    def test_order_response_minimal_data(self):
        """Test creating order response with minimal data"""
        # Given minimal order response data
        response_data = {
            "order_id": "order-123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Limit",
            "qty": "0.01",
            "status": "New"
        }

        # When creating response
        response = OrderResponse(**response_data)

        # Then response is created
        assert response.order_id == "order-123"
        assert response.symbol == "BTCUSDT"
        assert response.side == "Buy"
        assert response.order_type == "Limit"
        assert response.qty == "0.01"
        assert response.status == "New"
        assert response.price is None
        assert response.order_link_id is None

    def test_order_response_with_all_fields(self):
        """Test creating order response with all fields"""
        # Given complete order response data
        response_data = {
            "order_id": "order-123",
            "order_link_id": "my-order-123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Limit",
            "qty": "0.01",
            "price": "50000",
            "status": "Filled"
        }

        # When creating response
        response = OrderResponse(**response_data)

        # Then all fields are set
        assert response.order_id == "order-123"
        assert response.order_link_id == "my-order-123"
        assert response.price == "50000"
        assert response.status == "Filled"

    def test_order_response_allows_extra_fields(self):
        """Test OrderResponse allows additional fields from Bybit"""
        # Given response data with extra fields
        response_data = {
            "order_id": "order-123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "order_type": "Limit",
            "qty": "0.01",
            "status": "New",
            "created_time": "1234567890",
            "updated_time": "1234567891",
            "extra_field": "extra_value"
        }

        # When creating response
        response = OrderResponse(**response_data)

        # Then response is created without error
        assert response.order_id == "order-123"


class TestBalanceResponse:
    """Test BalanceResponse model"""

    def test_balance_response_minimal_data(self):
        """Test creating balance response with minimal data"""
        # Given empty balance response
        response_data = {}

        # When creating response
        response = BalanceResponse(**response_data)

        # Then response is created with None values
        assert response.total_equity is None
        assert response.available_balance is None
        assert response.used_margin is None

    def test_balance_response_with_all_fields(self):
        """Test creating balance response with all fields"""
        # Given complete balance response data
        response_data = {
            "total_equity": "10000.50",
            "available_balance": "8000.25",
            "used_margin": "2000.25"
        }

        # When creating response
        response = BalanceResponse(**response_data)

        # Then all fields are set
        assert response.total_equity == "10000.50"
        assert response.available_balance == "8000.25"
        assert response.used_margin == "2000.25"

    def test_balance_response_allows_extra_fields(self):
        """Test BalanceResponse allows additional fields from Bybit"""
        # Given response data with extra fields
        response_data = {
            "total_equity": "10000",
            "unrealized_pnl": "500",
            "wallet_balance": "9500",
            "extra_field": "extra_value"
        }

        # When creating response
        response = BalanceResponse(**response_data)

        # Then response is created without error
        assert response.total_equity == "10000"


# ============================================================================
# CONDITIONAL / BRACKET ORDER FIELD TESTS (Phase A5)
# ============================================================================

class TestConditionalOrderFields:
    """Validation for take_profit / stop_loss / tpsl_mode / trigger_* fields"""

    def _base_kwargs(self):
        return {
            "category": Category.LINEAR,
            "symbol": "SOLUSDT",
            "side": OrderSide.BUY,
            "order_type": OrderType.MARKET,
            "qty": "0.1",
        }

    def test_take_profit_and_stop_loss_accepted(self):
        order = PlaceOrderRequest(
            **self._base_kwargs(),
            take_profit="160",
            stop_loss="140",
            tpsl_mode="Full",
        )
        assert order.take_profit == "160"
        assert order.stop_loss == "140"
        assert order.tpsl_mode == "Full"

    def test_negative_stop_loss_rejected(self):
        with pytest.raises(ValidationError):
            PlaceOrderRequest(**self._base_kwargs(), stop_loss="-1")

    def test_invalid_tpsl_mode_rejected(self):
        with pytest.raises(ValidationError):
            PlaceOrderRequest(**self._base_kwargs(), tpsl_mode="HalfBaked")

    def test_trigger_price_without_direction_rejected(self):
        with pytest.raises(ValidationError):
            PlaceOrderRequest(**self._base_kwargs(), trigger_price="155")

    def test_trigger_direction_without_price_rejected(self):
        with pytest.raises(ValidationError):
            PlaceOrderRequest(**self._base_kwargs(), trigger_direction=1)

    def test_invalid_trigger_direction_rejected(self):
        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                **self._base_kwargs(),
                trigger_price="155",
                trigger_direction=3,
            )

    def test_complete_conditional_order_accepted(self):
        order = PlaceOrderRequest(
            **self._base_kwargs(),
            trigger_price="155",
            trigger_direction=1,
        )
        assert order.trigger_price == "155"
        assert order.trigger_direction == 1
