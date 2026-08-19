---
phase: quick/260816-qjo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - services/trading-engine/app/database/models.py
  - services/trading-engine/app/repositories.py
  - services/trading-engine/app/position_manager.py
  - services/trading-engine/app/config.py
  - services/trading-engine/app/execution/smart_router.py
  - services/trading-engine/tests/unit/test_repositories.py
  - services/trading-engine/tests/test_accounting_invariants_phase1.py
  - services/trading-engine/tests/execution/test_smart_router.py
  - database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql
autonomous: true
requirements: [RES-03, RES-04, RES-05]

must_haves:
  truths:
    - "portfolios.total_value is written by the engine on every position close and balance update (was never written — the column was not even ORM-mapped)"
    - "portfolios.total_pnl and portfolios.unrealized_pnl are maintained in the same UPDATE as cash_balance, so the four columns can never disagree"
    - "The closing position's stale unrealized_pnl cannot be double-counted into the portfolio aggregate"
    - "A newly created PAPER portfolio row carries risk_per_trade / max_daily_loss agreeing with ADR-010 (0.10) and ADR-028 (0.12), not the stale 0.02 / 0.05"
    - "SmartRouterConfig.small_order_threshold is operator-tunable via Settings instead of a hardcoded 1000.0 literal"
  artifacts:
    - path: "services/trading-engine/app/database/models.py"
      provides: "Portfolio.total_value ORM column"
      contains: "total_value"
    - path: "services/trading-engine/app/repositories.py"
      provides: "Aggregate maintenance in both portfolio write paths + unrealized zeroing on position close"
      contains: "total_value"
    - path: "services/trading-engine/app/position_manager.py"
      provides: "Serialized close persistence (position CLOSED commits before the portfolio aggregate is computed)"
    - path: "services/trading-engine/app/config.py"
      provides: "smart_router_small_order_threshold_usd Setting"
      contains: "smart_router_small_order_threshold_usd"
    - path: "database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql"
      provides: "One-time repair of the never-maintained display columns + stale risk columns"
  key_links:
    - from: "services/trading-engine/app/repositories.py"
      to: "positions.unrealized_pnl"
      via: "correlated scalar subquery over OPEN positions"
      pattern: "scalar_subquery"
    - from: "services/trading-engine/app/execution/smart_router.py"
      to: "app.config.get_settings"
      via: "lazy import inside get_smart_router()"
      pattern: "smart_router_small_order_threshold_usd"
---

<objective>
Repair three trading-engine defects found in the 2026-08-16 audit:

- **RES-03** — `portfolios.total_value` / `total_pnl` / `unrealized_pnl` are never maintained. `total_value` is not even ORM-mapped, so the engine *cannot* write it; `total_pnl` is mapped and never assigned. Only `cash_balance` and `realized_pnl` move.
- **RES-04** — `portfolios.risk_per_trade` (0.0200) and `max_daily_loss` (0.0500) contradict ADR-010 (10% paper per-trade) and ADR-028 (12% daily). They have zero runtime readers today, so this is a truthfulness fix on a row an operator reads, not a behavior change.
- **RES-05** — `SmartRouterConfig.small_order_threshold` is a hardcoded `1000.0` literal, not operator-tunable.

Purpose: these columns are what an operator sees when they query the portfolio row directly. Today they lie. Nothing reads them at runtime, which is exactly why the drift went unnoticed — and exactly why repairing them is low-risk.

Output: 3 pathspec-scoped commits + one one-time repair SQL file (written, NOT executed by the executor).
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.claude/rules/money.md

@services/trading-engine/app/repositories.py
@services/trading-engine/app/database/models.py
@services/trading-engine/app/position_manager.py
@services/trading-engine/app/execution/smart_router.py
</context>

<interfaces>
<!-- Verified against the working tree 2026-08-16. Use these directly — no codebase exploration needed. -->

`app/repositories.py` already imports everything Task 1 needs — adding imports is a defect, not a fix:

```python
from app.config import get_settings           # :15
from app.database.models import Position as DBPosition, Portfolio as DBPortfolio   # :17-20
from sqlalchemy import case, func, select, update                                   # :21
```

