#!/usr/bin/env python3
"""Fail the commit if an account-size literal is written into money code.

THE ACCOUNT IS $100. ``shared/account.py`` is the declaration of record and
the number must never appear as a literal (CLAUDE.md, .claude/rules/money.md).
The repository accumulated ~1,000 occurrences of ``10000`` as a capital figure
and the purge only sticks if something mechanical stops the next one landing.

Why this matches on CONTEXT rather than on the bare number
----------------------------------------------------------
A plain ``\\b10_?000\\b`` scan over the money paths returns ~80 hits on the
current tree, and the overwhelming majority are legitimate:

  * basis-point arithmetic -- ``* 10000``, ``/ Decimal("10000")``,
    ``bps / 10_000.0`` -- in post_trade_analysis, exchanges/router, funding_gate,
    paper_slippage, twap_vwap
  * query bounds (``le=10000``), Prometheus buckets, bootstrap resample counts
    (``n_resamples=10_000``), log tails, millisecond timeouts
  * ~15 fix-provenance comments that quote the old value ("was 10000.0")

A guard with that false-positive rate gets ``SKIP=``'d within a week, which
defeats the point. So this matches a capital-ish NAME adjacent to the literal,
which is the shape the defect actually takes:

    initial_capital: float = 10000.0        portfolio.get("balance", 10000)
    BacktestConfig(initial_capital=10000)   "initial_balance": 10000
    MAX_POSITION_VALUE_USD = 10000.0        "totalEquity": "10000.00"

The baseline is not an amnesty
------------------------------
The tree was NOT clean when this guard landed: 48 real account-size literals
remained across 33 files, mostly research/backtest harnesses in ``scripts/``
and ``backtesting/`` passing ``initial_capital=10000.0``, plus operator shell
scripts defaulting to ``.get('initial_balance', 10000)``. They are recorded in
``scripts/capital_literals_baseline.txt`` so the guard can be switched on
without a flag day. Every line in that file is a defect and the file is the
burn-down list — delete lines from it as they are fixed, never add to it.

Usage
-----
    python3 scripts/check_capital_literals.py                # scan money paths
    python3 scripts/check_capital_literals.py FILE [FILE...] # scan given files
    python3 scripts/check_capital_literals.py --update-baseline

Exit code 1 on any hit that is neither allowlisted nor baselined. Run from the
repository root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "scripts" / "capital_literals_baseline.txt"

# Directories whose contents size, account for, or display real capital.
MONEY_GLOBS = (
    "services/*/app/**/*.py",
    "scripts/**/*.py",
    "scripts/**/*.sh",
    "backtesting/**/*.py",
    "frontend/src/**/*.js",
    "frontend/src/**/*.jsx",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.tsx",
)

# Identifiers/keys that mean "an amount of account money". Deliberately does
# NOT include bare "value" -- `position_value` and `total_value` are listed
# explicitly instead, because `spread_value`, `atr_value` and friends are not
# capital and would drown the signal.
CAPITAL_WORD = r"""
    initial_capital | initial_balance | starting_capital | starting_balance
  | paper_initial_balance | account_size | account_equity | account_balance
  | portfolio_value | total_value | total_equity | totalEquity
  | wallet_balance | walletBalance | net_worth | net_liquidation
  | capital | balance | equity | funds
"""

# A 10,000-ish account-size literal: 10000, 10_000, 10000.0, "10000.00".
LITERAL = r"""["']? \b (?: 10_?000 ) (?: \.0+ )? \b ["']?"""

# capital-ish name, then at most a short run of separator/type/constructor
# characters, then the literal. The bounded gap is what keeps
# `balance` on one side of a long line from binding to an unrelated 10000
# on the other.
PATTERN = re.compile(
    rf"(?ix) (?: {CAPITAL_WORD} ) [\"']? \s* [:=,)]? [^,()\[\]]{{0,28}}? \s* {LITERAL}"
)

# ---------------------------------------------------------------------------
# Allowlist. Every entry names a REAL hit on the tree at the time this guard
# landed, with the reason it is not an account-size literal. Entries that are
# genuine defects are marked DEFECT and carry an owner -- they are suppressed
# only so the guard can be enabled at all, and should be burned down.
# ---------------------------------------------------------------------------
ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    # (path suffix, substring that must appear in the line, reason)
    (
        "services/bybit-connector/app/bybit_rest_client.py",
        "totalEquity",
        "mock wallet-balance fixture for the stubbed REST client, not a config default",
    ),
    (
        "services/bybit-connector/app/bybit_rest_client.py",
        "walletBalance",
        "same mock fixture as above",
    ),
    (
        "services/portfolio-manager/app/services/performance_history.py",
        '"all": 10000',
        "row-limit sentinel for an 'all history' query, not money",
    ),
    (
        "services/trading-engine/app/strategies/grid_trading_strategy_v2.py",
        "MAX_POSITION_VALUE_USD",
        "DEFECT: $10k per-position ceiling on a $100 account. Owned by the "
        "trading-engine work; suppressed here only so this guard can be enabled.",
    ),
)


def is_allowlisted(rel_path: str, line: str) -> bool:
    return any(
        rel_path.endswith(suffix) and needle in line
        for suffix, needle, _reason in ALLOWLIST
    )


