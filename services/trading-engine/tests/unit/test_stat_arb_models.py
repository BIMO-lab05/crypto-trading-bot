"""
Unit tests for Statistical Arbitrage Pydantic models
Tests validation logic for all request/response models
"""

import pytest
from pydantic import ValidationError
from app.models.stat_arb_models import (
    InitializeManagerRequest,
    AddPairsStrategyRequest,
    CalibratePairsStrategyRequest,
    AddFundingStrategyRequest,
    SetupTriangularArbitrageRequest,
    GenerateSignalsRequest,
)


class TestInitializeManagerRequest:
    """Tests for InitializeManagerRequest model"""

    def test_valid_initialization(self):
        """Test valid initialization request"""
        request = InitializeManagerRequest(
            total_capital=100000.0,
            pairs_allocation=0.4,
            funding_allocation=0.4,
            triangular_allocation=0.2
        )

        assert request.total_capital == 100000.0
        assert request.pairs_allocation == 0.4
        assert request.funding_allocation == 0.4
        assert request.triangular_allocation == 0.2

    def test_default_values(self):
        """Test default values are applied correctly"""
        request = InitializeManagerRequest()

        assert request.total_capital == 100000.0
        assert request.pairs_allocation == 0.4
        assert request.funding_allocation == 0.4
        assert request.triangular_allocation == 0.2

    def test_invalid_negative_capital(self):
        """Test validation fails for negative capital"""
        with pytest.raises(ValidationError) as exc:
            InitializeManagerRequest(total_capital=-10000.0)

        errors = exc.value.errors()
        assert any('greater than 0' in str(e['msg']).lower() for e in errors)

    def test_invalid_allocation_sum_too_low(self):
        """Test validation fails when allocations sum to less than 1.0"""
        with pytest.raises(ValidationError) as exc:
            InitializeManagerRequest(
                pairs_allocation=0.3,
                funding_allocation=0.3,
                triangular_allocation=0.3  # Sum = 0.9
            )

        errors = exc.value.errors()
        assert any('must sum to 1.0' in str(e['msg']).lower() for e in errors)

    def test_invalid_allocation_sum_too_high(self):
        """Test validation fails when allocations sum to more than 1.0"""
        with pytest.raises(ValidationError) as exc:
            InitializeManagerRequest(
                pairs_allocation=0.5,
                funding_allocation=0.5,
                triangular_allocation=0.2  # Sum = 1.2
            )

        errors = exc.value.errors()
        assert any('must sum to 1.0' in str(e['msg']).lower() for e in errors)

    def test_invalid_allocation_out_of_range(self):
        """Test validation fails for allocation > 1.0"""
        with pytest.raises(ValidationError) as exc:
            InitializeManagerRequest(
                pairs_allocation=1.5,  # > 1.0
                funding_allocation=0.0,
                triangular_allocation=-0.5
            )

        errors = exc.value.errors()
        assert len(errors) > 0

    def test_allocation_sum_within_tolerance(self):
        """Test allocations are accepted within tolerance (±0.001)"""
        # Should pass: sum = 0.9999
        request = InitializeManagerRequest(
            pairs_allocation=0.3333,
            funding_allocation=0.3333,
            triangular_allocation=0.3333
        )
        assert request is not None


class TestAddPairsStrategyRequest:
    """Tests for AddPairsStrategyRequest model"""

    def test_valid_pairs_strategy(self):
        """Test valid pairs strategy request"""
        request = AddPairsStrategyRequest(
            symbol_x="BTCUSDT",
            symbol_y="ETHUSDT",
            entry_threshold=2.0,
            exit_threshold=0.5
        )

        assert request.symbol_x == "BTCUSDT"
        assert request.symbol_y == "ETHUSDT"
        assert request.entry_threshold == 2.0
        assert request.exit_threshold == 0.5

    def test_symbol_case_normalization(self):
        """Test symbols are converted to uppercase"""
        request = AddPairsStrategyRequest(
            symbol_x="btcusdt",
            symbol_y="ethusdt"
        )

        assert request.symbol_x == "BTCUSDT"
        assert request.symbol_y == "ETHUSDT"

    def test_invalid_symbol_too_short(self):
        """Test validation fails for symbols < 3 characters"""
        with pytest.raises(ValidationError) as exc:
            AddPairsStrategyRequest(
                symbol_x="BT",  # Too short
                symbol_y="ETHUSDT"
            )

        errors = exc.value.errors()
        assert any('invalid symbol' in str(e['msg']).lower() for e in errors)

    def test_invalid_exit_greater_than_entry(self):
        """Test validation fails when exit > entry threshold"""
        with pytest.raises(ValidationError) as exc:
            AddPairsStrategyRequest(
                symbol_x="BTCUSDT",
                symbol_y="ETHUSDT",
                entry_threshold=1.0,
                exit_threshold=2.0  # Greater than entry
            )

        errors = exc.value.errors()
        assert any('must be less than entry' in str(e['msg']).lower() for e in errors)

    def test_default_values(self):
        """Test default parameter values"""
        request = AddPairsStrategyRequest(
            symbol_x="BTCUSDT",
            symbol_y="ETHUSDT"
        )

        assert request.entry_threshold == 2.0
        assert request.exit_threshold == 0.5
        assert request.lookback_period == 20
        assert request.stop_loss_z == 3.0

    def test_invalid_negative_threshold(self):
        """Test validation fails for negative thresholds"""
        with pytest.raises(ValidationError) as exc:
            AddPairsStrategyRequest(
                symbol_x="BTCUSDT",
                symbol_y="ETHUSDT",
                entry_threshold=-2.0
            )

        errors = exc.value.errors()
        assert len(errors) > 0

    def test_valid_tight_thresholds(self):
        """Test very tight but valid thresholds"""
        request = AddPairsStrategyRequest(
            symbol_x="BTCUSDT",
            symbol_y="ETHUSDT",
            entry_threshold=0.2,
            exit_threshold=0.1
        )

        assert request.entry_threshold == 0.2
        assert request.exit_threshold == 0.1