Current `Portfolio` ORM (`app/database/models.py:31-72`) — note the absent `total_value`:

```python
initial_balance = Column(DECIMAL(20, 8), nullable=False)
cash_balance    = Column(DECIMAL(20, 8), nullable=False)
realized_pnl    = Column(DECIMAL(20, 8), default=0)
unrealized_pnl  = Column(DECIMAL(20, 8), default=0)
total_pnl       = Column(DECIMAL(20, 8), default=0)   # mapped, never assigned
# ...
risk_per_trade  = Column(DECIMAL(5, 4), default=0.02)   # fraction, 4dp -> max 9.9999
max_daily_loss  = Column(DECIMAL(5, 4), default=0.05)   # fraction, 4dp
```

`Position` ORM (`app/database/models.py:99+`) — the aggregate source:

```python
portfolio_id   = Column(String(100), ForeignKey("portfolios.portfolio_id"), nullable=False)
unrealized_pnl = Column(DECIMAL(20, 8), default=0)
status         = Column(String(20), nullable=False, default="OPEN")   # CHECK IN ('OPEN','CLOSED')
```

`SmartRouterConfig` (`app/execution/smart_router.py:101-138`) is a plain `@dataclass`; `small_order_threshold: float = 1000.0` at `:117`. Factory at `:1546`:

```python
def get_smart_router(config: Optional[SmartRouterConfig] = None) -> SmartOrderRouter:
    global _smart_router
    if _smart_router is None:
        _smart_router = SmartOrderRouter(config)
    return _smart_router
```

Settings `Field` house style (`app/config.py:557-594`) — keyword `default=`, validators, prose `description`. `model_config` at `:736` has **no** `env_prefix`, so the env key is the upper-cased field name.
</interfaces>

<verified_diagnosis>
Established by live-DB + repo greps on 2026-08-16, re-confirmed against the working tree while planning. Do not re-derive.

**Both portfolio write paths are the engine's only portfolio writers:** `record_position_close` (`repositories.py:724`) and `update_balance` (`:778`). Zero code consumers of `total_value` / `total_pnl` exist — every API/frontend `total_value` comes from portfolio-manager's in-memory sync, not the DB. DB-level readers are only the unused `portfolio_performance` view and a dead root-level `sync_portfolio_pnl.sql`.

**The close path is a genuine race — this is why Task 1 is bigger than "add three keys to a `.values()`".**
`position_manager.close_position` is **sync** (`def`, `:456`). It fires *two independent* `asyncio.create_task` persistences via `_spawn_persist` (`:71-86`):

- `:545` `position_repo.close(...)` — writes `status='CLOSED'` but **does not touch `unrealized_pnl`**, so the row keeps its last stale tick value forever.
- `:576` `portfolio_repo.record_position_close(...)` — where the new `SUM(unrealized_pnl) WHERE status='OPEN'` subquery would run.

Separate sessions, no ordering guarantee. If the portfolio task's SELECT wins the race, the just-closed position is still `OPEN` carrying stale unrealized P&L, which lands in `unrealized_pnl` / `total_value` / `total_pnl` **on top of** the realized delta just accumulated. A nondeterministic double-count that a mocked unit test would never catch. Task 1 closes it two ways: zero `unrealized_pnl` in `close()` (correct by definition) *and* serialize the two persists.

`update_balance` needs no ordering fix: it is called on partial exit and scale-in, where the position is genuinely still OPEN, so including its unrealized is intended.

**Equity definition (decided — do not reopen).** `total_value = cash + open_unrealized` mirrors `PaperTradingEngine.get_total_equity()` (`paper_trading.py:209-211`). That definition excludes `posted_margin`, which is debited from cash at open — arguably understating equity while positions are open. It is nonetheless the engine-wide definition used by the kill switch, `/performance`, and the frontend. Making the DB the only surface with a *different* equity definition would be strictly worse than the current "never maintained". The margin exclusion is filed as an out-of-scope finding (RES-06 candidate).

**The `total_value` column already exists in the DDL — verified while planning, no migration needed.** `database/schema.sql:176` and `database/migrations/002_create_tables.sql:115` both declare `total_value DECIMAL(20, 8) NOT NULL`, with **no DDL default**. Two consequences:

