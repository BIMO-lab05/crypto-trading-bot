"""Unit tests for app.runner.metrics_bridge — TOURN-07 grep gate enforcement."""

import re
import subprocess
from pathlib import Path

import pytest


HARNESS_ROOT = Path(__file__).resolve().parents[2]


def test_no_metric_definitions_in_tournament_harness():
    """TOURN-07 — no parallel metrics path under services/tournament-harness/."""
    pattern = re.compile(r"def\s+(directional_accuracy|sharpe|deflated)")
    matches = []
    for py in HARNESS_ROOT.rglob("*.py"):
        if "/tests/" in str(py):
            continue
        text = py.read_text()
        for m in pattern.finditer(text):
            matches.append((py.relative_to(HARNESS_ROOT), m.group(0)))
    assert matches == [], f"TOURN-07 violation: parallel metrics found: {matches}"


def test_metrics_bridge_imports_resolve():
    """Importable shape — module imports the canonical functions, not redefining."""
    # This test runs OUTSIDE the container; it depends on /opt/ml_retraining
    # being on PYTHONPATH. Skip if either tensorflow or app.core (ml-retraining)
    # are not importable — the full check runs inside the container where
    # PYTHONPATH=/app:/opt/ml_retraining resolves both.
    pytest.importorskip("tensorflow")
    pytest.importorskip("app.core.returns_metrics")
    from app.runner import metrics_bridge

    # The names must be present (imported) on the bridge module
    assert hasattr(metrics_bridge, "compute_returns_metrics")
    assert hasattr(metrics_bridge, "evaluate_with_cpcv")
    assert hasattr(metrics_bridge, "probabilistic_sharpe_ratio")
    assert hasattr(metrics_bridge, "deflated_sharpe_ratio")
    assert hasattr(metrics_bridge, "cpcv_to_dsr")
    assert hasattr(metrics_bridge, "compute_all_metrics")


def test_grep_gate_command_returns_zero():
    """Sanity — the CI grep command itself returns no matches.

    Mirrors the plan's verification command:
        grep -r "def directional_accuracy|def sharpe|def deflated" \\
            services/tournament-harness/ --include='*.py' | grep -v '/tests/' | wc -l
    Must be 0.  The tests/ subtree is excluded because this test file itself
    contains the pattern as a string literal inside grep args.
    """
    grep_proc = subprocess.run(
        [
            "grep",
            "-r",
            "--include=*.py",
            "def directional_accuracy\\|def sharpe\\|def deflated",
            str(HARNESS_ROOT),
        ],
        capture_output=True,
        text=True,
    )
    # Filter out hits in the tests/ subtree (this file contains the pattern
    # as a literal string in the grep-args list, which grep would match).
    non_test_hits = [
        line for line in grep_proc.stdout.splitlines() if "/tests/" not in line
    ]
    assert non_test_hits == [], (
        "TOURN-07 grep gate found definitions outside tests/:\n"
        + "\n".join(non_test_hits)
    )
