"""Tests for app.significance.win_gate.evaluate_win_gate (D-08 + CD-08)."""

from __future__ import annotations

from typing import Any, Dict

from app.significance.win_gate import (
    MIN_MEMBERS,
    P_THRESHOLD,
    evaluate_win_gate,
)


def _passing_entry(**overrides: Any) -> Dict[str, Any]:
    """Helper: a four-conditions-pass entry; overrides per-field for negative tests."""
    base: Dict[str, Any] = {
        "sharpe_pvalue": 0.01,
        "dir_acc_pvalue": 0.02,
        "sharpe_lift": 0.05,
        "dir_acc_lift": 0.02,
        "n_members": 3,
        # Pass-through extras the gate must preserve untouched.
        "n_oos_bars": 500,
        "block_size": 22,
        "n_resamples": 10_000,
        "bootstrap_seed": 1234567,
    }
    base.update(overrides)
    return base


def test_constants_match_decision_record() -> None:
    """T-04-08: code-review tripwire on threshold drift."""
    assert P_THRESHOLD == 0.05  # D-08
    assert MIN_MEMBERS == 3  # CD-08


def test_win_when_all_four_conditions_pass() -> None:
    """D-08: all four conditions hold → win_gate_passed True, empty reasons."""
    sig = {"BTCUSDT": _passing_entry()}
    out = evaluate_win_gate(sig)
    assert out["n_winning_symbols"] == 1
    btc = out["per_symbol"]["BTCUSDT"]
    assert btc["win_gate_passed"] is True
    assert btc["gate_failure_reasons"] == []


def test_no_win_when_sharpe_pvalue_fails() -> None:
    """D-08 condition 1: sharpe_pvalue >= 0.05 blocks the win."""
    sig = {"BTCUSDT": _passing_entry(sharpe_pvalue=0.05)}
    out = evaluate_win_gate(sig)
    btc = out["per_symbol"]["BTCUSDT"]
    assert btc["win_gate_passed"] is False
    assert any("sharpe_pvalue" in r for r in btc["gate_failure_reasons"])
    assert out["n_winning_symbols"] == 0


def test_no_win_when_dir_acc_pvalue_fails() -> None:
    """D-08 condition 2: dir_acc_pvalue >= 0.05 blocks the win."""
    sig = {"BTCUSDT": _passing_entry(dir_acc_pvalue=0.10)}
    out = evaluate_win_gate(sig)
    btc = out["per_symbol"]["BTCUSDT"]
    assert btc["win_gate_passed"] is False
    assert any("dir_acc_pvalue" in r for r in btc["gate_failure_reasons"])


def test_no_win_when_sharpe_lift_non_positive() -> None:
    """D-08 condition 3: sharpe_lift <= 0 blocks the win."""
    sig = {"BTCUSDT": _passing_entry(sharpe_lift=0.0)}
    out = evaluate_win_gate(sig)
    btc = out["per_symbol"]["BTCUSDT"]
    assert btc["win_gate_passed"] is False
    assert any("sharpe_lift" in r for r in btc["gate_failure_reasons"])


def test_no_win_when_dir_acc_lift_negative() -> None:
    """D-08 condition 4: dir_acc_lift <= 0 (here negative) blocks the win."""
    sig = {"BTCUSDT": _passing_entry(dir_acc_lift=-0.001)}
    out = evaluate_win_gate(sig)
    btc = out["per_symbol"]["BTCUSDT"]
    assert btc["win_gate_passed"] is False
    assert any("dir_acc_lift" in r for r in btc["gate_failure_reasons"])


def test_insufficient_runs_blocks_win() -> None:
    """CD-08: n_members < 3 → blocked + reason 'insufficient_runs'.

    The pass-through input fields stay untouched so the PR body / leaderboard
    can still report the (sub-3) numbers as ``[insufficient runs]``.
    """
    sig = {"BTCUSDT": _passing_entry(n_members=2)}
    out = evaluate_win_gate(sig)
    btc = out["per_symbol"]["BTCUSDT"]
    assert btc["win_gate_passed"] is False
    assert "insufficient_runs" in btc["gate_failure_reasons"]
    assert btc["n_members"] == 2  # input survived
    assert btc["sharpe_pvalue"] == 0.01  # input survived


def test_n_winning_symbols_count() -> None:
    """3 symbols: 2 passing, 1 failing on dir_acc → n_winning_symbols == 2."""
    sig = {
        "BTCUSDT": _passing_entry(),
        "ETHUSDT": _passing_entry(),
        "SOLUSDT": _passing_entry(dir_acc_pvalue=0.50),
    }
    out = evaluate_win_gate(sig)
    assert out["n_winning_symbols"] == 2
    assert out["per_symbol"]["BTCUSDT"]["win_gate_passed"] is True
    assert out["per_symbol"]["ETHUSDT"]["win_gate_passed"] is True
    assert out["per_symbol"]["SOLUSDT"]["win_gate_passed"] is False


def test_returns_full_pass_through() -> None:
    """Input keys not consumed by the gate flow through unchanged.

    Specifically guards `bootstrap_seed`, `n_oos_bars`, `block_size`,
    `n_resamples` — required by D-14 significance.json schema.
    """
    sig = {"BTCUSDT": _passing_entry(custom_field="kept")}
    out = evaluate_win_gate(sig)
    btc = out["per_symbol"]["BTCUSDT"]
    assert btc["custom_field"] == "kept"
    assert btc["bootstrap_seed"] == 1234567
    assert btc["n_oos_bars"] == 500
    assert btc["block_size"] == 22
    assert btc["n_resamples"] == 10_000


def test_multiple_failure_reasons_aggregate() -> None:
    """A symbol failing on several conditions records each reason."""
    sig = {
        "BTCUSDT": _passing_entry(
            sharpe_pvalue=0.5,
            dir_acc_pvalue=0.5,
            sharpe_lift=-0.01,
            dir_acc_lift=0.0,
            n_members=2,
        )
    }
    out = evaluate_win_gate(sig)
    reasons = out["per_symbol"]["BTCUSDT"]["gate_failure_reasons"]
    assert len(reasons) >= 4  # all four + insufficient_runs


def test_missing_keys_default_to_failing() -> None:
    """Defensive defaults: a symbol with no signal data fails gate, never crashes.

    The harness shouldn't pass empty dicts in normal flow, but a defensive
    default keeps the gate from raising KeyError on partial inputs.
    """
    sig: Dict[str, Dict[str, Any]] = {"BTCUSDT": {}}
    out = evaluate_win_gate(sig)
    btc = out["per_symbol"]["BTCUSDT"]
    assert btc["win_gate_passed"] is False
    assert len(btc["gate_failure_reasons"]) >= 1


def test_empty_input_yields_zero_wins() -> None:
    """Edge: no symbols → empty per_symbol, n_winning_symbols == 0."""
    out = evaluate_win_gate({})
    assert out == {"per_symbol": {}, "n_winning_symbols": 0}