- Existing rows cannot be NULL, so `float(self.total_value)` in `to_dict()` is safe (and no trading-engine handler calls `Portfolio.to_dict()` today anyway — grep returns nothing).
- NOT NULL with no default means an INSERT omitting the column is rejected. Because `total_value` is currently unmapped, SQLAlchemy omits it, so `get_or_create` cannot insert a new portfolio row against the real schema at all. Mapping it with `default=0` **repairs that latent INSERT failure** as a side effect — mention this in the summary.

**Wrong-file traps — three of them, all live:**

| Trap | Correct target | Do NOT touch |
|---|---|---|
| Two `SmartOrderRouter` classes | `app/execution/smart_router.py` (imported by `handlers/execution_router.py`, `lifespan/risk.py`) | `app/execution/smart_order_router.py` — not live |
| Third sibling `1000.0` literal | — | `app/execution/execution_optimizer.py` — out of scope, flag only |
| Two `test_repositories.py` | `tests/unit/test_repositories.py` (no module skip, 25 pass) | root `tests/test_repositories.py` — `pytestmark = pytest.mark.skip` at `:15`; edits there run nothing |

**Baselines measured while planning (host, `--no-cov`, no env exports):**

| cwd | Files | Result |
|---|---|---|
| `services/trading-engine` | `tests/unit/test_repositories.py` + `tests/execution/test_smart_router.py` | **63 passed** (25 + 38) |
| `services/trading-engine` | `test_partial_exit_cash_persistence` + `test_accounting_invariants_phase1` + `test_cash_conservation_invariant` + `test_posted_margin_ledger` | **27 passed** |
| repo root | `tests/test_account_size_invariant.py` + `tests/test_account_config_sync.py` | **26 passed** |

Any failure in these is caused by this plan — there are no pre-existing failures to explain away.
</verified_diagnosis>

<test_protocol>
Host runs only. Use `python3`, not `python` (there is no `python` on PATH in this environment).

- trading-engine tests: **cwd must be `services/trading-engine`** (cwd-sensitive) and always `--no-cov`.
- **Export NO env vars.** `conftest.py` pins `env_file=None`; exporting settings vars now corrupts `Dict` settings.
- The account-invariant tests live at **repo root** `tests/`, not in the service — run them from the repo root.
- The executor does **not** run SQL against the live DB and does **not** rebuild Docker images.
</test_protocol>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RES-03 — maintain total_value / total_pnl / unrealized_pnl in both portfolio write paths, and make the close path deterministic</name>
  <files>
services/trading-engine/app/database/models.py
services/trading-engine/app/repositories.py
services/trading-engine/app/position_manager.py
services/trading-engine/tests/unit/test_repositories.py
services/trading-engine/tests/test_accounting_invariants_phase1.py
  </files>
  <behavior>
    - `record_position_close` issues ONE UPDATE whose values set `cash_balance`, `realized_pnl` (accumulated), `unrealized_pnl`, `total_value`, `total_pnl`, `updated_at`.
    - `update_balance` sets the same aggregate trio and still honors its overwrite semantics: the `realized_pnl` param when supplied, the stored column otherwise.
    - `PositionRepository.close()` writes `unrealized_pnl = 0` alongside `status='CLOSED'` — a closed position has no unrealized P&L.
    - Ordering: with `position_repo.close` and `portfolio_repo.record_position_close` both appending a marker to a shared list, a full close yields exactly `["close", "ledger"]` — never the reverse, never interleaved.
    - Neither repository method gains or loses a parameter; all four money-path suites stay green unchanged.
  </behavior>
  <action>
Three source files, in this order.

**1. `app/database/models.py` — map the missing column.** In `Portfolio`, directly under `total_pnl` (`:46`), add a `total_value` column: `DECIMAL(20, 8)`, `nullable=False`, `default=0`. Add it to `to_dict()` as `float(self.total_value)` next to the other P&L keys. Leave the `risk_per_trade` / `max_daily_loss` DDL defaults alone — Task 2 owns those and deliberately does not change the DDL.

