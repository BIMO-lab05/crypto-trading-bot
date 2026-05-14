"""Per-symbol win gate for the Phase 4 significance pipeline (D-08 + CD-08).

A pure-function classifier: takes the per-symbol significance dict produced
by ``bootstrap.stationary_block_bootstrap_pvalue`` and returns it augmented
with ``win_gate_passed: bool`` plus a structured ``gate_failure_reasons``
list per symbol, alongside a top-level ``n_winning_symbols`` count.

D-08 — all four conditions per symbol must hold:
  1. ``sharpe_pvalue < 0.05``
  2. ``dir_acc_pvalue < 0.05``
  3. ``sharpe_lift > 0``
  4. ``dir_acc_lift > 0``

CD-08 — ``n_members < 3`` blocks the win regardless of the four conditions
and records reason ``"insufficient_runs"``. Pass-through fields stay
untouched so the leaderboard markdown / PR body can still report the
sub-3 numbers under an ``[insufficient runs]`` annotation.

T-04-08 — ``P_THRESHOLD`` and ``MIN_MEMBERS`` are module-level constants;
any future PR that lowers them is a code-review tripwire.

This module is pure-Python — no I/O, no metric helpers (TOURN-07), no
NumPy dependency.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Decision-record-pinned thresholds. Lowering these is a code-review tripwire.
P_THRESHOLD: float = 0.05  # D-08
MIN_MEMBERS: int = 3  # CD-08


def evaluate_win_gate(
    per_symbol_significance: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """D-08: classify each symbol; CD-08: block sub-3-member symbols.

    Parameters
    ----------
    per_symbol_significance
        ``{symbol: {sharpe_pvalue, dir_acc_pvalue, sharpe_lift, dir_acc_lift,
        n_members, ...}}``. Extra keys (e.g. ``bootstrap_seed``,
        ``n_oos_bars``, ``block_size``, ``n_resamples``) flow through
        unchanged into the per-symbol output (D-14 schema needs them).

    Returns
    -------
    dict
        ``{"per_symbol": {symbol: {**input, win_gate_passed: bool,
        gate_failure_reasons: list[str]}}, "n_winning_symbols": int}``.

    Notes
    -----
    Defensive defaults: a missing key reads as the worst plausible value
    (p-value 1.0, lift 0.0, n_members 0). Keeps the gate from raising
    ``KeyError`` on partial inputs while always producing a populated
    ``gate_failure_reasons`` list.
    """
    out_per_symbol: Dict[str, Dict[str, Any]] = {}
    n_wins = 0

    for sym, sig in per_symbol_significance.items():
        reasons: List[str] = []

        n_members = int(sig.get("n_members", 0))
        sharpe_p = float(sig.get("sharpe_pvalue", 1.0))
        dir_p = float(sig.get("dir_acc_pvalue", 1.0))
        sharpe_lift = float(sig.get("sharpe_lift", 0.0))
        dir_lift = float(sig.get("dir_acc_lift", 0.0))

        # CD-08: insufficient runs guard fires first so the reason is always
        # recorded even when the four conditions also fail.
        if n_members < MIN_MEMBERS:
            reasons.append("insufficient_runs")

        if not (sharpe_p < P_THRESHOLD):
            reasons.append(f"sharpe_pvalue>={P_THRESHOLD}")
        if not (dir_p < P_THRESHOLD):
            reasons.append(f"dir_acc_pvalue>={P_THRESHOLD}")
        if not (sharpe_lift > 0):
            reasons.append("sharpe_lift_non_positive")
        if not (dir_lift > 0):
            reasons.append("dir_acc_lift_non_positive")

        passed = len(reasons) == 0
        # Pass-through: input dict survives unchanged; only augmented.
        out_per_symbol[sym] = {
            **sig,
            "win_gate_passed": passed,
            "gate_failure_reasons": reasons,
        }
        if passed:
            n_wins += 1

    return {"per_symbol": out_per_symbol, "n_winning_symbols": n_wins}


__all__ = [
    "P_THRESHOLD",
    "MIN_MEMBERS",
    "evaluate_win_gate",
]
