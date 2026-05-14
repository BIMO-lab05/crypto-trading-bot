"""Integration test: T0.1.x experiment artifacts and verdict contract (MLCL-02).

Pins five properties of the Phase 5 Plan 02 deliverables:

1. Tournament config YAML exists, is parseable, and its fields satisfy the schema.
2. Evidence leaderboard markdown exists and is non-empty.
3. Evidence decision_note exists, is >=20 lines, and ends with a valid terminal verdict.
4. Decision note cites the tournament_id from the YAML (cross-reference integrity).
5. DECISION.md preamble exists, is >=80 lines, and contains the ## Decision: heading.

All tests are pure file-I/O + yaml/regex — no Docker, no network, no monkey-patching.
Expected runtime: <5 seconds.

Pattern: mirrors test_no_legacy_r2_criterion.py (Phase 4 canonical grep-gate shape).
Path discovery: Path(__file__).resolve().parents[N] — verified against repo layout.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

# Path roots — verified against repo layout:
#   parents[0] = .../tests/integration/
#   parents[1] = .../tests/
#   parents[2] = .../services/tournament-harness/    (HARNESS_ROOT)
#   parents[3] = .../services/
#   parents[4] = .../crypto-trading-bot/              (REPO_ROOT)
# Note: REPO_ROOT = HARNESS_ROOT.parents[1] because HARNESS_ROOT is two levels
# below repo root (crypto-trading-bot/services/tournament-harness/).
# Mirrors test_no_legacy_r2_criterion.py: REPO_ROOT = HARNESS_ROOT.parents[1].
HARNESS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = HARNESS_ROOT.parents[1]

# ---- artifact paths ----

YAML_CONFIG = HARNESS_ROOT / "app" / "config" / "t0_1_x_experiment.yaml"
EVIDENCE_DIR = REPO_ROOT / ".planning" / "evidence" / "t0_1_x"
LEADERBOARD_MD = EVIDENCE_DIR / "leaderboard_row.md"
DECISION_NOTE = EVIDENCE_DIR / "decision_note.md"
DECISION_DOC = (
    REPO_ROOT / ".planning" / "phases" / "05-ml-cleanup-post-v0" / "05-02-DECISION.md"
)

# Valid terminal verdict strings (exactly).
VALID_VERDICTS = {"EDGE_FOUND", "NO_EDGE_FOUND", "INSUFFICIENT_DATA"}

# Allowed symbols per v1 validated set.
ALLOWED_SYMBOLS = {"SOLUSDT", "BNBUSDT", "ADAUSDT"}


# ---- Test 1: YAML config ----


def test_yaml_config_exists_and_valid():
    """Tournament config YAML exists, parses, and passes field constraints."""
    assert YAML_CONFIG.exists(), (
        f"Tournament YAML not found: {YAML_CONFIG}\n"
        "Expected at services/tournament-harness/app/config/t0_1_x_experiment.yaml.\n"
        "Run: git log --all --oneline | grep '05-02-task2' to check commit."
    )

    text = YAML_CONFIG.read_text()
    cfg = yaml.safe_load(text)

    # tournament_id starts with the required prefix.
    tid = cfg.get("tournament_id", "")
    assert tid.startswith("t0_1_x_"), (
        f"tournament_id must start with 't0_1_x_', got: {tid!r}"
    )

    # max_experiments must be <= 100 (loader hard cap).
    max_exp = cfg.get("max_experiments", 0)
    assert max_exp <= 100, (
        f"max_experiments must be <= 100 to stay inside harness cap, got: {max_exp}"
    )

    # symbols must be a non-empty subset of the v1 validated set.
    symbols = cfg.get("symbols", [])
    assert len(symbols) > 0, "symbols list must be non-empty"
    bad_symbols = set(symbols) - ALLOWED_SYMBOLS
    assert not bad_symbols, (
        f"symbols contains invalid entries: {bad_symbols}. Allowed: {ALLOWED_SYMBOLS}"
    )


# ---- Test 2: leaderboard markdown ----


def test_leaderboard_markdown_exists_and_nonempty():
    """Leaderboard evidence markdown exists and has content (file size > 0)."""
    assert LEADERBOARD_MD.exists(), (
        f"Leaderboard evidence not found: {LEADERBOARD_MD}\n"
        "Expected in .planning/evidence/t0_1_x/leaderboard_row.md.\n"
        "This file must exist even when the tournament result is INSUFFICIENT_DATA."
    )

    size = LEADERBOARD_MD.stat().st_size
    assert size > 0, (
        f"leaderboard_row.md is empty (0 bytes): {LEADERBOARD_MD}\n"
        "Minimum content: schema stub or actual leaderboard rows."
    )


# ---- Test 3: decision note terminal verdict ----


def test_decision_note_exists_has_min_lines_and_valid_verdict():
    """Decision note exists, is >=20 lines, and ends with a valid terminal verdict."""
    assert DECISION_NOTE.exists(), (
        f"Decision note not found: {DECISION_NOTE}\n"
        "Expected in .planning/evidence/t0_1_x/decision_note.md."
    )

    lines = DECISION_NOTE.read_text().splitlines()
    non_blank = [ln for ln in lines if ln.strip()]

    assert len(non_blank) >= 20, (
        f"decision_note.md has only {len(non_blank)} non-blank lines; minimum is 20."
    )

    # Find the final non-blank line.
    last_line = non_blank[-1].strip()
    assert last_line in VALID_VERDICTS, (
        f"Final non-blank line of decision_note.md must be one of {VALID_VERDICTS}.\n"
        f"Got: {last_line!r}\n"
        f"File: {DECISION_NOTE}"
    )


# ---- Test 4: cross-reference integrity ----


def test_decision_note_cites_tournament_id_from_yaml():
    """Decision note contains the exact tournament_id from the YAML (case-sensitive)."""
    assert YAML_CONFIG.exists(), f"YAML not found: {YAML_CONFIG}"
    assert DECISION_NOTE.exists(), f"Decision note not found: {DECISION_NOTE}"

    cfg = yaml.safe_load(YAML_CONFIG.read_text())
    tid = cfg.get("tournament_id", "")
    assert tid, "tournament_id is missing from YAML"

    note_text = DECISION_NOTE.read_text()
    assert tid in note_text, (
        f"decision_note.md does not contain tournament_id {tid!r}.\n"
        "The decision note must cite the tournament_id from the YAML exactly "
        "(case-sensitive substring match).\n"
        f"File: {DECISION_NOTE}"
    )


# ---- Test 5: DECISION.md preamble ----


def test_decision_doc_exists_has_min_lines_and_decision_heading():
    """05-02-DECISION.md exists, is >=80 lines, and has a ## Decision: heading."""
    assert DECISION_DOC.exists(), (
        f"DECISION.md not found: {DECISION_DOC}\n"
        "Expected at .planning/phases/05-ml-cleanup-post-v0/05-02-DECISION.md."
    )

    lines = DECISION_DOC.read_text().splitlines()
    assert len(lines) >= 80, (
        f"05-02-DECISION.md has only {len(lines)} lines; minimum is 80.\n"
        f"File: {DECISION_DOC}"
    )

    has_decision_heading = any(re.match(r"^##\s+Decision:", ln) for ln in lines)
    assert has_decision_heading, (
        "05-02-DECISION.md must contain a '## Decision:' heading "
        "naming the selected experiment.\n"
        f"File: {DECISION_DOC}"
    )
