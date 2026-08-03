"""The $100 account invariant, enforced by AST inspection.

THE ACCOUNT IS $100. `shared/account.py` is the declaration of record. This test
fails if any in-scope file re-declares an account size as a bare numeric literal.

Implemented with `ast`, not regex, deliberately: the AST gives the assignment
TARGET NAME structurally and excludes docstrings and comments for free, which
removes most of the false-positive surface without special-casing.

Evidence: `.planning/audits/2026-08-03-capital-audit.md`
Plan:     `.planning/quick/260803-4mt-enforce-100-account-invariant/`
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shared.account import DEFAULTS

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# SCAN SURFACE — bounded on purpose. This is a SCOPING DECISION, not an
# oversight.
#
# A repo-wide detector would also light up on the audit's P2 bucket (55 hits /
# 11 files under the strict pattern, ~169 files under the broad sweep) and its
# P3 bucket (docstrings and `__main__` demo blocks). Both are explicitly out of
# scope for this change, so a repo-wide detector would land red and could never
# go green. These 12 files are the audit's P1 set — the ones this change
# actually fixes.
# ---------------------------------------------------------------------------
SCANNED_FILES = (
    "services/trading-engine/app/trading_enhancements/kill_switch.py",
    "services/trading-engine/app/handlers/performance_dashboard.py",
    "services/trading-engine/app/handlers/statistical_arbitrage.py",
    "services/trading-engine/app/managers/statistical_arbitrage_manager.py",
    "services/trading-engine/app/main.py",
    "services/trading-engine/app/strategies/backtester.py",
    "services/risk-metrics-service/app/backtest_models.py",
    "services/risk-metrics-service/app/backtesting.py",
    "services/risk-metrics-service/app/main.py",
    "backtesting/simulators/risk_of_ruin.py",
    "backtesting/simulators/monte_carlo.py",
    "services/technical-analysis/backtesting/sqzmom_backtest.py",
)

# ---------------------------------------------------------------------------
# EXPANSION_QUEUE — deliberate next batches, in rough priority order. Nothing
# below is covered by this test today; their absence from SCANNED_FILES must not
# be mistaken for coverage. See the audit for the full tables.
#
#   1. P2 — test fixtures. 55 hits across 11 files matched the strict pattern in
#      `services/*/tests/`; a broader "any capital literal in a test-named file"
#      sweep matched ~169 further files. Highest-density offenders:
#      `services/trading-engine/tests/strategies/test_funding_rate_arbitrage.py`,
#      `.../tests/analytics/test_advanced_metrics.py`,
#      `.../tests/strategies/test_pairs_trading.py`,
#      `.../tests/integration/test_statistical_arbitrage_integration.py`,
#      `.../tests/risk/test_sector_exposure.py`,
#      `services/portfolio-manager/tests/test_portfolio_optimizer.py`.
#      (audit "P2 — test fixture" table)
#
#   2. P3 — docstrings, OpenAPI `json_schema_extra` examples and
#      `if __name__ == "__main__"` demo blocks. High reinfection risk precisely
#      because they read as working examples:
#      `app/handlers/risk_kelly.py`, `app/handlers/risk_budget.py`,
#      `app/risk/diversification_calculator.py`, `app/risk/sector_exposure.py`,
#      `app/risk/kelly_position_sizing.py`, `app/risk/dynamic_budget.py`
#      (dead module — prefer deleting over fixing),
#      `app/auto_trader.py:1840` (`* 10000` feeding only a log line),
#      `database/migrations/005_seed_data.sql:35` (stale RAISE NOTICE).
#      (audit "P3" table)
#
#   3. The four standalone SQZMOM backtest runners, which pass `10000.0`
#      EXPLICITLY and therefore are NOT fixed by correcting the default in
#      `services/technical-analysis/backtesting/sqzmom_backtest.py`:
#         services/technical-analysis/backtesting/run_backtest.py
#         services/technical-analysis/backtesting/run_btc_eth_backtest.py
#         services/technical-analysis/backtesting/quick_test.py
#         services/technical-analysis/backtesting/optimize_parameters.py
#      Their runtime behaviour is unchanged by this work. Known residual.
#
#   4. `services/trading-engine/app/main.py:1419-1420`
#         max_position_size: float = Query(default=10000.0, ...)
#      DELIBERATELY outside the capital-name pattern below: `max_position_size`
#      is a position cap, not an account-size claim. It is nonetheless 100x the
#      whole account and worth a later look. Recorded here so that the
#      detector's silence about it is understood as by-design, not as coverage.
#
#   5. The `portfolios` Postgres table's `initial_balance` column. A row created
#      before the 2026-04-27 repositories.py fix still reads 10000 and would
#      poison every ROI%/drawdown figure derived from it by 100x. A static
#      detector cannot see DB state; verify with
#      `SELECT portfolio_id, initial_balance FROM portfolios;`
#      (audit "DB-state defect")
# ---------------------------------------------------------------------------

#: Identifiers that CLAIM AN ACCOUNT SIZE. Matched against the WHOLE identifier,
#: lowercased — never as a substring. `max_position_size` and
#: `min_position_value` are not in here, and `REDIS_MAX_CONNECTIONS` cannot
#: partially match `equity`.
CAPITAL_NAMES = frozenset(
    {
        "initial_capital",
        "initial_balance",
        "starting_capital",
        "start_capital",
        "account_balance",
        "account_equity",
        "portfolio_value",
        "total_capital",
        "total_value",
        "final_capital",
        "peak_capital",
        "max_position_value",
        "base_equity",
        "equity",
    }
)

#: Calls whose `default=` keyword carries the real value: pydantic `Field`,
#: FastAPI `Query`, and `dataclasses.field`.
DEFAULT_CARRYING_CALLS = frozenset({"Field", "Query", "field"})

#: A capital-named binding may hold a numeric literal ONLY if that literal is
#: not an account-size claim:
#:   * 0 / 0.0 / Decimal("0") — a zero sentinel or accumulator seed.
#:   * the declared account size itself — sourced from `shared.account.DEFAULTS`
#:     rather than written here, so this test does not become a sixth
#:     independent hardcoding of the number it exists to police. This is what
#:     lets in-container files that legitimately cannot import `shared.account`
#:     (per the F1 packaging limitation) still state the correct figure.
EXEMPT_VALUES = frozenset({0.0, DEFAULTS["PAPER_INITIAL_BALANCE"]})


def _is_capital_name(name: object) -> bool:
    return isinstance(name, str) and name.lower() in CAPITAL_NAMES


def _numeric_literal(node: ast.AST | None) -> float | None:
    """Return the value if `node` is a numeric literal, else None.

    Recognises plain `int`/`float` constants, negations of them, and
    `Decimal("...")` / `Decimal(...)` wrappers. Booleans are `int` subclasses in
    Python and are explicitly NOT numeric literals here.
    """
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return None
        if isinstance(node.value, (int, float)):
            return float(node.value)
        return None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _numeric_literal(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "Decimal" and len(node.args) == 1:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(
                arg.value, (str, int, float)
            ):
                try:
                    return float(arg.value)
                except (TypeError, ValueError):
                    return None
        return None
    return None


def _offending_value(node: ast.AST | None) -> float | None:
    """Numeric literal supplied by `node`, directly or via a `default=` kwarg.

    Handles both `initial_capital = 10000.0` and
    `initial_capital: Decimal = Field(default=Decimal("10000"))`.
    """
    direct = _numeric_literal(node)
    if direct is not None:
        return direct if direct not in EXEMPT_VALUES else None

    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in DEFAULT_CARRYING_CALLS:
            for kw in node.keywords:
                if kw.arg == "default":
                    value = _numeric_literal(kw.value)
                    if value is not None and value not in EXEMPT_VALUES:
                        return value
    return None


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in node.elts:
            names.extend(_target_names(element))
        return names
    return []


def find_violations(source: str, filename: str = "<fixture>") -> list[str]:
    """Return one human-readable violation string per offending binding."""
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []

    def report(lineno: int, name: str, value: float, shape: str) -> None:
        violations.append(
            f"{filename}:{lineno}: {shape} `{name}` = {value:g} "
            f"(capital-named literal; declared account size is "
            f"{DEFAULTS['PAPER_INITIAL_BALANCE']:g})"
        )

    for node in ast.walk(tree):
        # Rule 1 — assignments and annotated assignments.
        if isinstance(node, ast.Assign):
            for name in [n for t in node.targets for n in _target_names(t)]:
                if _is_capital_name(name):
                    value = _offending_value(node.value)
                    if value is not None:
                        report(node.lineno, name, value, "assignment")
        elif isinstance(node, ast.AnnAssign):
            for name in _target_names(node.target):
                if _is_capital_name(name):
                    value = _offending_value(node.value)
                    if value is not None:
                        report(node.lineno, name, value, "annotated assignment")

        # Rule 2 — function parameter defaults (incl. Field/Query wrappers).
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spec = node.args
            positional = list(spec.posonlyargs) + list(spec.args)
            pairs: list[tuple[ast.arg, ast.expr]] = list(
                zip(positional[len(positional) - len(spec.defaults) :], spec.defaults)
            )
            pairs += [
                (arg, default)
                for arg, default in zip(spec.kwonlyargs, spec.kw_defaults)
                if default is not None
            ]
            for arg, default in pairs:
                if _is_capital_name(arg.arg):
                    value = _offending_value(default)
                    if value is not None:
                        report(
                            default.lineno,
                            arg.arg,
                            value,
                            f"parameter default of `{node.name}()`",
                        )

        # Rule 4 — `<anything>.get("<capital-named>", <num>)` dict fallbacks.
        # Required for risk-metrics-service's
        # `portfolio.get("total_value", 10000)`, which no name-based rule sees.
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and len(node.args) == 2
                and isinstance(node.args[0], ast.Constant)
                and _is_capital_name(node.args[0].value)
            ):
                value = _offending_value(node.args[1])
                if value is not None:
                    report(
                        node.lineno,
                        str(node.args[0].value),
                        value,
                        "dict-get fallback for",
                    )

    return sorted(set(violations))


# ---------------------------------------------------------------------------
# The detector's own unit tests. These are GREEN from the commit that
# introduces this file — only `test_no_capital_literals_in_scanned_files` is
# expected to land red and be cleared by the fix commits.
# ---------------------------------------------------------------------------

NEGATIVE_FIXTURE = '''
"""Constructs that look capital-shaped but are not account-size claims."""
from decimal import Decimal
from pydantic import Field

REDIS_MAX_CONNECTIONS = 50
WS_MAX_RECONNECT_ATTEMPTS = 10
SERVICE_PORT = 8005
HTTP_TIMEOUT_SECONDS = 10000
MAX_UPLOAD_BYTES = 100000
MAX_POSITION_SIZE = 10000.0
MIN_POSITION_VALUE = 10.0


class Model:
    row_limit: int = Field(default=10000)
    zero_guard: Decimal = Field(default=Decimal("0"))
    initial_capital: float = 0.0
    equity: Decimal = Field(default=Decimal("0"))
    total_value: float = 100.0
    starting_capital: Decimal = Field(default=Decimal("100"))
    enabled: bool = True


def f(timeout_ms: int = 10000, max_positions: int = 5, initial_balance=None):
    ...


def g(initial_capital: float = 0.0, max_position_size: float = 10000.0):
    ...


cfg = {}
batch = cfg.get("batch_size", 10000)
limit = cfg.get("row_limit", 100000)
equity_seed = cfg.get("total_value", 0)
'''

POSITIVE_FIXTURE = """
from decimal import Decimal
from pydantic import Field
from fastapi import Query


