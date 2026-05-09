"""Atomic artifact writers for Phase 4 significance pipeline.

Implements D-03 (config-by-reference ensemble.json — no weights / no scalers /
no prediction arrays), D-14 (per-symbol significance.json schema), and CD-05
(leaderboard.md atomic write). Every writer mirrors the atomic-write pattern
from app/leaderboard/snapshot.py:65-87 verbatim — Path.write_text MUST NOT be
used here; it would defeat the atomic guarantee that downstream phases (04-02
bootstrap, 04-03 PR body) depend on.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Union

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _atomic_write(
    path: Path,
    payload: Union[str, bytes],
    *,
    prefix: str,
    suffix: str,
) -> None:
    """Atomic write helper — copies snapshot.py:65-87 verbatim.

    tempfile.mkstemp in target's parent dir → write payload via fdopen →
    flush + fsync → os.replace → best-effort chmod 0o644.
    On any exception, unlinks tmp file silently then re-raises.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(path.parent))
    mode = "wb" if isinstance(payload, (bytes, bytearray)) else "w"
    try:
        with os.fdopen(fd, mode) as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
        try:
            os.chmod(path, 0o644)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_ensemble(
    snapshot: Dict[str, Any],
    ensembles: Dict[str, list[Dict[str, Any]]],
    git_sha: str,
    output_path: Union[str, os.PathLike],
) -> Dict[str, Any]:
    """D-03/D-14: write {tournament_id}.ensemble.json — config-by-reference only.

    Inputs:
      snapshot   — Phase 3 export dict; only `tournament_id` is read here.
      ensembles  — {symbol: [{run_id, architecture, hp_hash, dsr}, ...]} per D-03.
      git_sha    — captured by caller from launcher._git_sha (or snapshot.config.git_sha).
      output_path— absolute or relative path; parent created if missing.

    Output JSON contains exactly: schema_version, tournament_id, git_sha,
    created_at, aggregation="mean_log_returns", ensembles. NO weights / scalers /
    prediction arrays — the test_write_ensemble_no_weights_no_predictions test
    grep-asserts this (T-04-03 mitigation).

    Returns the payload dict that was written.
    """
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tournament_id": snapshot["tournament_id"],
        "git_sha": git_sha,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "aggregation": "mean_log_returns",
        "ensembles": [{"symbol": s, "members": ms} for s, ms in ensembles.items()],
    }
    serialized = json.dumps(payload, indent=2, default=str)
    _atomic_write(Path(output_path), serialized, prefix="ensemble.", suffix=".json.tmp")
    logger.info("ensemble.json written: %s (%d symbols)", output_path, len(ensembles))
    return payload


def write_significance(
    snapshot: Dict[str, Any],
    per_symbol_results: Dict[str, Dict[str, Any]],
    *,
    git_sha: str,
    tournaments_evaluated_count: int,
    n_winning_symbols: int,
    output_path: Union[str, os.PathLike],
) -> Dict[str, Any]:
    """D-14: write {tournament_id}.significance.json.

    per_symbol_results values must include (per CD-07 / D-14):
      sharpe_lift, sharpe_pvalue, dir_acc_lift, dir_acc_pvalue,
      n_oos_bars, block_size, n_resamples, win_gate_passed (bool),
      n_members (int), bootstrap_seed (int).

    Top-level fields per D-14: per_symbol, baseline="persistence" (D-04),
    aggregation="mean_log_returns" (D-02), git_sha, evaluated_at,
    tournaments_evaluated_count (int), n_winning_symbols (int),
    schema_version, tournament_id.

    Returns the payload dict that was written.
    """
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tournament_id": snapshot["tournament_id"],
        # D-04 — string field allows future swap to "production_aggregator" without schema rev (D-14 note).
        "baseline": "persistence",
        "aggregation": "mean_log_returns",  # D-02
        "git_sha": git_sha,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "tournaments_evaluated_count": int(tournaments_evaluated_count),
        "n_winning_symbols": int(n_winning_symbols),
        "per_symbol": per_symbol_results,
    }
    serialized = json.dumps(payload, indent=2, default=str)
    _atomic_write(
        Path(output_path), serialized, prefix="significance.", suffix=".json.tmp"
    )
    logger.info(
        "significance.json written: %s (%d symbols, %d winners)",
        output_path,
        len(per_symbol_results),
        n_winning_symbols,
    )
    return payload


def write_leaderboard_markdown(
    markdown_text: str, output_path: Union[str, os.PathLike]
) -> str:
    """D-14 + CD-05: write {tournament_id}.leaderboard.md atomically.

    Returns the markdown text exactly as written so callers can re-use it
    (e.g. embed inline in PR body).
    """
    _atomic_write(
        Path(output_path), markdown_text, prefix="leaderboard.", suffix=".md.tmp"
    )
    logger.info(
        "leaderboard.md written: %s (%d chars)", output_path, len(markdown_text)
    )
    return markdown_text


__all__ = [
    "SCHEMA_VERSION",
    "write_ensemble",
    "write_significance",
    "write_leaderboard_markdown",
]