def in_money_paths(path: Path) -> bool:
    """Whether `path` is in scope, tested WITHOUT walking the tree.

    pre-commit passes staged filenames, and globbing every money path just to
    build a membership set costs ~15s on this NTFS mount — slow enough that
    the hook would get skipped, which is how guards die.
    """
    try:
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return False

    if path.suffix not in (".py", ".sh", ".js", ".jsx", ".ts", ".tsx"):
        return False
    if rel.startswith(("scripts/", "backtesting/", "frontend/src/")):
        return True
    # services/<name>/app/... only — a service's tests/ and scripts/ are not
    # in scope here.
    parts = rel.split("/")
    return len(parts) > 3 and parts[0] == "services" and parts[2] == "app"


def iter_target_files(argv: list[str]) -> list[Path]:
    """Files to scan: those named on argv, else every file under MONEY_GLOBS."""
    if argv:
        return [Path(a).resolve() for a in argv if Path(a).is_file()]
    found: list[Path] = []
    for glob in MONEY_GLOBS:
        found.extend(REPO_ROOT.glob(glob))
    return sorted(found)


def _blank_python_prose(text: str) -> str:
    """Blank comments and triple-quoted strings, preserving line numbering.

    Comments and docstrings quote the old value ON PURPOSE -- "was 10000.0,
    100x the real account" is the provenance of a fix and deleting it would be
    worse than keeping it. Triple-quoted strings only: single-quoted strings
    must survive, because `portfolio.get("balance", 10000)` needs its key to
    still be visible for the pattern to bind.
    """
    import io
    import tokenize

    lines = text.split("\n")
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text  # unparseable: scan it raw rather than skipping it

    for tok in tokens:
        is_comment = tok.type == tokenize.COMMENT
        is_docstring = tok.type == tokenize.STRING and tok.string.lstrip("rbuRBUf")[
            :3
        ] in ('"""', "'''")
        if not (is_comment or is_docstring):
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        for row in range(srow, erow + 1):
            i = row - 1
            if i >= len(lines):
                break
            start = scol if row == srow else 0
            end = ecol if row == erow else len(lines[i])
            lines[i] = lines[i][:start] + " " * (end - start) + lines[i][end:]

    return "\n".join(lines)


def scan(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    raw_lines = text.split("\n")
    if path.suffix == ".py":
        text = _blank_python_prose(text)

    hits = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        if line.strip().startswith(("#", "//", "*")):
            continue
        if PATTERN.search(line):
            hits.append((lineno, raw_lines[lineno - 1].strip()))
    return hits


def baseline_key(rel_path: str, line: str) -> str:
    """Identity of an offending line that survives the line moving.

    Keyed on path plus normalised text, not on a line number, so unrelated
    edits above an offender don't churn the baseline.
    """
    return f"{rel_path}::{' '.join(line.split())}"


def load_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    return {
        ln.rstrip("\n")
        for ln in BASELINE_PATH.read_text(encoding="utf-8").split("\n")
        if ln.strip() and not ln.startswith("#")
    }


def collect(targets: list[Path]) -> list[tuple[str, int, str]]:
    found = []
    for path in targets:
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in scan(path):
            if is_allowlisted(rel, line):
                continue
            found.append((rel, lineno, line))
    return found


def write_baseline(entries: list[tuple[str, int, str]]) -> None:
    header = [
        "# Pre-existing account-size literals, recorded so the guard can be",
        "# enabled without a flag day. Every line here is a REAL defect: a",
        "# $10,000 figure on a $100 account. New offenders are rejected; these",
        "# are the burn-down list. Delete a line as you fix it.",
        "#",
        "# Regenerate: python3 scripts/check_capital_literals.py --update-baseline",
        "",
    ]
    body = sorted({baseline_key(rel, line) for rel, _no, line in entries})
    BASELINE_PATH.write_text("\n".join(header + body) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    update = "--update-baseline" in argv
    argv = [a for a in argv if not a.startswith("--")]

    targets = iter_target_files(argv)
    # A file named on argv may sit outside the money paths (pre-commit passes
    # whatever is staged); only those paths are in scope.
    if argv:
        targets = [p for p in targets if in_money_paths(p)]

    if update:
        entries = collect(iter_target_files([]))
        write_baseline(entries)
        print(f"Baseline written: {len(entries)} pre-existing offending line(s).")
        return 0

    baseline = load_baseline()
    failures: list[str] = []
    for rel, lineno, line in collect(targets):
        if baseline_key(rel, line) in baseline:
            continue
        failures.append(f"{rel}:{lineno}: {line}")

    if failures:
        print("Account-size literal found in money code.\n")
        print("THE ACCOUNT IS $100. Do not write the number as a literal.")
        print("  services/*/app/**  -> read the service's own Settings")
        print("                        (settings.paper_initial_balance)")
        print("  scripts/, backtesting/, tests/ -> from shared.account import ...")
        print("See .claude/rules/money.md.\n")
        for f in failures:
            print(f"  {f}")
        print(
            f"\n{len(failures)} offending line(s). If a hit is genuinely not an "
            "account size, add it to ALLOWLIST in this file with a reason.\n"
            "Pre-existing offenders live in scripts/capital_literals_baseline.txt "
            "and are not reported here; do not add new lines to that file to "
            "silence this check."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
