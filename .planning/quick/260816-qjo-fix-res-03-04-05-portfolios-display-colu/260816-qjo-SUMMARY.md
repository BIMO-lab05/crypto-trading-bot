---
phase: quick/260816-qjo
plan: 01
subsystem: trading-engine
tags: [portfolio-ledger, accounting, adr-010, adr-028, smart-router, res-03, res-04, res-05]
requires:
  - portfolios DDL total_value column (already present, schema.sql:176)
provides:
  - portfolios.total_value / total_pnl / unrealized_pnl maintained by the engine
  - deterministic close persistence ordering (CLOSED row before portfolio aggregate)
  - PAPER portfolio risk columns seeded from Settings per ADR-010 / ADR-028
  - operator-tunable smart-router small-order threshold
affects:
  - services/trading-engine/app/repositories.py
  - services/trading-engine/app/position_manager.py
  - services/trading-engine/app/database/models.py
  - services/trading-engine/app/config.py
  - services/trading-engine/app/execution/smart_router.py
tech-stack:
  added: []
  patterns:
    - correlated scalar subquery (SUM over status='OPEN') inside an UPDATE ... SET
    - chained persistence coroutine replacing two independent asyncio.create_task()s
    - lazy in-function Settings import to avoid a config/execution import cycle
key-files:
  created:
    - database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql
  modified:
    - services/trading-engine/app/database/models.py
    - services/trading-engine/app/repositories.py
    - services/trading-engine/app/position_manager.py
    - services/trading-engine/app/config.py
    - services/trading-engine/app/execution/smart_router.py
    - services/trading-engine/tests/unit/test_repositories.py
    - services/trading-engine/tests/test_accounting_invariants_phase1.py
    - services/trading-engine/tests/execution/test_smart_router.py
decisions:
  - "total_value = cash + open_unrealized, mirroring PaperTradingEngine.get_total_equity(); margin-exclusive by design"
  - "DDL defaults for risk_per_trade / max_daily_loss left at the LIVE-conservative 0.02 / 0.05; only the PAPER seeding path changes"
  - "Smart-router threshold wired in the factory, not the lifespan, because POST /execution/reset rebuilds through the factory"
metrics:
  tasks: 3
  commits: 3
  tests_added: 7
  tests_passing: 97
  completed: 2026-08-16
---

# Quick Task 260816-qjo: Fix RES-03 / RES-04 / RES-05 — portfolios display columns Summary

Three trading-engine audit defects repaired: the portfolio display columns are now written in the same UPDATE as `cash_balance` (and the close-path race that would have corrupted them is closed), new PAPER portfolio rows carry ADR-010/ADR-028 risk values, and the smart-router small-order threshold is operator-tunable.

## What Shipped

| Task | Commit | Requirement |
|---|---|---|
| 1 — maintain the display trio + serialize close persists | `277b4b9` | RES-03 |
| 2 — seed PAPER risk columns from Settings + repair SQL | `217a115` | RES-04 |
| 3 — smart-router threshold from Settings | `aefca0a` | RES-05 |

### RES-03 — the display columns were never maintained

`portfolios.total_value` was not ORM-mapped at all, so the engine *could not* write it; `total_pnl` was mapped and never assigned. Only `cash_balance` and `realized_pnl` ever moved.

- `Portfolio.total_value` mapped (`DECIMAL(20,8)`, `nullable=False`, `default=0`) and exposed in `to_dict()`.
- Both portfolio write paths (`record_position_close`, `update_balance`) now set `unrealized_pnl`, `total_value` and `total_pnl` **in the same UPDATE** as `cash_balance`, from a scalar subquery `SUM(unrealized_pnl) WHERE status='OPEN'`. One statement, so the four columns cannot disagree.
- `PositionRepository.close()` zeroes `unrealized_pnl` — a CLOSED row previously kept its last stale tick value forever.
- `update_balance`'s overwrite semantics are unchanged: `realized_pnl` is still written **only** when the param is supplied.

**Side effect worth recording:** the DDL declares `total_value NOT NULL` with no default. Because the column was unmapped, SQLAlchemy omitted it from every INSERT, so `get_or_create` could not create a portfolio row against the real schema at all. Mapping it repairs that latent INSERT failure.

### RES-03 — the close-path race was real, and is now proven closed

