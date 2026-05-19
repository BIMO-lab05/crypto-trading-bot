"""Unit tests for scripts.closure.liveclose_03_psr_evidence.

Covers PASS / INSUFFICIENT / EMPTY / paper-mode-refusal / gap-streak /
ACCRUAL_WINDOW_DAYS import-drift / evidence-payload natural-keys branches
of the LIVECLOSE-03 PSR-evidence exporter.

All filesystem writes use pytest's ``tmp_path`` fixture — no test writes
into the repo ``.planning/evidence/`` tree. All DB queries use
``sqlite3.connect(":memory:")`` — no docker, no network.

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-04-PLAN.md
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import jsonschema
import pytest

from scripts.closure import liveclose_03_psr_evidence as harness
from scripts.closure._common import (
    STATUS_AWAITING_HUMAN,
    STATUS_INSUFFICIENT_DATA,
    load_schema,
)
from scripts.closure.liveclose_03_psr_evidence import (
    ACCRUAL_WINDOW_DAYS,
    build_evidence_payload,
    main,
    query_seven_day_window,
)
from scripts.forward_paper_test.run_evidence_loop import (
    ACCRUAL_WINDOW_DAYS as RUN_EVIDENCE_LOOP_ACCRUAL_WINDOW_DAYS,
)

# Fixture file lives next to this test file. The plan calls for resolution
# via Path(__file__).resolve().parents[1] / "closure" / "fixtures" / ... ,
# but the test file already lives under tests/closure/ so the parents[0]
# parent (tests/closure/) + fixtures/ is the direct route.
_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "liveclose_03_seven_day_fixture.sql"
)


def load_fixture_section(section: str) -> str:
    """Return SQL text for the named ``-- SECTION:`` block in the fixture file.

    Sections recognised: ``schema``, ``pass_fixture``, ``insufficient_fixture``,
    ``gap_fixture``.
    """
    sql_text = _FIXTURE_PATH.read_text()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    buf: list[str] = []
    for line in sql_text.splitlines():
        if line.startswith("-- SECTION:"):
            if current is not None:
                sections[current] = "\n".join(buf)
            current = line.split(":", 1)[1].strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf)
    if section not in sections:
        raise KeyError(
            f"Section '{section}' not found in {_FIXTURE_PATH}. "
            f"Available: {sorted(sections)}"
        )
    return sections[section]


def _seed(conn: sqlite3.Connection, *section_names: str) -> None:
    """Run schema + zero or more data sections against ``conn``."""
    pieces = [
        load_fixture_section("schema"),
        *(load_fixture_section(s) for s in section_names),
    ]
    conn.executescript("\n".join(pieces))


# ---------------------------------------------------------------------------
# 1. Import drift detector — ACCRUAL_WINDOW_DAYS single source of truth
# ---------------------------------------------------------------------------


def test_imports_accrual_window_from_run_evidence_loop():
    """Harness ACCRUAL_WINDOW_DAYS == run_evidence_loop's == 7.

    This drift detector fails loudly if either side redefines ``7``. The
    contract is the import line itself; this test enforces it survives
    refactors and formatter passes.
    """
    assert ACCRUAL_WINDOW_DAYS == RUN_EVIDENCE_LOOP_ACCRUAL_WINDOW_DAYS == 7

    # Stronger guarantee: the constant must resolve to the same object
    # identity (literal int) — guards against a future re-binding to a
    # different int value in the harness module.
    assert harness.ACCRUAL_WINDOW_DAYS is RUN_EVIDENCE_LOOP_ACCRUAL_WINDOW_DAYS, (
        "harness ACCRUAL_WINDOW_DAYS was rebound — single-source-of-truth broken"
    )


# ---------------------------------------------------------------------------
# 2-4. Pure-query branches (PASS / INSUFFICIENT / EMPTY)
# ---------------------------------------------------------------------------


def test_pass_with_seven_consecutive_days():
    """7 consecutive-day rows in one natural-key group → AWAITING_HUMAN."""
    conn = sqlite3.connect(":memory:")
    _seed(conn, "pass_fixture")

    rows = query_seven_day_window(conn)
    assert len(rows) >= 7, "expected all 7 rows from the passing group"

    payload = build_evidence_payload(rows, db_path=":memory:")
    assert payload["status"] == STATUS_AWAITING_HUMAN
    assert payload["row_count"] == 7
    assert payload["consecutive_days_observed_max"] == 7
    conn.close()


def test_insufficient_with_six_days():
    """6 consecutive-day rows (one short of window) → INSUFFICIENT_DATA."""
    conn = sqlite3.connect(":memory:")
    _seed(conn, "insufficient_fixture")

    rows = query_seven_day_window(conn)
    assert rows == [], "6-day fixture must not satisfy ≥7-day window"

    payload = build_evidence_payload(rows, db_path=":memory:")
    assert payload["status"] == STATUS_INSUFFICIENT_DATA
    assert payload["row_count"] == 0
    conn.close()


def test_empty_table_returns_insufficient():
    """Empty leaderboard table → empty result + INSUFFICIENT_DATA."""
    conn = sqlite3.connect(":memory:")
    _seed(conn)  # schema only, no inserts

    rows = query_seven_day_window(conn)
    assert rows == []

    payload = build_evidence_payload(rows, db_path=":memory:")
    assert payload["status"] == STATUS_INSUFFICIENT_DATA
    assert payload["consecutive_days_observed_max"] == 0
    conn.close()


# ---------------------------------------------------------------------------
# 5-6. main() exit codes + schema-valid file write
# ---------------------------------------------------------------------------


def _seed_tmp_db(tmp_path: Path, *section_names: str) -> Path:
    """Create a fresh on-disk sqlite at tmp_path/tournament.db with the named
    fixture sections applied, return the path."""
    db_path = tmp_path / "tournament.db"
    conn = sqlite3.connect(db_path)
    try:
        _seed(conn, *section_names)
    finally:
        conn.close()
    return db_path


def test_main_exit_code_on_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """main(...) returns 0 when the DB has a ≥7-day passing group; writes
    a schema-valid evidence file with status=AWAITING_HUMAN."""
    monkeypatch.delenv("TRADING_MODE", raising=False)
    db_path = _seed_tmp_db(tmp_path, "pass_fixture")
    target = tmp_path / "psr-evidence.json"

    rc = main(
        [
            "--db-path",
            str(db_path),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 0
    assert target.exists()
    payload = json.loads(target.read_text())
    jsonschema.validate(payload, load_schema())
    assert payload["liveclose_id"] == "LIVECLOSE-03"
    assert payload["status"] == "AWAITING_HUMAN"
    assert payload["human_needed"] is True
    assert payload["row_count"] == 7
    assert payload["consecutive_days_observed_max"] == 7


def test_main_exit_code_on_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """main(...) returns 1 when no group meets the window; writes a
    schema-valid evidence file with status=INSUFFICIENT_DATA."""
    monkeypatch.delenv("TRADING_MODE", raising=False)
    db_path = _seed_tmp_db(tmp_path, "insufficient_fixture")
    target = tmp_path / "psr-evidence.json"

    rc = main(
        [
            "--db-path",
            str(db_path),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 1
    assert target.exists()
    payload = json.loads(target.read_text())
    jsonschema.validate(payload, load_schema())
    assert payload["liveclose_id"] == "LIVECLOSE-03"
    assert payload["status"] == "INSUFFICIENT_DATA"
    assert payload["row_count"] == 0


# ---------------------------------------------------------------------------
# 7. Paper-only refusal under TRADING_MODE=LIVE
# ---------------------------------------------------------------------------


def test_paper_only_refusal_under_trading_mode_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """TRADING_MODE=LIVE in the environment forces SystemExit(1) before any
    SQL is touched; stderr names LIVE so the operator knows why."""
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    # Use a path that does NOT exist so we'd see a sqlite error if the
    # guard didn't fire first.
    bogus_db = tmp_path / "nonexistent.db"

    with pytest.raises(SystemExit) as excinfo:
        main(["--db-path", str(bogus_db), "--target-path", str(tmp_path / "x.json")])

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "LIVE" in captured.err, f"stderr should mention LIVE; got: {captured.err!r}"


# ---------------------------------------------------------------------------
# 8. Consecutive-streak detection with a gap (longest streak < window)
# ---------------------------------------------------------------------------


def test_consecutive_streak_detection_with_gap():
    """8 rows split 4+4 with one missing day in between — longest streak
    is 4 < ACCRUAL_WINDOW_DAYS=7, so INSUFFICIENT_DATA."""
    conn = sqlite3.connect(":memory:")
    _seed(conn, "gap_fixture")

    rows = query_seven_day_window(conn)
    assert rows == [], (
        "Gap fixture has 8 rows but max consecutive streak is 4; "
        "harness must NOT treat total-count as the criterion."
    )

    payload = build_evidence_payload(rows, db_path=":memory:")
    assert payload["status"] == STATUS_INSUFFICIENT_DATA
    conn.close()


# ---------------------------------------------------------------------------
# 9. Evidence payload carries the natural-key tuple for the operator
# ---------------------------------------------------------------------------


def test_evidence_payload_contains_natural_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """After a PASS run, ``extra.natural_keys_passing`` is a list and contains
    the passing group's natural key: (gru, SOLUSDT, 5, log_returns, abc123)."""
    monkeypatch.delenv("TRADING_MODE", raising=False)
    db_path = _seed_tmp_db(tmp_path, "pass_fixture")
    target = tmp_path / "psr-evidence.json"

    rc = main(["--db-path", str(db_path), "--target-path", str(target)])
    assert rc == 0

    payload = json.loads(target.read_text())
    assert "natural_keys_passing" in payload
    assert isinstance(payload["natural_keys_passing"], list)
    # JSON tuples decay to lists; the harness uses lists directly so the
    # JSON-round-trip is identity. Each natural key is a 5-element list:
    # [architecture, symbol, horizon, target_mode, hp_hash].
    assert ["gru", "SOLUSDT", 5, "log_returns", "abc123"] in payload[
        "natural_keys_passing"
    ]


# ---------------------------------------------------------------------------
# Extra: T-11.1-04-01 mitigation smoke — harness must never INSERT/UPDATE/DELETE.
# ---------------------------------------------------------------------------


def test_query_does_not_mutate_leaderboard(tmp_path: Path):
    """Running the read-side query against an on-disk DB does not change
    the row set — T-11.1-04-01 (Tampering) disposition: mitigate."""
    db_path = _seed_tmp_db(tmp_path, "pass_fixture", "insufficient_fixture")

    # Snapshot row count before.
    conn = sqlite3.connect(db_path)
    before = conn.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0]

    # Run the read-side query.
    _ = query_seven_day_window(conn)

    after = conn.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0]
    conn.close()

    assert before == after == 13, (
        f"harness must not mutate leaderboard (before={before}, after={after})"
    )
