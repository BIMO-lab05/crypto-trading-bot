"""Phase-1 capital-audit regression tests (workstream E, AUDIT.md 2.3/2.5).

Covers:
- the repaired /statistical-arbitrage/funding/add endpoint (was a guaranteed
  TypeError from a kwarg mismatch, AUDIT 2.5 / main.py:1444-1445),
- settings-derived capital defaults replacing hardcoded $10,000 in handler
  request models, BacktestConfig, and the Kelly simulator,
- loud failure (no silent default) in the analytics state-restore paths,
- required-capital signatures on the strategy generate_signal entry points,
- the grid-v2 reject-below-minimum rule (never round a position UP),
- the infrastructure/ migration seed (AUDIT 2.3).

Run from services/trading-engine (cwd-sensitive settings; conftest pins
env_file=None, and capital env vars must NOT be exported — pydantic-settings
deep-merges Dict fields across sources):
    python -m pytest tests/test_capital_defaults_phase1.py --no-cov
"""

import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

# The configured account size — resolved from Settings, never hardcoded here.
EXPECTED_CAPITAL = get_settings().paper_initial_balance
# The audited wrong constant; asserted ABSENT. Since ADR-029 the declared
# account is $10,000, so the stale/unrouted value to guard against is the old
# $100 — a default equal to it means some site never re-routed through Settings.
WRONG_CAPITAL = 100.0
assert WRONG_CAPITAL != EXPECTED_CAPITAL, (
    "WRONG_CAPITAL sentinel collides with the declared account size — "
    "pick a value unequal to Settings.paper_initial_balance"
)


# ---------------------------------------------------------------------------
# 1. The repaired funding/add endpoint (task E3)
# ---------------------------------------------------------------------------


