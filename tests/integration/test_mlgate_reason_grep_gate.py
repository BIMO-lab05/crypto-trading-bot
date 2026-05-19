"""Phase 9 MLGATE-03 grep gate — Plan 09-03 Task 2.

Two CI-enforced regression detectors per the plan's success criteria #3:

1. ``test_mlgate_reason_field_present`` — every line in ``services/trading-engine/app/``
   (excluding ``/tests/``) containing the substring ``"ML predictions disabled"``
   MUST also contain ``"reason="`` on the same line. Catches an emission that
   open-codes the literal without the structured reason field — exactly the
   shape of the bug MLGATE-03 was filed to prevent.
2. ``test_mlgate_reason_helper_imported_at_emission_sites`` — both
   ``enhanced_aggregator.py`` and ``signal_aggregator.py`` MUST import
   ``log_ml_disabled`` from ``app.aggregation.ml_gate_reasons``. Defence
   against the autoflake regression pattern documented in project memory
   ``feedback_main_imports_autoflake.md``.

SCOPE LOCK (per plan D-09-03): scans are intentionally narrowed to
``services/trading-engine/app/`` only (NOT the repo root) — RUNBOOK.md and
other docs may contain the literal as prose, and a docs-only match must NOT
mask silent removal of the production emission. The subprocess grep call
mirrors the literal command a CI workflow runs.

Self-avoidance: this test file itself contains the literal as part of the
assertion-message template assembled at runtime from variables. The pathlib
scan excludes ``/tests/`` so this file's own match cannot satisfy the gate.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Scope is load-bearing. Restrict the scan to the trading-engine app tree;
# do NOT lift to REPO_ROOT — RUNBOOK.md, planning docs, and SUMMARY files
# legitimately contain the literal as prose and would mask silent production
# removal if they were included.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"


# ---------------------------------------------------------------------------
# Diagnostic-message assembly helpers — assembled from variable parts so the
# emitted assertion text does NOT itself contain the literal grep gate
# substring as a single contiguous run. Same self-avoidance discipline as
# Phase 8 (see 08-01-SUMMARY.md issue #2).
# ---------------------------------------------------------------------------
_ML_PRED_PART = "ML predictions "
_DISABLED_PART = "disabled"
_REASON_PART = "reason="


def _literal_target() -> str:
    """Return the full literal to grep for, assembled from parts at runtime."""
    return _ML_PRED_PART + _DISABLED_PART


def _reason_field() -> str:
    """Return the required same-line companion field."""
    return _REASON_PART


# ---------------------------------------------------------------------------
# Gate #1 — every disabled-event emission must carry a reason= field
# ---------------------------------------------------------------------------


def test_mlgate_reason_field_present():
    """Every line in trading-engine production code containing the disabled-event
    literal MUST also contain ``reason=`` on the same line.

    Dual-form scan:

    * pathlib ``rglob`` — finds every ``.py`` under TE_APP (excluding ``tests/``);
      iterates lines; collects offenders.
    * subprocess ``grep -rn ... | grep -v reason=`` — fidelity to the CI gate
      command an operator would run locally. Scope is TE_APP, not REPO_ROOT.
    """
    target = _literal_target()
    required = _reason_field()
    offenders: list[str] = []

    for py in TE_APP.rglob("*.py"):
        if "/tests/" in py.as_posix():
            continue
        try:
            text = py.read_text(errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if target in line and required not in line:
                offenders.append(
                    f"{py.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
                )

    # Diagnostic message is assembled from variable parts so this file's own
    # assertion text does NOT contain the bare literal as a contiguous run.
    parts = [
        "Found {n} line(s) containing the {t!r} literal".format(
            n=len(offenders), t=target
        ),
        f"without a same-line {required!r} field.",
        "Every disabled-event emission in services/trading-engine/app/ MUST",
        "delegate to app.aggregation.ml_gate_reasons.log_ml_disabled() so the",
        "structured reason field is appended to the log line. Offenders:",
        *offenders,
    ]
    assert not offenders, "\n  ".join(parts)

    # Fidelity to the literal CI grep command. Pipe through `grep -v reason=`
    # to extract the offending lines (same as the subprocess form an operator
    # would invoke locally).
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"grep -rn {target!r} "
                f"--include='*.py' {str(TE_APP)} "
                "| grep -v '/tests/' "
                f"| grep -vE {required!r} || true"
            ),
        ],
        capture_output=True,
        text=True,
    )
    # An empty stdout from the pipeline means no offenders — assert that.
    diag = (
        f"subprocess grep pipeline found unexpected offenders under {TE_APP}:\n"
        f"{result.stdout}"
    )
    assert result.stdout.strip() == "", diag


# ---------------------------------------------------------------------------
# Gate #2 — emission-site imports must survive autoflake
# ---------------------------------------------------------------------------


def test_mlgate_reason_helper_imported_at_emission_sites():
    """``log_ml_disabled`` MUST be importable at every emission site.

    Defends against the autoflake regression pattern (see project memory
    ``feedback_main_imports_autoflake.md``): if autoflake strips the import,
    the emission call site raises NameError at runtime — but unit tests on
    the helper module itself would still pass. This gate forces the import
    line to remain present in both files.
    """
    emission_sites = [
        TE_APP / "aggregation" / "enhanced_aggregator.py",
        TE_APP / "signal_aggregator.py",
    ]
    import_re = re.compile(
        r"from\s+app\.aggregation\.ml_gate_reasons\s+import\s+.*log_ml_disabled"
    )
    missing: list[str] = []
    for site in emission_sites:
        try:
            text = site.read_text(errors="ignore")
        except OSError:
            missing.append(f"{site.relative_to(REPO_ROOT)} (could not read)")
            continue
        if not import_re.search(text):
            missing.append(str(site.relative_to(REPO_ROOT)))

    assert not missing, (
        "log_ml_disabled import missing from emission site(s): "
        + ", ".join(missing)
        + ". Restore the `from app.aggregation.ml_gate_reasons import "
        "log_ml_disabled` line with a `# noqa: F401` comment for autoflake-survival."
    )