`close_position` fired two *independent* `asyncio.create_task` persistences in separate sessions with no ordering guarantee. Once the portfolio write derives an aggregate from `status='OPEN'` rows, a portfolio task that wins the race reads the just-closed position while it is still OPEN, carrying stale unrealized P&L — double-counted on top of the realized delta.

The two persists are now a single chained coroutine: `position_repo.close(...)` awaited first, `portfolio_repo.record_position_close(...)` in the matching `finally`. Failure behavior is preserved — the ledger write is still attempted if `close()` raises, and the exception still propagates to `_persist_done`. The `_cash_now` guard is preserved inside the `finally`, so a ledger write with `cash_balance=None` is impossible.

**The ordering test discriminates, rather than passing by luck.** As first written (plain `side_effect` appends) it passed against the *old* two-task code, because `create_task` schedules FIFO and AsyncMocks never yield. Adding an `await asyncio.sleep(0)` mid-write — which is what a real DB round trip does — made it fail against the old shape with `['ledger', 'close']`, the exact double-count ordering. It passes as `['close', 'ledger']` against the fix. This strengthening is within the plan's stated contract (`assert == ["close", "ledger"]`), it just drives it so the assertion can actually fail.

### RES-04 — risk columns seeded from Settings

`get_or_create` now seeds `risk_per_trade` from `settings.max_risk_per_trade` and `max_daily_loss` from `settings.max_daily_loss_pct / 100`.

**The units trap was handled and is asserted on values.** Both columns are `DECIMAL(5,4)` **fractions** (max representable 9.9999). `max_risk_per_trade` is already a fraction; `max_daily_loss_pct` is a **percent** (12.0) and is divided by 100 — unconverted it overflows the column outright. The test uses deliberately non-default settings (`0.07` / `9.0` → `Decimal("0.07")` / `Decimal("0.09")`), because the real defaults `0.10` / `0.12` are close enough that a wrong or missing transform can pass by luck. Asserting `add.assert_called_once()` would not have caught it: with mocks there is no DB to reject an out-of-range value.

DDL defaults are deliberately unchanged at the LIVE-conservative `0.02` / `0.05`.

### RES-05 — smart-router threshold operator-tunable

New Setting `smart_router_small_order_threshold_usd` (`default=1000.0`, `gt=0`, env key `SMART_ROUTER_SMALL_ORDER_THRESHOLD_USD`). `get_smart_router()` builds a settings-derived config **only when the caller passes none**, so an explicit config still wins. The dataclass default stays `1000.0`, pinned by a test.

Wired in the factory rather than the lifespan, verified against `handlers/execution_router.py:484-497`: `POST /api/v1/execution/reset` calls `reset_smart_router()` and the six `get_smart_router()` sites rebuild through the factory, so lifespan-only wiring would revert to the literal on the first reset. The Setting's description states it is a market-microstructure calibration and explicitly **not** an account-size figure, so a future capital-audit pass does not "fix" it to derive from equity.

## Verification

All host runs, from `services/trading-engine`, `--no-cov`, no env exports.

| Sweep | Baseline | After |
|---|---|---|
| 6-file regression sweep | 90 passed | **97 passed** (7 new) |
| `tests/unit/test_repositories.py` | 25 | 28 |
| `tests/execution/test_smart_router.py` | 38 | 41 |
| root `test_account_size_invariant` + `test_account_config_sync` | 26 | **26 passed** |

Zero failures, zero pre-existing failures to explain away.

Beyond the plan's checks, the UPDATE was compiled against the `postgresql` dialect to confirm the scalar subquery actually renders (mocks never compile a statement). All five columns appear in the `SET` clause with the subquery correctly scoped by `portfolio_id` and `status='OPEN'`.

Task-gate greps: `total_value` in comment-stripped `repositories.py` = **7** (≥2 required, both write paths); comment-stripped `UPDATE portfolios` in the repair SQL = **2**.

## Deviations from Plan

**None affecting behavior.** Two process notes:

1. **[Rule 3 — blocking] The PostToolUse format hook mangled `tests/execution/test_smart_router.py`** — a 45-line addition produced a 231/129-line diff and autoflake stripped `asyncio`, `timedelta` and `MagicMock` from the imports. Reverted with `git checkout -- <that one file>` and re-applied via Bash + `pathlib` exact replacement with `count == 1` asserts, per the task constraints. `app/execution/smart_router.py` was applied the same way pre-emptively (it uses aligned inline comments and is not black-formatted). The four already-black-formatted files took Edit cleanly. Every diff was grepped for `^[+-](import|from)` before testing; the only import change in the final commits is the deliberate `from types import SimpleNamespace` in `tests/unit/test_repositories.py`.