**2. `app/repositories.py` — maintain the aggregates.** Every symbol needed is already imported (`select`, `func`, `update`, `DBPosition`, `DBPortfolio`, `get_settings`).

Build one correlated scalar subquery used by both write paths, bound to a local named `open_unrl`: `select` of `func.coalesce(func.sum(DBPosition.unrealized_pnl), 0)`, filtered on `DBPosition.portfolio_id == portfolio_id` and `DBPosition.status == "OPEN"`, finished with `.scalar_subquery()`.

In `record_position_close`, bind the existing accumulation expression to a local named `new_realized` so it is written once and reused — it stays `func.coalesce(DBPortfolio.realized_pnl, 0) + realized_pnl_delta`. Then extend the SAME values with `unrealized_pnl=open_unrl`, `total_value=open_unrl + cash_balance` (subquery on the left — avoids relying on `Decimal.__radd__` dispatch), and `total_pnl=new_realized + open_unrl`. Do not add a second UPDATE and do not split the statement — the entire point is that the columns can never disagree with `cash_balance`.

In `update_balance`, extend the existing `update_values` dict the same way. The realized term must preserve the documented overwrite semantics at `:784-787`: when the `realized_pnl` param is not `None` use the param, otherwise use `func.coalesce(DBPortfolio.realized_pnl, 0)`. Compute that into a local first, then use it for `total_pnl` — and keep writing the `realized_pnl` key **only** when the param was supplied. Do not start writing `realized_pnl` on calls that omit it, and do not change the overwrite semantics; both would break `test_partial_exit_cash_persistence.py`.

Add a comment at both write sites recording two things a future reader will otherwise "fix" into a bug: (a) `total_value = cash + open_unrealized` deliberately mirrors `PaperTradingEngine.get_total_equity()` (`paper_trading.py:209-211`) and is therefore margin-exclusive — the two definitions must move together or not at all; (b) between a partial exit and the final close, `total_pnl` understates by the partial's realized slice, because `update_balance` is called with `realized_pnl=None` while `portfolios.realized_pnl` only accumulates on full close — this self-corrects at close, since `record_position_close`'s delta is the position's *total* net realized P&L, partials included. Neither is a bug to fix.

In `PositionRepository.close()` (`:195`), add `unrealized_pnl` set to `Decimal("0")` to the `values` dict next to `remaining_quantity`, with a one-line comment: a CLOSED row previously kept its last stale tick value forever, which is what makes the aggregate subquery above race-sensitive.

**3. `app/position_manager.py` — serialize the close persistence.** In `close_position` (`:456`, sync), the two `_spawn_persist` calls at `:545` and `:576` currently produce two independent `asyncio.create_task`s in separate sessions with no ordering guarantee. Replace them with a single spawned coroutine that awaits `position_repo.close(...)` first and `portfolio_repo.record_position_close(...)` second, so the row is CLOSED with zeroed unrealized before the portfolio aggregate is computed. Define it as a local `async def` closure inside `close_position` and pass its coroutine to one `_spawn_persist` call with a label such as "position close + portfolio ledger".

Preserve today's failure behavior: the ledger write must still be attempted even if `close()` raises. Put the `await position_repo.close(...)` in a `try` and the `await portfolio_repo.record_position_close(...)` in the matching `finally`, so an exception still propagates to `_persist_done` and is logged. Keep the existing `_cash_now` guard exactly as it is — when the paper-engine balance could not be read, today's code skips the ledger write entirely, so the chained coroutine must schedule only the `close()` leg in that case, never a ledger write with a `None` balance. Keep the surrounding comment block at `:558-564`.

**4. Tests — `tests/unit/test_repositories.py`** (no module skip; the root `tests/test_repositories.py` is skipped and edits there run nothing). Extend `TestPortfolioRepository` following the file's existing mock style (`patch.object(repo.db, "get_async_session")`, `AsyncMock` session, `Mock` result). Add:

- a `record_position_close` test asserting the executed statement carries all of `cash_balance`, `realized_pnl`, `unrealized_pnl`, `total_value`, `total_pnl` — capture the statement from `mock_async_session.execute.call_args[0][0]` and assert on the presence of those keys in its compiled values (a `str(stmt)` containment check is an acceptable fallback, but assert on key presence, never on exact generated SQL text);
- an `update_balance` test proving `realized_pnl` is absent from the values when the param is omitted and present when supplied — the overwrite-semantics regression guard;
**5. The ordering test goes in `tests/test_accounting_invariants_phase1.py`, NOT in `tests/unit/test_repositories.py`.** The unit file imports only the three repositories and `DBPosition` — it has no `PositionManager`, no paper engine, no `stack` fixture, and no drain helper. Rebuilding those there means reconstructing `_entry_fees` / `_exit_fees` / `posted_margin` *and* `get_paper_engine()`, and that last one decides the outcome: `close_position:566-574` imports `get_paper_engine` inside a `try`, so if it raises or returns an object without `get_balance()`, `_cash_now` stays `None` and **the ledger leg is never scheduled at all** — the assertion sees `["close"]` and you burn the task budget debugging a fixture instead of the fix.

`tests/test_accounting_invariants_phase1.py` already has everything: the `stack` fixture with a real engine behind it, `_drain_tasks` (`:38`), `_order`, and `repo.record_position_close = AsyncMock()` (`:67`). Add a test there that attaches `side_effect`s to the two existing repo mocks appending `"close"` / `"ledger"` to a shared list, drives a full position close, awaits `_drain_tasks()`, then asserts the list equals `["close", "ledger"]`. (`tests/test_partial_exit_cash_persistence.py:23-26` shows the shared-fixture import pattern if a new sibling file is preferred.)

Do not otherwise touch `tests/test_partial_exit_cash_persistence.py` — its assertions are key-subset (`kwargs.get("realized_pnl") is None`), so a correct implementation leaves it green. If it goes red, the implementation changed a signature or the overwrite semantics.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine && python3 -m pytest tests/unit/test_repositories.py tests/test_partial_exit_cash_persistence.py tests/test_accounting_invariants_phase1.py tests/test_cash_conservation_invariant.py tests/test_posted_margin_ledger.py --no-cov -q</automated>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine && grep -v '^\s*#' app/repositories.py | grep -c 'total_value'</automated>
  </verify>
  <done>
First command: all pass, with at least 3 more tests than the 52-test baseline (25 unit + 27 money-path) and zero failures. Second command: returns 2 or more (both write paths), proving the token is in code and not only in a comment. `git diff` shows no signature change to `record_position_close` or `update_balance`.