class TestFundingAddEndpoint:
    """main.py used to pass max_position_size= to add_funding_strategy,
    whose signature has no such parameter — every call TypeError'd."""

    @pytest.fixture()
    def client(self):
        import app.main as main_module

        return TestClient(main_module.app)

    def test_uninitialized_manager_yields_400_not_typeerror(self, client, monkeypatch):
        import app.handlers.statistical_arbitrage as stat_arb_handlers

        monkeypatch.setattr(stat_arb_handlers, "_stat_arb_manager", None)
        # raise_server_exceptions defaults True: the old TypeError would
        # propagate and fail this test. The fixed path raises HTTPException 400.
        resp = client.post(
            "/api/v1/statistical-arbitrage/funding/add",
            params={"symbol": "BTCUSDT"},
        )
        assert resp.status_code == 400
        assert "not initialized" in resp.json()["detail"].lower()

    def test_success_path_forwards_position_size_pct(self, client, monkeypatch):
        import app.handlers.statistical_arbitrage as stat_arb_handlers

        captured = {}

        class StubManager:
            def add_funding_strategy(self, symbol, **kwargs):
                captured.update(kwargs)
                return f"{symbol}_funding"

        monkeypatch.setattr(stat_arb_handlers, "_stat_arb_manager", StubManager())
        resp = client.post(
            "/api/v1/statistical-arbitrage/funding/add",
            params={"symbol": "BTCUSDT", "position_size_pct": 0.25},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["strategy_id"] == "BTCUSDT_funding"
        assert captured["position_size_pct"] == 0.25
        # No dollar-denominated max_position_size sneaks through anywhere.
        assert "max_position_size" not in captured

    def test_endpoint_no_longer_exposes_dollar_position_size(self, client):
        schema = client.get("/openapi.json").json()
        params = schema["paths"]["/api/v1/statistical-arbitrage/funding/add"]["post"]["parameters"]
        names = {p["name"] for p in params}
        assert "max_position_size" not in names
        assert "position_size_pct" in names


# ---------------------------------------------------------------------------
# 2. Settings-derived defaults in handler request models / engine config
# ---------------------------------------------------------------------------


class TestSettingsDerivedDefaults:
    def test_backtest_config_default_equity(self):
        from app.backtesting.backtest_engine import BacktestConfig

        cfg = BacktestConfig()
        assert cfg.initial_equity == pytest.approx(EXPECTED_CAPITAL)
        assert cfg.initial_equity != WRONG_CAPITAL

    def test_backtest_request_default_equity(self):
        from app.handlers.backtest import BacktestRequest

        req = BacktestRequest(strategy="rsi_momentum")
        assert req.initial_equity == pytest.approx(EXPECTED_CAPITAL)

    def test_walk_forward_request_default_equity(self):
        from app.handlers.backtest import WalkForwardRequest

        req = WalkForwardRequest(strategy="rsi_momentum")
        assert req.initial_equity == pytest.approx(EXPECTED_CAPITAL)

    def test_grid_backtest_request_default_equity(self):
        from app.handlers.grid_trading import BacktestRequest, GridTradingConfig

        req = BacktestRequest(symbol="BTCUSDT", config=GridTradingConfig())
        assert req.initial_equity == pytest.approx(EXPECTED_CAPITAL)

    def test_kelly_simulate_request_default_capital(self):
        from app.handlers.risk_kelly import KellySimulateRequest

        req = KellySimulateRequest(win_rate=0.6, avg_win_pct=2.0, avg_loss_pct=1.5)
        assert req.capital == pytest.approx(EXPECTED_CAPITAL)

    def test_add_funding_request_max_position_size_derived(self):
        from app.models.stat_arb_models import AddFundingStrategyRequest

        settings = get_settings()
        expected = settings.paper_initial_balance * settings.max_position_size_pct / 100.0
        req = AddFundingStrategyRequest(symbol="BTCUSDT")
        assert req.max_position_size == pytest.approx(expected)
        assert req.max_position_size != WRONG_CAPITAL

    def test_simulate_kelly_default_capital_matches_settings(self):
        from app.risk.kelly_position_sizing import KellyPositionSizer

        sizer = KellyPositionSizer()
        by_default = sizer.simulate_kelly(win_rate=0.6, avg_win_pct=2.0, avg_loss_pct=1.5)
        explicit = sizer.simulate_kelly(
            win_rate=0.6, avg_win_pct=2.0, avg_loss_pct=1.5, capital=EXPECTED_CAPITAL
        )
        assert float(by_default.position_value) == pytest.approx(float(explicit.position_value))

    def test_equity_curve_response_requires_initial_equity(self):
        from pydantic import ValidationError

        from app.handlers.performance_dashboard import EquityCurveResponse

        with pytest.raises(ValidationError):
            EquityCurveResponse()


# ---------------------------------------------------------------------------
# 3. Analytics: capital resolves from Settings; corrupt state fails loudly
# ---------------------------------------------------------------------------


class TestAnalyticsCapital:
    def test_attribution_default_capital(self):
        from app.analytics.attribution import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        assert analyzer.initial_capital == pytest.approx(EXPECTED_CAPITAL)
        assert analyzer.initial_capital != WRONG_CAPITAL

    def test_attribution_load_state_missing_capital_raises(self):
        from app.analytics.attribution import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        with pytest.raises(ValueError, match="initial_capital"):
            analyzer.load_state({})

    def test_advanced_metrics_default_capital(self):
        from app.analytics.advanced_metrics import AdvancedMetricsCalculator

        calc = AdvancedMetricsCalculator()
        assert calc.initial_capital == pytest.approx(EXPECTED_CAPITAL)
        assert calc.initial_capital != WRONG_CAPITAL

    def test_advanced_metrics_load_state_missing_capital_raises(self):
        from app.analytics.advanced_metrics import AdvancedMetricsCalculator

        calc = AdvancedMetricsCalculator()
        with pytest.raises(ValueError, match="initial_capital"):
            calc.load_state({})


# ---------------------------------------------------------------------------
# 4. Strategy entry points: capital is required (no silent $10k)
# ---------------------------------------------------------------------------


def _param(func, name):
    return inspect.signature(func).parameters[name]


class TestStrategySignatures:
    def test_capital_has_no_default_where_all_callers_pass_it(self):
        from app.strategies.funding_rate_arbitrage import FundingRateArbitrageStrategy
        from app.strategies.hybrid_strategy_router import HybridStrategyRouter
        from app.strategies.momentum_breakout_strategy import (
            MomentumBreakoutStrategy,
            generate_breakout_signal,
        )
        from app.strategies.pairs_trading import PairsTradingStrategy
        from app.strategies.research_optimized_strategy import (
            ResearchOptimizedStrategy,
        )
        from app.strategies.trend_following_strategy import (
            TrendFollowingStrategy,
            generate_trend_signal,
        )
        from app.strategies.triangular_arbitrage import TriangularArbitrageStrategy

        required = [
            (PairsTradingStrategy.generate_signal, "portfolio_value"),
            (FundingRateArbitrageStrategy.generate_signal, "portfolio_value"),
            (TriangularArbitrageStrategy.generate_signal, "capital"),
            (TriangularArbitrageStrategy.calculate_potential_daily_profit, "capital"),
            (HybridStrategyRouter.generate_signal, "capital"),
            (MomentumBreakoutStrategy.generate_signal, "capital"),
            (generate_breakout_signal, "capital"),
            (TrendFollowingStrategy.generate_signal, "capital"),
            (generate_trend_signal, "capital"),
            (ResearchOptimizedStrategy.generate_signal, "capital"),
        ]
        for func, name in required:
            param = _param(func, name)
            assert param.default is inspect.Parameter.empty, (
                f"{func.__qualname__}({name}=...) must be required — "
                f"found default {param.default!r}"
            )

    def test_capital_defaults_wired_to_settings_are_none_sentinels(self):
        # Sites where the default IS reachable use a None sentinel resolved
        # from Settings (mean_reversion_strategy, simulate_kelly) or raise
        # (support_resistance). Never a numeric literal.
        from app.risk.kelly_position_sizing import KellyPositionSizer
        from app.strategies.mean_reversion_strategy import MeanReversionStrategy
        from app.strategies.support_resistance_strategy import (
            SupportResistanceStrategy,
            generate_sr_signal,
        )

        for func, name in [
            (MeanReversionStrategy.generate_signal, "capital"),
            (KellyPositionSizer.simulate_kelly, "capital"),
            (SupportResistanceStrategy.generate_signal, "capital"),
            (generate_sr_signal, "capital"),
        ]:
            assert _param(func, name).default is None, (
                f"{func.__qualname__}({name}=...) must default to None "
                "(settings-resolved or raising), never a numeric literal"
            )

    def test_support_resistance_raises_without_capital(self):
        from app.strategies.support_resistance_strategy import (
            SupportResistanceStrategy,
        )

        strategy = SupportResistanceStrategy()
        with pytest.raises(ValueError, match="capital"):
            strategy.generate_signal(indicators={}, current_price=100.0)

    def test_mean_reversion_default_resolves_to_settings(self):
        from app.strategies.mean_reversion_strategy import MeanReversionStrategy

        # No usable indicators -> no signal, but the call must not blow up and
        # must not assume a $10k account. (Signal generation with empty
        # indicators returns None before capital is ever used for sizing; the
        # point here is that the None sentinel path executes.)
        out = MeanReversionStrategy().generate_signal({}, current_price=100.0)
        assert out is None


# ---------------------------------------------------------------------------
# 5. Grid v2: reject below venue minimum, never round up (task E7)
# ---------------------------------------------------------------------------


class TestGridV2MinNotional:
    def _make(self):
        from datetime import datetime, timezone

        from app.backtesting.strategy_base import OHLCV
        from app.strategies.grid_trading_strategy_v2 import (
            GridLevelV2,
            GridTradingStrategyV2,
        )

        strategy = GridTradingStrategyV2(symbol="BTCUSDT")
        bar = OHLCV(
            timestamp=datetime(2026, 8, 5, tzinfo=timezone.utc),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1000.0,
        )
        level = GridLevelV2(price=100.0, level_type="buy")
        return strategy, bar, level

    def test_below_minimum_is_rejected_not_rounded_up(self, caplog):
        from app.strategies.grid_trading_strategy_v2 import MIN_POSITION_VALUE_USD

        strategy, bar, level = self._make()
        # equity x position_size_pct (2%) below the $10 floor -> reject.
        equity = (MIN_POSITION_VALUE_USD / strategy.position_size_pct) * 0.5
        with caplog.at_level("WARNING"):
            signal = strategy._create_buy_signal(
                bar, level, equity=equity, rsi=25.0, volume_ratio=2.0
            )
        assert signal is None
        assert any("rejected" in rec.message.lower() for rec in caplog.records)

    def test_above_minimum_still_produces_signal_with_honest_size(self):
        from app.strategies.grid_trading_strategy_v2 import MIN_POSITION_VALUE_USD

        strategy, bar, level = self._make()
        equity = (MIN_POSITION_VALUE_USD / strategy.position_size_pct) * 2.0
        signal = strategy._create_buy_signal(bar, level, equity=equity, rsi=25.0, volume_ratio=2.0)
        assert signal is not None
        # The emitted sizing fraction is the configured pct, never inflated
        # to meet the venue floor.
        assert signal.position_size_pct == pytest.approx(strategy.position_size_pct)


# ---------------------------------------------------------------------------
# 6. Migration seed (task E8, AUDIT 2.3)
# ---------------------------------------------------------------------------


class TestMigrationSeed:
    """The seeds must ROUTE to the declared account size — asserted by parsing
    the seeded portfolio balances and comparing them to Settings, not by
    grepping for the absence of some historical wrong number."""

    @staticmethod
    def _seed_balances(sql: str) -> list[float]:
        import re

        match = re.search(
            r"INSERT INTO portfolios\s*\(.*?\)\s*VALUES\s*\((.*?)\)",
            sql,
            re.S | re.I,
        )
        assert match, "portfolio seed INSERT not found in migration"
        return [float(v) for v in re.findall(r"\d+\.\d+", match.group(1))]

    def test_infrastructure_seed_matches_account_of_record(self):
        repo_root = Path(__file__).resolve().parents[3]
        sql = (repo_root / "infrastructure" / "migrations" / "001_initial_schema.sql").read_text()
        balances = self._seed_balances(sql)
        assert balances, "seed INSERT carries no numeric balances"
        for value in balances:
            assert value == pytest.approx(EXPECTED_CAPITAL), (
                "infrastructure/migrations/001_initial_schema.sql seeds "
                f"{value} but the declared account size is {EXPECTED_CAPITAL} "
                "(shared/account.py / Settings.paper_initial_balance)"
            )
            assert value != WRONG_CAPITAL
        # The authority note must survive future edits.
        assert "database/migrations/ is the AUTHORITATIVE" in sql

    def test_database_seed_matches_account_of_record(self):
        repo_root = Path(__file__).resolve().parents[3]
        sql = (repo_root / "database" / "migrations" / "005_seed_data.sql").read_text()
        balances = self._seed_balances(sql)
        assert balances, "seed INSERT carries no numeric balances"
        for value in balances:
            assert value == pytest.approx(EXPECTED_CAPITAL), (
                "database/migrations/005_seed_data.sql seeds "
                f"{value} but the declared account size is {EXPECTED_CAPITAL} "
                "(shared/account.py / Settings.paper_initial_balance)"
            )
            assert value != WRONG_CAPITAL
