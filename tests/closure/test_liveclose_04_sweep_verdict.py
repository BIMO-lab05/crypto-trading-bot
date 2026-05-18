"""Unit tests for scripts.closure.liveclose_04_sweep_verdict.

Branch-coverage suite over the LIVECLOSE-04 sweep-verdict exporter. The
harness reads the T0.1.x sweep's `decision_note.md` terminal verdict +
`significance.json` per-symbol bootstrap p-values, validates them
against the verdict-acceptance contract, and writes structured evidence.

Status semantics (mirrors Plans 02/03):
  * Technical PASS -> AWAITING_HUMAN (operator commit + carry_ins.json flip remain).
  * INSUFFICIENT_DATA -> status=INSUFFICIENT_DATA (verdict line or missing p-values).
  * Malformed inputs / missing significance.json -> status=FAILED.

All filesystem writes use pytest's `tmp_path` fixture. Total runtime <5s
(no docker, no network).

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-05-PLAN.md
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema

from scripts.closure._common import SCHEMA_PATH
from scripts.closure.liveclose_04_sweep_verdict import (
    PASS_VERDICTS,
    VALID_VERDICTS,
    extract_bootstrap_pvalues,
    extract_terminal_verdict,
    main,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DECISION_NOTE_PASS = FIXTURES / "liveclose_04_decision_note_pass.md"
DECISION_NOTE_INSUFFICIENT = FIXTURES / "liveclose_04_decision_note_insufficient.md"
SIG_PASS = FIXTURES / "liveclose_04_significance_pass.json"
SIG_INSUFFICIENT = FIXTURES / "liveclose_04_significance_insufficient.json"


def _copy_fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Copy decision-note + significance.json fixtures into tmp_path.

    Returns (decision_note, significance_json, target_path).
    """
    dn = tmp_path / "decision_note.md"
    sj = tmp_path / "significance.json"
    target = tmp_path / "verdict.json"
    return dn, sj, target


# ---------------------------------------------------------------------------
# Constants — mirror the canonical source-of-record set
# ---------------------------------------------------------------------------


def test_valid_verdicts_matches_canonical_source():
    """VALID_VERDICTS must equal the literal in test_t0_1_x_experiment_shipped.py:48."""
    assert VALID_VERDICTS == {"EDGE_FOUND", "NO_EDGE_FOUND", "INSUFFICIENT_DATA"}


def test_pass_verdicts_excludes_insufficient_data():
    """PASS_VERDICTS strictly excludes INSUFFICIENT_DATA (terminal PASS contract)."""
    assert PASS_VERDICTS == {"EDGE_FOUND", "NO_EDGE_FOUND"}
    assert "INSUFFICIENT_DATA" not in PASS_VERDICTS


# ---------------------------------------------------------------------------
# Branch 1: PASS — verdict in PASS_VERDICTS AND >=1 symbol has non-null p-values
# ---------------------------------------------------------------------------


def test_pass_edge_found_with_pvalues(tmp_path):
    """EDGE_FOUND verdict + 3 symbols with non-null p-values -> AWAITING_HUMAN."""
    dn, sj, target = _copy_fixtures(tmp_path)
    shutil.copyfile(DECISION_NOTE_PASS, dn)
    shutil.copyfile(SIG_PASS, sj)

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 0, f"main() returned {rc}; expected 0 on AWAITING_HUMAN PASS"
    assert target.exists(), f"verdict.json not written to {target}"
    payload = json.loads(target.read_text())
    assert payload["status"] == "AWAITING_HUMAN"
    assert payload["liveclose_id"] == "LIVECLOSE-04"
    assert payload["verdict"] == "EDGE_FOUND"
    assert payload["n_symbols_with_pvalues"] == 3
    # human_needed=True because operator commit + carry_ins.json flip remain.
    assert payload["human_needed"] is True
    # per_symbol_pvalues preserves both axes.
    assert set(payload["per_symbol_pvalues"].keys()) == {
        "SOLUSDT",
        "BNBUSDT",
        "ADAUSDT",
    }
    assert payload["per_symbol_pvalues"]["SOLUSDT"]["sharpe_pvalue"] == 0.02


def test_pass_no_edge_found_with_pvalues(tmp_path):
    """NO_EDGE_FOUND verdict + p-values present -> AWAITING_HUMAN (terminal PASS)."""
    dn, sj, target = _copy_fixtures(tmp_path)
    # Copy pass decision note, then replace terminal line with NO_EDGE_FOUND.
    text = DECISION_NOTE_PASS.read_text()
    text = text.replace("EDGE_FOUND\n", "NO_EDGE_FOUND\n")
    dn.write_text(text)
    shutil.copyfile(SIG_PASS, sj)

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 0
    payload = json.loads(target.read_text())
    assert payload["status"] == "AWAITING_HUMAN"
    assert payload["verdict"] == "NO_EDGE_FOUND"
    assert payload["n_symbols_with_pvalues"] == 3


# ---------------------------------------------------------------------------
# Branch 2: INSUFFICIENT_DATA — verdict line or zero non-null p-values
# ---------------------------------------------------------------------------


def test_fail_insufficient_data(tmp_path):
    """INSUFFICIENT_DATA verdict + null p-values -> status=INSUFFICIENT_DATA."""
    dn, sj, target = _copy_fixtures(tmp_path)
    shutil.copyfile(DECISION_NOTE_INSUFFICIENT, dn)
    shutil.copyfile(SIG_INSUFFICIENT, sj)

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 1, f"main() returned {rc}; expected 1 on INSUFFICIENT_DATA"
    payload = json.loads(target.read_text())
    assert payload["status"] == "INSUFFICIENT_DATA"
    assert payload["verdict"] == "INSUFFICIENT_DATA"