Commit, pathspec-scoped (a shared git index means a bare `git add` sweeps in siblings' staged files):
`git commit -- services/trading-engine/app/database/models.py services/trading-engine/app/repositories.py services/trading-engine/app/position_manager.py services/trading-engine/tests/unit/test_repositories.py services/trading-engine/tests/test_accounting_invariants_phase1.py`
Message: `fix(trading-engine): maintain total_value/total_pnl/unrealized in portfolio write paths; serialize close persists`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: RES-04 — seed PAPER portfolio risk columns from Settings per ADR-010/028, plus the one-time repair SQL</name>
  <files>
services/trading-engine/app/repositories.py
services/trading-engine/tests/unit/test_repositories.py
database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql
  </files>
  <behavior>
    - `get_or_create` constructs a new PAPER Portfolio with `risk_per_trade` and `max_daily_loss` derived from Settings, not from the DDL defaults.
    - With `max_risk_per_trade=0.07` and `max_daily_loss_pct=9.0`, the constructed row carries `risk_per_trade == Decimal("0.07")` and `max_daily_loss == Decimal("0.09")` — the divide-by-100 is asserted on a value, never on a call.
    - Existing-portfolio lookups still return early and never re-seed.
  </behavior>
  <action>
**1. `app/repositories.py` — seed from Settings.** In `get_or_create` (`:706-712`), the `DBPortfolio(...)` constructor currently passes only `portfolio_id`, `name`, `initial_balance`, `cash_balance`, and `trading_mode="PAPER"`. Add `risk_per_trade` as `Decimal(str(get_settings().max_risk_per_trade))` and `max_daily_loss` as `Decimal(str(get_settings().max_daily_loss_pct)) / Decimal("100")`. `get_settings` is already imported at `:15` and already called at `:691` — follow that call style, and never hoist it to a module-level constant or a default argument (money.md: default args evaluate once at import and become invisible to the AST invariant checker).

**UNITS TRAP — the single most likely way this plan ships a silent bug.** `max_risk_per_trade` is a **fraction** (`0.10`). `max_daily_loss_pct` is a **percent** (`12.0`, ADR-028). The column is `DECIMAL(5, 4)` — a fraction with 4 decimal places, maximum representable value `9.9999`. Writing `12.0` unconverted therefore either raises a numeric-overflow error against a real DB or, against mocks, passes silently and corrupts the row on first live use. Divide by 100. This exact fraction-versus-percent class already shipped one silent bug in this repo (CLAUDE.md section 5).

Add a short comment naming both ADRs and stating plainly that the column is a fraction while the Setting is a percent.

Do **not** change the DDL defaults (`0.02` / `0.05`) in `models.py` — they are LIVE-conservative, which is the safe direction for any row created outside this path. Do **not** drop the columns: they are ORM-mapped in two model files, and dropping them recreates the schema-drift class that migration 003 fixed.

**2. The one-time repair SQL** — `database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql`. The executor **writes this file only and never executes it**. The orchestrator runs it, and only against a flat book (no OPEN positions), because the live `updated_at` trigger interacts with the restart balance-restore path at `paper_trading.py:176-187`.

Match the header style of the sibling `2026-08-07-cash-ledger-repair.sql`: a banner comment, what is being repaired and why, and — load-bearing — the explicit note that this is **NOT a numbered migration**, because `database/scripts/setup_database.sh` globs the migrations directory non-recursively and re-applies everything on every run, so a value overwrite must never sit on that path. Record the flat-book precondition in the header, and note that `max_daily_loss` is stored as a fraction (`0.12`), the same conversion the code path performs.

Two UPDATE statements, both scoped to `portfolio_id = 'paper_trading'`:

- RES-03 backfill — set `total_value = cash_balance`, `total_pnl = realized_pnl`, `unrealized_pnl = 0`. Under the flat-book precondition, open unrealized is zero, so this is exactly what the new code would compute.
- RES-04 repair — set `risk_per_trade = 0.10` and `max_daily_loss = 0.12`, additionally guarded by `AND trading_mode = 'PAPER'` so a LIVE row can never be relaxed by this file.

**3. Tests — `tests/unit/test_repositories.py`.** Extend `test_get_or_create_new_portfolio` or add a sibling test. Monkeypatch `app.repositories.get_settings` to return an object exposing `paper_initial_balance=100.0`, `max_risk_per_trade=0.07`, `max_daily_loss_pct=9.0` — **non-default values on purpose**: `0.10` / `0.12` are close enough that a wrong or missing transform can pass by luck, `0.07` / `0.09` cannot. Capture the constructed ORM object from `mock_async_session.add.call_args[0][0]` and assert `risk_per_trade == Decimal("0.07")` and `max_daily_loss == Decimal("0.09")`. `add.assert_called_once()` is not sufficient — with mocks there is no DB to reject an out-of-range value, so the values themselves must be asserted.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine && python3 -m pytest tests/unit/test_repositories.py --no-cov -q</automated>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot && test -f database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql && grep -v '^\s*--' database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql | grep -ci 'update portfolios'</automated>
  </verify>
  <done>
First command: all pass, at least 1 more test than the Task-1 count, zero failures. Second command: returns 2 — the comment-stripped filter proves both UPDATE statements are real SQL and not just header prose (a bare grep would pass on the banner comment alone).

Commit, pathspec-scoped:
`git commit -- services/trading-engine/app/repositories.py services/trading-engine/tests/unit/test_repositories.py database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql`
Message: `fix(trading-engine): seed PAPER portfolio risk columns from Settings per ADR-010/028`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: RES-05 — source the smart-router small-order threshold from Settings</name>
  <files>
services/trading-engine/app/config.py
services/trading-engine/app/execution/smart_router.py
services/trading-engine/tests/execution/test_smart_router.py
  </files>
  <behavior>
    - `SmartRouterConfig().small_order_threshold` still defaults to `1000.0` — the dataclass default is unchanged, so every direct construction behaves exactly as before.
    - `get_smart_router()` called with no argument builds a config whose `small_order_threshold` equals `settings.smart_router_small_order_threshold_usd`; monkeypatching that Setting to a distinctive value (e.g. `2500.0`) after `reset_smart_router()` yields a router carrying `2500.0`.
    - `get_smart_router(explicit_config)` still wins — the settings-derived config is built only when the caller passes nothing.
  </behavior>
  <action>
**1. `app/config.py` — add the Setting.** Add `smart_router_small_order_threshold_usd: float = Field(default=1000.0, gt=0, description=...)` in the house style of the `paper_*` block at `:557-594` (keyword `default=`, validator, prose description). Place it in its own commented section — there is no existing execution/router settings block, so introduce one; a sensible anchor is immediately after the paper-slippage block ending at `:594`, since both concern fill mechanics.

The `description` must state that this is a **market-microstructure calibration** (Bybit order-book depth — the notional above which a single market order stops being the cheapest execution) and explicitly **not** an account-size figure. Without that sentence, a future capital-audit pass sees `1000.0` in a $100-account repo and "fixes" it to derive from account size — a coupling that would silently reclassify large orders as small as the account grows, which is the opposite of what the threshold is for. `model_config` has no `env_prefix`, so the env key is `SMART_ROUTER_SMALL_ORDER_THRESHOLD_USD`; say so in the description.

Do not change the `SmartRouterConfig` dataclass default at `smart_router.py:117` — it stays `1000.0` so direct construction is unaffected.

**2. `app/execution/smart_router.py` — wire the factory.** In `get_smart_router()` (`:1546`), inside the `if _smart_router is None:` branch and **only when the `config` argument is `None`**, build a `SmartRouterConfig` with `small_order_threshold` taken from the Setting. Guarding on `config is None` is mandatory: `test_get_smart_router_with_config` (`:916`) passes an explicit config and must keep winning. Building the settings-derived config unconditionally breaks it.

Import Settings **lazily inside the function** (`from app.config import get_settings` in the function body), not at module scope — a module-scope import risks a config↔execution import cycle.

Wire it in the factory rather than in the lifespan: `POST /api/v1/execution/reset` rebuilds the router through this same factory (`handlers/execution_router.py` calls `get_smart_router()` at six sites; confirm the reset handler path with a quick `grep -n "reset" app/handlers/execution_router.py` before writing), so a lifespan-only wiring would be silently reverted to the literal on the first reset.

Leave `app/execution/smart_order_router.py` and `app/execution/execution_optimizer.py` untouched — the first is a dead duplicate class, the second is an out-of-scope sibling literal to be flagged in the summary only.

**3. Tests — `tests/execution/test_smart_router.py`** (38 tests, no skips; `get_smart_router` and `reset_smart_router` are already imported at `:47-48`). Add to the singleton-management class alongside `test_get_smart_router_singleton` (`:899`):

- a default assertion that `SmartRouterConfig().small_order_threshold == 1000.0`, pinning the unchanged dataclass default;
- a settings-driven factory test: call `reset_smart_router()`, monkeypatch `app.config.get_settings` to return an object whose `smart_router_small_order_threshold_usd` is a distinctive `2500.0`, call `get_smart_router()` with no argument, and assert `router.config.small_order_threshold == 2500.0`. Call `reset_smart_router()` again afterwards so the module-global singleton does not leak into other tests (`:85` shows the existing fixture already resets).
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine && python3 -m pytest tests/execution/test_smart_router.py --no-cov -q</automated>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot && python3 -m pytest tests/test_account_size_invariant.py tests/test_account_config_sync.py --no-cov -q</automated>
  </verify>
  <done>
First command: at least 40 pass (38 baseline + 2 new), zero failures. Second command: 26 pass — `config.py` is money-code, so adding a numeric Field puts the AST account-size invariant and the Settings-drift check in play; both must stay green.

Commit, pathspec-scoped:
`git commit -- services/trading-engine/app/config.py services/trading-engine/app/execution/smart_router.py services/trading-engine/tests/execution/test_smart_router.py`
Message: `fix(trading-engine): smart-router small-order threshold from Settings`
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|---|---|
| one-time repair SQL → live `portfolios` row | An unguarded UPDATE overwrites the authoritative cash/risk ledger the position sizer and kill switch read |
| `Settings` / env → `portfolios` risk columns | Operator-controlled values reach a `DECIMAL(5,4)` column that cannot represent a percent |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|---|---|---|---|---|
| T-qjo-01 | Tampering | one-time repair SQL | mitigate | Executor writes the file only; never executes it. Orchestrator runs it against a flat book. Both statements scoped by `portfolio_id`, the risk UPDATE additionally by `trading_mode='PAPER'` so a LIVE row can never be relaxed |
| T-qjo-02 | Tampering | `setup_database.sh` migration glob | mitigate | File lands in `one_time_repairs/`, which the non-recursive `*.sql` glob does not pick up, so the value overwrite cannot be re-applied on every setup run. Header states this explicitly |
| T-qjo-03 | Information disclosure (integrity of reported equity) | `record_position_close` aggregate subquery | mitigate | Serialized close persistence + `unrealized_pnl=0` on close prevent the stale-value double-count that would inflate reported equity nondeterministically |
| T-qjo-04 | Elevation of privilege (risk-cap widening) | `get_or_create` risk seeding | mitigate | Seeding path is PAPER-only; DDL defaults stay at the LIVE-conservative `0.02` / `0.05`; the percent→fraction conversion is asserted on non-default values |
| T-qjo-05 | Denial of service | `smart_router_small_order_threshold_usd` | accept | `gt=0` validator prevents zero/negative. A mis-set threshold degrades execution quality only; no order can be placed that risk checks would otherwise reject |

No package-manager installs in this plan, so no supply-chain (`T-*-SC`) row applies.
</threat_model>

<verification>
Full regression sweep after all three commits — run from `services/trading-engine`:

`python3 -m pytest tests/unit/test_repositories.py tests/execution/test_smart_router.py tests/test_partial_exit_cash_persistence.py tests/test_accounting_invariants_phase1.py tests/test_cash_conservation_invariant.py tests/test_posted_margin_ledger.py --no-cov -q`

Expected: at least 96 pass (90 baseline + 6 new), zero failures.

Then from the repo root: `python3 -m pytest tests/test_account_size_invariant.py tests/test_account_config_sync.py --no-cov -q` — 26 pass.

Then confirm the working tree contains exactly the 8 declared paths and that `git log --oneline -3` shows the three commit messages in order.

**Not in the executor's scope:** running the repair SQL, rebuilding images, restarting `crypto-bot-trading`. The running container serves pre-change code until the orchestrator rebuilds; no "working end-to-end" claim may be made from these test results alone (CLAUDE.md section 7).
</verification>

<success_criteria>
- `portfolios.total_value` is ORM-mapped and written by both engine write paths, in the same UPDATE as `cash_balance`.
- `total_pnl` and `unrealized_pnl` are maintained in that same UPDATE; `update_balance`'s overwrite semantics are unchanged.
- A full position close persists `status='CLOSED'` with `unrealized_pnl=0` **before** the portfolio aggregate is computed, proven by an ordering test — not by inspection.
- New PAPER portfolio rows carry `risk_per_trade=0.10` and `max_daily_loss=0.12`, with the percent→fraction conversion asserted on non-default values.
- `SmartRouterConfig().small_order_threshold` still defaults to `1000.0`; `get_smart_router()` with no argument honors the Setting; an explicit config still wins.
- The one-time repair SQL exists, is comment-documented, is scoped by `portfolio_id` (and `trading_mode` for the risk UPDATE), and has not been executed.
- 3 pathspec-scoped commits, in order, no unrelated files swept in.
</success_criteria>

<output>
Create `.planning/quick/260816-qjo-fix-res-03-04-05-portfolios-display-colu/260816-qjo-SUMMARY.md` when done.

Record in the summary: the sibling `1000.0` literal in `app/execution/execution_optimizer.py` (flagged, not fixed) and the RES-06 candidate — `get_total_equity()` excludes `posted_margin`, so every equity surface in the engine understates while positions are open.
</output>
