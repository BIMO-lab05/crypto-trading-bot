"""
THE PRICE-PRECISION INVARIANT.

round(price, 2) destroyed ADA precision and caused 30+ flip-flop losses
(commit 487d1bd; tracked as PRICE-01/02). Crypto prices span nine orders of
magnitude and every symbol has its own tick size; two decimals is correct for
none of them. The established fix is full precision - float(x) - with tick
quantization left to the trading-engine at order time (app/costs.py
quantize_price, limit_order_executor._round_to_tick).

Scope is a BOUNDED file tuple, deliberately: roughly 17 further sites live in
services/technical-analysis/app/indicators/*.py and are not yet fixed.
Adding a file here is a commitment that it is clean NOW. Grow the tuple as
files are fixed - never add a file you have not just cleaned, or this guard
lands red and gets disabled instead of obeyed.

Dimensionless quantities (RSI 0-100, confidence 0-1, volume ratios, position
fractions, strength scores) are legitimately rounded and must not trip this.
Scope is per-file, so those sites are exempted per LINE: a round() call whose
source line ends in the ALLOW_MARKER comment below is skipped. Four such
sites survive in the two technical-analysis files scanned first - the
strategy's `confidence`, and the indicator's `momentum_strength`,
`band_width_ratio` and _calculate_confidence return. WS1-B's four
trading-engine files carry twelve more (volume ratios, RSI, position
fractions, strength scores). Phase 22 enrolled three further trading-engine
files whose markers cover USD cost aggregates, basis points, ratios, percents,
seconds and 0-1 scores - those aggregates are why the marker means "not a
per-unit price" rather than strictly "dimensionless". Marking a line is a
claim about the value's units; do not use it to silence a price.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Files cleaned of price-domain rounding. Append only alongside a fix.
SCANNED_FILES: tuple[str, ...] = (
    "services/technical-analysis/app/strategies/squeeze_momentum_strategy.py",
    "services/technical-analysis/app/indicators/sqzmom_enhanced.py",
    # WS1-B: dormant strategy layer, cleaned 2026-08-17
    "services/trading-engine/app/strategies/momentum_breakout_strategy.py",
    "services/trading-engine/app/strategies/trend_following_strategy.py",
    "services/trading-engine/app/strategies/support_resistance_strategy.py",
    "services/trading-engine/app/utils/support_resistance_detector.py",
    # Phase 22: the LIVE ensemble path, cleaned 2026-08-27
    "services/trading-engine/app/strategies/simple_rsi_strategy.py",
    # Phase 22: trading-engine serialization, classified site-by-site 2026-08-27
    "services/trading-engine/app/analytics/post_trade_analysis.py",
    "services/trading-engine/app/trading_enhancements/adaptive_rsi.py",
)

# Not yet covered, tracked deliberately:
#   the OTHER services/technical-analysis/app/indicators/*.py modules
#                                                     (~17 sites, PRICE-02)
#   services/technical-analysis/app/handlers/sqzmom.py (4dp momentum)

BANNED_NDIGITS = frozenset({2, 4})

# Line-level opt-out. A banned round() whose own source line carries this
# comment is a declared dimensionless value. WS1-B reuses this exact string -
# do not respell it, and do not add a second escape mechanism.
ALLOW_MARKER = "# non-price-round"


def _ndigits_of(node: ast.Call) -> int | None:
    """The ndigits argument of a round() call, whatever shape it takes.

    Handles builtin `round(x, 2)` (ndigits is args[1]), the method form
    `series.round(2)` / `np.round(x, 2)` (ndigits is args[1] for np.round but
    args[0] for the bound-method form), `round(x, ndigits=2)`, and the numpy
    and pandas keyword spelling `np.round(x, decimals=2)` /
    `frame.round(decimals=2)`.

    Both keyword spellings are checked because a detector that silently
    misses one fails GREEN: the guard would pass while a price rounding sat
    in a file it claims to protect. No scanned file uses `decimals=` today,
    so this closes the gap before it can be walked into.
    """
    for keyword in node.keywords:
        if keyword.arg in ("ndigits", "decimals"):
            return _int_constant(keyword.value)

    func = node.func
    if isinstance(func, ast.Name) and func.id == "round":
        return _int_constant(node.args[1]) if len(node.args) == 2 else None
    if isinstance(func, ast.Attribute) and func.attr == "round":
        if len(node.args) == 2:  # np.round(x, 2)
            return _int_constant(node.args[1])
        if len(node.args) == 1:  # series.round(2)
            return _int_constant(node.args[0])
    return None


def _int_constant(node: ast.AST | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        if isinstance(node.value, bool):
            return None
        return node.value
    return None


def _is_round_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "round"
    if isinstance(func, ast.Attribute):
        return func.attr == "round"
    return False


def find_violations(source: str, filename: str = "<fixture>") -> list[str]:
    """One human-readable violation string per banned rounding call.

    A call is exempt when its own source line carries ALLOW_MARKER. The check
    is per-line, not per-file: marking one site never silences another.
    """
    tree = ast.parse(source, filename=filename)
    source_lines = source.splitlines()
    violations: list[str] = []

    for node in ast.walk(tree):
        if not _is_round_call(node):
            continue
        ndigits = _ndigits_of(node)
        if ndigits in BANNED_NDIGITS:
            line = (
                source_lines[node.lineno - 1]
                if node.lineno <= len(source_lines)
                else ""
            )
            if ALLOW_MARKER in line:
                continue
            violations.append(
                f"{filename}:{node.lineno}: round(..., {ndigits}) in a file "
                "declared free of price-domain rounding. Crypto prices need "
                "full precision here (float(x)); quantize at order time. If "
                f"the value really is dimensionless, append '{ALLOW_MARKER}' "
                "to that line."
            )

    return sorted(set(violations))


NEGATIVE_FIXTURE = """
value = round(pct_change, 3)
ratio = round(current_volume / avg_volume, 1)
scaled = round(fraction, 6)
dynamic = round(price, tick_decimals)
bare = round(x)
marked = round(current_volume / avg_volume, 2)  # non-price-round
"""

POSITIVE_FIXTURE = """
entry = round(entry_price, 2)
stop = round(sl, ndigits=2)
band = np.round(bb_upper, 4)
col = series.round(2)
kw_np = np.round(kc_upper, decimals=2)
kw_pd = frame.round(decimals=4)
"""

# One marked line and one unmarked violation in the same source. The marker
# must exempt its own line only - a file-wide or first-match-wins skip would
# report 0 here.
MARKER_LEAK_FIXTURE = """
allowed = round(rsi_value, 2)  # non-price-round
leaked = round(entry_price, 2)
"""


def test_negative_cases_do_not_trip():
    """Zero false positives on legitimate rounding, including a marked site.
    Parsed in-memory so the guarantee cannot drift when live repo files
    change."""
    violations = find_violations(NEGATIVE_FIXTURE, "negative_fixture.py")
    assert violations == [], "false positives:\n" + "\n".join(violations)


def test_positive_cases_do_trip():
    """All six call shapes are detected. No line here carries the marker.

    The two `decimals=` spellings matter disproportionately: a detector that
    misses a shape fails GREEN, so the guard would pass while a price
    rounding sat in a file it claims to protect.
    """
    violations = find_violations(POSITIVE_FIXTURE, "positive_fixture.py")
    rendered = "\n".join(violations)
    assert len(violations) == 6, (
        f"expected 6 violations, got {len(violations)}:\n{rendered}"
    )
    for expected in ("round(..., 2)", "round(..., 4)"):
        assert expected in rendered, f"missing {expected} in:\n{rendered}"


def test_marker_does_not_leak_to_other_lines():
    """The opt-out is per-line. Marking one site must not silence the next."""
    violations = find_violations(MARKER_LEAK_FIXTURE, "leak_fixture.py")
    rendered = "\n".join(violations)
    assert len(violations) == 1, (
        f"expected exactly 1 violation, got {len(violations)}:\n{rendered}"
    )
    assert "leak_fixture.py:3" in rendered, (
        f"the unmarked round on line 3 must be the one reported:\n{rendered}"
    )


@pytest.mark.parametrize("relative_path", SCANNED_FILES)
def test_scanned_file_exists(relative_path: str):
    """A rename must not silently shrink this guard's coverage."""
    assert (REPO_ROOT / relative_path).is_file(), (
        f"{relative_path} is in SCANNED_FILES but does not exist. Update the "
        "tuple deliberately - do not let a rename quietly reduce coverage."
    )


def test_no_price_rounding_in_scanned_files():
    """THE INVARIANT."""
    violations: list[str] = []
    for relative_path in SCANNED_FILES:
        path = REPO_ROOT / relative_path
        if not path.is_file():
            continue
        violations.extend(
            find_violations(path.read_text(encoding="utf-8"), relative_path)
        )

    assert not violations, (
        f"{len(violations)} banned rounding call(s) in files declared clean. "
        "round(price, 2) destroyed ADA precision (487d1bd). Use float(x) here "
        f"and quantize at order time - or, if the value is dimensionless, "
        f"append '{ALLOW_MARKER}' to that line. Never remove a file from "
        "SCANNED_FILES to make this pass:\n" + "\n".join(violations)
    )
