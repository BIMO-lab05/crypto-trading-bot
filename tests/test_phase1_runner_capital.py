"""
The Phase-1 runner must default --capital to the declared account size.

main() passes initial_capital=args.capital explicitly, so the argparse default
overrides backtest_engine's already-corrected PAPER_INITIAL_BALANCE default on
every default invocation.

tests/test_account_size_invariant.py cannot catch this: add_argument is not in
DEFAULT_CARRYING_CALLS, the flag is the string "--capital" rather than an
identifier, and "capital" alone is not in CAPITAL_NAMES. Adding the file to
SCANNED_FILES would be a false guard, so this scans the source directly.

Importing the module is not viable - the parser is built inside main() and
import pulls pandas plus data_downloader.
"""

import ast
from pathlib import Path

from shared.account import DEFAULTS

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "backtesting" / "run_phase1_backtest.py"


def test_runner_has_no_ten_thousand_literal():
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and not isinstance(node.value, bool)
        and isinstance(node.value, (int, float))
        and float(node.value) == 10000.0
    ]
    assert not offenders, (
        f"run_phase1_backtest.py lines {offenders}: the account is "
        f"${DEFAULTS['PAPER_INITIAL_BALANCE']:g}. Source --capital from "
        "shared.account.ACCOUNT_EQUITY_USD."
    )


def test_runner_sources_capital_from_shared_account():
    source = RUNNER.read_text(encoding="utf-8")
    assert "from shared.account import ACCOUNT_EQUITY_USD" in source
    assert "default=ACCOUNT_EQUITY_USD" in source
