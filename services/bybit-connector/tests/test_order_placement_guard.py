"""
SEC-0 regression tests: the connector must refuse to touch the exchange
unless it is explicitly configured for live trading.

Before this guard, POST /api/v1/order/place took no auth dependency and made
no mode check -- it passed straight to the live Bybit REST client. With
BYBIT_TESTNET=false (mainnet), live credentials, and compose publishing port
8001 on 0.0.0.0, a single unauthenticated request bypassed PAPER_TRADING_MODE,
TRADING_MODE, LIVE_TRADING_ACK, the kill switch, the per-trade cap and the
daily-loss breaker -- all of which live in trading-engine, which that route
does not go through.

The property under test is fail-closed: every condition must be explicitly
satisfied, so absent or malformed config refuses.
"""

import pytest

from app.config import Settings


def _settings(**overrides):
    base = dict(
        paper_trading_mode=True,
        trading_mode="PAPER",
        live_trading_ack="",
    )
    base.update(overrides)
    return Settings(**base)


class TestLiveOrdersPermitted:
    def test_defaults_refuse(self):
        """A Settings object with nothing set must not permit live orders."""
        permitted, reason = Settings().live_orders_permitted
        assert permitted is False
        assert reason

    def test_paper_mode_refuses(self):
        permitted, reason = _settings(paper_trading_mode=True).live_orders_permitted
        assert permitted is False
        assert "PAPER_TRADING_MODE" in reason

    def test_paper_trading_off_alone_is_not_enough(self):
        """Clearing one flag must not open the gate -- this is the drift case."""
        permitted, reason = _settings(paper_trading_mode=False).live_orders_permitted
        assert permitted is False
        assert "TRADING_MODE" in reason

    def test_live_mode_without_ack_refuses(self):
        permitted, reason = _settings(
            paper_trading_mode=False, trading_mode="LIVE"
        ).live_orders_permitted
        assert permitted is False
        assert "LIVE_TRADING_ACK" in reason

    def test_wrong_ack_string_refuses(self):
        permitted, reason = _settings(
            paper_trading_mode=False,
            trading_mode="LIVE",
            live_trading_ack="yes",
        ).live_orders_permitted
        assert permitted is False
        assert "LIVE_TRADING_ACK" in reason

    def test_all_three_set_permits(self):
        """The only combination that opens the gate."""
        permitted, reason = _settings(
            paper_trading_mode=False,
            trading_mode="LIVE",
            live_trading_ack="I_UNDERSTAND_REAL_MONEY",
        ).live_orders_permitted
        assert permitted is True
        assert reason == ""


class TestGuardDependency:
    def test_guard_raises_403_in_paper_mode(self, monkeypatch):
        from fastapi import HTTPException
        import app.main as main

        monkeypatch.setattr(main, "get_settings", lambda: _settings())

        with pytest.raises(HTTPException) as exc:
            main.require_live_orders_permitted()

        assert exc.value.status_code == 403
        assert "PAPER_TRADING_MODE" in str(exc.value.detail)

    def test_guard_passes_when_fully_configured_for_live(self, monkeypatch):
        import app.main as main

        monkeypatch.setattr(
            main,
            "get_settings",
            lambda: _settings(
                paper_trading_mode=False,
                trading_mode="LIVE",
                live_trading_ack="I_UNDERSTAND_REAL_MONEY",
            ),
        )

        assert main.require_live_orders_permitted() is None

    def test_order_routes_declare_the_guard(self):
        """
        Both money-touching routes must carry the dependency. A new order route
        added without it silently reintroduces SEC-0.
        """
        import app.main as main

        guarded = set()
        for route in main.app.routes:
            deps = getattr(getattr(route, "dependant", None), "dependencies", [])
            if any(
                getattr(d, "call", None) is main.require_live_orders_permitted
                for d in deps
            ):
                guarded.add(route.path)

        assert "/api/v1/order/place" in guarded
        assert "/api/v1/order/cancel" in guarded
