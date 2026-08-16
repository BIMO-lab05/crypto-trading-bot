"""RES-08 — portfolio_id resolves to the canonical portfolio, never "default".

The only portfolio that has ever existed in this deployment is `paper_trading`
(single DB row, is_active=t, PAPER); trading-engine `repositories.py` is already
canonical on it. Before this suite existed, every unparameterized portfolio
endpoint queried a portfolio id (`"default"`) that nothing writes to.

Two failure modes are guarded here, and they pull in opposite directions:

1. Resolution without reseeding. If the endpoints resolve to `paper_trading`
   while `PortfolioManager._create_default_portfolio` keeps seeding under
   `"default"`, `get_portfolio()` (a strict `dict.get`) misses and every route
   regresses from *200-with-an-empty-portfolio* to *404*. The 200 assertions
   below are the guard — a 404 here means the seed key was missed.
2. Aliasing. Resolving an *absent* id to the canonical one must not make an
   *explicitly requested* nonexistent id resolve to it too. `?portfolio_id=nope`
   must still 404.

Note on scope: portfolio-manager never reads the `trades` table, so an empty
`transactions` list is the correct result here and is not what these tests are
measuring. The observable delta is the `portfolio_id` label plus the status code.

This module intentionally carries NO `pytestmark = pytest.mark.skip`.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.portfolio_manager import PortfolioManager

# Must agree with trading-engine repositories.py.
CANONICAL = "paper_trading"


@pytest.fixture
def no_engine_sync():
    """Neutralize the trading-engine round trip.

    `handlers/portfolio.get_portfolio` mirrors the engine book before
    returning. That is a live HTTP call and is not what this suite measures;
    stubbing it True also keeps the `update_prices` fallback from firing.
    The in-memory `get_portfolio` / `get_snapshot` lookups stay real, which is
    what actually proves the seed key.
    """
    with patch.object(
        PortfolioManager, "sync_with_trading_engine", new=AsyncMock(return_value=True)
    ):
        yield


class TestSettingsField:
    def test_default_portfolio_id_is_canonical(self):
        assert settings.default_portfolio_id == CANONICAL

    def test_default_portfolio_id_is_env_overridable(self):
        # pydantic-settings is case-insensitive here, so the field name maps
        # straight to DEFAULT_PORTFOLIO_ID without an explicit alias.
        assert "default_portfolio_id" in type(settings).model_fields


class TestSeedKey:
    """FINDING 1 — the in-memory seed must use the same id the routes resolve to."""

    def test_seed_portfolio_keyed_by_setting(self):
        manager = PortfolioManager()

        assert CANONICAL in manager.portfolios
        assert CANONICAL in manager.transaction_history
        assert manager.portfolios[CANONICAL].portfolio_id == CANONICAL

    def test_dead_literal_is_not_seeded(self):
        manager = PortfolioManager()

        assert "default" not in manager.portfolios
        assert "default" not in manager.transaction_history

    def test_seed_key_follows_the_setting(self, monkeypatch):
        monkeypatch.setattr(settings, "default_portfolio_id", "alt_portfolio")

        manager = PortfolioManager()

        assert "alt_portfolio" in manager.portfolios
        assert CANONICAL not in manager.portfolios


class TestTransactionsResolution:
    """`/api/v1/transactions` touches no network — the cleanest 200-vs-404 probe."""

    def test_unparameterized_call_resolves_and_returns_200(self):
        with TestClient(app) as client:
            response = client.get("/api/v1/transactions")

        assert response.status_code == 200, (
            "404 here means the endpoints resolve to the canonical id but the "
            "in-memory seed is still keyed by the dead literal"
        )
        assert response.json()["portfolio_id"] == CANONICAL

    def test_explicit_id_wins_over_the_default(self):
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/transactions", params={"portfolio_id": CANONICAL}
            )

        assert response.status_code == 200
        assert response.json()["portfolio_id"] == CANONICAL

    def test_explicitly_requested_unknown_portfolio_still_404s(self):
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/transactions", params={"portfolio_id": "nope"}
            )

        assert response.status_code == 404

    def test_dead_literal_is_not_aliased(self):
        """ "default" must not secretly map onto the canonical portfolio."""
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/transactions", params={"portfolio_id": "default"}
            )

        assert response.status_code == 404

    def test_resolution_reads_settings_at_request_time(self, monkeypatch):
        """Proves a body-time read, not a signature default frozen at import."""
        monkeypatch.setattr(settings, "default_portfolio_id", "alt_portfolio")

        with TestClient(app) as client:
            response = client.get("/api/v1/transactions")

        assert response.status_code == 200
        assert response.json()["portfolio_id"] == "alt_portfolio"


class TestPortfolioResolution:
    def test_unparameterized_call_resolves_and_returns_200(self, no_engine_sync):
        with TestClient(app) as client:
            response = client.get("/api/v1/portfolio")

        assert response.status_code == 200
        assert response.json()["portfolio"]["portfolio_id"] == CANONICAL

    def test_explicitly_requested_unknown_portfolio_still_404s(self, no_engine_sync):
        with TestClient(app) as client:
            response = client.get("/api/v1/portfolio", params={"portfolio_id": "nope"})

        assert response.status_code == 404
