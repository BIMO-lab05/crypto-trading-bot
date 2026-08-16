---
phase: 260816-qjn
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - services/market-data-service/app/database.py
  - services/market-data-service/app/models.py
  - services/market-data-service/tests/test_database_ddl.py
  - database/migrations/one_time_repairs/2026-08-16-market-data-retention-and-orderbook-hypertable.sql
autonomous: true
requirements: [RES-02]
mode: quick

must_haves:
  truths:
    - "Boot DDL registers an integer-now function for every integer-time hypertable, so retention policies can be created at all."
    - "public.orderbook_snapshots gets a PK that includes the partition column, then converts to a hypertable, atomically."
    - "klines has NO retention policy — 385,808 rows of backfilled research history are never deleted by a background job."
    - "tickers retains 180 days; orderbook_snapshots retains 7 days; both expressed in ::bigint epoch-ms."
    - "Every table reference in the new DDL is schema-qualified public.<name>, so the dead market_data shadow hypertables are never touched."
    - "Host unit tests assert the DDL statement list — content AND order — without executing any SQL."
  artifacts:
    - path: "services/market-data-service/app/database.py"
      provides: "Module-level DDL_STATEMENTS ordered sequence + create_hypertables() iterating it"
      contains: "DDL_STATEMENTS"
    - path: "services/market-data-service/tests/test_database_ddl.py"
      provides: "String + ordering assertions over DDL_STATEMENTS"
      contains: "DDL_STATEMENTS"
    - path: "database/migrations/one_time_repairs/2026-08-16-market-data-retention-and-orderbook-hypertable.sql"
      provides: "Written record of the PK reshape + policy adds (record only, not executed)"
  key_links:
    - from: "services/market-data-service/app/main.py:85"
      to: "create_hypertables()"
      via: "boot lifespan, already wrapped in try/except"
      pattern: "await create_hypertables\\(\\)"
    - from: "create_hypertables()"
      to: "DDL_STATEMENTS"
      via: "for label, stmt, level in DDL_STATEMENTS: await _run_isolated(...)"
      pattern: "for .*DDL_STATEMENTS"
---

<objective>
Fix RES-02: market-data boot DDL silently fails on every startup. Two independent defects,
both verified live on 2026-08-16 against TimescaleDB 2.26.3:

1. `klines` and `tickers` are hypertables partitioned on `timestamp BIGINT` (epoch ms) with
   `integer_now_func = NULL`. `add_retention_policy(..., INTERVAL '90 days')` can never
   succeed on an integer time dimension — it needs an integer `drop_after` AND a registered
   integer-now function. Result: `timescaledb_information.jobs` has **0 retention jobs**.
2. `public.orderbook_snapshots` has `PRIMARY KEY (id)` only. `create_hypertable` refuses,
   because every unique index must include the partition column. The table has 0 rows and
   has never been a hypertable.

Both failures are swallowed by `_run_isolated` (logs a warning, continues), so the service
boots green and nobody notices.

Purpose: make the boot DDL actually converge to the intended DB state, and make the
intended state assertable in a host unit test so it cannot regress silently.
Output: rewritten DDL in `app/database.py`, a sibling unit-test file, a one-time SQL record.

**Diagnosis is verified — do not re-derive it.** Do not query the live DB, do not rebuild
containers, do not execute SQL. See `<executor_boundaries>`.
</objective>

<executor_boundaries>
**The executor does NOT:**
- run `docker`, `docker compose`, or any container build/restart
- connect to TimescaleDB or Postgres, or execute any SQL anywhere
- execute the file it writes under `database/migrations/one_time_repairs/` — that file is a
  **written record**, not a runbook step. It documents what the boot DDL will do on next
  restart. Writing it is the deliverable; running it is not.
- touch the `market_data` schema. It holds 4 empty never-used shadow hypertables from
  `infrastructure/scripts/init-timescale.sql`. They are dead. They are also why every table
  reference below is schema-qualified `public.` — an unqualified name can resolve to the
  wrong object depending on `search_path`.

**The executor DOES:** edit Python + write SQL text + run host pytest + commit.