2. **One extra test beyond the plan's minimum** — `test_explicit_config_still_wins_over_settings`, guarding the `config is None` branch directly rather than relying on the pre-existing `test_get_smart_router_with_config`.

## Not Done — Out of Scope by Instruction

- **The repair SQL was written, never executed.** No SQL was run against the live DB. The orchestrator runs it, against a flat book (no OPEN positions), with the trading-engine container stopped — the preconditions are recorded in the file header.
- **No Docker rebuild, no service restart.** The running `crypto-bot-trading` container serves pre-change code. **No "working end-to-end" claim is made from these test results** (CLAUDE.md §7): green host tests are not runtime proof.
- `STATE.md` / `ROADMAP.md` not updated, per task constraints.

## Blast-Radius Checks (post-implementation review)

`update_balance` previously touched only `cash_balance`; it now stamps the aggregate trio on **every** call. Two things were checked because "maintained with a plausible wrong number" would be worse for an operator than "never maintained":

1. **Aggregate freshness — bounded to one monitoring tick.** `positions.unrealized_pnl` is persisted for OPEN rows by `PositionRepository.update_price`, driven from `PositionManager.update_position_price` (`position_manager.py:394-425`) on every price update. The `SUM(...) WHERE status='OPEN'` is therefore at most one tick stale, not unbounded. That is inherent to any DB-persisted equity figure and matches the in-memory definition it mirrors.
2. **No boot-time caller.** `update_balance` has exactly two callers, both in `paper_trading.py` — the partial-exit cash snapshot (`:416`) and the scale-in cash snapshot (`:501`). In both the position is genuinely still OPEN, so including its unrealized P&L is intended. The restart balance-restore path (`paper_trading.py:176-187`) does **not** call it, so no aggregate is written before `load_positions_from_db` has hydrated the book.

**Known narrow interaction, left as the plan specifies:** in the chained close persistence, if `position_repo.close()` raises **and** `record_position_close()` also raises inside the `finally`, Python discards the first exception and only the ledger failure reaches `_persist_done`. Under the old two-task shape both would have been logged independently. This requires both legs to fail at once. It is left as-is deliberately: the plan prescribes exactly this try/finally shape, and the fix constraints cap this task at three commits on a branch shared with a concurrent executor, where amending history is prohibited. Worth a one-line follow-up (wrap the `finally` body's await in its own log-and-swallow `except`) if the close path ever starts failing in practice.

## Findings Flagged, Not Fixed

| ID | Finding | Evidence |
|---|---|---|
| RES-05 sibling | A third `small_order_threshold: float = 1000.0` literal lives in `app/execution/execution_optimizer.py:176`, untouched. `app/execution/smart_order_router.py` is a dead duplicate class and was also left alone. | verified 2026-08-16 |
| **RES-06 candidate** | `PaperTradingEngine.get_total_equity()` (`paper_trading.py:209-214`) returns `balance + unrealized_pnl` and never adds back `posted_margin`, which is debited from cash at open. **Every equity surface in the engine understates while positions are open** — kill switch, `/performance`, frontend, and now the DB. The DB deliberately adopted the same margin-exclusive definition rather than becoming the only surface that disagrees; the two must move together when this is fixed. | verified 2026-08-16 |

## Known Stubs

None. No placeholder values, empty collections, or unwired data paths were introduced.

## Threat Flags

None. No new network endpoint, auth path, or trust-boundary surface was introduced. The one new externally-controlled input (`SMART_ROUTER_SMALL_ORDER_THRESHOLD_USD`) is bounded by `gt=0` and can only degrade execution quality — it cannot cause an order that risk checks would otherwise reject (register row T-qjo-05, disposition `accept`).

## Self-Check: PASSED

- `database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql` — FOUND
- Commits `277b4b9`, `217a115`, `aefca0a` — all FOUND in `git log`, in plan order
- Commits touch exactly the 9 paths declared in the plan frontmatter (the plan's `<verification>` prose says "8"; the frontmatter `files_modified` list is 9, and that is what was committed). No unrelated files swept in, and **no files under `services/market-data-service/`** (the concurrent executor's directory) were touched
- `git diff --diff-filter=D` across all three commits — zero deletions
- Ordering test re-run in isolation post-fix — 1 passed (the `['close', 'ledger']` claim is verified, not inferred from the suite total)
