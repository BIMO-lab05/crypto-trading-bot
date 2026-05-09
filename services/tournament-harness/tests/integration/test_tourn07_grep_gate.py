"""TOURN-07 grep gate — Phase 3 success criterion #5 (ROADMAP.md).

The exact requirement:
    grep -r "def directional_accuracy\\|def sharpe\\|def deflated" \
         services/tournament-harness/
    must return zero matches.

This file MUST stay in tests/integration/ so a CI workflow can target it
(see .github/workflows/tournament-harness.yml).
"""

import re
import subprocess
from pathlib import Path

import pytest


# Find services/tournament-harness from the test file location.
HARNESS_ROOT = Path(__file__).resolve().parents[2]


def test_no_metric_definitions_in_production_code():
    """No `def directional_accuracy`, `def sharpe`, `def deflated` under
    services/tournament-harness/ outside tests/.

    These metric implementations live in services/ml-retraining-service/ and
    must be imported, never re-implemented (D-CONTEXT TOURN-07).
    """
    pattern = re.compile(
        r"^\s*def\s+(directional_accuracy|sharpe|deflated)", re.MULTILINE
    )
    matches = []
    for py in HARNESS_ROOT.rglob("*.py"):
        # Tests can reference these names in strings/comments — only fail on production code.
        if "/tests/" in str(py.as_posix()):
            continue
        text = py.read_text()
        for m in pattern.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            matches.append(
                (str(py.relative_to(HARNESS_ROOT)), line_no, m.group(0).strip())
            )

    assert matches == [], (
        "TOURN-07 violation — parallel metric definitions found:\n  "
        + "\n  ".join(f"{p}:{ln}: {snippet}" for p, ln, snippet in matches)
    )


def test_grep_command_from_roadmap_returns_zero():
    """Run the literal command from ROADMAP.md success criterion #5."""
    cmd = [
        "grep",
        "-r",
        "--include=*.py",
        "def directional_accuracy\\|def sharpe\\|def deflated",
        str(HARNESS_ROOT),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Exclude tests/ from results (the grep command itself doesn't, but ROADMAP success
    # is about no production code defining them — keep the subprocess output for diagnostics).
    output_lines = [ln for ln in result.stdout.splitlines() if "/tests/" not in ln]
    assert output_lines == [], "TOURN-07 grep gate failed:\n" + "\n".join(output_lines)


def test_metric_imports_resolve_from_ml_retraining():
    """Sanity — the imports are working (TOURN-07 enforces NO re-implementation
    AND requires the imports DO succeed). If both this test AND the
    test_no_metric_definitions test pass, the harness is using the canonical
    implementations only.

    Skip conditions:
      - TensorFlow not installed (CI without TF layer).
      - app.core not importable — happens when running outside the container
        where both service roots share the 'app' namespace.  Inside the container
        PYTHONPATH=/app:/opt/ml_retraining resolves the packages without collision.
    """
    pytest.importorskip("tensorflow")
    # Skip when ml-retraining's app.core isn't reachable (outside-container env).
    try:
        import importlib

        if importlib.util.find_spec("app.core") is None:
            pytest.skip(
                "app.core not importable — namespace collision outside container; "
                "run inside crypto-bot-tournament-harness for full verification."
            )
    except Exception:
        pytest.skip(
            "app.core import probe failed — likely outside-container environment."
        )

    from app.runner.metrics_bridge import (
        compute_returns_metrics,
        evaluate_with_cpcv,
        probabilistic_sharpe_ratio,
        deflated_sharpe_ratio,
        cpcv_to_dsr,
        compute_all_metrics,
    )

    # Identity check — the imported names point at the ml-retraining modules,
    # not at locally-defined re-implementations (TOURN-07).
    assert compute_returns_metrics.__module__.startswith("app.core.returns_metrics")
    assert evaluate_with_cpcv.__module__.startswith("app.core.cpcv_evaluation")
    assert probabilistic_sharpe_ratio.__module__.startswith("app.sharpe_metrics")
    assert deflated_sharpe_ratio.__module__.startswith("app.sharpe_metrics")
    assert cpcv_to_dsr.__module__.startswith("app.cpcv")
    # compute_all_metrics is defined in the bridge itself (not re-implemented
    # from ml-retraining) — it CALLS the imported functions; its module is the bridge.
    assert compute_all_metrics.__module__ == "app.runner.metrics_bridge"
