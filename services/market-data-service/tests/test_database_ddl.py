"""RES-02 boot-DDL assertions — sibling file to test_database.py.

Cross-references:
- RES-02 in `.planning/quick/260816-qjn-fix-res-02-market-data-boot-ddl-integer-/`
- `services/market-data-service/app/database.py::DDL_STATEMENTS`
- `database/migrations/one_time_repairs/`
  `2026-08-16-market-data-retention-and-orderbook-hypertable.sql`

WHY THIS FILE EXISTS:
`services/market-data-service/tests/test_database.py:15` carries a module-level
`pytestmark = pytest.mark.skip(reason="stale tests after PR #86 refactor; needs
rewrite")` which wholesale-skips every test in that file. Adding these
assertions there would silently no-op — the highest-probability false pass in
this work. `tests/test_config_defaults.py` is the established precedent for the
same workaround; this file mirrors its shape.

WHAT IS BEING GUARDED (all verified live 2026-08-16, TimescaleDB 2.26.3):
1. `klines` and `tickers` are hypertables partitioned on `timestamp BIGINT`
   (epoch ms) with `integer_now_func = NULL`. An INTERVAL retention window can
   never apply to an integer time dimension, so the service ran with ZERO
   retention jobs while logging only warnings.
2. `public.orderbook_snapshots` had `PRIMARY KEY (id)` only, so
   `create_hypertable` refused it — every unique index must contain the
   partition column.

ASSERT AGAINST THE IMPORTED CONSTANT, NEVER AGAINST FILE TEXT. The klines
rationale in `database.py` is a Python comment containing the literal token
`add_retention_policy`, so any grep/read-the-source negative assertion would be
self-invalidating. Importing the constant excludes comments by construction.

Imports are done lazily inside each test so pytest collection survives
host/container dependency differences (same rationale as the precedent file).
"""

from __future__ import annotations

import re

import pytest

# NOTE: NO module-level `pytestmark = pytest.mark.skip` here — that wholesale
# skip is the trap on the sibling `test_database.py:15`. This file must
# actually run.

# Tables whose every reference in the DDL must be schema-qualified `public.`.
_TABLES = ("klines", "tickers", "orderbook_snapshots")

# Catalog predicates compare against TimescaleDB's `hypertable_name` column,
# which stores the UNQUALIFIED relation name — it can never be `public.`
# prefixed. Strip those comparisons before running the qualification regex,
# otherwise the guard flags the very statement that implements the guard.
# The companion schema check lives in
# `test_all_table_references_schema_qualified` (the
# `hypertable_schema = 'public'` assertion) and covers the same risk.
_CATALOG_PREDICATE = re.compile(r"hypertable_name\s*=\s*'[a-z_]+'")


def _statements() -> list[str]:
    """Return just the SQL text of every DDL entry, in order."""
    try:
        from app.database import DDL_STATEMENTS  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - host env problem
        pytest.fail(
            "Could not import `app.database.DDL_STATEMENTS` on the host. Run "
            "from `services/market-data-service` with `--no-cov`. Underlying "
            f"ImportError: {exc!r}"
        )
    return [stmt for _label, stmt, _level in DDL_STATEMENTS]


def _idx(stmts: list[str], substr: str) -> int:
    """Index of the first statement containing `substr`, or -1.

    A bare `next()` would raise StopIteration and surface as an unreadable
    error instead of a failed assertion, so callers assert `!= -1` first.
    """
    return next((i for i, s in enumerate(stmts) if substr in s), -1)


def test_klines_has_no_retention_policy() -> None:
    """T-RES02-01: klines must never get a background retention job.

    A 90-day window would delete 385,808 rows — 52% of the table, the entire
    backfilled research history every backtest depends on. Total footprint is
    288 MB for 2.7 years, so disk is a non-issue. Deleting research data must
    be an explicit operator action, never a scheduled job.
    """
    offenders = [
        s for s in _statements() if "add_retention_policy" in s and "klines" in s
    ]
    assert offenders == [], (
        "A klines retention policy is back in DDL_STATEMENTS. This deletes "
        "385,808 rows of backfilled research history on a schedule with no "
        f"operator in the loop. Offending statement(s): {offenders!r}"
    )


