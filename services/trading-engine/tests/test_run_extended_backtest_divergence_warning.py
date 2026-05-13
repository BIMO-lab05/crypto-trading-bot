"""
Tests: run_extended_backtest.py divergence invariants (MLCL-04 / ADR-012)
========================================================================

These 5 tests pin the `document_divergence_permanently` disposition chosen in
`05-04-DECISION.md`. They assert:

1. SC-4 punt language ("Fixing requires", "separate change") is absent.
2. The PERMANENT DIVERGENCE marker is present in the module source.
3. CoreAggregator is named (the script explicitly documents what it diverges from).
4. ADR-012 is referenced in the module source.
5. The runtime warning fires at script entry and contains the mandatory strings.

Run: pytest services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py -v

Do NOT weaken these tests. See docs/decisions/ADR-012-extended-backtest-disposition.md.
"""

import re
import sys
import logging
from pathlib import Path


# ---------------------------------------------------------------------------
# Resolve the script path — located at the service root (one level above tests/)
# ---------------------------------------------------------------------------
SERVICE_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = SERVICE_ROOT / "run_extended_backtest.py"

# Ensure service root is on the import path so we can import the module directly
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


# ---------------------------------------------------------------------------
# Test 1: SC-4 punt language MUST be absent
# ---------------------------------------------------------------------------
def test_no_sc4_punt_language():
    """
    The phrases 'Fixing requires' and 'separate change' constituted the SC-4
    ambiguity violation in the original docstring. Verify both are gone.
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    punt_pattern = re.compile(r"Fixing requires|separate change")
    matches = punt_pattern.findall(source)
    assert matches == [], (
        f"SC-4 punt phrases found in {SCRIPT_PATH.name}: {matches!r}. "
        "Remove 'Fixing requires' and 'separate change' — see 05-04-DECISION.md."
    )


# ---------------------------------------------------------------------------
# Test 2: PERMANENT DIVERGENCE marker MUST be present
# ---------------------------------------------------------------------------
def test_permanent_divergence_marker_present():
    """
    The docstring must contain the exact string 'PERMANENT DIVERGENCE' to
    make the disposition unambiguous to future readers and contributors.
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "PERMANENT DIVERGENCE" in source, (
        f"'PERMANENT DIVERGENCE' not found in {SCRIPT_PATH.name}. "
        "Add the permanence marker to the module docstring — see 05-04-DECISION.md."
    )


# ---------------------------------------------------------------------------
# Test 3: CoreAggregator MUST be named (explict divergence target)
# ---------------------------------------------------------------------------
def test_core_aggregator_named_in_source():
    """
    The script must reference 'CoreAggregator' so any reader knows exactly
    which live component the script intentionally diverges from.
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "CoreAggregator" in source, (
        f"'CoreAggregator' not found in {SCRIPT_PATH.name}. "
        "The docstring must name the live aggregator the script diverges from."
    )


# ---------------------------------------------------------------------------
# Test 4: ADR-012 reference MUST be present
# ---------------------------------------------------------------------------
def test_adr_012_referenced_in_source():
    """
    The script must reference 'ADR-012' so operators can find the decision
    rationale without searching.
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "ADR-012" in source, (
        f"'ADR-012' not found in {SCRIPT_PATH.name}. "
        "Add an ADR-012 reference to the module docstring or runtime warning."
    )


# ---------------------------------------------------------------------------
# Test 5: Runtime warning fires at script entry
# ---------------------------------------------------------------------------
def test_runtime_warning_fires_at_entry(caplog):
    """
    Importing the module and calling its _emit_divergence_warning() helper
    must emit a WARNING-level log record containing:
      - 'RUN_EXTENDED_BACKTEST'
      - 'diverges from live CoreAggregator'

    The helper is a thin wrapper added specifically to make the warning
    independently testable without triggering the full HTTP-heavy main() loop.
    """
    import run_extended_backtest as rbe

    with caplog.at_level(logging.WARNING, logger="run_extended_backtest"):
        rbe._emit_divergence_warning()

    warning_text = " ".join(r.message for r in caplog.records)
    assert "RUN_EXTENDED_BACKTEST" in warning_text, (
        f"Expected 'RUN_EXTENDED_BACKTEST' in log output; got: {warning_text!r}"
    )
    assert "diverges from live CoreAggregator" in warning_text, (
        f"Expected 'diverges from live CoreAggregator' in log output; got: {warning_text!r}"
    )