class TestCalibratePairsStrategyRequest:
    """Tests for CalibratePairsStrategyRequest model"""

    def test_valid_calibration_request(self):
        """Test valid calibration request"""
        request = CalibratePairsStrategyRequest(
            strategy_id="BTCUSDT_ETHUSDT",
            historical_data={
                "BTCUSDT": [45000, 45100],
                "ETHUSDT": [3000, 3010]
            }
        )

        assert request.strategy_id == "BTCUSDT_ETHUSDT"
        assert "BTCUSDT" in request.historical_data

    def test_optional_historical_data(self):
        """Test historical_data is optional"""
        request = CalibratePairsStrategyRequest(
            strategy_id="BTCUSDT_ETHUSDT"
        )

        assert request.strategy_id == "BTCUSDT_ETHUSDT"
        assert request.historical_data is None


class TestAddFundingStrategyRequest:
    """Tests for AddFundingStrategyRequest model"""

    def test_valid_funding_strategy(self):
        """Test valid funding strategy request"""
        request = AddFundingStrategyRequest(
            symbol="BTCUSDT",
            min_funding_rate=0.0001,
            max_position_size=10000.0
        )

        assert request.symbol == "BTCUSDT"
        assert request.min_funding_rate == 0.0001
        assert request.max_position_size == 10000.0

    def test_symbol_normalization(self):
        """Test symbol is converted to uppercase"""
        request = AddFundingStrategyRequest(
            symbol="btcusdt"
        )

        assert request.symbol == "BTCUSDT"

    def test_default_values(self):
        """Test default parameter values"""
        request = AddFundingStrategyRequest(
            symbol="BTCUSDT"
        )

        assert request.min_funding_rate == 0.0001
        assert request.max_position_size == 10000.0

    def test_invalid_negative_funding_rate(self):
        """Test validation fails for negative funding rate"""
        with pytest.raises(ValidationError) as exc:
            AddFundingStrategyRequest(
                symbol="BTCUSDT",
                min_funding_rate=-0.0001
            )

        errors = exc.value.errors()
        assert len(errors) > 0

    def test_invalid_zero_position_size(self):
        """Test validation fails for zero position size"""
        with pytest.raises(ValidationError) as exc:
            AddFundingStrategyRequest(
                symbol="BTCUSDT",
                max_position_size=0.0
            )

        errors = exc.value.errors()
        assert any('greater than 0' in str(e['msg']).lower() for e in errors)


class TestSetupTriangularArbitrageRequest:
    """Tests for SetupTriangularArbitrageRequest model"""

    def test_valid_triangular_setup(self):
        """Test valid triangular arbitrage setup"""
        request = SetupTriangularArbitrageRequest(
            assets=["BTC", "ETH", "BNB", "USDT"],
            min_profit_threshold=0.005,
            max_latency_ms=100.0
        )

        assert len(request.assets) == 4
        assert request.min_profit_threshold == 0.005
        assert request.max_latency_ms == 100.0

    def test_assets_case_normalization(self):
        """Test assets are converted to uppercase"""
        request = SetupTriangularArbitrageRequest(
            assets=["btc", "eth", "bnb"]
        )

        assert all(asset.isupper() for asset in request.assets)
        assert "BTC" in request.assets

    def test_duplicate_assets_removed(self):
        """Test duplicate assets are detected"""
        with pytest.raises(ValidationError) as exc:
            SetupTriangularArbitrageRequest(
                assets=["BTC", "ETH", "BTC"]  # Duplicate
            )

        errors = exc.value.errors()
        assert any('duplicate' in str(e['msg']).lower() for e in errors)

    def test_insufficient_assets(self):
        """Test validation fails with < 3 assets"""
        with pytest.raises(ValidationError) as exc:
            SetupTriangularArbitrageRequest(
                assets=["BTC", "ETH"]  # Only 2
            )

        errors = exc.value.errors()
        assert any('at least 3' in str(e['msg']).lower() for e in errors)

    def test_default_values(self):
        """Test default parameter values"""
        request = SetupTriangularArbitrageRequest(
            assets=["BTC", "ETH", "BNB"]
        )

        assert request.min_profit_threshold == 0.005
        assert request.max_latency_ms == 100.0

    def test_invalid_profit_threshold_out_of_range(self):
        """Test validation fails for profit threshold > 1.0"""
        with pytest.raises(ValidationError) as exc:
            SetupTriangularArbitrageRequest(
                assets=["BTC", "ETH", "BNB"],
                min_profit_threshold=1.5  # > 1.0
            )

        errors = exc.value.errors()
        assert len(errors) > 0