initial_capital = 10000.0


class Cfg:
    initial_capital: Decimal = Field(default=Decimal("10000"))
    peak_capital: float = 10000.0


total_capital: float = 100000.0


def endpoint(total_capital: float = Query(default=100000.0, description="x")):
    ...


def sizer(account_balance: float = 10000.0):
    ...


portfolio = {}
value = Decimal(str(portfolio.get("total_value", 10000)))
"""


def test_negative_cases_do_not_trip():
    """Zero false positives on non-capital constructs. Parsed in-memory so the
    guarantee does not drift when the live repo files change."""
    violations = find_violations(NEGATIVE_FIXTURE, "negative_fixture.py")
    assert violations == [], "false positives:\n" + "\n".join(violations)


def test_positive_cases_do_trip():
    violations = find_violations(POSITIVE_FIXTURE, "positive_fixture.py")
    rendered = "\n".join(violations)
    assert len(violations) == 7, (
        f"expected 7 violations, got {len(violations)}:\n{rendered}"
    )
    for expected in (
        "`initial_capital` = 10000",
        "`peak_capital` = 10000",
        "`total_capital` = 100000",
        "`account_balance` = 10000",
        "`total_value` = 10000",
    ):
        assert expected in rendered, f"missing {expected} in:\n{rendered}"


def test_exempt_values_are_sourced_from_shared_account():
    """The exemption tracks the declaration of record, not a literal here."""
    assert DEFAULTS["PAPER_INITIAL_BALANCE"] in EXEMPT_VALUES
    assert 10000.0 not in EXEMPT_VALUES
    assert 100000.0 not in EXEMPT_VALUES


@pytest.mark.parametrize("relative_path", SCANNED_FILES)
def test_scanned_file_exists(relative_path: str):
    """A rename must not silently shrink the coverage of this test."""
    assert (REPO_ROOT / relative_path).is_file(), (
        f"{relative_path} is in SCANNED_FILES but does not exist. Update the "
        "tuple deliberately — do not let a rename quietly reduce coverage."
    )


def test_no_capital_literals_in_scanned_files():
    """THE INVARIANT. No in-scope file may claim an account size other than the
    one declared in `shared/account.py`."""
    violations: list[str] = []
    for relative_path in SCANNED_FILES:
        path = REPO_ROOT / relative_path
        if not path.is_file():
            continue
        violations.extend(
            find_violations(path.read_text(encoding="utf-8"), relative_path)
        )

    assert not violations, (
        f"{len(violations)} capital-named numeric literal(s) found. THE ACCOUNT "
        f"IS ${DEFAULTS['PAPER_INITIAL_BALANCE']:g}. Source the value from the "
        "service's own Settings (in-container) or from shared.account "
        "(host-run):\n" + "\n".join(violations)
    )
