"""Unit tests for app.pr.body — PR title + body templating (CD-01, CD-12, D-09, D-14)."""

from __future__ import annotations

import re


from app.pr.body import (
    MAX_BODY_CHARS,
    render_leaderboard_markdown,
    render_pr_body,
    render_pr_title,
)


# --- helpers ------------------------------------------------------------------


def _row(symbol: str, run_id: str, **overrides):
    base = {
        "run_id": run_id,
        "symbol": symbol,
        "architecture": "gru",
        "hp_hash": "deadbeef",
        "status": "success",
        "dsr": 0.5,
        "psr": 0.6,
        "cpcv_dsr": 0.4,
        "oos_sharpe": 0.7,
        "dir_acc_corrected": 0.55,
    }
    base.update(overrides)
    return base


def _snapshot(symbols=("BTCUSDT",), rows=None):
    rows = list(rows or [])
    return {
        "tournament_id": "t-test",
        "summary": {"symbols": list(symbols)},
        "rows": rows,
    }


def _significance(per_symbol: dict, n_winning_symbols: int = 0):
    return {"per_symbol": per_symbol, "n_winning_symbols": n_winning_symbols}


# --- title -------------------------------------------------------------------


def test_pr_title_under_90_chars():
    long_tid = "a" * 64
    title = render_pr_title(
        tournament_id=long_tid, n_winning_symbols=2, n_total_symbols=5
    )
    assert len(title) <= 90


def test_pr_title_truncates_tid_to_12():
    long_tid = "abcdefghijklmnopqrstuvwxyz0123456789"
    title = render_pr_title(
        tournament_id=long_tid, n_winning_symbols=1, n_total_symbols=3
    )
    assert long_tid[:12] in title
    assert long_tid not in title  # full tid must not appear


def test_pr_title_format():
    title = render_pr_title(
        tournament_id="t-001", n_winning_symbols=2, n_total_symbols=5
    )
    assert re.fullmatch(
        r"^Tournament [A-Za-z0-9._\-]+: ensemble wins \d+/\d+ symbols \(p<0\.05 vs persistence\)$",
        title,
    )


# --- body --------------------------------------------------------------------


def _make_body(
    *,
    n_winning_symbols=1,
    tournaments_evaluated_count=3,
    prior_tids=("t-prev1", "t-prev2"),
    symbols=("BTCUSDT",),
    extra_rows=None,
):
    rows = [_row(symbols[0], "r1", dsr=0.9), _row(symbols[0], "r2", dsr=0.8)]
    if extra_rows:
        rows.extend(extra_rows)
    snap = _snapshot(symbols=symbols, rows=rows)
    per_symbol = {
        symbols[0]: {
            "win_gate_passed": n_winning_symbols >= 1,
            "gate_failure_reasons": []
            if n_winning_symbols >= 1
            else ["sharpe_pvalue>=0.05"],
            "n_members": 3,
            "sharpe_pvalue": 0.01,
            "dir_acc_pvalue": 0.02,
            "sharpe_lift": 0.1,
            "dir_acc_lift": 0.05,
        }
    }
    sig = _significance(per_symbol, n_winning_symbols=n_winning_symbols)
    ensembles = {
        symbols[0]: [
            {"run_id": "r1", "architecture": "gru", "hp_hash": "h", "dsr": 0.9}
        ]
    }
    lb_md = render_leaderboard_markdown(snap, sig, ensembles)
    body = render_pr_body(
        tournament_id="t-test",
        git_sha="abc1234",
        snapshot=snap,
        ensembles=ensembles,
        significance=sig,
        leaderboard_markdown=lb_md,
        leaderboard_md_relative_path="data/snapshots/t-test.leaderboard.md",
        tournaments_evaluated_count=tournaments_evaluated_count,
        prior_tournament_ids=prior_tids,
    )
    return body, snap, sig, ensembles, lb_md


def test_pr_body_contains_required_sections():
    body, *_ = _make_body()
    for marker in (
        "## Leaderboard",
        "## Ensemble",
        "## Significance",
        "## Reproduce",
        "## Disclosure",
    ):
        assert marker in body, f"missing section header: {marker}"


def test_pr_body_includes_tournaments_evaluated_count():
    body, *_ = _make_body(tournaments_evaluated_count=7)
    assert "tournaments_evaluated_count: 7" in body


def test_pr_body_includes_bonferroni_note():
    body, *_ = _make_body()
    assert "p_adjusted" in body
    assert "DSR deflates within a tournament, NOT across" in body


def test_pr_body_reproducer_line_present():
    body, *_ = _make_body()
    matches = re.findall(
        r"python -m services\.tournament_harness\.app\.cli reproduce [^\s]+ --git-sha [^\s]+",
        body,
    )
    assert len(matches) == 1, (
        f"expected exactly one reproducer line, found {len(matches)}"
    )


def test_pr_body_length_cap_falls_back_to_summary():
    # Manufacture 200+ rows so leaderboard markdown alone exceeds 60k.
    big_rows = [_row("BTCUSDT", f"r{i}", dsr=0.9 - i * 0.001) for i in range(300)]
    body, *_ = _make_body(extra_rows=big_rows)
    assert len(body) <= MAX_BODY_CHARS
    assert "data/snapshots/t-test.leaderboard.md" in body


def test_pr_body_renders_per_symbol_status_tags():
    # Win symbol gets [WIN]; force a failing symbol to get [no win]; insufficient_runs case too.
    snap = _snapshot(
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        rows=[
            _row("BTCUSDT", "r1", dsr=0.9),
            _row("ETHUSDT", "r2", dsr=0.8),
            _row("SOLUSDT", "r3", dsr=0.7),
        ],
    )
    per_symbol = {
        "BTCUSDT": {
            "win_gate_passed": True,
            "gate_failure_reasons": [],
            "n_members": 3,
        },
        "ETHUSDT": {
            "win_gate_passed": False,
            "gate_failure_reasons": ["sharpe_pvalue>=0.05"],
            "n_members": 3,
        },
        "SOLUSDT": {
            "win_gate_passed": False,
            "gate_failure_reasons": ["insufficient_runs"],
            "n_members": 1,
        },
    }
    sig = _significance(per_symbol, n_winning_symbols=1)
    ensembles = {s: [] for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
    md = render_leaderboard_markdown(snap, sig, ensembles)
    assert "[WIN]" in md
    assert "[no win]" in md
    assert "[insufficient runs]" in md


def test_pr_body_handles_zero_wins():
    body, *_ = _make_body(n_winning_symbols=0)
    # Title still renders — render the title separately.
    title = render_pr_title(
        tournament_id="t-test", n_winning_symbols=0, n_total_symbols=1
    )
    assert "wins 0/" in title
    assert "no_win: true" in body
