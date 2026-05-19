"""
Regression tests for the /circuit-breaker route.

Anchors the contract that the route reads DAILY return (not lifetime) and
converts it from percent-form (the portfolio-manager convention) to
fractional-form (what risk_engine.check_circuit_breaker expects).

Bug 2026-05-19: the route read `portfolio.total_return_pct` (lifetime,
percent) and passed it as daily_pnl (treated as fractional inside the
engine). An account at -25% lifetime would produce a phantom
"Daily loss -2507.74% exceeds limit of 5.0%" trip every loop, even on a
flat day. The fix:
  1. Pull `metrics.daily_return_pct` from `/api/v1/performance`.
  2. Divide by 100 to convert percent -> fractional.
  3. Fall back to 0.0 on fetch failure (no signal != loss).
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def cb_route_client(monkeypatch):
    """
    TestClient for the /circuit-breaker route.

    The base ``test_client`` fixture in conftest.py replaces
    ``httpx.AsyncClient`` wholesale and returns a generic
    ``{"status": "healthy"}`` for every GET — which is great for routes
    that only care that the call succeeded, but useless for ones that
    need a specific JSON payload back. This fixture lets each test patch
    ``app.main.fetch_portfolio_data`` and ``app.main.fetch_performance_data``
    directly so the engine sees exactly the (lifetime, daily) pair under
    test.

    It also resets the circuit-breaker state on the singleton engine so
    tests don't bleed state into each other.
    """
    monkeypatch.setenv("HTTP_TIMEOUT", "0.1")

    from app.main import app, get_risk_engine
    from app.models import CircuitBreakerState

    with TestClient(app) as client:
        # The risk engine is created by the FastAPI lifespan startup hook,
        # so it only exists once we've entered the TestClient context.
        engine = get_risk_engine()
        engine.circuit_breaker_state = CircuitBreakerState.CLOSED
        engine.circuit_breaker_active = False
        engine.circuit_breaker_tripped_at = None
        engine.circuit_breaker_cooldown_until = None
        engine.circuit_breaker_failure_count = 0
        engine.circuit_breaker_success_count = 0
        yield client


def _portfolio_payload(*, total_return_pct: float, total_value: float = 7500.0) -> dict:
    return {
        "portfolio": {
            "total_value": total_value,
            "available_balance": total_value * 0.5,
            "total_return_pct": total_return_pct,
            "holdings": [],
        }
    }


def _performance_payload(daily_return_pct: float) -> dict:
    return {
        "success": True,
        "portfolio_id": "default",
        "metrics": {
            "total_return": "0",
            "total_return_pct": "0",
            "daily_return": "0",
            "daily_return_pct": str(daily_return_pct),
        },
    }


@pytest.mark.integration
@pytest.mark.circuit_breaker
class TestCircuitBreakerRouteDailyLossScale:
    """Route-level checks for the daily-loss metric scale + selection."""

    @patch("app.main.fetch_performance_data", new_callable=AsyncMock)
    @patch("app.main.fetch_portfolio_data", new_callable=AsyncMock)
    def test_lifetime_loss_alone_does_not_trip_daily_cb(
        self, mock_fetch_portfolio, mock_fetch_performance, cb_route_client
    ):
        """
        Regression for the 2026-05-19 100x-scale bug.

        Account is down -25% lifetime but flat today (daily 0%). The CB
        must NOT trip on daily-loss — `total_return_pct` is not a daily
        metric.
        """
        mock_fetch_portfolio.return_value = _portfolio_payload(total_return_pct=-25.0)
        mock_fetch_performance.return_value = _performance_payload(daily_return_pct=0.0)

        response = cb_route_client.get("/circuit-breaker")
        assert response.status_code == 200

        data = response.json()
        daily_reasons = [r for r in data.get("reasons", []) if "Daily loss" in r]
        assert daily_reasons == [], (
            "CB tripped on daily-loss when the day was flat. "
            f"Reasons returned: {data.get('reasons')!r}"
        )

    @patch("app.main.fetch_performance_data", new_callable=AsyncMock)
    @patch("app.main.fetch_portfolio_data", new_callable=AsyncMock)
    def test_daily_loss_in_percent_form_is_scaled_to_fractional(
        self, mock_fetch_portfolio, mock_fetch_performance, cb_route_client
    ):
        """
        Daily return -6% (percent form, the portfolio-manager convention)
        must trip the CB (default daily-loss threshold = 5% fractional).
        The displayed value must be ~-6%, not -600%.
        """
        mock_fetch_portfolio.return_value = _portfolio_payload(total_return_pct=0.0)
        mock_fetch_performance.return_value = _performance_payload(
            daily_return_pct=-6.0
        )

        response = cb_route_client.get("/circuit-breaker")
        assert response.status_code == 200

        data = response.json()
        daily_reasons = [r for r in data.get("reasons", []) if "Daily loss" in r]
        assert len(daily_reasons) == 1, (
            "Expected exactly one daily-loss trip reason for daily_return_pct=-6. "
            f"Got: {data.get('reasons')!r}"
        )

        reason = daily_reasons[0]
        assert "-6." in reason, (
            "Daily-loss percentage displayed in the trip reason should be ~-6%, "
            f"got: {reason!r}. A '-600%' or '-6000%' here means the scale fix is "
            "missing — the route is still passing percent-form to the engine."
        )

    @patch("app.main.fetch_performance_data", new_callable=AsyncMock)
    @patch("app.main.fetch_portfolio_data", new_callable=AsyncMock)
    def test_paper_mode_gross_32pct_does_not_trip_exposure_cb(
        self, mock_fetch_portfolio, mock_fetch_performance, cb_route_client
    ):
        """
        Regression for 2026-05-19: paper-mode normal operation must not
        trip the exposure CB.

        5 symbols × ~6.4% positions = 32% gross is the expected operating
        range under ADR-010 (paper per-trade cap 10%, ensemble sizing
        producing 5-8% positions). Old defaults (max_exposure=0.20 → CB
        trip at 0.24) made the CB trip every loop. ADR-017 raised
        max_exposure to 0.50 → CB trip at 0.60 = 60% gross.
        """
        holdings = [
            {
                "symbol": f"{sym}USDT",
                "current_value": 6.4,
                "quantity": 1.0,
                "current_price": 6.4,
            }
            for sym in ("BTC", "ETH", "SOL", "BNB", "ADA")
        ]
        mock_fetch_portfolio.return_value = {
            "portfolio": {
                "total_value": 100.0,
                "available_balance": 68.0,
                "total_return_pct": 0.0,
                "holdings": holdings,
            }
        }
        mock_fetch_performance.return_value = _performance_payload(daily_return_pct=0.0)

        response = cb_route_client.get("/circuit-breaker")
        assert response.status_code == 200

        data = response.json()
        exposure_reasons = [r for r in data.get("reasons", []) if "Exposure" in r]
        assert exposure_reasons == [], (
            "CB tripped on exposure at ~32% gross — must be allowed under paper-mode "
            f"max_exposure=0.50 (CB trips at 0.60). Reasons: {data.get('reasons')!r}"
        )
        assert data["is_tripped"] is False, (
            f"CB tripped at all on normal paper-mode operation. Full response: {data!r}"
        )

    @patch("app.main.fetch_performance_data", new_callable=AsyncMock)
    @patch("app.main.fetch_portfolio_data", new_callable=AsyncMock)
    def test_runaway_gross_above_paper_threshold_still_trips(
        self, mock_fetch_portfolio, mock_fetch_performance, cb_route_client
    ):
        """
        Safety net still fires when gross exposure exceeds the paper-mode
        trip threshold (max_exposure × multiplier = 0.50 × 1.2 = 0.60).
        Raising the limits in ADR-017 must not disable the safety net —
        a 70% gross deployment is still a runaway condition.
        """
        # 7 positions × $10 each = 70% gross of a $100 balance — above CB trip (60%)
        holdings = [
            {
                "symbol": f"SYM{i}USDT",
                "current_value": 10.0,
                "quantity": 1.0,
                "current_price": 10.0,
            }
            for i in range(7)
        ]
        mock_fetch_portfolio.return_value = {
            "portfolio": {
                "total_value": 100.0,
                "available_balance": 30.0,
                "total_return_pct": 0.0,
                "holdings": holdings,
            }
        }
        mock_fetch_performance.return_value = _performance_payload(daily_return_pct=0.0)

        response = cb_route_client.get("/circuit-breaker")
        assert response.status_code == 200

        data = response.json()
        exposure_reasons = [r for r in data.get("reasons", []) if "Exposure" in r]
        assert len(exposure_reasons) >= 1, (
            "Safety-net CB failed to trip on 70% gross exposure. "
            f"Reasons: {data.get('reasons')!r}"
        )

    @patch("app.main.fetch_performance_data", new_callable=AsyncMock)
    @patch("app.main.fetch_portfolio_data", new_callable=AsyncMock)
    def test_performance_fetch_failure_falls_back_to_no_signal(
        self, mock_fetch_portfolio, mock_fetch_performance, cb_route_client
    ):
        """
        If /api/v1/performance is unreachable (returns None), the route
        must default daily_pnl to 0 — a missing daily metric is not a
        daily loss. This prevents a portfolio-manager outage from
        cascading into a false CB trip.
        """
        mock_fetch_portfolio.return_value = _portfolio_payload(total_return_pct=-50.0)
        mock_fetch_performance.return_value = None  # simulate fetch failure

        response = cb_route_client.get("/circuit-breaker")
        assert response.status_code == 200

        data = response.json()
        daily_reasons = [r for r in data.get("reasons", []) if "Daily loss" in r]
        assert daily_reasons == [], (
            "CB tripped on daily-loss after a performance fetch failure. "
            "A missing daily metric must be treated as no-signal, not a loss. "
            f"Reasons returned: {data.get('reasons')!r}"
        )
