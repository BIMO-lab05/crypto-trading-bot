"""Default-on gate for Tier-1 feature flags in the trading-engine config.

SC-1 from ROADMAP Phase 5: "per-feature default-on flips are blocked until PSR
with bootstrap CI is published."

This file pins five invariants:

  Test 1 — Current state PASS: all three flags have default=False → gate is silent.
  Test 2 — Vol-targeting default-on WITHOUT evidence → gate FAILS.
  Test 3 — Vol-targeting default-on WITH evidence → gate PASSES.
  Test 4 (test_tier1_flag_default_on_requires_published_evidence) — Gate covers all
           three flags independently; assertion message identifies the failing flag.
  Test 5 — Marker-file convention pinned: literal name "PSR_CI_PUBLISHED" in flag dir.

Implementation: pure filesystem + regex check, no runtime dependency on canonical
kernels (PSR-CI or bootstrap). AST/regex over config.py text; marker file existence
at .planning/evidence/forward_paper_test/<flag>/PSR_CI_PUBLISHED.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# -------------------------------------------------------------------------
# Constants pinned here for Test 5 (rename regression catch)
# -------------------------------------------------------------------------

MARKER_FILENAME = "PSR_CI_PUBLISHED"  # Test 5 anchor — must stay a plain literal

TIER1_FLAGS: tuple[str, ...] = (
    "enable_vol_targeting",
    "prefer_maker_orders",
    "enable_funding_gate",
)

# Regex: matches "enable_vol_targeting: bool = Field(\n    default=False," etc.
# re.DOTALL lets \s match newlines (Field arguments span multiple lines).
_FLAG_DEFAULT_PATTERN = re.compile(
    r"(enable_vol_targeting|prefer_maker_orders|enable_funding_gate)"
    r":\s*bool\s*=\s*Field\(\s*default\s*=\s*(True|False)",
    re.DOTALL,
)

# Repo root: tests/ -> trading-engine/ -> services/ -> repo root (3 levels up)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_PATH = _REPO_ROOT / "services" / "trading-engine" / "app" / "config.py"
_EVIDENCE_BASE = _REPO_ROOT / ".planning" / "evidence" / "forward_paper_test"


# -------------------------------------------------------------------------
# Core gate logic (shared by all tests)
# -------------------------------------------------------------------------


def _check_default_on_gate(
    config_path: Path,
    evidence_base: Path,
) -> list[str]:
    """Scan config_path for Tier-1 flags with default=True.

    For each flag where default=True, the marker file
    ``evidence_base / <flag> / PSR_CI_PUBLISHED`` must exist.

    Returns a list of violation messages.  Empty list means the gate passes.
    """
    text = config_path.read_text()
    matches = _FLAG_DEFAULT_PATTERN.findall(text)

    violations: list[str] = []
    for flag_name, default_val in matches:
        if default_val != "True":
            continue
        marker = evidence_base / flag_name / MARKER_FILENAME
        if not marker.exists():
            violations.append(
                f"Flag '{flag_name}' has default=True in {config_path} "
                f"but no published evidence marker exists at {marker}. "
                f"Run the ≥7-day forward-paper-test for '{flag_name}', "
                f"compute PSR CI, and publish via "
                f"'python -m scripts.forward_paper_test.run_isolation "
                f"publish-evidence <evidence_dir>', then copy or symlink "
                f"the PSR_CI_PUBLISHED marker to {evidence_base / flag_name}."
            )
    return violations


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------


@pytest.fixture()
def config_with_flag_on(tmp_path: Path):
    """Return a factory that copies the real config.py into tmp_path and
    patches the named flag to default=True.

    Usage::

        patched = config_with_flag_on("enable_vol_targeting")
    """

    def _factory(flag: str) -> Path:
        src = _CONFIG_PATH.read_text()
        # Replace only the exact flag's default from False to True.
        # Pattern is tight enough not to touch other flags.
        patched = re.sub(
            rf"({re.escape(flag)}:\s*bool\s*=\s*Field\(\s*default\s*=\s*)False",
            r"\g<1>True",
            src,
            count=1,
            flags=re.DOTALL,
        )
        dest = tmp_path / "config.py"
        dest.write_text(patched)
        return dest

    return _factory


@pytest.fixture()
def evidence_dir_with_marker(tmp_path: Path):
    """Return a factory that creates a flag-level evidence directory with
    the PSR_CI_PUBLISHED marker in the right place.

    Usage::

        evidence_base = evidence_dir_with_marker("enable_vol_targeting")
    """

    def _factory(flag: str) -> Path:
        base = tmp_path / "evidence" / "forward_paper_test"
        marker_dir = base / flag
        marker_dir.mkdir(parents=True, exist_ok=True)
        (marker_dir / MARKER_FILENAME).write_text("published\n")
        return base

    return _factory


# -------------------------------------------------------------------------
# Test 1: Current repo state — gate does NOT fire (all defaults are False)
# -------------------------------------------------------------------------


def test_gate_passes_on_current_repo_state():
    """With all three Tier-1 flags at default=False, the gate is silent.

    This test will FAIL if a developer flips any flag to default=True without
    following the forward-paper-test evidence process.
    """
    violations = _check_default_on_gate(_CONFIG_PATH, _EVIDENCE_BASE)
    assert violations == [], (
        "Gate fired unexpectedly on current repo state.\n"
        "Violations:\n  " + "\n  ".join(violations)
    )


# -------------------------------------------------------------------------
# Test 2: Vol-targeting default=True WITHOUT evidence → gate FAILS
# -------------------------------------------------------------------------


def test_vol_targeting_default_on_without_evidence_fails(
    config_with_flag_on,
    tmp_path: Path,
):
    """Patching enable_vol_targeting to default=True without a marker → violation."""
    patched_config = config_with_flag_on("enable_vol_targeting")
    # Use an empty evidence base (no marker files anywhere)
    empty_evidence = tmp_path / "empty_evidence"
    empty_evidence.mkdir()

    violations = _check_default_on_gate(patched_config, empty_evidence)

    assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
    assert "enable_vol_targeting" in violations[0]
    assert MARKER_FILENAME in violations[0]


# -------------------------------------------------------------------------
# Test 3: Vol-targeting default=True WITH evidence → gate PASSES
# -------------------------------------------------------------------------


def test_vol_targeting_default_on_with_evidence_passes(
    config_with_flag_on,
    evidence_dir_with_marker,
):
    """Patching enable_vol_targeting to default=True WITH a marker → no violation."""
    patched_config = config_with_flag_on("enable_vol_targeting")
    evidence_base = evidence_dir_with_marker("enable_vol_targeting")

    violations = _check_default_on_gate(patched_config, evidence_base)

    assert violations == [], "Gate fired even though marker exists:\n  " + "\n  ".join(
        violations
    )


# -------------------------------------------------------------------------
# Test 4: Gate covers all three flags independently
# Named test_tier1_flag_default_on_requires_published_evidence per must_haves artifact.
# -------------------------------------------------------------------------


def test_tier1_flag_default_on_requires_published_evidence(
    config_with_flag_on,
    tmp_path: Path,
):
    """For each Tier-1 flag independently: default=True without marker → violation
    that names the failing flag.

    This is the canonical gate test required by MLCL-01 must_haves artifact
    ``services/trading-engine/tests/test_config_default_on_gate.py``.
    """
    for flag in TIER1_FLAGS:
        patched_config = config_with_flag_on(flag)
        empty_evidence = tmp_path / f"empty_{flag}"
        empty_evidence.mkdir(exist_ok=True)

        violations = _check_default_on_gate(patched_config, empty_evidence)

        # Must have exactly one violation for the flag under test (the other
        # two flags remain default=False in the patched config).
        assert len(violations) == 1, (
            f"Expected 1 violation for '{flag}' default=True, got {len(violations)}:\n"
            + "\n".join(violations)
        )
        assert flag in violations[0], (
            f"Violation message does not identify '{flag}':\n{violations[0]}"
        )
        # The message must include the expected marker path so the operator
        # knows exactly what file to create.
        assert MARKER_FILENAME in violations[0], (
            f"Violation message does not mention {MARKER_FILENAME!r}:\n{violations[0]}"
        )


# -------------------------------------------------------------------------
# Test 5: Marker-file convention is pinned
# -------------------------------------------------------------------------


def test_marker_file_convention_is_pinned():
    """Pin the literal marker filename to 'PSR_CI_PUBLISHED'.

    If someone renames the marker constant or the directory structure without
    updating this gate, this test fails — catching the silent regression before
    it allows a premature default-on flip to pass CI.

    Two explicit checks:
      a) The module-level constant ``MARKER_FILENAME`` equals the literal.
      b) The gate function constructs the path as evidence_base/<flag>/MARKER.
    """
    # (a) Literal constant pinned
    assert MARKER_FILENAME == "PSR_CI_PUBLISHED", (
        f"MARKER_FILENAME changed from 'PSR_CI_PUBLISHED' to {MARKER_FILENAME!r}. "
        "Update the gate tests and the operator runbook before merging."
    )

    # (b) Gate constructs the correct path (functional regression check):
    # Create a temp directory with the marker at the WRONG location (run_id subdir)
    # and assert the gate still fires — proving it requires the flag-level path.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "evidence" / "forward_paper_test"
        wrong_subdir = base / "enable_vol_targeting" / "some_run_id"
        wrong_subdir.mkdir(parents=True)
        (wrong_subdir / MARKER_FILENAME).write_text("published\n")

        # Build a patched config with enable_vol_targeting=True
        src = _CONFIG_PATH.read_text()
        patched = re.sub(
            r"(enable_vol_targeting:\s*bool\s*=\s*Field\(\s*default\s*=\s*)False",
            r"\g<1>True",
            src,
            count=1,
            flags=re.DOTALL,
        )
        patched_config = Path(td) / "config.py"
        patched_config.write_text(patched)

        # Marker at <flag>/<run_id>/PSR_CI_PUBLISHED — WRONG path for the gate
        violations = _check_default_on_gate(patched_config, base)
        assert len(violations) == 1, (
            "Gate must NOT be satisfied by a marker in a run_id subdir. "
            f"Got violations: {violations}"
        )
        assert MARKER_FILENAME in violations[0]
