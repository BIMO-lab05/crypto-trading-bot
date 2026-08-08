"""Drift detector: trading-engine `Settings` defaults vs `shared/account.py`.

`shared/account.py` is the declaration of record, but it is NOT importable from
any service container: every service builds with `context: ./services/<name>`,
the Dockerfiles copy only `app/`, and nothing mounts repo-root `shared/`. So
in-container code reads its own `Settings` and agreement is enforced HERE, at
test time, rather than by a boot assert. That is a real weakening — a drift
introduced and deployed without running the suite would not be caught at boot —
and it is recorded in the `shared/account.py` docstring as such.

This file must be GREEN on the commit that introduces it: it encodes agreement
that already holds.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from shared.account import DEFAULTS

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "services" / "trading-engine" / "app" / "config.py"

#: `Settings` field name -> (`shared.account` DEFAULTS key, unit label).
#: The unit label is not decoration: `max_risk_per_trade` is a FRACTION while
#: the neighbouring `*_pct` fields are PERCENTS, and conflating them is the
#: exact bug this whole change exists to make impossible.
FIELD_PAIRS = {
    "paper_initial_balance": ("PAPER_INITIAL_BALANCE", "USD"),
    "max_risk_per_trade": ("MAX_RISK_PER_TRADE", "fraction"),
    "max_daily_loss_pct": ("MAX_DAILY_LOSS_PCT", "percent"),
    "max_position_size_pct": ("MAX_POSITION_SIZE_PCT", "percent"),
}


def _load_trading_engine_settings_class():
    """Spec-load trading-engine's config.py under a unique module name.

    Deliberately NOT `sys.path.insert(...)` + `from app.config import Settings`:
    `services/trading-engine` is not a valid package root, and
    `tests/security/conftest.py` already places api-gateway's `app` package on
    `sys.path` — a second `app` would collide within the same pytest session.

    Safe to spec-load with no package context: config.py imports only `pydantic`,
    `pydantic_settings` and `typing`.
    """
    module_name = "_gsd_trading_engine_config_for_sync_test"
    spec = importlib.util.spec_from_file_location(module_name, CONFIG_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {CONFIG_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module.Settings


def test_config_py_exists():
    assert CONFIG_PATH.is_file(), f"{CONFIG_PATH} missing — coverage would be silent"


@pytest.mark.parametrize("field_name", sorted(FIELD_PAIRS))
def test_settings_default_matches_shared_account(field_name: str):
    """Compare DECLARED defaults only.

    `Settings()` is never instantiated: instantiation reads the operator's
    `.env`, which would turn this into a test of their current environment
    instead of a test for declared-default drift.
    """
    settings_cls = _load_trading_engine_settings_class()
    account_key, unit = FIELD_PAIRS[field_name]

    assert field_name in settings_cls.model_fields, (
        f"Settings has no field `{field_name}` — it was renamed or removed. "
        f"shared.account still declares {account_key}."
    )
    settings_default = settings_cls.model_fields[field_name].default
    account_default = DEFAULTS[account_key]

    assert settings_default == account_default, (
        f"drift: Settings.{field_name}={settings_default} ({unit}) != "
        f"shared.account {account_key}={account_default} ({unit}). "
        f"Update whichever is wrong — they must agree, and the unit must match."
    )


def test_every_declared_default_is_covered_or_deliberately_not():
    """DEFAULTS keys with no trading-engine counterpart are venue constants.

    `MIN_NOTIONAL_USD`, `TAKER_FEE_PER_SIDE` and `MAKER_FEE_PER_SIDE` describe
    Bybit, not the account, and have no unit-compatible `Settings` field to
    drift against — `paper_commission_pct` is a PERCENT while both fee
    constants are FRACTIONS, which is exactly why neither is paired here.
    Asserting the split keeps a newly-added DEFAULTS entry from silently
    escaping this test.
    """
    covered = {key for key, _ in FIELD_PAIRS.values()}
    venue_only = {"MIN_NOTIONAL_USD", "TAKER_FEE_PER_SIDE", "MAKER_FEE_PER_SIDE"}
    assert set(DEFAULTS) == covered | venue_only, (
        "shared.account.DEFAULTS changed. Add the new key to FIELD_PAIRS (if "
        "trading-engine Settings has a counterpart) or to `venue_only`."
    )