Live verification (retention jobs appear in `timescaledb_information.jobs`,
`public.orderbook_snapshots` becomes a hypertable) happens **after** the orchestrator
rebuilds and restarts market-data-service. This plan ends at green host tests + commit.
</executor_boundaries>

<context>
@services/market-data-service/app/database.py
@services/market-data-service/app/models.py
@services/market-data-service/tests/test_config_defaults.py

**Verified line numbers (2026-08-16, re-check before editing):**
- `app/database.py:123-206` — `create_hypertables()`
- `app/database.py:135-154` — `hypertable_statements` (orderbook entry at :149-153)
- `app/database.py:156-163` — `retention_statements` (the broken INTERVAL ones)
- `app/database.py:165-174` — `column_migrations` (idempotent precedent — keep unchanged in
  substance; only the table references get `public.`-qualified)
- `app/database.py:186-198` — `_run_isolated` + the two driving loops
- `app/models.py:131-153` — `OrderBook`, `id` as sole PK
- `app/models.py:157-206` — dead `CREATE_HYPERTABLE_SQL` constant (zero importers — grep
  across the repo returns only its own definition; it still says klines/90d and contradicts
  this fix)
- `app/main.py:83-88` — sole caller, already `try/except` + warning. Failures stay non-fatal
  so the service still boots against a non-TimescaleDB Postgres. **Do not make DDL fatal.**

**SQLAlchemy note so you don't rewrite working SQL:** `text()` bind-param detection has a
negative lookbehind for `:`, so PostgreSQL `::bigint` casts and `$$`-quoted bodies pass
through untouched. Keep `::bigint`; do not convert to `CAST(...)`.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite boot DDL as one ordered, schema-qualified statement sequence</name>
  <files>services/market-data-service/app/database.py, services/market-data-service/app/models.py</files>

  <action>
**Step 0 — baseline first.** From `services/market-data-service`, run
`python -m pytest tests/ --no-cov -q 2>&1 | tail -5` and record the pass/fail/skip counts.
This suite has pre-existing wholesale-skipped files; you need the before-number to prove you
did not regress anything in Task 2.

Then confirm no *other* repo path creates a klines retention policy — the `must_haves` truth
and T-RES02-01 depend on it. Run
`grep -rn "add_retention_policy" --include=*.sql --include=*.py . | grep -v __pycache__`.
**Verified 2026-08-16, expected result:** the only `klines` hits are the two this task
deletes (`app/database.py:158`, `app/models.py:203`). Every other hit targets the dead
`market_data.*` schema (`infrastructure/scripts/init-timescale.sql:83-86`) or unrelated app
tables (`database/schema.sql:537-543`) — leave all of those alone. If a klines policy turns
up anywhere else, stop and report it; that is a scope call for the orchestrator, not a fix
to make here.

**Then rewrite `create_hypertables()` in `app/database.py`.**

Replace the three separate lists (`hypertable_statements` :135-154, `retention_statements`
:156-163) with **one module-level ordered constant**:

`DDL_STATEMENTS: list[tuple[str, str, str]]` — each entry is `(label, statement, level)`,
where `level` is `"warning"` or `"error"` and controls the log level used when that statement
fails. Move it to module scope (above `create_hypertables`) so tests can import it.

Order is load-bearing and must be exactly this — TimescaleDB enforces each dependency:

1. `("Integer-now function", "CREATE OR REPLACE FUNCTION public.unix_now_ms() RETURNS BIGINT LANGUAGE SQL STABLE AS $$ SELECT (extract(epoch FROM now()) * 1000)::bigint $$", "error")`
   — must exist before any `set_integer_now_func` references it. `STABLE` is required
   (TimescaleDB rejects VOLATILE for an integer-now func).
