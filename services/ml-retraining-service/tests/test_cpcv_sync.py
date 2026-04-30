"""
Drift guard for the CPCV / Sharpe modules duplicated from risk-metrics-service.

``app/cpcv.py`` and ``app/sharpe_metrics.py`` are byte-identical copies of
the canonical files in ``services/risk-metrics-service/app/``. They are
duplicated (rather than imported from the sibling service) because each
service in this repo is built into its own container with no shared
Python path — see Dockerfile and the precedent check in T0.2 wiring.

If anyone edits one copy without the other this test fails, forcing a
deliberate sync. Skipped when the canonical copy is not in the checkout
(e.g. partial clone in CI).
"""

from __future__ import annotations

from pathlib import Path

import pytest


SERVICE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SERVICE_ROOT.parent.parent

CANONICAL_CPCV = REPO_ROOT / "services" / "risk-metrics-service" / "app" / "cpcv.py"
CANONICAL_SHARPE = REPO_ROOT / "services" / "risk-metrics-service" / "app" / "sharpe_metrics.py"

LOCAL_CPCV = SERVICE_ROOT / "app" / "cpcv.py"
LOCAL_SHARPE = SERVICE_ROOT / "app" / "sharpe_metrics.py"


@pytest.mark.parametrize(
    "canonical, local",
    [
        (CANONICAL_CPCV, LOCAL_CPCV),
        (CANONICAL_SHARPE, LOCAL_SHARPE),
    ],
    ids=["cpcv", "sharpe_metrics"],
)
def test_duplicate_in_sync(canonical: Path, local: Path) -> None:
    if not canonical.exists():
        pytest.skip(f"canonical not in checkout: {canonical}")
    assert local.exists(), f"local copy missing: {local}"
    assert local.read_bytes() == canonical.read_bytes(), (
        f"{local.name} drifted from canonical at {canonical}; "
        "edit both files together or extract a shared module."
    )
