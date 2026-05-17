"""Phase 10 DASHLIVE — Path-to-LIVE defence-in-depth grep gates (D-10-20).

Two CI-enforced regression detectors per 10-CONTEXT.md decision D-10-20:

1. ``test_path_to_live_tile_component_exists`` — the literal ``PathToLiveTile``
   must exist in production code under ``frontend/src/`` (*.jsx or *.js files).
   Catches silent removal of the DASHLIVE-01 tile component.
   Scope is intentionally narrowed to ``frontend/src/`` only — RUNBOOK.md,
   CONTEXT.md, and other docs may contain the literal as prose, and a docs-only
   match must NOT satisfy the gate (08-03 precedent).

2. ``test_carry_ins_endpoint_referenced`` — the literal ``carry-ins`` must exist
   in production code under ``services/api-gateway/app/`` (*.py files).
   Catches silent removal of the DASHLIVE-02 ``/api/preflight/carry-ins`` endpoint.
   Scope is narrowed to api-gateway app code only.

Both gates use a dual-form scan — pathlib ``rglob`` for cross-platform fidelity
AND a subprocess ``grep`` call to mirror the literal command an operator runs
locally. Pattern verbatim from tests/integration/test_preflight_grep_gates.py.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Module-level constants — SCOPE IS LOAD-BEARING.
#
# REPO_ROOT resolves from this file's location. Scope dirs are intentionally
# narrow: frontend/src/ and services/api-gateway/app/ only.
# Neither scope includes .planning/, RUNBOOK.md, REQUIREMENTS.md, or docs —
# prose containing the literals must NOT satisfy the gates (08-03 precedent).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
API_GATEWAY_APP = REPO_ROOT / "services" / "api-gateway" / "app"


# ---------------------------------------------------------------------------
# Gate #1 — PathToLiveTile component must survive in frontend/src/
# ---------------------------------------------------------------------------


def test_path_to_live_tile_component_exists():
    """The ``PathToLiveTile`` literal must exist in frontend/src/ (*.jsx or *.js).

    Dual-form scan:

    * pathlib ``rglob`` — finds at least one .jsx or .js file under FRONTEND_SRC
      (excluding ``tests/`` and node_modules) containing the literal.
    * subprocess ``grep -r`` — fidelity to the literal command an operator runs
      in CI; scope is FRONTEND_SRC only (intentionally narrower than repo root)
      so docs-only matches cannot satisfy the gate.

    Catches silent removal of the DASHLIVE-01 PathToLiveTile component.
    """
    pattern = re.compile(r"PathToLiveTile")
    matches: list[str] = []

    for ext in ("*.jsx", "*.js"):
        for f in FRONTEND_SRC.rglob(ext):
            posix = f.as_posix()
            if "/tests/" in posix or "node_modules" in posix:
                continue
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            if pattern.search(text):
                matches.append(str(f.relative_to(FRONTEND_SRC)))

    assert matches, (
        "PathToLiveTile component removed from frontend. "
        "DASHLIVE-01 contract requires the tile to live under frontend/src/. "
        "Restore the component file (e.g. frontend/src/components/PathToLiveTile.jsx) "
        "and ensure it is imported/rendered in Dashboard.jsx."
    )

    # Fidelity to the literal CI grep command. Scope MUST be FRONTEND_SRC — not
    # REPO_ROOT — to keep docs prose from satisfying the gate.
    result = subprocess.run(
        ["grep", "-r", "PathToLiveTile", str(FRONTEND_SRC)],
        capture_output=True,
        text=True,
    )
    assert result.stdout, (
        f"subprocess grep returned no matches for PathToLiveTile under {FRONTEND_SRC}. "
        f"pathlib scan found {matches!r} but the literal grep -r form "
        "(the exact CI gate command) returned empty — investigate path resolution "
        "or file-encoding issues."
    )


# ---------------------------------------------------------------------------
# Gate #2 — carry-ins endpoint must survive in services/api-gateway/app/
# ---------------------------------------------------------------------------


def test_carry_ins_endpoint_referenced():
    """The ``carry-ins`` literal must exist in api-gateway production code (*.py).

    Dual-form scan:

    * pathlib ``rglob`` — finds at least one .py file under API_GATEWAY_APP
      (excluding ``tests/``) containing the literal.
    * subprocess ``grep -r`` — scope is API_GATEWAY_APP only; docs directories
      excluded.

    Catches silent removal of the DASHLIVE-02 ``/api/preflight/carry-ins`` endpoint.
    """
    pattern = re.compile(r"carry-ins")
    matches: list[str] = []

    for py in API_GATEWAY_APP.rglob("*.py"):
        if "/tests/" in py.as_posix():
            continue
        try:
            text = py.read_text(errors="ignore")
        except OSError:
            continue
        if pattern.search(text):
            matches.append(str(py.relative_to(API_GATEWAY_APP)))

    assert matches, (
        "carry-ins endpoint silently removed from api-gateway. "
        "DASHLIVE-02 contract requires /api/preflight/carry-ins. "
        "Check that services/api-gateway/app/routes/preflight_carry_ins.py still "
        "exists and is registered in main.py via app.include_router(...)."
    )

    # Fidelity to the literal CI grep command. Scope MUST be API_GATEWAY_APP.
    result = subprocess.run(
        ["grep", "-r", "carry-ins", str(API_GATEWAY_APP)],
        capture_output=True,
        text=True,
    )
    assert result.stdout, (
        f"subprocess grep returned no matches for 'carry-ins' under {API_GATEWAY_APP}. "
        f"pathlib scan found {matches!r} but the literal grep -r form returned "
        "empty — investigate path resolution or file-encoding issues."
    )