def test_retention_uses_bigint_drop_after() -> None:
    """Integer time dimensions take `drop_after`, never `INTERVAL`.

    `klines`/`tickers`/`orderbook_snapshots` partition on `timestamp BIGINT`
    (epoch ms). `add_retention_policy(..., INTERVAL '90 days')` cannot apply to
    an integer dimension — that is why 0 retention jobs existed. The `::bigint`
    cast on the multiplier is also required: `90 * 86400000` overflows int4 and
    was reproduced failing live.
    """
    stmts = _statements()

    assert not any("INTERVAL" in s for s in stmts), (
        "An INTERVAL-based retention statement is back. It can never succeed "
        "against a BIGINT epoch-ms time dimension; the failure is swallowed as "
        "a log line and the policy silently never exists."
    )

    policies = [s for s in stmts if "add_retention_policy" in s]
    assert policies, "No retention policies at all — expected tickers + orderbook"
    for s in policies:
        assert "drop_after" in s, f"retention without drop_after: {s!r}"
        assert "::bigint" in s, (
            "retention drop_after arithmetic must cast to bigint (int4 "
            f"overflow reproduced live): {s!r}"
        )


def test_retention_windows() -> None:
    """tickers = 180 days, orderbook_snapshots = 90 days, expressed in epoch ms.

    T-RES02-02: tickers is 180d rather than the original 30d because a 30-day
    window would wipe 72% of tickers, including the clean post-2026-08-12
    mainnet record.

    orderbook_snapshots widened 7d -> 90d for edge-search v2 (spec
    2026-08-19 §2 A1; Phase C gate needs >=21 consecutive days of snapshots).
    """
    stmts = _statements()

    tickers = [s for s in stmts if "add_retention_policy" in s and "tickers" in s]
    assert len(tickers) == 1, f"expected exactly one tickers policy, got {tickers!r}"
    assert "180::bigint * 86400000" in tickers[0], (
        f"tickers retention window is not 180 days: {tickers[0]!r}"
    )

    orderbook = [
        s for s in stmts if "add_retention_policy" in s and "orderbook_snapshots" in s
    ]
    assert len(orderbook) == 1, (
        f"expected exactly one orderbook policy, got {orderbook!r}"
    )
    assert "90::bigint * 86400000" in orderbook[0], (
        f"orderbook retention window is not 90 days: {orderbook[0]!r}"
    )


def test_integer_now_func_registered_for_every_hypertable() -> None:
    """Every integer-partitioned hypertable needs a registered integer-now func.

    Without it `integer_now_func` stays NULL and `add_retention_policy` can
    never succeed — the live root cause of 0 retention jobs.
    """
    stmts = _statements()

    assert any("CREATE OR REPLACE FUNCTION public.unix_now_ms" in s for s in stmts), (
        "the public.unix_now_ms() integer-now function is not created"
    )

    assert any("STABLE" in s for s in stmts), (
        "the integer-now function must be declared STABLE — TimescaleDB "
        "rejects a VOLATILE function for set_integer_now_func"
    )

    for table in _TABLES:
        needle = f"set_integer_now_func('public.{table}'"
        assert any(needle in s for s in stmts), (
            f"no set_integer_now_func registration for public.{table}; "
            "its time dimension will keep integer_now_func = NULL and no "
            "retention policy can ever be created on it"
        )


def test_all_table_references_schema_qualified() -> None:
    """T-RES02-04: no bare table names — the market_data shadows must not match.

    `infrastructure/scripts/init-timescale.sql` created four never-used shadow
    hypertables under the `market_data` schema. An unqualified name can resolve
    to one of those depending on `search_path`.

    The regex uses a word boundary plus a negative lookbehind, which covers
    both quoted literals (`'klines'`) and bare identifiers (`ALTER TABLE
    klines`). `_` is a word character, so `idx_klines_mainnet` correctly does
    NOT match.

    Catalog predicates (`hypertable_name = 'orderbook_snapshots'`) are stripped
    first — `timescaledb_information.hypertables.hypertable_name` stores the
    UNQUALIFIED relation name, so that comparison cannot be `public.`-prefixed
    and is not a defect. Do not "fix" this by qualifying it; the schema half of
    that predicate is asserted separately below.
    """
    stmts = _statements()
    patterns = {t: re.compile(rf"(?<!public\.)\b{t}\b") for t in _TABLES}

    for stmt in stmts:
        probe = _CATALOG_PREDICATE.sub("", stmt)
        for table, pattern in patterns.items():
            match = pattern.search(probe)
            assert match is None, (
                f"unqualified reference to `{table}` in DDL statement — it can "
                "resolve to the dead market_data shadow hypertable depending "
                f"on search_path. Statement: {stmt!r}"
            )

    do_blocks = [s for s in stmts if "timescaledb_information.hypertables" in s]
    assert do_blocks, "no hypertable existence guard found"
    for block in do_blocks:
        assert "hypertable_schema = 'public'" in block, (
            "the hypertable existence guard is missing "
            "`hypertable_schema = 'public'`. Without it the guard matches the "
            "dead market_data.orderbook_snapshots shadow and the real "
            f"conversion is skipped forever. Statement: {block!r}"
        )


