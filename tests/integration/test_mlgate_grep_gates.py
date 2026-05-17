"""Phase 9 MLGATE-02 grep gates — defence-in-depth for auto-flip log emission.

Two CI-enforced regression detectors, mirroring the Phase 8 pattern at
``tests/integration/test_preflight_grep_gates.py``:

1. ``test_mlgate_auto_flip_log_exists`` — the boot-time auto-flip log
   literal must survive in production code under
   ``services/trading-engine/app/``. Catches silent removal of the
   ``logger.critical(...)`` emission that anchors the operator-visible
   audit trail for ML re-enablement decisions.
2. ``test_mlgate_module_imports_at_main`` — ``services/trading-engine
   /app/main.py`` must import the auto-flip phase from
   ``app.lifespan`` (either the named import or the bare module
   reference). Defence against autoflake stripping the F401-marked
   autoflake-survival import — the exact regression pattern Phase 8
   documented in ``feedback_main_imports_autoflake.md``.

Both gates use a dual-form scan — pathlib ``rglob`` for cross-platform
fidelity AND a subprocess ``grep`` call to mirror the literal command an
operator runs locally. The subprocess form is what the CI workflow runs
directly. Scope is intentionally narrowed to
``services/trading-engine/app/`` (NOT the repo root) — PLAN.md prose and
this very file's docstring may contain the grep target literal, and a
docs-only match must NOT satisfy the gate.

Diagnostic-message discipline (Phase 8 lesson, 08-01-SUMMARY.md issue
#2): the assertion failure messages assemble the bare grep target from
variables so the test file itself does not self-satisfy the gate when
the gate's subprocess scope is accidentally widened.
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
# MUST NOT be passed into the subprocess grep below; otherwise PLAN.md prose
# (which contains the literal as part of the Phase 9 spec) would satisfy
# the gate even if the production-code emission was deleted. The
# per-test acceptance asserts the subprocess scope is TE_APP.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"

# Bare grep target assembled from variables so this file's diagnostic
# messages do not contain the contiguous literal token. The bare token
# appears in this module exactly three times: the re.compile call, the
# subprocess.run argument list, and the module docstring above (the
# docstring is not actionable code — it cannot satisfy a code-scope gate
# even if scope widens later).
_TOKEN_HEAD = "MLGATE"
_TOKEN_TAIL = "AUTO_FLIP"
_GREP_TARGET_DIAG = f"{_TOKEN_HEAD}_{_TOKEN_TAIL}"  # never a contiguous source literal


# ---------------------------------------------------------------------------
# Gate #3 — MLGATE_AUTO_FLIP log emission must survive in production
# ---------------------------------------------------------------------------


def test_mlgate_auto_flip_log_exists():
    """The boot-time auto-flip log literal must exist in the trading-engine
    production code (services/trading-engine/app/).

    Dual-form scan:

    * pathlib ``rglob`` — finds at least one ``.py`` file under TE_APP
      (excluding ``tests/``) containing the literal token.
    * subprocess ``grep -r`` — fidelity to the literal command an operator
      runs in CI; scope is TE_APP only (intentionally narrower than the
      repo root) so docs-only matches cannot satisfy the gate.

    Mirrors Phase 8's ``test_live_preflight_rejected_log_exists`` at
    ``tests/integration/test_preflight_grep_gates.py:50``.
    """
    pattern = re.compile(r"MLGATE_AUTO_FLIP")
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
        f"{_GREP_TARGET_DIAG} log emission removed from production code. "
        "Phase 9 MLGATE-02 enforces the literal must live in "
        "services/trading-engine/app/ so CI grep gates can detect silent "
        "removal. Restore the logger.critical(...) line in "
        "app/lifespan/ml.py::auto_flip_ml_predictions."
    )

    # Fidelity to the literal CI grep command. Scope MUST be TE_APP — not
    # REPO_ROOT — to keep this file's docstring and PLAN.md prose from
    # satisfying the gate.
    result = subprocess.run(
        ["grep", "-r", "MLGATE_AUTO_FLIP", str(TE_APP)],
        capture_output=True,
        text=True,
    )
    assert result.stdout, (
        f"subprocess grep returned no matches under {TE_APP}. "
        f"pathlib scan found {matches!r} but the literal grep -r form (the "
        f"exact CI gate command) returned empty — investigate path "
        f"resolution or file-encoding issues. Diagnostic token: "
        f"{_GREP_TARGET_DIAG}."
    )


# ---------------------------------------------------------------------------
# Gate #4 — auto_flip_ml_predictions module reference must survive autoflake
# ---------------------------------------------------------------------------


def test_mlgate_module_imports_at_main():
    """``services/trading-engine/app/main.py`` must import the auto-flip
    phase from ``app.lifespan``.

    Without the F401-marked autoflake-survival import, ``make format`` will
    strip the bare-package import and Phase 9 MLGATE-02's grep-gate scope
    silently shrinks. Project memory ``feedback_main_imports_autoflake.md``
    documents the exact regression pattern.

    Accepts either ``from app.lifespan import ... auto_flip_ml_predictions
    ...`` (current form) or the bare ``import app.lifespan.ml`` — either
    keeps the module referenced at lifespan and therefore loaded at
    FastAPI app boot. Mirrors the permissive form of Phase 8 gate #2 at
    ``tests/integration/test_preflight_grep_gates.py:103``.
    """
    import app.main as main_mod

    src = inspect.getsource(main_mod)
    has_named_import = (
        "from app.lifespan import" in src and "auto_flip_ml_predictions" in src
    )
    has_bare_import = "import app.lifespan.ml" in src
    assert has_named_import or has_bare_import, (
        "services/trading-engine/app/main.py must reference "
        "app.lifespan.auto_flip_ml_predictions (or import app.lifespan.ml) "
        "so Phase 9 MLGATE-02's grep-gate anchor remains wired at lifespan. "
        "Likely cause: autoflake stripped the F401-marked import on a "
        "recent `make format` run. Restore the "
        "`from app.lifespan import (..., auto_flip_ml_predictions, ...) "
        "# noqa: F401` block near the top of main.py."
    )
