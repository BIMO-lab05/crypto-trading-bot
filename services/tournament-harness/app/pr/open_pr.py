"""run_open_pr — orchestrator for `tournament open-pr {tid}` (D-02, D-04, D-09, D-10, D-11).

Wires the 04-01 / 04-02 / 04-07 modules into the operator-facing pipeline:

  1. Load the snapshot (data/snapshots/{tid}.json).
  2. Refuse on a dirty git tree unless --allow-dirty (D-11) — exit 3.
  3. Build per-symbol top-3 ensembles (04-01 select_top_n_per_symbol).
  4. For each member, fetch (or build via 04-07's predict_fn) OOS predictions.
  5. Convert each member's pred_prices → log-returns (04-01 helper) and
     equal-weight average across members per timestep (D-02 — the load-bearing
     aggregation contract). NEVER average in price space.
  6. Compute ensemble + persistence-baseline metrics through metrics_bridge
     entry points only (B2 — no parallel Sharpe/dir-acc here).
  7. Bootstrap p-values on per-bar paired diffs (D-05/D-06 stationary block
     bootstrap; one-tailed; seed = derive_seed(tid, sym)).
  8. evaluate_win_gate over ALL symbols (W1 — even insufficient_runs symbols
     flow through so the gate populates gate_failure_reasons).
  9. Write 3 artifacts (ensemble.json, significance.json, leaderboard.md)
     atomically (artifacts.py).
 10. If n_winning_symbols >= 1 and not dry_run: open draft PR via gh CLI.
     Else: log + exit 0.

Exit codes:
  0  success (PR opened, dry-run, or no-win)
  2  GH_TOKEN unset OR gh not installed (raised by pr.gh)
  3  dirty git tree without --allow-dirty (raised here)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from app.leaderboard.db import LeaderboardDB
from app.orchestrator.launcher import _git_is_dirty, _git_sha
from app.pr.body import (
    render_leaderboard_markdown,
    render_pr_body,
    render_pr_title,
)
from app.pr.gh import open_draft_pr

# D-02 wiring: aggregate_log_returns + log_returns_from_predictions are the
# canonical 04-01 helpers. open_pr.py imports them here and NEVER averages
# member pred_prices in price space (B5 acceptance gate).
from app.significance.artifacts import (
    write_ensemble,
    write_leaderboard_markdown,
    write_significance,
)
from app.significance.bootstrap import (
    derive_seed,
    stationary_block_bootstrap_pvalue,
)

# D-02 acceptance grep gates require single-line imports of
# `aggregate_log_returns` and `log_returns_from_predictions` so we re-import
# them here on dedicated lines. The bundled `from ... import (...)` block above
# stays for consistency with other modules and is harmless (Python re-binds).
from app.significance.ensemble import (
    member_descriptor,
    select_top_n_per_symbol,
)
from app.significance.ensemble import aggregate_log_returns
from app.significance.predict_cache import get_or_build_predictions
from app.significance.predict_cache import log_returns_from_predictions
from app.significance.win_gate import evaluate_win_gate

# B2 + B5: every metric routes through metrics_bridge. NO local _sharpe / _dir_acc.
# CONTEXT.md canonical_refs: "do NOT re-implement Sharpe/dir-acc on log-returns".
from app.runner.metrics_bridge import (
    dir_acc_corrected_from_log_returns,
    probabilistic_sharpe_ratio,
)

# B3: production predict callable (04-07) — replaces the prior stub from 04-01.
from app.runner.predict_fn import build_predict_fn


logger = logging.getLogger(__name__)

HARNESS_ROOT = Path(__file__).resolve().parents[2]  # services/tournament-harness/


def _zero_safe_baseline_sharpe(
    baseline_log_ret: np.ndarray, *, var_eps: float = 1e-12
) -> float:
    """Sharpe of the D-04 persistence baseline, never nan.

    PSR is undefined for a zero-variance series (returns nan per
    ``sharpe_metrics.probabilistic_sharpe_ratio`` docstring line 171-172).
    The persistence baseline is exactly that: predict ``last_close`` every
    step → log-return = 0 every bar → constant zero series. A constant
    baseline has no risk-adjusted return signal, so we DEFINE its Sharpe
    to be 0.0. The lift ``ens_sharpe - base_sharpe`` then reduces to the
    candidate's own PSR, which is the load-bearing comparison anyway.

    Scope is bounded by T-04-10-01: this shortcut applies ONLY to the
    baseline side. The candidate still flows through the full canonical
    PSR path at the call site. A genuinely flat candidate yields
    ``candidate_psr = nan``, ``lift = nan - 0 = nan``, and the win-gate's
    ``not (lift > 0)`` check (``nan > 0`` is False) records
    ``sharpe_lift_non_positive`` — the fix never masks a no-edge candidate.

    The ``var_eps`` gate (``1e-12``) catches floating-point drift around
    strict zero — if an upstream subtraction produces a series of 1e-15
    instead of strict zeros, the canonical PSR would still return nan
    (``std == 0.0`` strict equality holds at that magnitude in some
    representations); ``var_eps`` makes the short-circuit robust.
    """
    arr = np.asarray(baseline_log_ret, dtype=float)
    if arr.size < 2:
        return 0.0
    if float(np.std(arr, ddof=1)) < var_eps:
        return 0.0
    return float(probabilistic_sharpe_ratio(arr, benchmark_sr=0.0))


def _load_snapshot(tournament_id: str) -> Dict[str, Any]:
    path = HARNESS_ROOT / "data" / "snapshots" / f"{tournament_id}.json"
    if not path.exists():
        raise SystemExit(f"snapshot not found: {path}")
    with open(path) as f:
        return json.load(f)


def run_open_pr(
    tournament_id: str,
    *,
    allow_dirty: bool = False,
    dry_run: bool = False,
    output_suffix: str = "",
) -> int:
    """Orchestrate snapshot → ensemble → significance → artifacts → gh.

    W2: ``output_suffix`` (default empty) inserts a ``.{suffix}`` segment into
    artifact filenames so 04-04 ``reproduce`` can write
    ``{tid}.dry-run.{ensemble,significance,leaderboard}.{json,md}`` without
    overwriting the operator's originals.
    """
    if not allow_dirty and _git_is_dirty():
        sys.stderr.write(
            "git tree dirty — refusing to open PR. "
            "Pass --allow-dirty if intentional (mirrors `tournament run`).\n"
        )
        raise SystemExit(3)
    git_sha = _git_sha()
    snapshot = _load_snapshot(tournament_id)
    rows = snapshot["rows"]

    # B3: factory closes over snapshot once; per-row callable below.
    row_predict = build_predict_fn(snapshot)

    # 1. Per-symbol top-3 ensemble (D-01).
    selected = select_top_n_per_symbol(rows, n=3)
    ensembles: Dict[str, List[Dict[str, Any]]] = {
        sym: [member_descriptor(r) for r in members]
        for sym, members in selected.items()
    }

    # 2. Per-symbol significance.
    per_symbol_significance: Dict[str, Dict[str, Any]] = {}
    for sym, members in selected.items():
        member_preds: List[dict] = []
        for m in members:
            preds = get_or_build_predictions(
                harness_root=HARNESS_ROOT,
                tournament_id=tournament_id,
                run_id=m["run_id"],
                # bind row per-iteration via default-arg trick
                predict_fn=lambda member_row=m: row_predict(member_row),
            )
            member_preds.append(preds)
        n_members = len(member_preds)
        seed = derive_seed(tournament_id, sym)

        # W1: every symbol — including n_members < 3 — flows through
        # evaluate_win_gate. The gate populates gate_failure_reasons:
        # ["insufficient_runs"] per 04-02 Task 2.
        if n_members < 3:
            per_symbol_significance[sym] = {
                "n_members": n_members,
                "sharpe_pvalue": 1.0,
                "dir_acc_pvalue": 1.0,
                "sharpe_lift": 0.0,
                "dir_acc_lift": 0.0,
                "n_oos_bars": 0,
                "block_size": 0,
                "n_resamples": 0,
                "bootstrap_seed": seed,
            }
            continue

        # 2a. Per-member log-return arrays (D-02 step 1). CD-11: actual_prices
        #     and last_close are identical across members for the same symbol.
        actual_prices = member_preds[0]["actual_prices"]
        last_close = member_preds[0]["last_close"]
        for mp in member_preds[1:]:
            if mp["actual_prices"].shape != actual_prices.shape:
                raise ValueError(
                    f"{sym}: ensemble members disagree on actual_prices length"
                )
            if mp["last_close"].shape != last_close.shape:
                raise ValueError(
                    f"{sym}: ensemble members disagree on last_close length"
                )

        member_log_rets = [
            log_returns_from_predictions(mp["pred_prices"], mp["last_close"])
            for mp in member_preds
        ]

        # 2b. Equal-weighted mean across members per timestep (D-02 step 2 —
        #     the load-bearing aggregation; differs from price-space averaging
        #     by a Jensen gap and is canonical per 04-01 Task 2).
        ens_log_ret = aggregate_log_returns(member_log_rets)

        # 2c. Reference series.
        actual_log_ret = log_returns_from_predictions(actual_prices, last_close)
        # D-04 persistence baseline: predict last_close every step → log-return = 0.
        baseline_log_ret = np.zeros_like(actual_log_ret)

        # 2d. Ensemble + baseline metrics — single canonical entry points (B2 + B5).
        ens_dir_acc = float(
            dir_acc_corrected_from_log_returns(actual_log_ret, ens_log_ret)
        )
        base_dir_acc = float(
            dir_acc_corrected_from_log_returns(actual_log_ret, baseline_log_ret)
        )
        ens_sharpe = float(probabilistic_sharpe_ratio(ens_log_ret, benchmark_sr=0.0))
        # Plan 04-10 Gap A fix: PSR(zeros) returns nan (std==0 → divide-by-zero
        # in the canonical formula). The persistence baseline IS all-zero log
        # returns by D-04 design. Define its Sharpe as 0.0 so the lift below
        # is finite. The candidate's PSR path is unchanged.
        base_sharpe = _zero_safe_baseline_sharpe(baseline_log_ret)
        sharpe_lift = ens_sharpe - base_sharpe
        dir_acc_lift = ens_dir_acc - base_dir_acc

        # 2e. Bootstrap p-values on per-bar paired diffs (D-05). Test statistic
        #     is r.mean() (raw lift) — NOT a Sharpe re-implementation. The
        #     user-facing numbers (sharpe_lift, dir_acc_lift) already came
        #     from canonical bridge entry points above.
        paired_d = ens_log_ret - baseline_log_ret  # ≡ ens_log_ret under persistence
        sharpe_res = stationary_block_bootstrap_pvalue(
            paired_d,
            metric_fn=lambda r: float(r.mean()),  # B2: raw mean — NOT a parallel Sharpe
            n_resamples=10_000,
            seed=seed,
        )
        ens_signs = np.sign(ens_log_ret)
        base_signs = np.sign(baseline_log_ret)
        actual_signs = np.sign(actual_log_ret)
        ens_agree = (ens_signs == actual_signs).astype(float)
        base_agree = (base_signs == actual_signs).astype(float)
        dir_paired = ens_agree - base_agree
        dir_res = stationary_block_bootstrap_pvalue(
            dir_paired,
            metric_fn=lambda r: float(r.mean()),
            n_resamples=10_000,
            seed=seed ^ 0xA5A5A5A5,
        )

        per_symbol_significance[sym] = {
            "n_members": n_members,
            "sharpe_pvalue": sharpe_res["p_value"],
            "sharpe_lift": sharpe_lift,
            "dir_acc_pvalue": dir_res["p_value"],
            "dir_acc_lift": dir_acc_lift,
            "n_oos_bars": sharpe_res["n_oos_bars"],
            "block_size": sharpe_res["block_size"],
            "n_resamples": sharpe_res["n_resamples"],
            "bootstrap_seed": seed,
        }

    # 3. Win gate (W1: ALL symbols flow through, including insufficient_runs).
    gate_out = evaluate_win_gate(per_symbol_significance)

    # 4. Artifacts. W2: output_suffix parameterizes paths so reproduce never
    #    overwrites the operator's originals.
    snapshot_dir = HARNESS_ROOT / "data" / "snapshots"
    suffix_seg = f".{output_suffix}" if output_suffix else ""
    ensemble_path = snapshot_dir / f"{tournament_id}{suffix_seg}.ensemble.json"
    sig_path = snapshot_dir / f"{tournament_id}{suffix_seg}.significance.json"
    lb_md_path = snapshot_dir / f"{tournament_id}{suffix_seg}.leaderboard.md"

    write_ensemble(snapshot, dict(ensembles), git_sha, ensemble_path)

    # tournaments_evaluated_count: queried at PR-open time (D-09 — never module-level).
    db_path = HARNESS_ROOT / "data" / "leaderboard" / "tournaments.db"
    if db_path.exists():
        db = LeaderboardDB(db_path)
        try:
            tcount = db.count_tournaments()
            priors = sorted({r["tournament_id"] for r in db.list_runs()}, reverse=True)[
                :20
            ]
        finally:
            db.close()
    else:
        tcount, priors = 0, []

    write_significance(
        snapshot,
        gate_out["per_symbol"],
        git_sha=git_sha,
        tournaments_evaluated_count=tcount,
        n_winning_symbols=gate_out["n_winning_symbols"],
        output_path=sig_path,
    )
    lb_md_text = render_leaderboard_markdown(
        snapshot,
        {"per_symbol": gate_out["per_symbol"]},
        ensembles,
    )
    write_leaderboard_markdown(lb_md_text, lb_md_path)

    # 5. Open PR (or skip).
    n_wins = gate_out["n_winning_symbols"]
    n_total = len(snapshot["summary"]["symbols"])
    title = render_pr_title(
        tournament_id=tournament_id,
        n_winning_symbols=n_wins,
        n_total_symbols=n_total,
    )
    body = render_pr_body(
        tournament_id=tournament_id,
        git_sha=git_sha,
        snapshot=snapshot,
        ensembles=ensembles,
        significance={
            "per_symbol": gate_out["per_symbol"],
            "n_winning_symbols": n_wins,
        },
        leaderboard_markdown=lb_md_text,
        leaderboard_md_relative_path=str(
            lb_md_path.relative_to(HARNESS_ROOT.parent.parent)
        ),
        tournaments_evaluated_count=tcount,
        prior_tournament_ids=priors,
    )
    labels = ["tournament", "evaluation-gate"]
    if n_wins >= 1:
        labels.append("winner")

    if n_wins == 0:
        print(
            json.dumps(
                {
                    "tournament_id": tournament_id,
                    "no_win": True,
                    "n_total": n_total,
                },
                indent=2,
            )
        )
        return 0
    if dry_run:
        print(
            json.dumps(
                {
                    "tournament_id": tournament_id,
                    "n_winning_symbols": n_wins,
                    "title": title,
                    "branch": f"tournament/{tournament_id}",
                    "labels": labels,
                    "dry_run": True,
                },
                indent=2,
            )
        )
        return 0
    url = open_draft_pr(
        title=title,
        body=body,
        head=f"tournament/{tournament_id}",
        labels=tuple(labels),
    )
    print(
        json.dumps(
            {
                "tournament_id": tournament_id,
                "n_winning_symbols": n_wins,
                "pr_url": url,
            },
            indent=2,
        )
    )
    return 0


__all__ = ["run_open_pr"]
