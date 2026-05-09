"""Safe --where DSL + ORDER BY validator for leaderboard queries (CD-05).

Operator-facing string parsed by tokeniser -> whitelist gate -> parameterised SQL.
Bare string concat into SQL is forbidden (T-03-29).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any, List, Tuple


logger = logging.getLogger(__name__)


# Whitelist columns operator can filter on. Excludes metric columns to keep the
# DSL small — top/by handles ORDER BY against numeric metrics.
ALLOWED_FILTER_COLS = {
    "tournament_id",
    "run_id",
    "architecture",
    "symbol",
    "horizon",
    "target_mode",
    "hp_hash",
    "status",
    "failure_reason",
    "train_window_includes_contaminated",
}
# Whitelist columns operator can sort on (--by). Includes metrics.
ALLOWED_ORDER_BY = {
    "r2_returns",
    "dir_acc_corrected",
    "oos_sharpe",
    "psr",
    "dsr",
    "cpcv_dsr",
    "train_seconds",
    "created_at",
    "horizon",
}
ALLOWED_OPS = ("=", "!=", "<", "<=", ">", ">=", "LIKE", "IN")

# Token regex — matches identifiers, simple values (quoted or unquoted), operators, joiners.
_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<and>\bAND\b)         |
        (?P<or>\bOR\b)           |
        (?P<op>!=|<=|>=|=|<|>|LIKE|IN) |
        (?P<ident>[A-Za-z_][A-Za-z0-9_]*) |
        (?P<qstr>'[^']*')        |
        (?P<num>-?\d+(?:\.\d+)?) |
        (?P<lparen>\()           |
        (?P<rparen>\))           |
        (?P<comma>,)
    )\s*
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _tokenise(where: str) -> List[Tuple[str, str]]:
    """Yield (kind, text) tokens. Raises ValueError on any unrecognised char."""
    tokens: List[Tuple[str, str]] = []
    pos = 0
    while pos < len(where):
        m = _TOKEN_RE.match(where, pos)
        if not m or m.end() == pos:
            raise ValueError(
                f"invalid token near char {pos}: {where[pos : pos + 10]!r}"
            )
        for kind in (
            "and",
            "or",
            "op",
            "ident",
            "qstr",
            "num",
            "lparen",
            "rparen",
            "comma",
        ):
            if m.group(kind) is not None:
                tokens.append((kind, m.group(kind)))
                break
        pos = m.end()
    return tokens


def parse_where(where: str) -> Tuple[str, List[Any]]:
    """Parse a --where clause into (sql_fragment, params).

    Grammar (v1, deliberately small):
        clause   := comparison (AND|OR comparison)*
        comparison := IDENT OP value
                    | IDENT IN ( value (, value)* )
        value    := QSTR | NUM | IDENT_LITERAL
    No parens, no nested expressions. Operator can use IN for set membership.
    """
    if not where or not where.strip():
        return ("", [])

    # Cheap pre-filters — anything containing these is rejected before tokenising.
    forbidden = (
        ";",
        "--",
        "/*",
        "*/",
        "UNION",
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "ATTACH",
        "DETACH",
    )
    upper = where.upper()
    for f in forbidden:
        if f in upper:
            raise ValueError(f"forbidden token in --where: {f!r}")

    tokens = _tokenise(where)
    sql_parts: List[str] = []
    params: List[Any] = []
    i = 0
    expect_clause = True

    while i < len(tokens):
        if expect_clause:
            # Read: IDENT OP value [, value ...]
            if i + 2 >= len(tokens):
                raise ValueError(f"unexpected end of --where at token {i}")
            kind_a, ident = tokens[i]
            kind_b, op = tokens[i + 1]
            if kind_a != "ident":
                raise ValueError(
                    f"expected column name at token {i}, got {kind_a}: {ident!r}"
                )
            if ident not in ALLOWED_FILTER_COLS:
                raise ValueError(
                    f"column {ident!r} not in allowlist: {sorted(ALLOWED_FILTER_COLS)}"
                )
            if kind_b != "op":
                raise ValueError(
                    f"expected operator at token {i + 1}, got {kind_b}: {op!r}"
                )
            if op.upper() not in ALLOWED_OPS:
                raise ValueError(f"operator {op!r} not in allowlist: {ALLOWED_OPS}")
            if op.upper() == "IN":
                # next must be lparen, then values, then rparen
                if i + 2 >= len(tokens) or tokens[i + 2][0] != "lparen":
                    raise ValueError(f"IN must be followed by '(' at token {i + 2}")
                j = i + 3
                in_values: List[Any] = []
                while j < len(tokens):
                    kind_v, val = tokens[j]
                    if kind_v == "qstr":
                        in_values.append(val[1:-1])
                    elif kind_v == "num":
                        in_values.append(float(val) if "." in val else int(val))
                    elif kind_v == "ident":
                        # Bare ident as value (e.g. symbol IN (SOL, BNB)) -> treat as string
                        in_values.append(val)
                    elif kind_v == "rparen":
                        break
                    elif kind_v == "comma":
                        j += 1
                        continue
                    else:
                        raise ValueError(
                            f"unexpected token in IN list: {kind_v}={val!r}"
                        )
                    j += 1
                if j >= len(tokens) or tokens[j][0] != "rparen":
                    raise ValueError("unterminated IN list — missing ')'")
                placeholders = ",".join(["?"] * len(in_values))
                sql_parts.append(f"{ident} IN ({placeholders})")
                params.extend(in_values)
                i = j + 1
                expect_clause = False
                continue
            # Plain comparison
            kind_v, val = tokens[i + 2]
            if kind_v == "qstr":
                value = val[1:-1]
            elif kind_v == "num":
                value = float(val) if "." in val else int(val)
            elif kind_v == "ident":
                value = val  # bare ident -> string literal (e.g. symbol=SOL)
            else:
                raise ValueError(
                    f"expected value at token {i + 2}, got {kind_v}: {val!r}"
                )
            sql_parts.append(f"{ident} {op.upper()} ?")
            params.append(value)
            i += 3
            expect_clause = False
        else:
            # Expect AND / OR joiner
            kind, txt = tokens[i]
            if kind not in ("and", "or"):
                raise ValueError(f"expected AND/OR at token {i}, got {kind}: {txt!r}")
            sql_parts.append(txt.upper())
            i += 1
            expect_clause = True

    if expect_clause:
        # Trailing AND/OR with nothing after
        raise ValueError("--where ends with AND/OR — incomplete clause")

    return (" ".join(sql_parts), params)


def run_query(
    db_path: str,
    *,
    tournament_id: str = None,
    top: int = 10,
    by: str = "dsr",
    where: str = "",
) -> List[dict]:
    """Run a leaderboard query through the safe DSL -> parameterised SQL pipeline."""
    if by not in ALLOWED_ORDER_BY:
        raise ValueError(f"--by {by!r} not in allowlist: {sorted(ALLOWED_ORDER_BY)}")
    top = max(1, min(int(top), 10_000))  # T-03-31 clamp

    where_sql, where_params = parse_where(where)

    sql_parts = ["SELECT * FROM leaderboard"]
    params: List[Any] = []
    clauses: List[str] = []
    if tournament_id is not None:
        clauses.append("tournament_id = ?")
        params.append(tournament_id)
    if where_sql:
        clauses.append(where_sql)
        params.extend(where_params)
    if clauses:
        sql_parts.append("WHERE " + " AND ".join(f"({c})" for c in clauses))
    # by is whitelisted above — safe to interpolate as identifier
    sql_parts.append(f"ORDER BY {by} DESC")
    sql_parts.append("LIMIT ?")
    params.append(top)

    sql = " ".join(sql_parts)
    logger.debug("run_query SQL: %s | params: %s", sql, params)

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


__all__ = [
    "parse_where",
    "run_query",
    "ALLOWED_FILTER_COLS",
    "ALLOWED_ORDER_BY",
    "ALLOWED_OPS",
]
