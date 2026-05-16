"""Phase 8 preflight grep gates — PREFLIGHT-02 defence-in-depth.

Two CI-enforced regression detectors per 08-CONTEXT.md "Grep gates
(defence-in-depth)" decision:

1. ``test_live_preflight_rejected_log_exists`` — the literal
   ``LIVE_PREFLIGHT_REJECTED`` must exist in production code under
   ``services/trading-engine/app/``. Catches silent removal of the boot-reject
   log emission. Scope is intentionally narrowed to ``services/trading-engine
   /app/`` (NOT the repo root) — ``RUNBOOK.md`` and other docs may contain
   the literal as prose, and a docs-only match must NOT satisfy the gate.
2. ``test_preflight_module_imports_at_lifespan`` — ``from app.preflight
   import`` (or the bare ``import app.preflight`` form) must appear in
   ``services/trading-engine/app/main.py``. Defence against autoflake
   stripping the F401-marked autoflake-survival import (the exact regression
   documented in project memory ``feedback_main_imports_autoflake.md``).

Both gates use a dual-form scan — pathlib ``rglob`` for cross-platform
fidelity AND a subprocess ``grep`` call to mirror the literal command an
operator runs locally. The subprocess form is what CI workflow PREFLIGHT-03
will invoke directly per 08-PATTERNS.md.
"""

from __future__ import annotations

import inspect
import re
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Module-level constants — SCOPE IS LOAD-BEARING.
#
# REPO_ROOT is defined for resolving the trading-engine app path, but it
# MUST NOT be passed into the subprocess grep below; otherwise RUNBOOK.md
# prose (which contains the literal as part of the Pre-LIVE checklist)
# would satisfy the gate even if the production-code emission was deleted.
# This file's per-test acceptance asserts the subprocess scope is TE_APP.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"


# ---------------------------------------------------------------------------
# Gate #1 — LIVE_PREFLIGHT_REJECTED log emission must survive in production
# ---------------------------------------------------------------------------


def test_live_preflight_rejected_log_exists():
    """The ``LIVE_PREFLIGHT_REJECTED`` log literal must exist in the
    trading-engine production code (services/trading-engine/app/).

    Dual-form scan:

    * pathlib ``rglob`` — finds at least one ``.py`` file under TE_APP
      (excluding ``tests/``) containing the literal.
    * subprocess ``grep -r`` — fidelity to the literal command an operator
      runs in CI; scope is TE_APP only (intentionally narrower than the
      repo root) so docs-only matches cannot satisfy the gate.

    Mirrors the TOURN-07 grep-gate pattern at
    ``services/tournament-harness/tests/integration/test_tourn07_grep_gate.py``.
    """
    pattern = re.compile(r"LIVE_PREFLIGHT_REJECTED")
    matches: list[str] = []
    for py in TE_APP.rglob("*.py"):
        if "/tests/" in py.as_posix():
            continue
        try:
            text = py.read_text(errors="ignore")
        except OSError:
            continue
        if pattern.search(text):
            matches.append(str(py.relative_to(TE_APP)))
    assert matches, (
        "LIVE_PREFLIGHT_REJECTED log emission removed from production code. "
        "PREFLIGHT-02 enforces the literal must live in "
        "services/trading-engine/app/ so CI grep gates can detect silent removal. "
        "Restore the logger.critical(...) line in app/main.py lifespan."
    )

    # Fidelity to the literal CI grep command. Scope MUST be TE_APP — not
    # REPO_ROOT — to keep RUNBOOK.md prose from satisfying the gate.
    result = subprocess.run(
        ["grep", "-r", "LIVE_PREFLIGHT_REJECTED", str(TE_APP)],
        capture_output=True,
        text=True,
    )
    assert result.stdout, (
        f"subprocess grep returned no matches under {TE_APP}. "
        f"pathlib scan found {matches!r} but the literal grep -r form (the "
        "exact CI gate command) returned empty — investigate path resolution "
        "or file-encoding issues."
    )


# ---------------------------------------------------------------------------
# Gate #2 — preflight module import must survive autoflake
# ---------------------------------------------------------------------------


def test_preflight_module_imports_at_lifespan():
    """``services/trading-engine/app/main.py`` must import ``app.preflight``.

    Without the F401-marked autoflake-survival import, ``make format`` will
    strip the bare-package import and PREFLIGHT-02's grep-gate scope
    silently shrinks. Project memory ``feedback_main_imports_autoflake.md``
    documents the exact regression pattern.

    Accepts either ``from app.preflight import ...`` (current form) or the
    bare ``import app.preflight`` — either keeps the package referenced at
    lifespan and therefore loaded at FastAPI app boot.
    """
    import app.main as main_mod

    src = inspect.getsource(main_mod)
    assert "from app.preflight import" in src or "import app.preflight" in src, (
        "services/trading-engine/app/main.py must import app.preflight for "
        "PREFLIGHT-02 cap-check enforcement to remain wired at lifespan. "
        "Likely cause: autoflake stripped the F401-marked import on a recent "
        "`make format` run. Restore the `from app.preflight import run_all "
        " # noqa: F401` line near the top of main.py."
    )