2. `create_hypertable('public.klines', 'timestamp', chunk_time_interval => 86400000, if_not_exists => TRUE, migrate_data => TRUE)` — level `"warning"` (already converted; no-ops).
3. Same for `'public.tickers'`.
4. **The orderbook DO block** (see below) — level `"error"`.
5. `SELECT set_integer_now_func('public.klines', 'public.unix_now_ms', replace_if_exists => TRUE)` — level `"error"`. Must come AFTER #2: the table has to already be a hypertable.
6. Same for `'public.tickers'` (after #3).
7. Same for `'public.orderbook_snapshots'` (after #4 — it only becomes a hypertable there).
8. `SELECT add_retention_policy('public.tickers', drop_after => 180::bigint * 86400000, if_not_exists => TRUE)` — level `"error"`. After #6.
9. `SELECT add_retention_policy('public.orderbook_snapshots', drop_after => 7::bigint * 86400000, if_not_exists => TRUE)` — level `"error"`. After #7.
10. The two existing `column_migrations` statements from :169-174 — unchanged in substance,
    with only their table references qualified to `public.klines` — at level `"warning"`.
    Keep their explanatory comment (:165-168) verbatim; it records the 2026-04-29 incident.

**klines gets NO retention policy.** This is deliberate, not an omission. Put a comment
block where the old `add_retention_policy('klines', INTERVAL '90 days', ...)` was, stating:
the 90d policy would delete 385,808 rows (52% of the table) — the entire backfilled research
history; total footprint is 288 MB for 2.7 years, so disk is a non-issue; deleting research
data must be an explicit operator action, never a background job. Also note tickers is 180d
rather than 30d because 30d would wipe 72% of it including the clean post-2026-08-12 mainnet
record.

**The orderbook DO block — one single statement, one list entry.** Do NOT split the
DROP CONSTRAINT / ADD PRIMARY KEY / create_hypertable into separate entries.
`_run_isolated` gives each entry its own transaction and swallows the exception; three
entries means a `create_hypertable` failure **commits the PK reshape anyway** and leaves a
half-migrated table with only a warning in the log. One DO block = atomic rollback.

The PK constraint name must be **resolved at runtime**, not hardcoded. The live diagnosis
verified the PK's columns, not its name; a wrong literal aborts the block and gets logged as
a swallowed warning, costing the orchestrator a rebuild cycle to discover.

```
DO $$
DECLARE pk_name text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'public' AND hypertable_name = 'orderbook_snapshots'
    ) THEN
        SELECT conname INTO pk_name FROM pg_constraint
        WHERE conrelid = 'public.orderbook_snapshots'::regclass AND contype = 'p';
        IF pk_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.orderbook_snapshots DROP CONSTRAINT %I', pk_name);
        END IF;
        ALTER TABLE public.orderbook_snapshots ADD PRIMARY KEY (id, "timestamp");
        PERFORM create_hypertable('public.orderbook_snapshots', 'timestamp',
            chunk_time_interval => 86400000::bigint,
            if_not_exists => TRUE, migrate_data => TRUE);
    END IF;
END $$
```

The `hypertable_schema = 'public'` guard is mandatory — an unqualified check matches the dead
`market_data.orderbook_snapshots` shadow and would skip the real conversion forever.

**int4 overflow is real and was reproduced live:** `90*86400000` errors as int4. Every
`drop_after` arithmetic expression uses `::bigint` on the multiplier. `86400000` alone as a
`chunk_time_interval` literal is under int4 max and is fine.

**`_run_isolated` hardening.** Change the signature to
`async def _run_isolated(stmt: str, label: str, level: str = "warning") -> None` and dispatch
to `logger.error` when `level == "error"`, else `logger.warning`. It must still **swallow**
the exception — `main.py:83-88` depends on non-fatal DDL so the service boots against plain
Postgres. Replace the two loops at :194-198 (plus the column-migration loop at :203-204) with
a single `for label, stmt, level in DDL_STATEMENTS: await _run_isolated(stmt, label, level)`.

**`app/models.py`:** leave the `OrderBook` class mapping `id` as the sole PK (:139) — the
composite DB PK is invisible to this insert-only model, and changing the ORM would make
SQLAlchemy emit a composite key it does not need. Add a short comment on the class noting the
DB-level PK is `(id, timestamp)` because TimescaleDB requires the partition column in every
unique index, and pointing at `database.py`. Then replace the dead `CREATE_HYPERTABLE_SQL`
constant (:157-206) with a one-line pointer comment naming `app/database.py::DDL_STATEMENTS`
as authoritative — it has zero importers and still asserts the wrong klines/90d policy.
  </action>

  <verify>
    <automated>cd services/market-data-service &amp;&amp; python -c "from app.database import DDL_STATEMENTS; s=[x[1] for x in DDL_STATEMENTS]; assert all('public.' in x for x in s), 'unqualified statement'; assert not any('INTERVAL' in x for x in s), 'INTERVAL retention survived'; assert not any('add_retention_policy' in x and 'klines' in x for x in s), 'klines retention present'; print(len(s), 'statements OK')"</automated>
  </verify>

  <done>
`DDL_STATEMENTS` is importable at module scope with entries in the order above.
`create_hypertables()` drives it through a single loop. No `INTERVAL` retention statement
remains. No `add_retention_policy` mentions klines. `_run_isolated` takes a level and still
swallows exceptions. `models.py` dead constant is gone. Nothing was executed against a DB.
  </done>
</task>

<task type="auto">
  <name>Task 2: Add DDL unit tests, write the one-time SQL record, commit</name>
  <files>services/market-data-service/tests/test_database_ddl.py, database/migrations/one_time_repairs/2026-08-16-market-data-retention-and-orderbook-hypertable.sql</files>

  <action>
**Create `tests/test_database_ddl.py` — a NEW sibling file with NO module-level skip.**

`tests/test_database.py:15` carries
`pytestmark = pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")`,
which wholesale-skips every test in it. Adding assertions there would silently no-op — that
is the highest-probability false pass in this task. `tests/test_config_defaults.py` is the
established precedent for this exact workaround (read its docstring); mirror its shape:
a header docstring explaining why the sibling exists, an explicit
`# NOTE: NO module-level pytestmark skip here` comment, and imports done lazily inside test
functions so collection survives host/container dependency differences.
(`tests/conftest.py` imports `app.main` at module scope for the whole directory; that already
works on host, per the precedent file.)

**Assert against the imported constant, never against the file source.** Import
`DDL_STATEMENTS` and build `stmts = [s for _, s, _ in DDL_STATEMENTS]`. Do NOT `grep` or read
`database.py` as text: the klines rationale comment you just wrote contains the literal token
`add_retention_policy`, so any text-based negative assertion is self-invalidating. Importing
the constant excludes comments by construction.

Tests to write:

1. `test_klines_has_no_retention_policy` — the negative that protects the research history.
   No statement contains both `add_retention_policy` and `klines`.
2. `test_retention_uses_bigint_drop_after` — every statement containing `add_retention_policy`
   also contains `drop_after` and `::bigint`, and none contains `INTERVAL`.
3. `test_retention_windows` — a tickers policy with `180::bigint * 86400000`, an
   orderbook_snapshots policy with `7::bigint * 86400000`.
4. `test_integer_now_func_registered_for_every_hypertable` — `unix_now_ms` is created, and
   `set_integer_now_func` appears for `public.klines`, `public.tickers`, and
   `public.orderbook_snapshots`.
5. `test_all_table_references_schema_qualified` — covers **both quoted literals and bare
   identifiers** (e.g. `ALTER TABLE klines` must fail the check too, not just `'klines'`).
   Use a word-boundary regex with a negative lookbehind — `(?<!public\.)\bklines\b`, same
   for `tickers` and `orderbook_snapshots` — and assert no statement matches. The boundary
   matters: `_` is a word character, so `idx_klines_mainnet` in the column migrations
   correctly does NOT match; a naive substring check would false-fail on it. Also assert the
   orderbook DO block's hypertable guard includes `hypertable_schema = 'public'`.
6. `test_statement_ordering` — **the assertion that actually protects the fix.** Content
   checks alone pass on a mis-ordered list. Write an `idx(substr)` helper using
   `next((i for i, s in enumerate(stmts) if substr in s), -1)` and assert `!= -1` before
   comparing — a bare `next()` raises `StopIteration` and surfaces as an unreadable error
   instead of a failed assertion. Then assert:
   - `unix_now_ms` creation precedes every `set_integer_now_func`
   - `create_hypertable('public.klines'` precedes `set_integer_now_func('public.klines'`
   - `set_integer_now_func('public.tickers'` precedes the tickers `add_retention_policy`
   - the orderbook DO block precedes `set_integer_now_func('public.orderbook_snapshots'`,
     which precedes the orderbook `add_retention_policy`
7. `test_orderbook_conversion_is_a_single_atomic_statement` — exactly one statement contains
   `ADD PRIMARY KEY (id, "timestamp")`, and that same statement also contains
   `create_hypertable` and `DROP CONSTRAINT` (proves it was not split across `_run_isolated`
   calls), and it resolves the constraint name via `pg_constraint` rather than hardcoding
   `orderbook_snapshots_pkey`.

**Write the one-time SQL record** at
`database/migrations/one_time_repairs/2026-08-16-market-data-retention-and-orderbook-hypertable.sql`.
`database/migrations/` is authoritative per the 2026-08-05 owner decision; the directory and
two prior repair files already exist — match their header style. **This file is a record, not
a runbook step — write it, do not execute it.** A header comment must state that the live
mechanism is the boot DDL in `services/market-data-service/app/database.py::DDL_STATEMENTS`
and that this file exists so the schema change is discoverable from the migrations tree.
Body: the same statements as `DDL_STATEMENTS` (integer-now func, orderbook PK reshape +
conversion, tickers 180d, orderbook 7d), plus an explicit note that **klines intentionally
has no retention policy** and why.

**Run the tests.** From `services/market-data-service`:
- `python -m pytest tests/test_database_ddl.py --no-cov -v` — all pass.
- `python -m pytest tests/ --no-cov -q 2>&1 | tail -5` — compare to the Step-0 baseline from
  Task 1. Pass count must not drop; skip count must not rise.

If the host is missing a dependency and collection fails on an unrelated import, say so
rather than weakening an assertion — do not add a skip mark to make the file green.

**Commit, pathspec-scoped** (parallel agents share one git index; never bare `git add .`).
Two of these four paths are **new and untracked**, and `git commit -- <paths>` only matches
tracked files — it aborts with `pathspec ... did not match any file(s) known to git`. Stage
the new files explicitly first; naming exact pathspecs keeps siblings' work out of the index:

```
git add services/market-data-service/tests/test_database_ddl.py \
  database/migrations/one_time_repairs/2026-08-16-market-data-retention-and-orderbook-hypertable.sql
git commit -- services/market-data-service/app/database.py \
  services/market-data-service/app/models.py \
  services/market-data-service/tests/test_database_ddl.py \
  database/migrations/one_time_repairs/2026-08-16-market-data-retention-and-orderbook-hypertable.sql
```

Subject: `fix(market-data): register integer-now funcs, convert orderbook hypertable, rewrite retention policies`

Body must record: 0 retention jobs existed because integer time dimensions had no
`integer_now_func`; orderbook PK excluded the partition column; klines retention deliberately
dropped to protect 385,808 backfilled research rows; tickers 30d→180d; the `models.py` dead
`CREATE_HYPERTABLE_SQL` removal (so it is not a surprise diff); and that live effect requires
a market-data-service rebuild + restart, not yet performed.
  </action>

  <verify>
    <automated>cd services/market-data-service &amp;&amp; python -m pytest tests/test_database_ddl.py --no-cov -q</automated>
  </verify>

  <done>
`tests/test_database_ddl.py` exists with no module-level skip, all 7 tests pass, and the full
market-data suite shows no regression against the Task-1 baseline. The one-time SQL record
exists and was not executed. One pathspec-scoped commit landed. No container was rebuilt.
  </done>
</task>

</tasks>

<orchestrator_followup>
Not executor work — recorded so post-rebuild verification is not improvised.

After `docker compose -f docker-compose.unified.yml up -d --build market-data-service`
(WSL2: prefix `DOCKER_BUILDKIT=0`), confirm all four:
1. Boot log shows the DDL labels applied, with no `Retention policy: ...` error lines.
2. `SELECT hypertable_name, config FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention'`
   returns exactly **two** rows — `tickers` and `orderbook_snapshots`. **Zero klines rows is
   the pass condition**, not a failure.
3. `SELECT integer_now_func FROM timescaledb_information.dimensions WHERE hypertable_schema='public'`
   is non-NULL for klines, tickers, orderbook_snapshots.
4. `public.orderbook_snapshots` appears in `timescaledb_information.hypertables` with
   `hypertable_schema='public'`, and its PK is `(id, timestamp)`.
5. `SELECT count(*) FROM public.klines` still returns the pre-change count — nothing deleted.

**Pre-recorded fallback (conditional — do not apply preemptively).** If the boot log shows
`create_hypertable` failing inside the DO block specifically over `migrate_data` in a
transaction, the table is at 0 rows, so `migrate_data => FALSE` is a safe escape hatch. This
restriction is unconfirmed for TimescaleDB 2.26.3; only apply it if that error actually
appears.
</orchestrator_followup>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| boot DDL → TimescaleDB | Service startup issues schema-changing statements with DB-owner rights. No untrusted input crosses here; all SQL is a static literal. The risk is **destructive DDL**, not injection. |
| background policy job → klines | A TimescaleDB retention job deletes rows on a schedule with no operator in the loop. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-RES02-01 | Denial of Service (data destruction) | `add_retention_policy` on `public.klines` | mitigate | No klines retention policy at all. A 90d window would delete 385,808 rows (52%) — the entire backfilled research history that every backtest depends on. Deleting research data must be an operator action, never a background job. Enforced by `test_klines_has_no_retention_policy` against the imported constant. |
| T-RES02-02 | Denial of Service (data destruction) | `add_retention_policy` on `public.tickers` | mitigate | 180d, not the original 30d. 30d would wipe 72% of tickers including the clean post-2026-08-12 mainnet epoch. 180d preserves the clean epoch. |
| T-RES02-03 | Tampering (half-applied migration) | orderbook PK reshape + `create_hypertable` | mitigate | Single `DO $$ ... $$` block = one `_run_isolated` transaction. A `create_hypertable` failure rolls back the PK drop instead of committing a table left with no usable primary key and a swallowed warning. Enforced by `test_orderbook_conversion_is_a_single_atomic_statement`. |
| T-RES02-04 | Tampering (wrong object) | unqualified table names vs dead `market_data` shadow hypertables | mitigate | Every reference is `public.`-qualified and the hypertable existence guard filters `hypertable_schema = 'public'`. Without it the guard matches the dead shadow and the real conversion is skipped forever. Enforced by `test_all_table_references_schema_qualified`. |
| T-RES02-05 | Denial of Service (availability) | `create_hypertables()` failure at boot | accept | DDL failures stay non-fatal and are only logged; `main.py:83-88` must keep booting against a non-TimescaleDB Postgres. Mitigated in part by raising retention/integer-now failures from `warning` to `error` so silent failure is visible in logs. |
| T-RES02-06 | Information Disclosure | — | accept | No credentials, PII, or user input involved. Statements are static literals; the only runtime-interpolated value is a constraint name read from `pg_constraint` and passed through `format(%I)`. |
| T-RES02-SC | Tampering (supply chain) | package installs | N/A | No npm/pip/cargo installs in this plan. Package Legitimacy Gate does not apply. |
</threat_model>

<verification>
- `DDL_STATEMENTS` importable; `create_hypertables()` drives it in one loop.
- `python -m pytest tests/test_database_ddl.py --no-cov -v` — all pass.
- Full market-data suite pass count ≥ Task-1 baseline; skip count not increased.
- No `INTERVAL`-based retention statement anywhere in `DDL_STATEMENTS`.
- No `docker` command run; no SQL executed against any database.
- One pathspec-scoped commit; working tree otherwise clean.
</verification>

<success_criteria>
RES-02's two root causes are corrected in the boot DDL and locked in by host unit tests that
assert both the content and the ordering of the statement sequence. klines research history is
explicitly protected from background deletion. The change is committed and ready for the
orchestrator to rebuild and verify live.
</success_criteria>

<output>
Create `.planning/quick/260816-qjn-fix-res-02-market-data-boot-ddl-integer-/260816-qjn-SUMMARY.md` when done.
</output>
</content>
</invoke>
