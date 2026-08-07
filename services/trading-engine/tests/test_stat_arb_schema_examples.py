"""
The stat-arb OpenAPI examples must actually render, and must not document an
account size or an edge that does not exist.

Two defects, one file:

* The module is Pydantic v2 (field_validator / ValidationInfo) but declared its
  examples with the v1 idiom ``class Config: schema_extra``. Pydantic v2
  IGNORES that silently, so every example was inert — the capital figures that
  had been corrected to the real account size never reached the schema at all,
  and neither did anything else.

* The performance example paired the account size with a $5,234.50 profit and
  a 2.34 Sharpe: a documented 5,234% return. No strategy in this repo has
  demonstrated a positive edge (CLAUDE.md 2), so that is an unsourced edge
  claim in the API docs.

Host-run test: the account size comes from shared/account.py, never a literal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.models import stat_arb_models as sam  # noqa: E402

# Every model in the module that declares an example.
MODELS_WITH_EXAMPLES = [
    sam.InitializeManagerRequest,
    sam.AddPairsStrategyRequest,
    sam.CalibratePairsStrategyRequest,
    sam.AddFundingStrategyRequest,
    sam.SetupTriangularArbitrageRequest,
    sam.GenerateSignalsRequest,
    sam.StrategyAllocationResponse,
    sam.InitializeManagerResponse,
    sam.StrategyResponse,
    sam.SignalsResponse,
    sam.PerformanceResponse,
    sam.StatusResponse,
    sam.ResetResponse,
    sam.ErrorResponse,
]

# Example keys that carry money rather than a ratio, count or timestamp.
MONEY_KEYS = {"total_capital", "allocated_capital", "total_pnl", "pnl"}


def _money_values(node, found=None):
    """Every money-keyed numeric value anywhere in a nested example."""
    if found is None:
        found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in MONEY_KEYS and isinstance(value, (int, float)):
                found.append((key, float(value)))
            _money_values(value, found)
    elif isinstance(node, list):
        for item in node:
            _money_values(item, found)
    return found


def test_the_v1_idiom_really_is_ignored():
    """Control. Documents WHY the migration was needed: on this Pydantic
    version the old form contributes nothing to the schema."""

    class OldStyle(BaseModel):
        x: int = 1

        class Config:
            schema_extra = {"example": {"x": 42}}

    class NewStyle(BaseModel):
        model_config = ConfigDict(json_schema_extra={"example": {"x": 42}})
        x: int = 1

    assert "example" not in OldStyle.model_json_schema()
    assert NewStyle.model_json_schema()["example"] == {"x": 42}


@pytest.mark.parametrize("model", MODELS_WITH_EXAMPLES, ids=lambda m: m.__name__)
def test_example_reaches_the_schema(model):
    schema = model.model_json_schema()
    assert "example" in schema, (
        f"{model.__name__} declares an example that never reaches the OpenAPI "
        f"schema — the Pydantic v1 `class Config: schema_extra` idiom is "
        f"silently ignored on v2"
    )
    assert schema["example"], f"{model.__name__} example is empty"


@pytest.mark.parametrize("model", MODELS_WITH_EXAMPLES, ids=lambda m: m.__name__)
def test_example_money_never_exceeds_the_account(model):
    """No example may imply an account larger than the configured one. This is
    what catches a $10,000-era figure creeping back in (allocated_capital was
    13333.33)."""
    capital = get_settings().paper_initial_balance
    for key, value in _money_values(model.model_json_schema()["example"]):
        assert abs(value) <= capital, (
            f"{model.__name__} example field {key!r} is {value}, which exceeds "
            f"the configured account size of {capital}"
        )


def test_capital_examples_track_settings_and_are_not_frozen_at_import():
    """json_schema_extra must be a CALLABLE. A dict literal is evaluated at
    class definition, which would freeze the account size at import."""
    settings = get_settings()
    assert settings.paper_initial_balance == ACCOUNT_EQUITY_USD

    before = sam.StatusResponse.model_json_schema()["example"]["total_capital"]
    assert before == ACCOUNT_EQUITY_USD

    saved = settings.paper_initial_balance
    try:
        settings.paper_initial_balance = saved * 2
        after = sam.StatusResponse.model_json_schema()["example"]["total_capital"]
        assert after == saved * 2, (
            "capital example did not follow Settings — it was frozen at import"
        )
        perf = sam.PerformanceResponse.model_json_schema()["example"]["performance"]
        assert perf["total_capital"] == saved * 2
    finally:
        settings.paper_initial_balance = saved


def test_performance_example_documents_no_edge():
    """CLAUDE.md 2: no strategy here has a positive edge. A docs example
    showing one is an unsourced edge claim."""
    perf = sam.PerformanceResponse.model_json_schema()["example"]["performance"]

    assert perf["total_pnl"] <= 0, (
        f"performance example documents a {perf['total_pnl']} profit; no "
        f"strategy in this repo has a demonstrated positive edge"
    )
    assert perf["sharpe_ratio"] <= 0, (
        f"performance example documents a Sharpe of {perf['sharpe_ratio']}; "
        f"every measured strategy is negative"
    )

    # Internally consistent: the counts and the win rate must agree, or the
    # example teaches a wrong relationship.
    assert perf["winning_trades"] + perf["losing_trades"] == perf["total_trades"]
    assert perf["win_rate"] == pytest.approx(
        perf["winning_trades"] / perf["total_trades"], abs=5e-4
    )
    leg = perf["strategies"]["BTCUSDT_ETHUSDT"]
    assert leg["pnl"] <= 0
    assert abs(leg["pnl"]) <= abs(perf["total_pnl"])
