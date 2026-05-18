#!/usr/bin/env python3
"""LIVECLOSE-04 sweep-verdict exporter.

Reads the T0.1.x sweep's terminal verdict from `decision_note.md` and the
per-symbol bootstrap p-values from `<tournament_id>.significance.json`,
asserts the verdict-acceptance contract, and writes structured evidence
JSON under `.planning/evidence/LIVECLOSE-04/`.

Contract corrections (vs loose ROADMAP wording — see Plan 11.1-05):
  * ROADMAP says verdict IN ('PASS','FAIL'). Actual valid terminals
    per services/tournament-harness/tests/integration/
    test_t0_1_x_experiment_shipped.py:48 are
    {EDGE_FOUND, NO_EDGE_FOUND, INSUFFICIENT_DATA}.
  * ROADMAP says p-values are persisted in a leaderboard DB column.
    No such column exists. P-values live in
    services/tournament-harness/data/snapshots/
    <tournament_id>.significance.json (per_symbol dict produced by
    open-pr CLI -> app/significance/artifacts.py::write_significance).
  * Terminal verdict lives as the final non-blank line of
    .planning/evidence/t0_1_x/decision_note.md (existing convention).

Acceptance contract:
  PASS = verdict in {EDGE_FOUND, NO_EDGE_FOUND} (NOT INSUFFICIENT_DATA)
         AND >=1 symbol has both sharpe_pvalue and dir_acc_pvalue non-null.
  -> status=AWAITING_HUMAN because operator still commits the resulting
     verdict.json + flips the LIVECLOSE-04 row in
     .planning/state/carry_ins.json. COMPLETE is reserved for terminal
     closures where no operator follow-up remains.

Operator workflow (this harness does NOT trigger the sweep itself):
  1. After OP-02 (migration 005 applied) + OP-03 (TOURNAMENT_READER_PASSWORD
     set), re-run the sweep:
        docker exec crypto-bot-tournament-harness \\
          python -m app.cli run /app/app/config/t0_1_x_experiment.yaml \\
                                --allow-dirty
  2. Open the PR (dry-run is enough to produce significance.json):
        docker exec crypto-bot-tournament-harness \\
          python -m app.cli open-pr t0_1_x_horizon_sweep \\
                                    --dry-run --allow-dirty
  3. Update .planning/evidence/t0_1_x/decision_note.md final line with
     the terminal verdict (EDGE_FOUND or NO_EDGE_FOUND), replacing the
     placeholder INSUFFICIENT_DATA line.
  4. Run this harness to capture closure evidence:
        python -m scripts.closure.liveclose_04_sweep_verdict
  5. Commit verdict.json under .planning/evidence/LIVECLOSE-04/ and flip
     the LIVECLOSE-04 row in .planning/state/carry_ins.json.

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-05-PLAN.md
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from scripts.closure._common import (
    STATUS_AWAITING_HUMAN,
    STATUS_FAILED,
    STATUS_INSUFFICIENT_DATA,
    write_evidence,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants — mirror the canonical source-of-record set.
# Source: services/tournament-harness/tests/integration/
#         test_t0_1_x_experiment_shipped.py:48
# Mirrored (not imported) because the harness must not pull a test module
# into a production-script import path; downstream maintainers should treat
# both copies as load-bearing and update them together.
# ---------------------------------------------------------------------------

VALID_VERDICTS: frozenset[str] = frozenset(
    {"EDGE_FOUND", "NO_EDGE_FOUND", "INSUFFICIENT_DATA"}
)
PASS_VERDICTS: frozenset[str] = frozenset({"EDGE_FOUND", "NO_EDGE_FOUND"})

LOG_PREFIX = "LIVECLOSE_04"
DEFAULT_TOURNAMENT_ID = "t0_1_x_horizon_sweep"
LIVECLOSE_ID = "LIVECLOSE-04"

# Path resolution: scripts/closure/liveclose_04_sweep_verdict.py is two
# directory levels below the repo root (parents[0]=closure/,
# parents[1]=scripts/, parents[2]=repo root). Mirrors _common.py idiom.
_REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Pure helpers — both unit-testable in isolation
# ---------------------------------------------------------------------------


def extract_terminal_verdict(decision_note_path: Path) -> str:
    """Return the terminal verdict from a decision_note.md.

    The terminal verdict is the final non-blank line of the file, after
    rstrip() to absorb trailing whitespace + blank lines. Must be a member
    of :data:`VALID_VERDICTS`.

    Raises:
        ValueError: when the final non-blank line is not a valid verdict.
    """
    text = decision_note_path.read_text()
    # Walk from the end; first non-blank rstripped line is the verdict.
    for raw in reversed(text.splitlines()):
        line = raw.rstrip()
        if line:
            if line in VALID_VERDICTS:
                return line
            raise ValueError(
                f"unparseable terminal verdict: {line!r}; "
                f"expected one of {sorted(VALID_VERDICTS)}"
            )
    raise ValueError(f"decision_note has no non-blank lines: {decision_note_path}")


def extract_bootstrap_pvalues(
    significance_json_path: Path,
) -> dict[str, dict[str, Optional[float]]]:
    """Return per-symbol bootstrap p-values from a significance.json.

    Shape produced by
    services/tournament-harness/app/significance/artifacts.py::write_significance:
        {
            "per_symbol": {
                "<SYMBOL>": {
                    "sharpe_pvalue": float | None,
                    "dir_acc_pvalue": float | None,
                    ...
                },
                ...
            },
            "n_winning_symbols": int,
            ...
        }

    Returns ``{symbol: {"sharpe_pvalue": ..., "dir_acc_pvalue": ...}}``.
    Null p-values flow through as ``None``.

    Raises:
        KeyError: when the file lacks a top-level ``per_symbol`` key.
    """
    payload = json.loads(significance_json_path.read_text())
    per_symbol = payload["per_symbol"]  # KeyError surfaces to caller
    if not isinstance(per_symbol, dict):
        raise KeyError(
            f"per_symbol must be a JSON object, got {type(per_symbol).__name__}"
        )
    out: dict[str, dict[str, Optional[float]]] = {}
    for symbol, sig in per_symbol.items():
        sharpe = sig.get("sharpe_pvalue")
        dir_acc = sig.get("dir_acc_pvalue")
        out[symbol] = {
            "sharpe_pvalue": float(sharpe) if sharpe is not None else None,
            "dir_acc_pvalue": float(dir_acc) if dir_acc is not None else None,
        }
    return out


def build_evidence_payload(
    verdict: str,
    per_symbol_pvalues: dict[str, dict[str, Optional[float]]],
    tournament_id: str,
    decision_note_path: str,
    significance_json_path: str,
) -> dict[str, Any]:
    """Assemble the evidence payload and resolve target status.

    Status resolution:
      * AWAITING_HUMAN — verdict in PASS_VERDICTS AND n_symbols_with_pvalues >= 1.
      * INSUFFICIENT_DATA — verdict == "INSUFFICIENT_DATA" OR
        (verdict in PASS_VERDICTS AND n_symbols_with_pvalues == 0).
      * FAILED is not produced here — caller raises before calling this
        helper when the inputs are malformed.
    """
    n_symbols_with_pvalues = sum(
        1
        for pv in per_symbol_pvalues.values()
        if pv["sharpe_pvalue"] is not None and pv["dir_acc_pvalue"] is not None
    )

    if verdict in PASS_VERDICTS and n_symbols_with_pvalues >= 1:
        status = STATUS_AWAITING_HUMAN
    else:
        # INSUFFICIENT_DATA verdict OR pass-verdict-with-no-pvalues downgrade.
        status = STATUS_INSUFFICIENT_DATA

    return {
        "status": status,
        "verdict": verdict,
        "tournament_id": tournament_id,
        "per_symbol_pvalues": per_symbol_pvalues,
        "decision_note_path": decision_note_path,
        "significance_json_path": significance_json_path,
        "n_symbols_with_pvalues": n_symbols_with_pvalues,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.closure.liveclose_04_sweep_verdict",
        description=(
            "LIVECLOSE-04 sweep-verdict exporter — reads T0.1.x decision_note "
            "+ significance.json, writes structured evidence under "
            ".planning/evidence/LIVECLOSE-04/."
        ),
    )
    parser.add_argument(
        "--tournament-id",
        default=DEFAULT_TOURNAMENT_ID,
        help=f"Tournament id (default: {DEFAULT_TOURNAMENT_ID}).",
    )
    parser.add_argument(
        "--decision-note-path",
        type=Path,
        default=_REPO / ".planning" / "evidence" / "t0_1_x" / "decision_note.md",
        help="Path to the T0.1.x decision_note.md.",
    )
    parser.add_argument(
        "--significance-json-path",
        type=Path,
        default=None,
        help=(
            "Path to <tournament_id>.significance.json. "
            "Default: services/tournament-harness/data/snapshots/"
            "<tournament_id>.significance.json."
        ),
    )
    parser.add_argument(
        "--target-path",
        type=Path,
        default=None,
        help=(
            "Output evidence JSON path. Default: "
            ".planning/evidence/LIVECLOSE-04/verdict-<utc_compact_ts>.json."
        ),
    )
    return parser


def _write_failed(
    *,
    failure_reason: str,
    target_path: Path,
    evidence_paths: list[str],
    decision_note_path: str,
    significance_json_path: str,
    extra_fields: Optional[dict[str, Any]] = None,
) -> None:
    """Write a FAILED evidence file. Used on missing/malformed inputs."""
    extra: dict[str, Any] = {
        "failure_reason": failure_reason,
        "decision_note_path": decision_note_path,
        "significance_json_path": significance_json_path,
    }
    if extra_fields:
        extra.update(extra_fields)
    write_evidence(
        liveclose_id=LIVECLOSE_ID,
        status=STATUS_FAILED,
        evidence_paths=evidence_paths,
        human_needed=True,
        extra=extra,
        target_path=target_path,
    )


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint.

    Exit codes:
      * 0 — STATUS_AWAITING_HUMAN (technical PASS; operator follow-up pending).
      * 1 — STATUS_INSUFFICIENT_DATA or paper-only refusal.
      * 2 — STATUS_FAILED (malformed/missing inputs).
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Paper-only refusal — T0.1.x sweep is paper-mode-only by design.
    # Mirrors LIVECLOSE-03 pattern. Done BEFORE argparse so an operator
    # who accidentally set TRADING_MODE=LIVE gets a fast, deterministic
    # exit without any IO.
    trading_mode = os.environ.get("TRADING_MODE", "").strip().upper()
    if trading_mode == "LIVE":
        print(
            f"{LOG_PREFIX}: refusing to run under TRADING_MODE=LIVE; "
            "T0.1.x sweep is paper-mode-only by design.",
            file=sys.stderr,
        )
        return 1

    parser = _build_parser()
    args = parser.parse_args(argv)

    tournament_id: str = args.tournament_id
    decision_note_path: Path = args.decision_note_path
    significance_json_path: Path = (
        args.significance_json_path
        if args.significance_json_path is not None
        else (
            _REPO
            / "services"
            / "tournament-harness"
            / "data"
            / "snapshots"
            / f"{tournament_id}.significance.json"
        )
    )
    target_path: Path = (
        args.target_path
        if args.target_path is not None
        else _resolve_default_target_path()
    )

    decision_note_str = str(decision_note_path)
    significance_json_str = str(significance_json_path)

    # Step 1 — verdict extraction (catches unparseable / missing-file cases).
    try:
        verdict = extract_terminal_verdict(decision_note_path)
    except FileNotFoundError:
        _write_failed(
            failure_reason="decision_note_missing",
            target_path=target_path,
            evidence_paths=[],
            decision_note_path=decision_note_str,
            significance_json_path=significance_json_str,
            extra_fields={"tournament_id": tournament_id},
        )
        print(
            f"{LOG_PREFIX}: decision_note not found at {decision_note_path}",
            file=sys.stderr,
        )
        return 2
    except ValueError as exc:
        _write_failed(
            failure_reason="unparseable_verdict",
            target_path=target_path,
            evidence_paths=[decision_note_str],
            decision_note_path=decision_note_str,
            significance_json_path=significance_json_str,
            extra_fields={"tournament_id": tournament_id, "error": str(exc)},
        )
        print(f"{LOG_PREFIX}: {exc}", file=sys.stderr)
        return 2

    # Step 2 — significance.json existence + parsing.
    if not significance_json_path.exists():
        _write_failed(
            failure_reason="significance_json_missing",
            target_path=target_path,
            evidence_paths=[decision_note_str],
            decision_note_path=decision_note_str,
            significance_json_path=significance_json_str,
            extra_fields={"tournament_id": tournament_id, "verdict": verdict},
        )
        print(
            f"{LOG_PREFIX}: significance.json not found at {significance_json_path}",
            file=sys.stderr,
        )
        return 2

    try:
        per_symbol_pvalues = extract_bootstrap_pvalues(significance_json_path)
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        _write_failed(
            failure_reason="significance_json_malformed",
            target_path=target_path,
            evidence_paths=[decision_note_str, significance_json_str],
            decision_note_path=decision_note_str,
            significance_json_path=significance_json_str,
            extra_fields={
                "tournament_id": tournament_id,
                "verdict": verdict,
                "error": str(exc),
            },
        )
        print(
            f"{LOG_PREFIX}: significance.json malformed: {exc}",
            file=sys.stderr,
        )
        return 2

    # Step 3 — build payload + resolve status.
    payload = build_evidence_payload(
        verdict=verdict,
        per_symbol_pvalues=per_symbol_pvalues,
        tournament_id=tournament_id,
        decision_note_path=decision_note_str,
        significance_json_path=significance_json_str,
    )
    status = payload.pop("status")

    extra: dict[str, Any] = payload
    write_evidence(
        liveclose_id=LIVECLOSE_ID,
        status=status,
        evidence_paths=[decision_note_str, significance_json_str],
        human_needed=True,
        extra=extra,
        target_path=target_path,
    )

    logger.info(
        "%s verdict=%s status=%s n_symbols_with_pvalues=%d",
        LOG_PREFIX,
        verdict,
        status,
        payload["n_symbols_with_pvalues"],
    )

    if status == STATUS_AWAITING_HUMAN:
        return 0
    # status is STATUS_INSUFFICIENT_DATA — only other reachable branch here.
    return 1


def _resolve_default_target_path() -> Path:
    """Compute the default evidence target path under .planning/evidence/LIVECLOSE-04/."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _REPO / ".planning" / "evidence" / LIVECLOSE_ID / f"verdict-{ts}.json"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
