"""PR title + body templating for `tournament open-pr` (CD-01, CD-05, CD-12, D-09).

Constants:
  MAX_BODY_CHARS = 60_000  # CD-12 GitHub PR-body length cap with safety margin.

Public API:
  render_pr_title(*, tournament_id, n_winning_symbols, n_total_symbols) -> str
      CD-01: ≤90 chars; tournament_id truncated to 12 chars when long.

  render_leaderboard_markdown(snapshot, significance, ensembles) -> str
      CD-05: GFM table per symbol; ensemble members marked with ★;
      symbol status tag [WIN] / [no win] / [insufficient runs] (CD-08, D-14).

  render_pr_body(...) -> str
      Full PR body. If len > MAX_BODY_CHARS, falls back to a summary form
      that links out to `data/snapshots/{tid}.leaderboard.md`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


MAX_BODY_CHARS = 60_000  # CD-12


def _finite_or(value, fallback: float) -> float:
    """Finite float or fallback — NaN is truthy, so `or 0.0` fabricates numbers."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return fallback
    return f if f == f and f not in (float("inf"), float("-inf")) else fallback


def _fmt4(value) -> str:
    """Render a metric honestly: 'n/a' for missing/NaN (psr is now always NULL
    per SEV-7 — printing 0.0000 would re-fabricate the number the rename killed)."""
    f = _finite_or(value, float("nan"))
    return "n/a" if f != f else f"{f:.4f}"


def render_pr_title(
    *,
    tournament_id: str,
    n_winning_symbols: int,
    n_total_symbols: int,
) -> str:
    """CD-01: ≤90 chars; truncate tournament_id to 12 chars if needed."""
    short = tournament_id[:12]
    return (
        f"Tournament {short}: ensemble wins {n_winning_symbols}/{n_total_symbols}"
        f" symbols (p<0.05 vs persistence)"
    )


def _status_tag(sig: Dict[str, Any]) -> str:
    """CD-08/D-14 leaderboard tag for one symbol."""
    if sig.get("win_gate_passed"):
        return "[WIN]"
    reasons = sig.get("gate_failure_reasons") or []
    if "insufficient_runs" in reasons:
        return "[insufficient runs]"
    return "[no win]"


def render_leaderboard_markdown(
    snapshot: Dict[str, Any],
    significance: Dict[str, Any],
    ensembles: Dict[str, List[Dict[str, Any]]],
) -> str:
    """CD-05: top-5 per symbol GFM table; ensemble rows marked with ★; symbol status tag."""
    lines: List[str] = []
    per_symbol = significance.get("per_symbol", {})
    for symbol in snapshot["summary"]["symbols"]:
        sig = per_symbol.get(symbol, {})
        tag = _status_tag(sig)
        lines.append(f"### {symbol} {tag}")
        lines.append("")
        lines.append(
            "| ★ | architecture | hp_hash | dsr | psr | cpcv_dsr | oos_sharpe | dir_acc_corrected |"
        )
        lines.append(
            "|---|--------------|---------|-----|-----|----------|------------|-------------------|"
        )
        ensemble_run_ids = {m["run_id"] for m in ensembles.get(symbol, [])}
        top_5 = sorted(
            [
                r
                for r in snapshot["rows"]
                if r["symbol"] == symbol and r.get("status") == "success"
            ],
            key=lambda r: -_finite_or(r.get("dsr"), float("-inf")),
        )[:5]
        for r in top_5:
            star = "★" if r["run_id"] in ensemble_run_ids else " "
            lines.append(
                f"| {star} | {r['architecture']} | {r['hp_hash']} | "
                f"{_fmt4(r.get('dsr'))} | {_fmt4(r.get('psr'))} | "
                f"{_fmt4(r.get('cpcv_dsr'))} | {_fmt4(r.get('oos_sharpe'))} | "
                f"{_fmt4(r.get('dir_acc_corrected'))} |"
            )
        lines.append("")
    return "\n".join(lines)


def _render_disclosure(
    *,
    tournaments_evaluated_count: int,
    prior_tids: Iterable[str],
) -> str:
    priors = list(prior_tids)[:20]
    return (
        "## Disclosure (anti-cherry-picking, D-09)\n\n"
        f"- tournaments_evaluated_count: {tournaments_evaluated_count}\n"
        "- p_adjusted ≈ p_value × tournaments_evaluated_count\n"
        "- DSR deflates within a tournament, NOT across tournaments — multiple-testing correction is the operator's job.\n"
        f"- Prior tournament_ids (most recent {len(priors)}): "
        + (", ".join(f"`{t}`" for t in priors) if priors else "_(none)_")
    )


def _short_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, sort_keys=True)


def render_pr_body(
    *,
    tournament_id: str,
    git_sha: str,
    snapshot: Dict[str, Any],
    ensembles: Dict[str, List[Dict[str, Any]]],
    significance: Dict[str, Any],
    leaderboard_markdown: str,
    leaderboard_md_relative_path: str,
    tournaments_evaluated_count: int,
    prior_tournament_ids: Iterable[str],
) -> str:
    """Full PR body with CD-12 fallback to summary+link when over MAX_BODY_CHARS."""
    n_wins = significance.get("n_winning_symbols", 0)
    n_total = len(snapshot["summary"]["symbols"])
    no_win = "true" if n_wins == 0 else "false"

    header = (
        f"# Tournament Significance — {tournament_id}\n\n"
        f"- git_sha: `{git_sha}`\n"
        f"- evaluated_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"- n_winning_symbols: {n_wins} / {n_total}\n"
        f"- no_win: {no_win}\n"
        f"- baseline: persistence\n"
        f"- aggregation: mean_log_returns\n"
    )
    ensemble_md = (
        "## Ensemble (config-by-reference)\n\n```json\n"
        + _short_json(ensembles)
        + "\n```"
    )
    sig_md = "## Significance\n\n```json\n" + _short_json(significance) + "\n```"
    repro_md = (
        "## Reproduce\n\n```bash\n"
        f"python -m services.tournament_harness.app.cli reproduce {tournament_id}"
        f" --git-sha {git_sha}\n"
        "```\n"
    )
    lb_md = "## Leaderboard\n\n" + leaderboard_markdown
    disc_md = _render_disclosure(
        tournaments_evaluated_count=tournaments_evaluated_count,
        prior_tids=prior_tournament_ids,
    )

    full = "\n\n".join([header, lb_md, ensemble_md, sig_md, repro_md, disc_md])
    if len(full) <= MAX_BODY_CHARS:
        return full

    # CD-12 fallback: drop the leaderboard markdown, link to the file artifact.
    link = (
        f"\n\n_Leaderboard exceeded {MAX_BODY_CHARS} chars; full table at_"
        f" `{leaderboard_md_relative_path}`"
    )
    summary = "\n\n".join([header, ensemble_md, sig_md, repro_md, disc_md]) + link
    if len(summary) <= MAX_BODY_CHARS:
        return summary

    # Hard fallback: drop the ensemble + significance JSON blobs too.
    return (
        header
        + "\n\n"
        + repro_md
        + "\n\n"
        + disc_md
        + f"\n\n_Body truncated; see `{leaderboard_md_relative_path}` and the artifacts in the PR diff._"
    )


__all__ = [
    "MAX_BODY_CHARS",
    "render_pr_title",
    "render_leaderboard_markdown",
    "render_pr_body",
]
