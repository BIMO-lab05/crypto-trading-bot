"""
Unit tests for app.risk.funding_gate (T2.3).

Three layers:
1. funding_gate_decision pure function — every rate × side × threshold combo.
2. FundingRateClient — TTL caching, connector contract, fail-open on errors.
3. (Auto_trader integration is covered separately in test_auto_trader.py.)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.risk.funding_gate import (
    FundingDecision,
    FundingGateConfig,
    FundingRateClient,
    funding_gate_decision,
)


# ---------------------------------------------------------------------------
# funding_gate_decision
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> FundingGateConfig:
    return FundingGateConfig(threshold_bps=5.0)  # 5 bps = 0.0005


class TestFundingGateDecisionLong:
    def test_zero_rate_allows(self, cfg):
        d = funding_gate_decision(0.0, is_long=True, config=cfg)
        assert d.allow is True
        assert d.rate_bps == 0.0

    def test_rate_under_threshold_allows(self, cfg):
        # +3 bps < +5 bps threshold
        d = funding_gate_decision(0.0003, is_long=True, config=cfg)
        assert d.allow is True

    def test_rate_at_threshold_allows(self, cfg):
        # Boundary: rate exactly equals threshold → not strictly greater → allow
        d = funding_gate_decision(0.0005, is_long=True, config=cfg)
        assert d.allow is True

    def test_rate_above_threshold_rejects_long(self, cfg):
        # +10 bps > +5 bps → long would pay → reject
        d = funding_gate_decision(0.0010, is_long=True, config=cfg)
        assert d.allow is False
        assert "long would pay funding" in d.reason
        assert d.rate_bps == pytest.approx(10.0)

    def test_negative_rate_does_not_block_long(self, cfg):
        # Negative rate means shorts pay longs → long is *paid*, allow
        d = funding_gate_decision(-0.0010, is_long=True, config=cfg)
        assert d.allow is True


class TestFundingGateDecisionShort:
    def test_negative_below_threshold_rejects_short(self, cfg):
        # -10 bps < -5 bps → short would pay → reject
        d = funding_gate_decision(-0.0010, is_long=False, config=cfg)
        assert d.allow is False
        assert "short would pay funding" in d.reason

    def test_negative_at_threshold_allows(self, cfg):
        d = funding_gate_decision(-0.0005, is_long=False, config=cfg)
        assert d.allow is True

    def test_positive_rate_does_not_block_short(self, cfg):
        # Positive rate means longs pay shorts → short is *paid*, allow
        d = funding_gate_decision(0.0010, is_long=False, config=cfg)
        assert d.allow is True


class TestFundingGateDegraded:
    def test_none_rate_fails_open(self, cfg):
        d = funding_gate_decision(None, is_long=True, config=cfg)
        assert d.allow is True
        assert "no rate" in d.reason
        assert d.rate_per_period is None
        assert d.rate_bps is None

    def test_insane_rate_fails_open(self, cfg):
        # 10% per settlement is well above Bybit caps → almost certainly bad data
        d = funding_gate_decision(0.10, is_long=True, config=cfg)
        assert d.allow is True
        assert "sanity cap" in d.reason


# ---------------------------------------------------------------------------
# FundingRateClient (mocked httpx)
# ---------------------------------------------------------------------------


def _http_response(payload: dict) -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json = Mock(return_value=payload)
    return resp


@pytest.mark.asyncio
class TestFundingRateClient:
    async def test_fetches_and_returns_signed_rate(self):
        client_mock = Mock()
        client_mock.get = AsyncMock(
            return_value=_http_response(
                {"success": True, "data": [{"fundingRate": "0.0001"}]}
            )
        )
        c = FundingRateClient("http://bybit:8001", FundingGateConfig(), client=client_mock)
        rate = await c.get_latest_rate("BTCUSDT")
        assert rate == 0.0001

    async def test_fetches_negative_rate(self):
        client_mock = Mock()
        client_mock.get = AsyncMock(
            return_value=_http_response(
                {"success": True, "data": [{"fundingRate": "-0.00012"}]}
            )
        )
        c = FundingRateClient("http://bybit:8001", FundingGateConfig(), client=client_mock)
        assert await c.get_latest_rate("BTCUSDT") == -0.00012

    async def test_caches_within_ttl(self):
        client_mock = Mock()
        client_mock.get = AsyncMock(
            return_value=_http_response(
                {"success": True, "data": [{"fundingRate": "0.0002"}]}
            )
        )
        c = FundingRateClient(
            "http://bybit:8001", FundingGateConfig(cache_ttl_seconds=300), client=client_mock
        )
        r1 = await c.get_latest_rate("BTCUSDT")
        r2 = await c.get_latest_rate("BTCUSDT")
        assert r1 == r2 == 0.0002
        # Only one HTTP fetch despite two calls
        assert client_mock.get.call_count == 1

    async def test_separate_symbols_have_separate_cache_entries(self):
        client_mock = Mock()
        client_mock.get = AsyncMock(
            side_effect=[
                _http_response({"success": True, "data": [{"fundingRate": "0.0001"}]}),
                _http_response({"success": True, "data": [{"fundingRate": "-0.0002"}]}),
            ]
        )
        c = FundingRateClient("http://bybit:8001", FundingGateConfig(), client=client_mock)
        assert await c.get_latest_rate("BTCUSDT") == 0.0001
        assert await c.get_latest_rate("SOLUSDT") == -0.0002
        assert client_mock.get.call_count == 2

    async def test_http_error_returns_none_and_caches_miss(self):
        client_mock = Mock()
        client_mock.get = AsyncMock(side_effect=RuntimeError("connection refused"))
        c = FundingRateClient(
            "http://bybit:8001", FundingGateConfig(cache_ttl_seconds=300), client=client_mock
        )
        assert await c.get_latest_rate("BTCUSDT") is None
        # Second call within TTL should not retry — fail-open caching
        assert await c.get_latest_rate("BTCUSDT") is None
        assert client_mock.get.call_count == 1

    async def test_empty_data_returns_none(self):
        client_mock = Mock()
        client_mock.get = AsyncMock(
            return_value=_http_response({"success": True, "data": []})
        )
        c = FundingRateClient("http://bybit:8001", FundingGateConfig(), client=client_mock)
        assert await c.get_latest_rate("BTCUSDT") is None

    async def test_uses_linear_category_param(self):
        client_mock = Mock()
        client_mock.get = AsyncMock(
            return_value=_http_response({"success": True, "data": [{"fundingRate": "0.0"}]})
        )
        c = FundingRateClient("http://bybit:8001", FundingGateConfig(), client=client_mock)
        await c.get_latest_rate("BTCUSDT")
        params = client_mock.get.call_args.kwargs["params"]
        assert params["symbol"] == "BTCUSDT"
        assert params["category"] == "linear"
        assert params["limit"] == 1