def test_statement_ordering() -> None:
    """Order is load-bearing; content checks alone pass on a mis-ordered list.

    TimescaleDB enforces each dependency: the integer-now function must exist
    before it is named, a table must already be a hypertable before
    `set_integer_now_func`, and the integer-now func must be registered before
    a retention policy can be added.
    """
    stmts = _statements()

    def idx(substr: str) -> int:
        i = _idx(stmts, substr)
        assert i != -1, f"no DDL statement contains {substr!r}"
        return i

    # Anchor on the CREATE, not the bare token: statements 5-7 also contain
    # `unix_now_ms` as the 'public.unix_now_ms' argument.
    create_fn = idx("CREATE OR REPLACE FUNCTION public.unix_now_ms")
    for table in _TABLES:
        assert create_fn < idx(f"set_integer_now_func('public.{table}'"), (
            "public.unix_now_ms() must be created before it is referenced by "
            f"set_integer_now_func on public.{table}"
        )

    ht_klines = idx("create_hypertable('public.klines'")
    inf_klines = idx("set_integer_now_func('public.klines'")
    assert ht_klines < inf_klines, (
        "public.klines must be a hypertable before set_integer_now_func"
    )

    ht_tickers = idx("create_hypertable('public.tickers'")
    inf_tickers = idx("set_integer_now_func('public.tickers'")
    ret_tickers = idx("add_retention_policy('public.tickers'")
    assert ht_tickers < inf_tickers < ret_tickers, (
        "public.tickers order must be create_hypertable -> "
        "set_integer_now_func -> add_retention_policy"
    )

    do_block = idx('ADD PRIMARY KEY (id, "timestamp")')
    inf_ob = idx("set_integer_now_func('public.orderbook_snapshots'")
    ret_ob = idx("add_retention_policy('public.orderbook_snapshots'")
    assert do_block < inf_ob < ret_ob, (
        "public.orderbook_snapshots only becomes a hypertable inside the DO "
        "block, so the block must precede set_integer_now_func, which must "
        "precede its retention policy"
    )


def test_orderbook_conversion_is_a_single_atomic_statement() -> None:
    """T-RES02-03: the PK reshape and the conversion share one transaction.

    `_run_isolated` gives every entry its own transaction and swallows the
    exception. Split across entries, a `create_hypertable` failure would COMMIT
    the PK drop anyway and leave a table with no usable primary key behind a
    single log warning.
    """
    stmts = _statements()

    # Scoped to orderbook_snapshots: open_interest (edge-search v2 A2) got its
    # own PK-reshaping DO block following the same atomic convention, so a
    # blanket "ADD PRIMARY KEY" count would no longer be 1.
    reshapers = [
        s for s in stmts if "ADD PRIMARY KEY" in s and "orderbook_snapshots" in s
    ]
    assert len(reshapers) == 1, (
        f"expected exactly one orderbook_snapshots PK-reshaping statement, "
        f"got {len(reshapers)}"
    )
    block = reshapers[0]

    assert '(id, "timestamp")' in block, (
        "the new primary key must include the partition column `timestamp` — "
        "TimescaleDB rejects create_hypertable otherwise. Statement: "
        f"{block!r}"
    )
    assert "DROP CONSTRAINT" in block, (
        "the old single-column PK drop is not in the same statement as the "
        "ADD PRIMARY KEY — split entries mean separate transactions"
    )
    assert "create_hypertable" in block, (
        "create_hypertable is not in the same statement as the PK reshape; a "
        "conversion failure would commit a half-migrated table"
    )
    assert "pg_constraint" in block, (
        "the existing PK constraint name must be resolved at runtime from "
        "pg_constraint. The live diagnosis verified the PK's COLUMNS, not its "
        "name; a hardcoded literal would abort the block and be swallowed as "
        "a warning."
    )
    assert "orderbook_snapshots_pkey" not in block, (
        "constraint name is hardcoded — resolve it from pg_constraint instead"
    )