def test_pass_verdict_with_no_pvalues_downgrades_to_insufficient(tmp_path):
    """EDGE_FOUND verdict but all p-values null -> downgrade to INSUFFICIENT_DATA.

    Load-bearing branch — verdict alone is NOT sufficient; >=1 symbol must
    have non-null bootstrap p-values for technical PASS.
    """
    dn, sj, target = _copy_fixtures(tmp_path)
    shutil.copyfile(DECISION_NOTE_PASS, dn)  # ends with EDGE_FOUND
    shutil.copyfile(SIG_INSUFFICIENT, sj)  # only nulls

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 1
    payload = json.loads(target.read_text())
    assert payload["status"] == "INSUFFICIENT_DATA"
    # verdict preserved — we don't rewrite operator's terminal line.
    assert payload["verdict"] == "EDGE_FOUND"
    assert payload["n_symbols_with_pvalues"] == 0


# ---------------------------------------------------------------------------
# Branch 3: FAILED — missing significance.json
# ---------------------------------------------------------------------------


def test_fail_missing_significance_json(tmp_path):
    """significance.json does not exist on disk -> status=FAILED."""
    dn, sj, target = _copy_fixtures(tmp_path)
    shutil.copyfile(DECISION_NOTE_PASS, dn)
    # Deliberately do NOT create sj.

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 2, f"main() returned {rc}; expected 2 on FAILED"
    payload = json.loads(target.read_text())
    assert payload["status"] == "FAILED"
    assert payload["failure_reason"] == "significance_json_missing"


# ---------------------------------------------------------------------------
# Branch 4: FAILED — unparseable verdict
# ---------------------------------------------------------------------------


def test_fail_unparseable_verdict(tmp_path):
    """Terminal line not in VALID_VERDICTS -> status=FAILED, failure_reason=unparseable_verdict."""
    dn, sj, target = _copy_fixtures(tmp_path)
    dn.write_text("# Some decision note\n\nMALFORMED_VERDICT\n")
    shutil.copyfile(SIG_PASS, sj)

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 2
    payload = json.loads(target.read_text())
    assert payload["status"] == "FAILED"
    assert payload["failure_reason"] == "unparseable_verdict"


# ---------------------------------------------------------------------------
# Branch 5: paper-only refusal under TRADING_MODE=LIVE
# ---------------------------------------------------------------------------


def test_paper_only_refusal_under_trading_mode_live(tmp_path, monkeypatch, capsys):
    """TRADING_MODE=LIVE refuses to run (T0.1.x is paper-mode-only by design)."""
    dn, sj, target = _copy_fixtures(tmp_path)
    shutil.copyfile(DECISION_NOTE_PASS, dn)
    shutil.copyfile(SIG_PASS, sj)
    monkeypatch.setenv("TRADING_MODE", "LIVE")

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )

    assert rc == 1
    captured = capsys.readouterr()
    assert "LIVE" in captured.err


# ---------------------------------------------------------------------------
# Schema validation — evidence round-trips through .planning/evidence/_schema.json
# ---------------------------------------------------------------------------


def test_evidence_validates_against_schema(tmp_path):
    """After a happy-path PASS run, the written evidence passes jsonschema validation."""
    dn, sj, target = _copy_fixtures(tmp_path)
    shutil.copyfile(DECISION_NOTE_PASS, dn)
    shutil.copyfile(SIG_PASS, sj)

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )
    assert rc == 0

    payload = json.loads(target.read_text())
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(payload, schema)

    # Explicit assertion: technical PASS = AWAITING_HUMAN, NOT COMPLETE.
    # Plan 05 follows Plans 02/03/04: operator commit + carry_ins.json flip
    # remain after harness PASS.
    assert payload["status"] == "AWAITING_HUMAN"
    assert payload["status"] != "COMPLETE"


# ---------------------------------------------------------------------------
# Helper function direct tests
# ---------------------------------------------------------------------------


def test_extract_terminal_verdict_handles_trailing_whitespace(tmp_path):
    """Trailing whitespace + blank lines after the verdict are stripped."""
    p = tmp_path / "trailing.md"
    p.write_text("# Note\n\nEDGE_FOUND   \n\n\n")
    assert extract_terminal_verdict(p) == "EDGE_FOUND"


def test_extract_bootstrap_pvalues_returns_per_symbol_dict():
    """extract_bootstrap_pvalues returns {symbol: {sharpe_pvalue, dir_acc_pvalue}}."""
    out = extract_bootstrap_pvalues(SIG_PASS)
    assert set(out.keys()) == {"SOLUSDT", "BNBUSDT", "ADAUSDT"}
    for sym in ("SOLUSDT", "BNBUSDT", "ADAUSDT"):
        assert "sharpe_pvalue" in out[sym]
        assert "dir_acc_pvalue" in out[sym]
    assert out["SOLUSDT"]["sharpe_pvalue"] == 0.02
    assert out["BNBUSDT"]["dir_acc_pvalue"] == 0.04


def test_fail_significance_json_malformed_no_per_symbol(tmp_path):
    """significance.json without `per_symbol` -> status=FAILED, failure_reason=significance_json_malformed."""
    dn, sj, target = _copy_fixtures(tmp_path)
    shutil.copyfile(DECISION_NOTE_PASS, dn)
    sj.write_text(json.dumps({"schema_version": 1, "tournament_id": "x"}))

    rc = main(
        [
            "--decision-note-path",
            str(dn),
            "--significance-json-path",
            str(sj),
            "--target-path",
            str(target),
        ]
    )
    assert rc == 2
    payload = json.loads(target.read_text())
    assert payload["status"] == "FAILED"
    assert payload["failure_reason"] == "significance_json_malformed"
