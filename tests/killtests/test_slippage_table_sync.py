"""
Both research cost models must equal the paper engine's.

There are three copies of the slippage table. paper_slippage.py is canonical.
edge_lab/config.py is the copy EVERY battery Gate 1 verdict is computed
against (gate1.py:22 imports it, gate1.py:44-45 passes it to screen_trades,
run_battery.py:451 calls run_gate1). screen.py's module-scope table feeds only
the standalone CLI (`python backtesting/screen.py --trades ...`).

Neither research copy imports paper_slippage: screen.py must stay runnable
standalone, and config.py is a declared-before-any-run pin. Nothing enforced
agreement, and paper_slippage.py is explicitly slated for recalibration
("SOLUSDT ... calibrate first") - a recalibration would silently leave both
research paths on stale costs.

Loading technique: paper_slippage.py is spec-loaded under a unique module
name, NOT via sys.path. tests/security/conftest.py already places
api-gateway's `app` package on sys.path in the same pytest session, and a
second `app` would collide (see tests/test_account_config_sync.py:43-49).
This is safe here because paper_slippage.py imports only logging, decimal
and typing.
"""

import importlib.util
import sys
from pathlib import Path

import screen  # backtesting/ is on sys.path via tests/killtests/conftest.py
from edge_lab.config import SLIPPAGE_BPS, SLIPPAGE_FALLBACK_BPS

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPER_SLIPPAGE_PATH = (
    REPO_ROOT / "services" / "trading-engine" / "app" / "paper_slippage.py"
)

# The obvious way to make a config failure green is forbidden. config.py:1-2:
# "Declared before any run; changing a value after verdicts exist invalidates
# them (spec section 4 anti-overfitting rule)."
CONFIG_REMEDIATION = (
    "paper_slippage has been recalibrated, so the pinned battery cost model is "
    "stale - this INVALIDATES the existing battery verdicts under "
    ".planning/evidence/killtests/. Re-pin and re-run the battery. Do NOT edit "
    "backtesting/edge_lab/config.py just to make this test green."
)


def _load_paper_slippage():
    name = "_slippage_sync_paper_slippage"
    spec = importlib.util.spec_from_file_location(name, PAPER_SLIPPAGE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_battery_slippage_table_matches_paper_engine():
    paper = _load_paper_slippage()
    assert SLIPPAGE_BPS == paper.DEFAULT_SLIPPAGE_BPS, (
        "edge_lab.config and the paper engine disagree on slippage; every "
        "battery Gate 1 verdict is computed against edge_lab.config. "
        + CONFIG_REMEDIATION
    )


def test_battery_slippage_fallback_matches_paper_engine():
    paper = _load_paper_slippage()
    assert SLIPPAGE_FALLBACK_BPS == paper.FALLBACK_SLIPPAGE_BPS, CONFIG_REMEDIATION


def test_screen_slippage_table_matches_paper_engine():
    paper = _load_paper_slippage()
    assert screen.SLIPPAGE_BPS_BY_SYMBOL == paper.DEFAULT_SLIPPAGE_BPS, (
        "the standalone screen CLI and the paper engine disagree on slippage; "
        "`python backtesting/screen.py --trades ...` is computed against the "
        "screen's table"
    )


def test_screen_slippage_fallback_matches_paper_engine():
    paper = _load_paper_slippage()
    assert screen.SLIPPAGE_FALLBACK_BPS == paper.FALLBACK_SLIPPAGE_BPS