class TestGenerateSignalsRequest:
    """Tests for GenerateSignalsRequest model"""

    def test_valid_market_data(self):
        """Test valid market data"""
        request = GenerateSignalsRequest(
            market_data={
                "BTCUSDT": {"price": 45000.0, "volume": 1000000},
                "ETHUSDT": {"price": 3000.0, "volume": 500000}
            }
        )

        assert "BTCUSDT" in request.market_data
        assert request.market_data["BTCUSDT"]["price"] == 45000.0

    def test_invalid_empty_market_data(self):
        """Test validation fails for empty market data"""
        with pytest.raises(ValidationError) as exc:
            GenerateSignalsRequest(market_data={})

        errors = exc.value.errors()
        assert any('cannot be empty' in str(e['msg']).lower() for e in errors)

    def test_invalid_missing_price(self):
        """Test validation fails when price is missing"""
        with pytest.raises(ValidationError) as exc:
            GenerateSignalsRequest(
                market_data={
                    "BTCUSDT": {"volume": 1000000}  # Missing 'price'
                }
            )

        errors = exc.value.errors()
        assert any('price missing' in str(e['msg']).lower() for e in errors)

    def test_invalid_negative_price(self):
        """Test validation fails for negative price"""
        with pytest.raises(ValidationError) as exc:
            GenerateSignalsRequest(
                market_data={
                    "BTCUSDT": {"price": -45000.0}
                }
            )

        errors = exc.value.errors()
        assert any('invalid price' in str(e['msg']).lower() for e in errors)

    def test_invalid_zero_price(self):
        """Test validation fails for zero price"""
        with pytest.raises(ValidationError) as exc:
            GenerateSignalsRequest(
                market_data={
                    "BTCUSDT": {"price": 0.0}
                }
            )

        errors = exc.value.errors()
        assert any('invalid price' in str(e['msg']).lower() for e in errors)

    def test_market_data_with_additional_fields(self):
        """Test market data accepts additional fields"""
        request = GenerateSignalsRequest(
            market_data={
                "BTCUSDT": {
                    "price": 45000.0,
                    "volume": 1000000,
                    "funding_rate": 0.0001,
                    "bid": 44999.0,
                    "ask": 45001.0
                }
            }
        )

        assert request.market_data["BTCUSDT"]["price"] == 45000.0
        assert "funding_rate" in request.market_data["BTCUSDT"]


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_very_large_capital(self):
        """Test very large capital value"""
        request = InitializeManagerRequest(
            total_capital=1_000_000_000.0  # $1 billion
        )
        assert request.total_capital == 1_000_000_000.0

    def test_very_small_capital(self):
        """Test very small but positive capital"""
        request = InitializeManagerRequest(
            total_capital=0.01  # 1 cent
        )
        assert request.total_capital == 0.01

    def test_extreme_allocation_split(self):
        """Test extreme but valid allocation split"""
        request = InitializeManagerRequest(
            pairs_allocation=0.99,
            funding_allocation=0.005,
            triangular_allocation=0.005
        )
        assert request.pairs_allocation == 0.99

    def test_very_tight_entry_exit_thresholds(self):
        """Test very tight thresholds"""
        request = AddPairsStrategyRequest(
            symbol_x="BTCUSDT",
            symbol_y="ETHUSDT",
            entry_threshold=0.01,
            exit_threshold=0.001
        )
        assert request.entry_threshold == 0.01

    def test_very_large_lookback_period(self):
        """Test very large lookback period"""
        request = AddPairsStrategyRequest(
            symbol_x="BTCUSDT",
            symbol_y="ETHUSDT",
            lookback_period=1000
        )
        assert request.lookback_period == 1000

    def test_many_assets_triangular(self):
        """Test triangular arbitrage with many assets"""
        assets = [f"ASSET{i}" for i in range(10)]
        request = SetupTriangularArbitrageRequest(
            assets=assets
        )
        assert len(request.assets) == 10

    def test_very_strict_latency_requirement(self):
        """Test very strict latency requirement"""
        request = SetupTriangularArbitrageRequest(
            assets=["BTC", "ETH", "USDT"],
            max_latency_ms=1.0  # 1ms
        )
        assert request.max_latency_ms == 1.0

    def test_very_high_profit_threshold(self):
        """Test very high profit threshold"""
        request = SetupTriangularArbitrageRequest(
            assets=["BTC", "ETH", "USDT"],
            min_profit_threshold=0.5  # 50%
        )
        assert request.min_profit_threshold == 0.5
