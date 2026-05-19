"""
Regression test for the performance_history UPSERT ON CONFLICT clause.

Bug 2026-05-19: the snapshot writer used
    ON CONFLICT (portfolio_id, date_trunc('day', timestamp))
which does not resolve to any unique index because date_trunc on a
timestamptz is only STABLE — PostgreSQL refuses to back a unique
index with a non-IMMUTABLE expression. The actual unique index in
migration 002_performance_history.sql is
    UNIQUE INDEX (portfolio_id, ((timestamp AT TIME ZONE 'UTC')::date))
The ON CONFLICT clause must reference the same expression for the
UPSERT to be matched. The mismatch caused every snapshot attempt to
fail with "there is no unique or exclusion constraint matching the
ON CONFLICT specification", silently breaking history persistence.

This test pins both pieces in place:
  1. The Python query uses the IMMUTABLE UTC-anchored cast expression.
  2. The migration file declares a matching unique index.

If a future refactor switches back to date_trunc, or someone changes
the migration's index without updating the Python query, this test
fails immediately.

The test is intentionally source-level (no DB fixture, no skip mark)
because the project's portfolio-manager test suite has no shared
asyncpg fixture and the existing integration tests for this module
are file-level-skipped pending PR #86 follow-up. A string-level
regression test runs everywhere and catches the exact failure mode.
"""

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]

PERFORMANCE_HISTORY_PY = (
    REPO_ROOT
    / "services"
    / "portfolio-manager"
    / "app"
    / "services"
    / "performance_history.py"
)
MIGRATION_002_SQL = (
    REPO_ROOT / "infrastructure" / "migrations" / "002_performance_history.sql"
)

# Match either single- or double-quoted 'UTC' and allow optional outer parens
# around the cast — both `(timestamp AT TIME ZONE 'UTC')::date` and
# `((timestamp AT TIME ZONE 'UTC')::date)` are semantically identical to
# PostgreSQL.
_UTC_CAST = re.compile(
    r"\(*\s*timestamp\s+AT\s+TIME\s+ZONE\s+['\"]UTC['\"]\s*\)*\s*::\s*date",
    re.IGNORECASE,
)


@pytest.mark.unit
class TestPerformanceHistoryUpsertExpression:
    """Pin the UPSERT ON CONFLICT expression to the unique index it targets."""

    def test_python_query_uses_immutable_utc_cast(self):
        """The Python query must not regress to date_trunc on a timestamptz."""
        src = PERFORMANCE_HISTORY_PY.read_text()

        # Locate the INSERT INTO portfolio.performance_history block — there
        # is currently only one, but anchoring the assertion to it isolates
        # this from unrelated future inserts. Use RETURNING id; as the
        # closing anchor (the literal end of the query); a plain `.*?;`
        # would stop at the first semicolon, which could be a punctuation
        # character inside a SQL comment line in the query string.
        insert_match = re.search(
            r"INSERT\s+INTO\s+portfolio\.performance_history.*?RETURNING\s+id\s*;",
            src,
            re.DOTALL | re.IGNORECASE,
        )
        assert insert_match is not None, (
            "Could not find the INSERT INTO portfolio.performance_history "
            "query in performance_history.py — has the writer been moved?"
        )
        query = insert_match.group(0)

        # Strip SQL line comments before pattern-checking — the production
        # query carries a multi-line comment that explains why date_trunc
        # is wrong, and that comment must not trip the assertion below.
        query_no_comments = re.sub(r"--[^\n]*", "", query)

        assert "ON CONFLICT" in query_no_comments.upper(), (
            "Snapshot writer must use ON CONFLICT to support intra-day "
            "re-snapshot via UPSERT — see migration 002 unique index."
        )

        # The bug: date_trunc('day', timestamp) — STABLE, cannot back a
        # unique index. Anchor to the exact failure mode.
        assert "date_trunc" not in query_no_comments, (
            "Snapshot ON CONFLICT must not use date_trunc(timestamptz) — it "
            "is only STABLE so Postgres cannot back a unique index with it. "
            "Use ((timestamp AT TIME ZONE 'UTC')::date) instead to match "
            "uniq_performance_portfolio_day from migration 002."
        )

        assert _UTC_CAST.search(query_no_comments), (
            "Snapshot ON CONFLICT must reference "
            "((timestamp AT TIME ZONE 'UTC')::date) — the same IMMUTABLE "
            "expression migration 002 uses on the unique index. Without "
            "an exact match, asyncpg returns 'there is no unique or "
            "exclusion constraint matching the ON CONFLICT specification'."
        )

    def test_migration_defines_matching_unique_index(self):
        """The unique index in migration 002 must use the same UTC cast."""
        sql = MIGRATION_002_SQL.read_text()

        # Locate the unique-index definition for the snapshot table.
        idx_match = re.search(
            r"CREATE\s+UNIQUE\s+INDEX[^;]*portfolio\.performance_history[^;]*;",
            sql,
            re.DOTALL | re.IGNORECASE,
        )
        assert idx_match is not None, (
            "Migration 002 must declare a UNIQUE INDEX on "
            "portfolio.performance_history to back the ON CONFLICT clause. "
            "If this disappears, the snapshot writer's UPSERT cannot match "
            "any constraint and will fail at runtime."
        )
        idx = idx_match.group(0)

        assert "portfolio_id" in idx, (
            "Unique index must include portfolio_id as the first column."
        )
        assert _UTC_CAST.search(idx), (
            "Unique index must use ((timestamp AT TIME ZONE 'UTC')::date) — "
            "date_trunc on timestamptz is STABLE and Postgres refuses to "
            "back the index with it. If the migration is rewritten to use "
            "date_trunc, the unique index will fail to create and the "
            "snapshot writer's UPSERT will silently break on every cycle."
        )
