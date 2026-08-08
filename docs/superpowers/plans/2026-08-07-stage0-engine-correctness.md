# Stage 0 — Engine Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the paper engine size positions off a truthful cash ledger and record honestly *why* each position closed, so that any later measurement of strategy edge is trustworthy.

**Architecture:** Three independent repairs against `services/trading-engine`. (1) Margin becomes a **persisted per-position dollar amount** posted at open and consumed proportionally at close, replacing a global `settings.default_leverage` re-read at close time. (2) A new `ExitKind` enum rides `OrderBase` into a new nullable `positions.exit_kind` column, alongside — not replacing — the existing prose `exit_reason`. (3) The ensemble entry path applies the strategy's own stop/target and enforces the five risk gates it currently skips. Schema lands first (migration 008), behavior second, the one-time cash repair last and only once the delta is fully explained.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Pydantic v2 (2.13.3), Decimal money arithmetic, raw-SQL migrations (no Alembic), pytest with `asyncio_mode=auto`, PostgreSQL 15 (`cryptobot` database in container `crypto-bot-postgres`).

## Global Constraints

- **Account is $100.** Never write an account-size literal. Inside `services/*/app/**` read the service's own `Settings`; **never `import shared.account`** (repo-root `shared/` is outside the Docker build context — `services/trading-engine/Dockerfile` does `COPY app/ ./app/` and `RUN mkdir -p ./shared` creates an *empty* directory).
- **Test invocation** is exactly: `cd services/trading-engine && python3 -m pytest <paths> --no-cov -q`. Do **not** prefix `MAX_TOTAL_EXPOSURE_PCT=` / `PAPER_INITIAL_BALANCE=` — that workaround was retired 2026-08-04 and exporting env vars now *corrupts* Dict settings (pydantic-settings v2 deep-merges `Dict` fields, so `SYMBOL_ALLOCATIONS` unions instead of replacing and sums to 1.25). `tests/conftest.py:56` sets `Settings.model_config["env_file"] = None` at import time.
- **`--no-cov` is mandatory** — `services/trading-engine/pytest.ini` injects `--cov=app --strict-config`.
- **`@pytest.mark.golden` is a collection error here.** It is registered only in the repo-root `pytest.ini`; the service `pytest.ini` uses `--strict-markers`. Available markers: `unit, integration, stat_arb, validation, grid_trading, slow, api` (pytest.ini) + `benchmark` (conftest) + `asyncio`.
- **Never run `git status` bare or `git add -A`** — it exceeds 60s on this 3.2 GB NTFS/WSL mount. Enumerate paths. Commit with an explicit pathspec: `git commit -m "..." -- path1 path2`.
- **Money is `Decimal`.** Convert float settings at the boundary with exactly `Decimal(str(self.settings.<x>))`. Never `Decimal(float)`.
- **Persistence is fire-and-forget** via `_spawn_persist` / `_spawn_trade_log`. Any test asserting on a repository call must `await _drain_tasks()` first.
- **Do not `xfail`/`skip` a failing test to green a suite.** If a skip is unavoidable its reason must name a tracking ID.
- **Known-good baseline — MEASURED 2026-08-08, supersedes the stale figure this plan first carried.** The full host suite is **1638 passed / 36 failed / 795 skipped**. The "13 failed" figure came from `progress.md` dated 2026-08-05, before the Phase 1 merge; it is obsolete.
  **Do not gate on the count.** Most of the 36 are cross-test pollution, not defects: `tests/unit/test_repositories.py` fails 18-21 in a whole-suite run and passes **21/21 in isolation**; `tests/unit/test_signal_cache.py` likewise passes **33/33 alone**. The mechanism is singleton leakage — `test_accounting_fixes` installs `_AsyncNoop` / `_FakeRepoClasses` objects that survive into later modules' `get_*_repository()` calls.
  **The criterion is therefore structural, not numeric:** (a) no NEW failure *family* — no failing file that was not already failing; and (b) every file your change touches passes **in isolation**. A raw count is gameable and drifts with unrelated work.
- **Branch:** `feature/engine-repair-edge-search` (already exists, holds the design spec at `eb7c3ee`).
- **The auto-trader is HALTED** (`safety/EMERGENCY_STOP`, created 2026-08-07 16:55). It must stay halted until Task 4 completes. Resuming takes two steps: `rm safety/EMERGENCY_STOP` then `POST /api/trading/start`.

## Verified interface facts (read before any task; source of truth for signatures)

**Live ledger state, measured 2026-08-07 18:00 UTC** — re-measure at Task 1, it drifts on every close:
- `portfolios`: one row, `portfolio_id='paper_trading'`, `initial_balance=100.00000000`, `cash_balance=255.97305338`, `realized_pnl=-0.41002416`, `updated_at=2026-08-07 15:00:55.18326`.
- `SUM(positions.realized_pnl)` over **all** rows = `−0.28337306`; over CLOSED only = `−0.41002416`. The `+0.1266511` gap is position 64's partial exit, accrued onto a still-OPEN row.
- Coherent value = `100 − 0.28337306 − 20.63558` (open posted margin at 1x) `− 0.01134957` (unconsumed entry fee) `≈ 79.07`. **Break ≈ +$176.90.**
- Invariant C holds exactly: `portfolios.realized_pnl == SUM(positions.realized_pnl WHERE status='CLOSED') == -0.41002416`. **P&L is clean; cash alone is corrupt.** Note this invariant is *narrower* than the cash identity — it deliberately excludes open-position partial realized, which is exactly why the repair must not key on `portfolios.realized_pnl`.
- Open positions: id 61 BNBUSDT SHORT (`quantity=0.01`, `remaining_quantity=0.01`, `entry_price=602.69`, notional $6.0269) and id 64 SOLUSDT LONG (`quantity=0.30`, `remaining_quantity=0.201`, `entry_price=72.68`, remaining notional $14.6087). Both opened post-leverage-flip, i.e. at 1x.
- 19 positions total, **all** `strategy='ensemble'`.

**Leverage — exactly 4 non-test read sites repo-wide** (`settings.default_leverage`):
- `paper_trading.py:95` (`_open_position_cost`, restart reconstruction) and `paper_trading.py:253` (`execute_market_order`) — **these two must stop reading the global.**
- `auto_trader.py:2012` (research/hybrid sizing) and `auto_trader.py:4412` (ensemble sizing) — **these are correct**; they are the *capture* points where the value to stamp is computed.
- Four arithmetic uses of the `paper_trading.py:253` local: `:325` (`margin_returned` on close/reduce), `:407` (scale-in `margin_required`), `:447` (open `margin_required`), plus log strings at `:461` and `:479`.
- `auto_trader` gates leverage on `if self.settings.leverage_enabled:`; `paper_trading.py` does **not**. Container env is `LEVERAGE_ENABLED=true, DEFAULT_LEVERAGE=1.0`, so they agree today. Storing posted margin removes the disagreement permanently.
- `config.py:614` `leverage_enabled: bool = Field(default=False, ...)`, `:617` `default_leverage: float = Field(default=1.0, ge=1.0, le=100.0, ...)`, `:623` `max_leverage: float = 20.0`, `:626` `min_leverage: float = 1.0`. All are `float`.

**Why posted margin, not a leverage ratio:** `PositionManager.scale_in` (`position_manager.py:616-619`) rewrites `entry_price` to a weighted average. The close credit is `entry_price × close_qty / L`, so a single stored ratio only reconciles if every leg used the same leverage. A dollar amount that is consumed proportionally is immune to both entry-price averaging and to any future `DEFAULT_LEVERAGE` change. `leverage` is stored **additionally**, for audit and for migration-backfill honesty — nothing reads it arithmetically.

**Four hand-written mappers.** There is no `model_dump()` propagation and no `from_orm` anywhere — `model_config=ConfigDict(from_attributes=True)` is declared on `Position` but `model_validate` is never called. A new column added to only the model + the table is a **silent no-op**. All four must be edited:
1. `repositories.py:63-85` — `PositionRepository.create`, domain→ORM (the only INSERT).
2. `handlers/trades.py:29-56` — `db_position_to_app_position`, ORM→domain for the trade-history API.
3. `position_manager.py:853-878` — inside `load_positions_from_db`, ORM→domain at restart.
4. `database/models.py:175` — ORM `Position.to_dict`.

Proof the risk is real: `positions.entry_signal_confidence` is declared at `database/models.py:145`, the domain model carries it, the paper engine passes it into `create_position` — and `repositories.py` contains **zero** references to it. It is NULL on all 19 live rows.

**`OrderCreate` cannot carry new fields, and will not tell you.** Neither `OrderBase` nor `OrderCreate` declares a `model_config`, so pydantic v2's default `extra='ignore'` applies — passing an undeclared kwarg is silently dropped with **no `ValidationError`** (verified on the installed pydantic 2.13.3). Worse, `paper_trading.py:255` does `Order(**order.model_dump(), ...)` and `Order` inherits **`OrderBase`**, not `OrderCreate` — so any field added to `OrderCreate` alone vanishes at that line. **New order fields go on `OrderBase`.**

**`set_position_stops` (`position_manager.py:778-830`) is synchronous and MEMORY-ONLY.** Its body mutates the in-memory `Position` and returns. There is no `_spawn_persist`, no repository call. `PositionRepository`'s complete method list is `create, update_price, close, record_reduction, record_scale_in, get_by_id, get_open_positions, get_closed_positions` — **there is no update-stops method.** `stop_loss` reaches the database at exactly one line repo-wide: `repositories.py:73`, inside `create()`. Consequence: copying the `_execute_trade_with_setup:2383` pattern gives stops that look right in memory and silently revert to the risk-manager default on the next restart, because `load_positions_from_db` re-reads the un-updated create-time value.

**Stops are not absent — they are wrong.** `paper_trading.py:464-472` calls `create_position(...)` with no `stop_loss`/`take_profit`; `position_manager.py:178-182` then substitutes `risk_manager.calculate_stop_loss/calculate_take_profit`, which derive from `settings.default_stop_loss_pct` (config.py:386, 2.0) and `default_take_profit_pct` (config.py:392, 4.0). All 19 live rows carry non-NULL stops: the open SOLUSDT row is entry `72.68` / SL `71.2264` / TP `75.5872` = exactly `×0.98` and `×1.04`.

**`min_signal_confidence` gates nothing on any autonomous path.** `config.py:408`, default `0.30`. Read in exactly one function, `RiskManager.validate_signal` (`risk_manager.py:284`, check at `:308`), whose sole production caller is `handlers/signals.py:395` — the REST `/signal` endpoint. `auto_trader.py` calls only `risk_mgr.should_halt_trading()`. Live evidence: `trades.signal_confidence` on ensemble entry legs reads `0.3804, 0.2995, 0.2680, 0.2818, 0.2960, 0.2357, 0.1730, 0.2695` — seven of eight below the floor.

**Five gates the ensemble path skips** (`_check_and_trade_ensemble`, `auto_trader.py:4329-4560`; the dispatch site at `:954-969` applies none of them either — it only checks `circuit_breaker.can_execute()`):
| Gate | Defined at | Async? |
|---|---|---|
| `_claim_open_slot` / `_release_open_slot` | `:1661-1781` | **async** / sync |
| `_check_daily_trade_limit` | `:1419-1440` | sync |
| `portfolio_heat_manager.can_open_trade` | `trading_enhancements/portfolio_heat.py:458` | sync |
| `allowed_trade_sides` / `short_trading_enabled` / `short_min_confidence` block | `:3895-3934` | sync |
| `min_signal_confidence` | `risk_manager.py:284` | sync |

`_snap_quantity_to_step` and `_passes_min_notional` **are** async and already called by the ensemble path. `_passes_exposure_gate` is sync. `set_position_stops` is sync — do not `await` it.

**`_claim_open_slot` already does `self.total_trades_rejected += 1` internally** before returning False. The ensemble path increments at each call site. Adding a naive `if not await self._claim_open_slot(...): self.total_trades_rejected += 1; return` double-counts. It also needs a matching `_release_open_slot` in a `finally` — `_check_and_trade_ensemble` has **8 early returns**.

**`EnsembleSignal.stop_loss` / `.take_profit` are required non-optional floats** (`strategies/multi_strategy_ensemble.py:38-51`), inherited verbatim from whichever leg had the largest absolute contribution (`:277-284`), never recomputed. **Nothing validates the stop is on the correct side of entry for the chosen action** — a weighted-vote BUY whose dominant leg fired SELL yields an inverted SL/TP. Precedent: the Jan 2026 inverted-R/R bug (`380a674`). A side-consistency assertion is mandatory.

**Two divergent substring predicates over one string:**
- `auto_trader.py:2883` routes limit-vs-market close on `"stop" in reason.lower() or "loss" in reason.lower()`.
- `auto_trader.py:3073` arms the SL cooldown on `"stop"` or `"loss"` **or `"max_hold"`**.
Producers: `position_manager.py:731-776` emits `"Stop loss triggered"`, `"Trailing stop triggered"` (both match), `"Take profit triggered"`, `"TP3 - Full exit"` (neither matches). `auto_trader.py:2583-2595` emits `"MAX_HOLD_TIME_EXCEEDED (49.0h > 48h)"`. Max-hold's current escape from the `:2883` predicate is that `_check_position_hold_time` calls `_close_position` directly.

**In PAPER mode the routed reason never reaches the database.** The persisted value is synthesized at `paper_trading.py:343-345` from `order.side` + `target.side` + `order.strategy`. All 17 non-null live values are one of four strings, e.g. `Market sell order (LONG close) [auto_close]`. LIVE is asymmetric: `live_trading.py:483` passes the routed reason straight through. `LiveTradingEngine.close_position` has a default `reason: str = "manual"` (`live_trading.py:431`).

**`check_all_exit_conditions` returns reason strings for NON-exits too** — `'Position not found'` (`:752`), `'Position not open'` (`:755`), `'No exit conditions met'` (`:776`). An `ExitKind` cannot model these; the diagnostic channel must stay separate from the exit channel.

**Migrations:** raw SQL, **no Alembic anywhere** (zero `alembic.ini`, zero `versions/`, zero `env.py`; `alembic` is an unused pin in 6 requirements files). Authoritative directory is repo-root `database/migrations/`; highest is `007_position_fee_partial_exit_accounting.sql`, so **008 is next**. `services/trading-engine/database/` does not exist. `infrastructure/migrations/` is a separate chain (highest 005) — do not merge them mentally. No tracking table: `database/scripts/setup_database.sh` globs `$MIGRATIONS_DIR/*.sql` non-recursively and re-applies everything, so **idempotency guards are the only safety net**. One-time repairs live in `database/migrations/one_time_repairs/` (date-named), which the glob does not reach.

**The ORM has already drifted from the live schema** — generate 008 from `\d positions`, not from `database/models.py`. Live PK is `id integer NOT NULL DEFAULT nextval('positions_id_seq')` with `position_id uuid` as a UNIQUE CONSTRAINT, while the ORM declares `position_id` as PK; live `strategy` is `varchar(100)` vs ORM `String(50)`; live timestamps are `timestamp WITHOUT time zone` vs ORM `DateTime(timezone=True)`. `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is safe against this; anything touching keys or types is not.

**`docker-compose.unified.yml` mounts only 007 into `initdb.d`** (line 63, as `05-position-fee-accounting.sql`). `initdb.d` runs only on a **fresh volume**. A new 008 needs a matching mount or `down -v && up` yields a schema the ORM cannot insert against.

**ORM enum-storage convention:** `String(N)` + a `CheckConstraint` listing literals — never a PG `ENUM` type. Note the existing precedent for drift: the `trades.order_type` CHECK allows `('MARKET','LIMIT','STOP','STOP_LIMIT')` while `OrderType` is `MARKET/LIMIT/STOP_LOSS/TAKE_PROFIT` — they already disagree. **Do not add a CHECK constraint that can disagree with the enum.**

**Tests that assert current behavior and WILL break** (budget the edits into the same commit):
- `tests/unit/test_restart_balance_restore.py` — module constant `LEVERAGE = Decimal("10")` (`:24`), `_engine()` builds via `PaperTradingEngine.__new__` and sets `engine.settings = SimpleNamespace(default_leverage=float(LEVERAGE))` (`:45`), `_position()` (`:28-37`) returns a `SimpleNamespace` with **no** `posted_margin`. 3 of 4 tests break. Needs the whole `_position`/`_engine` fixture pair rewritten.
- `tests/standalone/test_accounting_fixes.py:99` — `fresh_engine(leverage=...)` assigns `engine.settings.default_leverage`.
- `tests/test_sizing_caps_phase1.py:450` (`assert order.strategy == "stop_loss_limit"`), `:478-487`, `:511-523` (literal `"MAX_HOLD_TIME_EXCEEDED (49.0h > 48h)"`), `:526-535` (contrast case `"Take profit TP3 hit"` must NOT arm cooldown), `:543`.
- `tests/test_accounting_invariants_phase1.py:161` reads `engine.settings.default_leverage`, asserting round-trip conservation at `~:195`.

**`tests/integration/conftest.py` is a BAD template** — session-scoped `event_loop` fixture the root conftest deliberately removed, `db_manager.init_async_engine()` (needs live Postgres), hardcoded `Decimal("10000.00")`, and a `test_settings` fixture that mutates the `get_settings()` singleton in place and leaks across tests. Never copy `mock_settings` from `tests/unit/test_paper_trading.py:46` either — line 50 sets `paper_commission_pct = 0.1`, the pre-audit rate.

**Deferred/lazy imports must be monkeypatched on the MODULE OBJECT, not a dotted string.** The autouse `mock_database_connection` fixture's `patch.dict("sys.modules", ...)` teardown evicts modules first imported during a test. See `tests/test_sizing_caps_phase1.py:189-196`. Also pre-import `app.main` and `app.core.metrics` at module scope in any test touching prometheus-instrumented paths, or Counter re-registration raises `Duplicated timeseries in CollectorRegistry`.

**Out of scope, state it explicitly so it is neither missed nor over-scoped:** the separate exit vocabularies in `backtesting/backtest_engine.py:95`, `strategies/backtester.py:88`, `strategies/grid_trading_strategy*.py` (`grid_level_hit`, `grid_stop_loss`, `emergency_exit`), and `strategies/backtesting/strategy_base.py`. Also out of scope: partial-exit `ExitKind` (owner decision 2026-08-07 — full closes only), `PaperTradingEngine.can_open_position` (dead code — its only route `main.py:901` dispatches to `handlers/correlation.py:169`), and the ORM `Trade` class (dead — `repositories.py:385` documents that all writes go through raw SQL at `:438-460`).

---

### Task 1: Reconcile the cash break before touching the ledger

Owner decision 2026-08-07: *reconcile first, then repair*. `AUDIT.md §8.1` (2026-08-05) declined a repair at the $4.23 magnitude; there is no ruling at $177, and a repair cannot be written against an unexplained delta. This task writes **no application code**.

**Files:**
- Create: `.planning/evidence/cash-ledger-reconciliation-2026-08-07.md`

**Interfaces:**
- Consumes: nothing.
- Produces: a committed evidence file containing (a) the re-measured live figures, (b) a line-by-line reconstruction that accounts for the delta to within $0.01, (c) the exact `UPDATE` statement Task 4 will run, and (d) an explicit `RECONCILED` or `UNRECONCILED` verdict on its first line. Task 4 is gated on `RECONCILED`.

- [ ] **Step 1: Re-measure the live ledger**

```bash
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT initial_balance, cash_balance, realized_pnl, updated_at FROM portfolios;"

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT id, symbol, side, status, quantity, remaining_quantity, entry_price,
       ROUND(COALESCE(remaining_quantity, quantity) * entry_price, 8) AS rem_notional,
       entry_fee, exit_fee, realized_pnl, opened_at, closed_at
FROM positions ORDER BY id;"

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT symbol, side, quantity, price, fee, realized_pnl, strategy, executed_at
FROM trades ORDER BY executed_at;"
```

Record all three outputs verbatim in the evidence file. The auto-trader is halted, so these are stable.

- [ ] **Step 2: Pin the leverage-flip instant**

The compose comment dates the `DEFAULT_LEVERAGE` 10.0→1.0 change to 2026-08-04, but that is when the file changed, not when the running container adopted it. Row data bounds it to `2026-08-04 14:10` .. `2026-08-06 01:30`: the 14:10:25–14:10:33 batch opened BTC $95.77 + ETH $86.10 + SOL $76.75 + BNB $69.65 = $328 notional against a then-balance near $79 — unreachable at 1x under `max_position_size_pct=10.0`. Positions from 2026-08-06 onward ($23.58, $17.20, $21.80) are consistent with 1x.

Narrow it from the container's own logs — the open path logs `({leverage}x leverage)` at `paper_trading.py:461`:

```bash
docker logs crypto-bot-trading --since 2026-08-04T00:00:00 2>&1 | grep -E "x leverage" | head -40
docker inspect crypto-bot-trading --format '{{.State.StartedAt}} {{.RestartCount}}'
```

Record the tightest bound achieved. If the logs have rolled, say so and keep the row-derived bound.

- [ ] **Step 3: Reconstruct the delta arithmetically**

Build a per-close table. For each position closed after the flip that was opened before it, the over-credit is `entry_price × close_qty × (1/L_close − 1/L_open)` = `notional × 0.9` at `L_open=10, L_close=1`. Then subtract the restart re-debits: every `sync_balance_with_positions` run re-derives cash as `persisted_cash − _open_position_cost(positions opened after portfolios.updated_at)`, and `_open_position_cost` also used the *current* global leverage.

State plainly whether the reconstruction closes. The naive over-credit from the four pre-flip positions (~$295 at 0.9× notional) does **not** equal the observed +$177 without modelling those re-debits — that arithmetic has never been done, and doing it is the point of this task.

- [ ] **Step 4: Write the verdict and the repair statement**

First line of the file must be exactly `VERDICT: RECONCILED` or `VERDICT: UNRECONCILED`, followed by the residual in dollars. Then the proposed statement, with the *current* measured numbers substituted (do not copy these figures — re-derive them in Step 1):

```sql
-- Coherent cash = initial_balance
--               + SUM(realized_pnl over ALL positions)      <- not just CLOSED
--               - SUM(posted_margin on OPEN)
--               - SUM(unconsumed entry fee on OPEN)         <- not optional
UPDATE portfolios
SET cash_balance = <computed>,
    updated_at = NOW()
WHERE portfolio_id = 'paper_trading';
```

Both of the non-obvious terms matter on the current data. `portfolios.realized_pnl` reads
`−0.41002416` while `SUM(realized_pnl)` over all positions is `−0.28337306` — the
`+0.1266511` gap is position 64's partial exit, which accrued onto a still-OPEN row and
which `record_position_close` therefore never wrote. And the two open rows carry
`entry_fee` of `0.00331480` (pos 61, fully unconsumed) and `0.01199220 × 0.201/0.30`
(pos 64, partially consumed) that left cash at open but is not yet in any realized figure.

If the verdict is `UNRECONCILED`, the file must state the residual and stop. Do not proceed to Task 4; report to the owner instead.

- [ ] **Step 5: Commit**

```bash
git add .planning/evidence/cash-ledger-reconciliation-2026-08-07.md
git commit -m "docs(evidence): reconcile the paper cash-ledger break before repair" -- .planning/evidence/cash-ledger-reconciliation-2026-08-07.md
```

---

### Task 2: Migration 008 + ORM columns + all four mappers (schema only, no behavior change)

Adds `positions.posted_margin`, `positions.leverage` and `positions.exit_kind`. After this task the columns exist and round-trip, but nothing reads them arithmetically — the engine still behaves exactly as before. That is deliberate: it makes Task 3 a pure behavior diff.

**Files:**
- Create: `database/migrations/008_position_margin_leverage_exit_kind.sql`
- Modify: `services/trading-engine/app/database/models.py` (Position columns after `exit_fee` at `:133`; `to_dict` at `:175`)
- Modify: `services/trading-engine/app/models/enums.py` (append after line 64)
- Modify: `services/trading-engine/app/models/position.py` (`PositionBase`, `:19-49`)
- Modify: `services/trading-engine/app/repositories.py` (`create` `:63-85`; `close` `:129-182`)
- Modify: `services/trading-engine/app/handlers/trades.py` (`db_position_to_app_position` `:29-56`)
- Modify: `services/trading-engine/app/position_manager.py` (`load_positions_from_db` mapper `:853-878`)
- Modify: `docker-compose.unified.yml` (initdb.d mounts, near line 63)
- Test: `services/trading-engine/tests/test_stage0_schema.py` (new)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `app.models.enums.ExitKind(str, Enum)` with members `HARD_STOP, TRAILING_STOP, TAKE_PROFIT, MAX_HOLD, MANUAL, SIGNAL_REVERSAL, LIQUIDATION` (values equal names).
  - `Position.posted_margin: Decimal` (default `Decimal("0")`), `Position.leverage: Decimal` (default `Decimal("1")`), `Position.exit_kind: Optional[ExitKind]` (default `None`) on `PositionBase`, so `PositionCreate` inherits them.
  - `PositionRepository.create(position, portfolio_id="paper_trading", entry_fee=Decimal("0"))` now persists `posted_margin`, `leverage` and `entry_signal_confidence` from the domain object.
  - `PositionRepository.close(..., exit_kind: Optional[str] = None)`.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_stage0_schema.py`:

```python
"""
Stage 0 schema task: posted_margin / leverage / exit_kind must round-trip
through every one of the four hand-written mappers.

Regression target: positions.entry_signal_confidence has existed as a column
since before migration 007 and is NULL on all 19 live rows, because
PositionRepository.create never mapped it. A column added to the model and the
table but not to the mappers is a silent no-op.
"""

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.handlers.trades import db_position_to_app_position
from app.models.enums import ExitKind, PositionSide, PositionStatus
from app.models.position import Position


def _db_row(**overrides):
    """A stand-in for a SQLAlchemy DBPosition row."""
    row = MagicMock()
    row.position_id = uuid4()
    row.symbol = "SOLUSDT"
    row.side = "LONG"
    row.quantity = Decimal("0.30")
    row.remaining_quantity = Decimal("0.201")
    row.entry_price = Decimal("72.68")
    row.current_price = Decimal("74.00")
    row.exit_price = None
    row.stop_loss = Decimal("71.2264")
    row.take_profit = Decimal("75.5872")
    row.status = "OPEN"
    row.strategy = "ensemble"
    row.opened_at = None
    row.closed_at = None
    row.unrealized_pnl = Decimal("0")
    row.realized_pnl = Decimal("0")
    row.exit_reason = None
    row.entry_fee = Decimal("0.012")
    row.exit_fee = Decimal("0")
    row.posted_margin = Decimal("21.804")
    row.leverage = Decimal("1")
    row.exit_kind = None
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def test_exit_kind_members_are_name_valued():
    for member in ExitKind:
        assert member.value == member.name, f"{member!r} value must equal its name"
    assert ExitKind.HARD_STOP.value == "HARD_STOP"
    assert ExitKind.MAX_HOLD.value == "MAX_HOLD"


def test_position_model_carries_margin_leverage_exit_kind():
    pos = Position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("72.68"),
        quantity=Decimal("0.30"),
        posted_margin=Decimal("21.804"),
        leverage=Decimal("1"),
    )
    assert pos.posted_margin == Decimal("21.804")
    assert pos.leverage == Decimal("1")
    assert pos.exit_kind is None


def test_position_model_defaults_are_safe():
    pos = Position(
        symbol="BNBUSDT",
        side=PositionSide.SHORT,
        entry_price=Decimal("602.69"),
        quantity=Decimal("0.01"),
    )
    assert pos.posted_margin == Decimal("0")
    assert pos.leverage == Decimal("1")


def test_trade_history_mapper_carries_the_new_fields():
    """MAPPER 2 — handlers/trades.db_position_to_app_position."""
    row = _db_row(status="CLOSED", exit_kind="HARD_STOP", exit_price=Decimal("71.2264"))
    pos = db_position_to_app_position(row)
    assert pos.posted_margin == Decimal("21.804")
    assert pos.leverage == Decimal("1")
    assert pos.exit_kind == ExitKind.HARD_STOP


def test_trade_history_mapper_tolerates_nulls_on_legacy_rows():
    """The 17 pre-existing closed rows have NULL exit_kind and (pre-008) no margin."""
    row = _db_row(status="CLOSED", exit_kind=None, posted_margin=None, leverage=None)
    pos = db_position_to_app_position(row)
    assert pos.exit_kind is None
    assert pos.posted_margin == Decimal("0")
    assert pos.leverage == Decimal("1")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_stage0_schema.py --no-cov -q`
Expected: FAIL — `ImportError: cannot import name 'ExitKind' from 'app.models.enums'`.

- [ ] **Step 3: Append `ExitKind` to the enums module**

`services/trading-engine/app/models/enums.py` currently ends at line 64 with `TradingMode`. Append, matching the file's uniform `class X(str, Enum)` + name-equals-value convention:

```python


class ExitKind(str, Enum):
    """
    Why a position was closed (Stage 0, 2026-08-07).

    Replaces substring-matching over a free-text reason string. The two live
    predicates disagreed with each other (auto_trader.py:2883 tests
    "stop"/"loss"; :3073 also tests "max_hold"), and in PAPER mode neither
    string ever reached the database — positions.exit_reason was synthesized
    from order.side + order.strategy at paper_trading.py:343.

    Persisted to positions.exit_kind ALONGSIDE the prose exit_reason, which is
    left untouched: exit_reason is API-visible via TradeHistoryResponse, and
    the 17 existing rows are not backfilled.

    Full closes only. Partial exits (TP1/TP2/partial_profit_taker) survive in
    trades.strategy and are out of scope (owner decision 2026-08-07).
    """
    HARD_STOP = "HARD_STOP"
    TRAILING_STOP = "TRAILING_STOP"
    TAKE_PROFIT = "TAKE_PROFIT"
    MAX_HOLD = "MAX_HOLD"
    MANUAL = "MANUAL"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    LIQUIDATION = "LIQUIDATION"
```

Then export it. Check `services/trading-engine/app/models/__init__.py` for an `__all__`/import block listing the other enums and add `ExitKind` in the same style:

```bash
grep -n "TradingMode\|TimeInForce" services/trading-engine/app/models/__init__.py
```

- [ ] **Step 4: Add the fields to `PositionBase`**

In `services/trading-engine/app/models/position.py`, inside `class PositionBase(BaseModel)` (line 19), after the existing fields and matching their `Field(default=..., description=...)` style:

```python
    # Stage 0 (2026-08-07): margin is a per-position DOLLAR amount posted at
    # open and consumed proportionally at close. It replaces re-reading the
    # global settings.default_leverage at close time, which credited back
    # margin at whatever leverage was configured *then* — a 10x position
    # closed after DEFAULT_LEVERAGE dropped to 1.0 returned 10x what it
    # posted. A dollar amount is also immune to scale_in's entry_price
    # averaging, which a stored leverage RATIO is not.
    posted_margin: Decimal = Field(
        default=Decimal("0"),
        description="Margin currently posted and not yet returned, quote currency",
    )
    leverage: Decimal = Field(
        default=Decimal("1"),
        description="Leverage in force when this position opened (audit only; "
                    "no arithmetic reads this — posted_margin is authoritative)",
    )
    exit_kind: Optional[ExitKind] = Field(
        default=None,
        description="Structured close reason; None while OPEN and on pre-008 rows",
    )
```

Add `ExitKind` to the existing enum import at the top of the file (it already imports `PositionSide`/`PositionStatus` from `app.models.enums`).

`PositionUpdate` does **not** inherit `PositionBase` — leave it alone; nothing in this plan updates these fields through it.

- [ ] **Step 5: Add the ORM columns**

In `services/trading-engine/app/database/models.py`, in `class Position(Base)`, immediately after the `entry_fee`/`exit_fee` block at line 133, matching that block's inline-comment-citing-the-migration convention:

```python
    # Added by migration 008 (2026-08-07, Stage 0). posted_margin is the
    # dollar margin still posted; leverage is recorded for audit only.
    # exit_kind is a structured close reason stored ALONGSIDE the free-text
    # exit_reason, which is left untouched (API-visible, not backfilled).
    # No CheckConstraint on exit_kind deliberately: trades.order_type already
    # carries a CHECK that disagrees with its enum, and a stale CHECK rejects
    # valid writes.
    posted_margin = Column(DECIMAL(20, 8), nullable=False, default=0)
    leverage = Column(DECIMAL(10, 4), nullable=False, default=1)
    exit_kind = Column(String(30), nullable=True)
```

And in `to_dict` (line 175), following the `entry_fee` idiom exactly:

```python
            "posted_margin": float(self.posted_margin) if self.posted_margin is not None else 0.0,
            "leverage": float(self.leverage) if self.leverage is not None else 1.0,
            "exit_kind": self.exit_kind,
```

- [ ] **Step 6: Edit mapper 1 — `PositionRepository.create`**

In `services/trading-engine/app/repositories.py`, inside the `DBPosition(...)` constructor at `:63-85`, after `exit_fee=Decimal("0"),`:

```python
                    posted_margin=position.posted_margin,
                    leverage=position.leverage,
                    # Pre-existing gap fixed here: the column has existed since
                    # before 007 and was NULL on all 19 live rows because this
                    # mapper never wrote it.
                    entry_signal_confidence=position.entry_signal_confidence,
```

- [ ] **Step 7: Edit mapper 2 — `db_position_to_app_position`**

In `services/trading-engine/app/handlers/trades.py`, inside the `return Position(...)` at `:39-56`, after `exit_reason=db_pos.exit_reason`:

```python
        exit_reason=db_pos.exit_reason,
        posted_margin=Decimal(str(db_pos.posted_margin)) if db_pos.posted_margin is not None else Decimal("0"),
        leverage=Decimal(str(db_pos.leverage)) if db_pos.leverage is not None else Decimal("1"),
        exit_kind=ExitKind(db_pos.exit_kind) if db_pos.exit_kind else None,
```

Add `ExitKind` to the `app.models.enums` import at the top of the file.

- [ ] **Step 8: Edit mapper 3 — the restart hydrator**

In `services/trading-engine/app/position_manager.py`, inside the `Position(...)` construction in `load_positions_from_db` (the block ending `realized_pnl=Decimal(str(db_pos.realized_pnl or 0)),`):

```python
                    realized_pnl=Decimal(str(db_pos.realized_pnl or 0)),
                    # Stage 0: restore the posted margin so a restart credits
                    # back what was actually posted. NULL means 008 has not
                    # been applied — Task 3 handles that case loudly.
                    posted_margin=Decimal(str(db_pos.posted_margin))
                    if db_pos.posted_margin is not None
                    else Decimal("0"),
                    leverage=Decimal(str(db_pos.leverage))
                    if db_pos.leverage is not None
                    else Decimal("1"),
```

- [ ] **Step 9: Add `exit_kind` to `PositionRepository.close`**

In `services/trading-engine/app/repositories.py`, extend the signature at `:129-136` and the `values` dict, following the existing `exit_fee` optional-kwarg idiom exactly:

```python
    async def close(
        self,
        position_id: UUID,
        exit_price: Decimal,
        realized_pnl: Decimal,
        exit_reason: Optional[str] = None,
        exit_fee: Optional[Decimal] = None,
        exit_kind: Optional[str] = None,
        posted_margin: Optional[Decimal] = None,
    ):
```

Extend the docstring, then after the `if exit_fee is not None:` branch:

```python
                if exit_kind is not None:
                    values["exit_kind"] = exit_kind
                if posted_margin is not None:
                    values["posted_margin"] = posted_margin
```

- [ ] **Step 10: Write migration 008**

Create `database/migrations/008_position_margin_leverage_exit_kind.sql`. Copy 007's header structure exactly — banner, Description, Date, Depends on, the explicit `-d cryptobot` apply command (007's header warns against relying on a `\c` directive because older migrations name a database that does not exist), the `Mirrors ...models.py::Position` line, and `Idempotent: safe to re-run.`

```sql
-- ==========================================
-- MIGRATION 008: Per-position posted margin, leverage, structured exit kind
-- ==========================================
-- Description: Stage 0 (docs/superpowers/specs/2026-08-07-engine-repair-and-edge-search-design.md).
--   * Margin was never stored. paper_trading.py recomputed it at close as
--     entry_price*qty/settings.default_leverage — the CURRENT global value,
--     not the one in force at open. When DEFAULT_LEVERAGE dropped 10.0 -> 1.0,
--     every position opened at 10x credited back 10x the margin it posted.
--     posted_margin makes the posted dollar amount first-class; it is
--     consumed proportionally on reduce and zeroed on close.
--     A dollar amount, not a leverage ratio: scale_in rewrites entry_price to
--     a weighted average, which a single stored ratio cannot reconcile.
--   * leverage is recorded for AUDIT ONLY. No arithmetic reads it.
--   * exit_kind is a structured close reason stored ALONGSIDE the free-text
--     exit_reason. exit_reason is deliberately left untouched: it is
--     API-visible through TradeHistoryResponse, and the pre-existing rows are
--     NOT backfilled.
-- Date: 2026-08-07
-- Depends on: 007_position_fee_partial_exit_accounting.sql
--
-- Apply with an explicit database (do NOT rely on a \c directive; the live
-- deployment database is `cryptobot`, older migration headers referenced a
-- differently-named DB):
--   docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
--     -f - < database/migrations/008_position_margin_leverage_exit_kind.sql
--
-- Mirrors services/trading-engine/app/database/models.py::Position.
-- Idempotent: safe to re-run.
--
-- BACKFILL HONESTY: leverage is INFERRED, not recorded. No column, trades
-- field or log field captured it at open. The DEFAULT_LEVERAGE 10.0 -> 1.0
-- flip is bounded by row data to 2026-08-04 14:10 .. 2026-08-06 01:30 (the
-- 14:10:25-14:10:33 batch opened $328 of notional against a ~$79 balance,
-- unreachable at 1x under max_position_size_pct=10.0; every position from
-- 2026-08-06 on is inside the 10% cap). Rows are classified by that bound,
-- NOT by the docker-compose comment date. No CHECK constraint on exit_kind:
-- trades.order_type already carries a CHECK that disagrees with its enum, and
-- a stale CHECK rejects valid writes.
-- ==========================================

BEGIN;

-- Margin still posted on this position, quote currency. Consumed
-- proportionally on reduce; 0 once CLOSED.
ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS posted_margin NUMERIC(20, 8) NOT NULL DEFAULT 0;

-- Leverage in force at open. Audit only.
ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS leverage NUMERIC(10, 4) NOT NULL DEFAULT 1;

-- Structured close reason. NULL while OPEN and on every pre-008 row.
ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS exit_kind VARCHAR(30);

COMMENT ON COLUMN positions.posted_margin IS
    'Margin still posted and not yet returned, quote currency. Added by 008. '
    'Authoritative for the close-side cash credit; replaces recomputing '
    'entry_price*qty/settings.default_leverage at close time.';
COMMENT ON COLUMN positions.leverage IS
    'Leverage in force when the position opened. Added by 008. AUDIT ONLY — '
    'no code path reads this arithmetically. INFERRED for rows predating 008.';
COMMENT ON COLUMN positions.exit_kind IS
    'Structured close reason (app.models.enums.ExitKind). Added by 008. '
    'Stored alongside the free-text exit_reason, which is unchanged and not '
    'backfilled. NULL on every pre-008 row and while OPEN.';

-- Backfill: leverage inferred from the flip bound described in the header.
UPDATE positions SET leverage = 10
WHERE opened_at < TIMESTAMP '2026-08-06 01:30:00' AND leverage = 1;

UPDATE positions SET leverage = 1
WHERE opened_at >= TIMESTAMP '2026-08-06 01:30:00';

-- Backfill: closed positions have nothing posted.
UPDATE positions SET posted_margin = 0 WHERE status = 'CLOSED';

-- Backfill: open positions carry margin on their REMAINING quantity, at the
-- inferred leverage. Both live open rows post-date the flip (leverage 1), so
-- this equals their remaining notional.
UPDATE positions
SET posted_margin = ROUND(
        entry_price * COALESCE(remaining_quantity, quantity) / leverage, 8)
WHERE status = 'OPEN';

COMMIT;
```

- [ ] **Step 11: Mount 008 for fresh-volume boots**

`initdb.d` runs only on a fresh volume, and only 007 is mounted today. In `docker-compose.unified.yml`, next to the existing line 63 mount, add:

```yaml
      - ./database/migrations/008_position_margin_leverage_exit_kind.sql:/docker-entrypoint-initdb.d/06-position-margin-exit-kind.sql:ro
```

Verify the surrounding block first so the numeric prefix orders after `05-`:

```bash
grep -n "docker-entrypoint-initdb.d" docker-compose.unified.yml
```

- [ ] **Step 12: Run the test to verify it passes**

Run: `cd services/trading-engine && python3 -m pytest tests/test_stage0_schema.py --no-cov -q`
Expected: PASS, 6 tests.

- [ ] **Step 13: Apply the migration and prove the columns exist**

```bash
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
  -f - < database/migrations/008_position_margin_leverage_exit_kind.sql

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "\d positions" | grep -E "posted_margin|leverage|exit_kind"

docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT id, symbol, status, leverage, posted_margin,
       ROUND(entry_price * COALESCE(remaining_quantity, quantity), 4) AS rem_notional
FROM positions ORDER BY id;"
```

Expected: the two OPEN rows (61, 64) show `leverage=1` and `posted_margin` equal to their remaining notional (`6.02690000` and `14.60868000`). Every CLOSED row shows `posted_margin=0`. Paste this output into the commit message.

- [ ] **Step 14: Run it a second time to prove idempotency**

```bash
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
  -f - < database/migrations/008_position_margin_leverage_exit_kind.sql
```

Expected: no error, and the `SELECT` from Step 13 returns identical values. `setup_database.sh` re-applies every migration on every run, so this is not optional.

- [ ] **Step 15: Run the surrounding suites for regressions**

Run: `cd services/trading-engine && python3 -m pytest tests/test_accounting_invariants_phase1.py tests/test_sizing_caps_phase1.py tests/test_capital_defaults_phase1.py tests/unit/test_repositories.py tests/test_repositories.py --no-cov -q`
Expected: PASS. This task adds columns with safe defaults and changes no arithmetic; anything failing here is a mapper mistake.

- [ ] **Step 16: Commit**

```bash
git add database/migrations/008_position_margin_leverage_exit_kind.sql \
        services/trading-engine/app/database/models.py \
        services/trading-engine/app/models/enums.py \
        services/trading-engine/app/models/position.py \
        services/trading-engine/app/models/__init__.py \
        services/trading-engine/app/repositories.py \
        services/trading-engine/app/handlers/trades.py \
        services/trading-engine/app/position_manager.py \
        services/trading-engine/tests/test_stage0_schema.py \
        docker-compose.unified.yml
git commit -m "feat(trading-engine): add posted_margin, leverage and exit_kind columns

Migration 008 plus the model, ORM and all four hand-written mappers. No
arithmetic reads the new columns yet - this is schema only, so the behavior
change in the next commit is a clean diff.

Also fixes a pre-existing gap in the same mapper: entry_signal_confidence
has had a column since before 007 and was NULL on all 19 live rows because
PositionRepository.create never mapped it." -- \
  database/migrations/008_position_margin_leverage_exit_kind.sql \
  services/trading-engine/app/database/models.py \
  services/trading-engine/app/models/enums.py \
  services/trading-engine/app/models/position.py \
  services/trading-engine/app/models/__init__.py \
  services/trading-engine/app/repositories.py \
  services/trading-engine/app/handlers/trades.py \
  services/trading-engine/app/position_manager.py \
  services/trading-engine/tests/test_stage0_schema.py \
  docker-compose.unified.yml
```

---

### Task 3: Posted margin becomes authoritative for the cash credit

The behavior fix. After this task no cash arithmetic reads `settings.default_leverage`.

**Files:**
- Modify: `services/trading-engine/app/paper_trading.py` (`__init__` `:78`; `_open_position_cost` `:93-107`; `execute_market_order` `:253`, `:325`, `:407-418`, `:446-472`)
- Modify: `services/trading-engine/app/position_manager.py` (`create_position` `:141-239`; `scale_in` `:578-646`; `consume_posted_margin` new)
- Modify: `services/trading-engine/app/repositories.py` (`record_reduction` `:184`; `record_scale_in` `:236`)
- Modify: `services/trading-engine/app/auto_trader.py` (comment at `:4402-4407`)
- Modify: `services/trading-engine/tests/unit/test_restart_balance_restore.py` (fixture pair `:24-53`)
- Modify: `services/trading-engine/tests/standalone/test_accounting_fixes.py` (`:99`)
- Test: `services/trading-engine/tests/test_posted_margin_ledger.py` (new)

**Interfaces:**
- Consumes: `Position.posted_margin` / `Position.leverage` from Task 2.
- Produces:
  - `PositionManager.create_position(..., posted_margin: Decimal = Decimal("0"), leverage: Decimal = Decimal("1"))`
  - `PositionManager.scale_in(..., posted_margin: Decimal = Decimal("0"))` — accumulates.
  - `PositionManager.consume_posted_margin(position_id: UUID, quantity: Decimal) -> Decimal` — **synchronous**; returns the margin attributable to `quantity` and decrements `position.posted_margin`. Must be called **before** `close_position`/`reduce_position` mutate `remaining_quantity`.
  - `PositionRepository.record_reduction(..., posted_margin: Optional[Decimal] = None)` and `record_scale_in(..., posted_margin: Optional[Decimal] = None)`.

- [ ] **Step 1: Write the failing tests**

Create `services/trading-engine/tests/test_posted_margin_ledger.py`. Reuse the canonical `stack` fixture shape from `tests/test_accounting_invariants_phase1.py:38-131` — real `PositionManager` + real `PaperTradingEngine` over mocked repos, identity slippage, and the module-singleton save/restore:

```python
"""
Stage 0: posted margin is a per-position dollar amount, not a global ratio.

Defect being pinned: paper_trading.py:253 read settings.default_leverage at
CLOSE time and paper_trading.py:325 credited entry_price*close_qty/that value.
A position opened while DEFAULT_LEVERAGE=10 and closed after the compose flip
to 1.0 credited back 10x the margin it posted. Reconstructed against the live
DB, this fabricated ~$177 of cash on a $100 account.
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.paper_trading as paper_trading_module
from app.models import OrderCreate, OrderSide, OrderType
from app.paper_trading import PaperTradingEngine
from app.position_manager import PositionManager


async def _drain_tasks():
    for _ in range(10):
        await asyncio.sleep(0)


class _IdentitySlippage:
    def fill_price(self, symbol, side, price):
        return price

    def describe(self):
        return "identity (test)"


def _mock_position_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.update_price = AsyncMock()
    repo.close = AsyncMock()
    repo.record_reduction = AsyncMock()
    repo.record_scale_in = AsyncMock()
    repo.get_open_positions = AsyncMock(return_value=[])
    return repo


def _mock_portfolio_repo():
    repo = MagicMock()
    repo.record_position_close = AsyncMock()
    repo.update_balance = AsyncMock()
    repo.get_or_create = AsyncMock()
    return repo


def _mock_risk_manager():
    rm = MagicMock()
    rm.calculate_stop_loss = MagicMock(return_value=Decimal("0.00000001"))
    rm.calculate_take_profit = MagicMock(return_value=Decimal("99999999"))
    rm.update_daily_pnl = MagicMock()
    return rm


@pytest.fixture
def stack():
    position_repo = _mock_position_repo()
    portfolio_repo = _mock_portfolio_repo()
    trade_repo = MagicMock()
    trade_repo.log_trade = AsyncMock()
    risk_manager = _mock_risk_manager()

    with (
        patch("app.position_manager.get_risk_manager", return_value=risk_manager),
        patch("app.position_manager.get_position_repository", return_value=position_repo),
        patch("app.position_manager.get_portfolio_repository", return_value=portfolio_repo),
    ):
        manager = PositionManager()

    with (
        patch("app.paper_trading.get_position_manager", return_value=manager),
        patch("app.paper_trading.get_risk_manager", return_value=risk_manager),
        patch("app.paper_trading.get_trade_repository", return_value=trade_repo),
        patch("app.paper_trading.get_portfolio_repository", return_value=portfolio_repo),
    ):
        engine = PaperTradingEngine()
    engine.slippage = _IdentitySlippage()

    saved = paper_trading_module._paper_engine
    paper_trading_module._paper_engine = engine
    yield SimpleNamespace(
        engine=engine, manager=manager,
        position_repo=position_repo, portfolio_repo=portfolio_repo,
    )
    paper_trading_module._paper_engine = saved


def _order(symbol, side, qty, position_id=None, reduce_only=False):
    return OrderCreate(
        symbol=symbol,
        side=side,
        type=OrderType.MARKET,
        quantity=Decimal(str(qty)),
        strategy="test",
        position_id=position_id,
        reduce_only=reduce_only,
    )


async def test_open_stamps_posted_margin_equal_to_debited_margin(stack):
    """What leaves the cash ledger at open is exactly what the position records."""
    engine, manager = stack.engine, stack.manager
    # leverage_enabled MUST be set: config.py:614 defaults it to False, and the
    # Stage 0 fix gates paper_trading's leverage read on it (auto_trader always
    # did; paper_trading did not, which was an independent latent bug).
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0
    before = engine.balance

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()

    pos = manager.get_open_positions()[0]
    commission = engine.calculate_commission(Decimal("70"))
    debited = before - engine.balance

    assert pos.posted_margin == Decimal("7")            # 70 notional / 10x
    assert pos.leverage == Decimal("10")
    assert debited == pos.posted_margin + commission


async def test_close_credits_what_was_posted_not_the_current_global(stack):
    """THE REGRESSION. Open at 10x, flip the global to 1x, close: cash must
    return 7, not 70."""
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0
    start = engine.balance

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    engine.settings.default_leverage = 1.0          # the 2026-08-04 compose flip

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "1", position_id=pos.id, reduce_only=True),
        Decimal("70"),
    )
    await _drain_tasks()

    fees = engine.calculate_commission(Decimal("70")) * 2
    assert engine.balance == start - fees
    assert manager.positions[pos.id].posted_margin == Decimal("0")


async def test_partial_close_returns_proportional_margin(stack):
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]
    assert pos.posted_margin == Decimal("7")

    mid = engine.balance
    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "0.4", position_id=pos.id, reduce_only=True),
        Decimal("70"),
    )
    await _drain_tasks()

    exit_fee = engine.calculate_commission(Decimal("28"))
    assert manager.positions[pos.id].posted_margin == Decimal("4.2")
    assert engine.balance == mid + Decimal("2.8") - exit_fee


async def test_scale_in_accumulates_margin_across_different_leverage(stack):
    """A stored leverage RATIO cannot express this; a dollar ledger can.
    scale_in also rewrites entry_price to a weighted average."""
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    engine.settings.default_leverage = 2.0
    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.BUY, "1", position_id=pos.id), Decimal("80")
    )
    await _drain_tasks()

    # 70/10 + 80/2 = 7 + 40
    assert manager.positions[pos.id].posted_margin == Decimal("47")


async def test_margin_conservation_over_a_full_round_trip(stack):
    """Cash returns to its start less fees, whatever leverage did in between."""
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0
    start = engine.balance

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    for qty in ("0.3", "0.3"):
        engine.settings.default_leverage = 1.0
        await engine.execute_market_order(
            _order("SOLUSDT", OrderSide.SELL, qty, position_id=pos.id, reduce_only=True),
            Decimal("70"),
        )
        await _drain_tasks()

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "0.4", position_id=pos.id, reduce_only=True),
        Decimal("70"),
    )
    await _drain_tasks()

    total_fees = engine.calculate_commission(Decimal("70")) * 2
    assert engine.balance == start - total_fees
    assert manager.positions[pos.id].posted_margin == Decimal("0")


def test_consume_posted_margin_hands_the_exact_residual(stack):
    """Mirrors _consume_entry_fee: a whole-remainder leg gets the residual,
    not a computed share, so Decimal division cannot leak a fraction of a cent."""
    from app.models.enums import PositionSide

    manager = stack.manager
    pos = manager.create_position(
        symbol="ADAUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("0.2023"),
        quantity=Decimal("3"),
        posted_margin=Decimal("1"),
        leverage=Decimal("1"),
    )
    first = manager.consume_posted_margin(pos.id, Decimal("1"))
    pos.remaining_quantity = Decimal("2")
    second = manager.consume_posted_margin(pos.id, Decimal("2"))

    assert first + second == Decimal("1")
    assert pos.posted_margin == Decimal("0")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_posted_margin_ledger.py --no-cov -q`
Expected: FAIL — `TypeError: create_position() got an unexpected keyword argument 'posted_margin'`.

- [ ] **Step 3: Accept margin on `create_position`**

In `services/trading-engine/app/position_manager.py`, extend the signature after `entry_fee: Decimal = Decimal("0"),` (safe defaults so the live path and every existing caller keep working):

```python
        posted_margin: Decimal = Decimal("0"),  # Stage 0 (2026-08-07)
        leverage: Decimal = Decimal("1"),
```

Document both in the docstring, then pass them into the `Position(...)` construction after `entry_signal_confidence=entry_signal_confidence,`:

```python
            posted_margin=posted_margin,
            leverage=leverage,
```

Add `Entry fee: {entry_fee}` → `Entry fee: {entry_fee} | Margin: {posted_margin} ({leverage}x)` in the existing log line.

- [ ] **Step 4: Add `consume_posted_margin`**

Insert immediately after `_consume_entry_fee` (which ends at `position_manager.py:139`), mirroring its shape exactly — including the whole-remainder residual branch that makes conservation exact:

```python
    def consume_posted_margin(self, position_id: UUID, quantity: Decimal) -> Decimal:
        """Margin attributable to `quantity`, released from the position.

        Stage 0 (2026-08-07). Mirrors `_consume_entry_fee`: spread the still-
        posted margin over the REMAINING quantity, and hand a leg that takes
        the whole remainder the exact residual rather than a computed share,
        so conservation is exact and not subject to Decimal rounding.

        MUST be called BEFORE close_position/reduce_position mutate
        remaining_quantity — those methods set it to 0 / decrement it.

        Public (not underscore-prefixed) because the cash ledger lives in
        PaperTradingEngine, not here: reduce_position's docstring states that
        'the caller is responsible for cash accounting'.
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        posted = position.posted_margin or Decimal("0")
        remaining = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )
        if posted <= 0 or remaining <= 0 or quantity <= 0:
            return Decimal("0")

        if quantity >= remaining:
            portion = posted
        else:
            portion = posted * quantity / remaining

        position.posted_margin = posted - portion
        return portion
```

- [ ] **Step 5: Accumulate margin on `scale_in`**

In `scale_in` (`position_manager.py:578`), add `posted_margin: Decimal = Decimal("0"),` after `entry_fee`, document it, and next to the `total_entry_fee` accumulation add:

```python
        position.posted_margin = (position.posted_margin or Decimal("0")) + posted_margin
```

Pass it through the existing `record_scale_in` persist call as `posted_margin=position.posted_margin,`.

- [ ] **Step 6: Persist margin on reduce and scale-in**

In `services/trading-engine/app/repositories.py`, add `posted_margin: Optional[Decimal] = None` to both `record_reduction` (`:184`) and `record_scale_in` (`:236`), and in each, guard the write exactly as `close` guards `exit_fee`:

```python
                if posted_margin is not None:
                    values["posted_margin"] = posted_margin
```

Then in `position_manager.reduce_position`, add `posted_margin=position.posted_margin,` to the `record_reduction(...)` call.

- [ ] **Step 7: Rewire the paper engine**

In `services/trading-engine/app/paper_trading.py`:

**(a)** `execute_market_order` — replace line 253. The local stays, because the OPEN legs still need to compute margin from the *current* configured leverage; only the CLOSE leg stops using it:

```python
        # Stage 0 (2026-08-07): this is the leverage a NEW leg posts margin at.
        # It is stamped onto the position. The CLOSE leg no longer reads it —
        # it consumes position.posted_margin instead. Gated on leverage_enabled
        # to match auto_trader.py:4408-4413, which paper_trading did not do.
        leverage = Decimal("1")
        if getattr(self.settings, "leverage_enabled", False):
            leverage = Decimal(str(self.settings.default_leverage))
```

**(b)** Close/reduce credit — replace line 325's `margin_returned = (target.entry_price * close_qty) / leverage` with:

```python
            # Stage 0 (2026-08-07): return what this position POSTED, not what
            # the current global leverage would imply. The old form recomputed
            # entry_price*close_qty/settings.default_leverage; a position
            # opened at 10x and closed after DEFAULT_LEVERAGE dropped to 1.0
            # credited back 10x its margin (~$177 fabricated on a $100 account).
            # Must run BEFORE close_position/reduce_position touch
            # remaining_quantity.
            margin_returned = self.position_manager.consume_posted_margin(
                target.id, close_qty
            )
```

**(c)** Open path (`:446-472`) — pass the margin and leverage down:

```python
        position = self.position_manager.create_position(
            symbol=order.symbol,
            side=open_side,
            entry_price=fill_price,
            quantity=order.quantity,
            strategy=order.strategy,
            entry_signal_confidence=order.entry_signal_confidence,
            entry_fee=commission,
            posted_margin=margin_required,
            leverage=leverage,
        )
```

**(d)** Scale-in path (`:407-418`) — `self.position_manager.scale_in(pos.id, order.quantity, fill_price, entry_fee=commission, posted_margin=margin_required)`.

**(e)** Close persistence — pass the zeroed margin through so a restart cannot resurrect it. In `position_manager.close_position`, add `posted_margin=Decimal("0"),` to the `self.position_repo.close(...)` call, and set `position.posted_margin = Decimal("0")` alongside the existing `position.remaining_quantity = Decimal("0")`.

**(f)** `_open_position_cost` (`:93-107`) — it now reads the stored amount, and its docstring stops lying:

```python
    def _open_position_cost(self, positions) -> Decimal:
        """Margin + commission actually debited when these positions opened.

        Stage 0 (2026-08-07): reads the margin each position RECORDED at open
        rather than recomputing it from the current settings.default_leverage.
        The previous form made this docstring false — after the 2026-08-04
        DEFAULT_LEVERAGE 10.0 -> 1.0 flip it over-deducted for every 10x-era
        position on every restart.
        """
        total = Decimal("0")
        for pos in positions:
            qty = (
                pos.remaining_quantity
                if pos.remaining_quantity is not None
                else pos.quantity
            )
            posted = getattr(pos, "posted_margin", None) or Decimal("0")
            total += posted + (pos.entry_price * qty * self.commission_pct)
        return total
```

**(g)** `__init__` line 78 — fix the float leak while you are here (the `/ 100` currently happens in float before the `Decimal(str(...))` wrap):

```python
        self.commission_pct = Decimal(str(self.settings.paper_commission_pct)) / Decimal("100")
```

- [ ] **Step 8: Handle an un-backfilled `posted_margin` loudly at restart**

**A NULL check here would be dead code — do not write one.** Migration 008 declared the column
`NOT NULL DEFAULT 0`, so a row that never got a real margin presents as **`0`**, never as NULL.
The anomaly to detect is therefore *zero margin on an OPEN position*, which by this task's own
design is unreachable: open sets `margin_required > 0`, a partial close leaves a positive
remainder, and a full close zeroes it only while setting `status = CLOSED`. If you ever see it,
something upstream is wrong.

In `position_manager.load_positions_from_db`, alongside the existing `remaining_quantity` branch:

```python
                # Stage 0 (2026-08-07): migration 008 made this column
                # NOT NULL DEFAULT 0, so an un-backfilled row reads 0, not NULL —
                # a NULL check would never fire. Zero margin on an OPEN position
                # is unreachable by design (open posts > 0; a partial close leaves
                # a positive remainder; a full close zeroes it only while setting
                # status=CLOSED), so it means either 008's backfill missed this row
                # or the margin ledger has a defect. Either way the next close
                # credits NO margin back — say so.
                if (position.posted_margin or Decimal("0")) <= 0:
                    logger.error(
                        f"positions.posted_margin is 0 on OPEN position "
                        f"{db_pos.position_id} ({db_pos.symbol}) — 008 backfill "
                        f"missed it, or the margin ledger is broken. Closing this "
                        f"position will credit NO margin back to cash."
                    )
```

Silence here would be a second `entry_signal_confidence`.

While you are in this method, **also correct the stale comment** on the neighbouring
`remaining_quantity` branch if it claims a NULL indicates "migration 007 not applied" in terms
that no longer hold post-008 — say what a NULL actually means now.

- [ ] **Step 9: Update the stale coupling comment**

`auto_trader.py:4402-4407` asserts *"paper_engine then divides notional by default_leverage to compute margin deducted"*. That is now false. Replace that sentence with:

```python
            # paper_engine posts margin = notional / leverage and RECORDS the
            # dollar amount on the position (Stage 0, 2026-08-07); the close
            # leg returns exactly that recorded amount, so cash impact =
            # balance x position_size_pct regardless of any later change to
            # DEFAULT_LEVERAGE. Leverage only scales notional (P&L exposure).
```

Apply the identical correction to the twin block at `auto_trader.py:2008-2013` if its comment makes the same claim.

- [ ] **Step 10: Rewrite the two tests that encode the old behavior**

`tests/unit/test_restart_balance_restore.py` is a deliberate DL-2 regression pin whose every number derives from `LEVERAGE = Decimal("10")`. Its `_position()` returns a `SimpleNamespace` with no `posted_margin`, and `_engine()` builds via `PaperTradingEngine.__new__`. Rewrite the fixture pair:

```python
LEVERAGE = Decimal("10")
COMMISSION_PCT = Decimal("0.001")  # 0.1%


def _position(entry_price, quantity, opened_at):
    """Minimal stand-in for an in-memory Position.

    Stage 0: carries posted_margin, because _open_position_cost now reads the
    recorded amount instead of recomputing notional/settings.default_leverage.
    """
    entry = Decimal(str(entry_price))
    qty = Decimal(str(quantity))
    return SimpleNamespace(
        entry_price=entry,
        quantity=qty,
        remaining_quantity=None,
        posted_margin=(entry * qty) / LEVERAGE,
        leverage=LEVERAGE,
        opened_at=opened_at,
        side=PositionSide.LONG,
        status=PositionStatus.OPEN,
    )
```

Leave `_engine()` as-is — `engine.settings` may keep `default_leverage`; nothing in `_open_position_cost` reads it any more. Run the file and confirm the three previously-failing assertions now hold with the **same** expected numbers (`posted_margin` reproduces `notional/10` exactly).

For `tests/standalone/test_accounting_fixes.py:99`, `fresh_engine(leverage=...)` assigns `engine.settings.default_leverage`; add `engine.settings.leverage_enabled = True` next to it so the new gate in Step 7(a) does not silently pin leverage to 1.

- [ ] **Step 11: Run the new tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_posted_margin_ledger.py --no-cov -q`
Expected: PASS, 6 tests.

- [ ] **Step 12: Run every suite that touches this arithmetic**

Run: `cd services/trading-engine && python3 -m pytest tests/test_posted_margin_ledger.py tests/test_accounting_invariants_phase1.py tests/test_sizing_caps_phase1.py tests/unit/test_restart_balance_restore.py tests/unit/test_paper_trading.py tests/unit/test_paper_slippage.py tests/standalone/test_accounting_fixes.py tests/test_stage0_schema.py --no-cov -q`
Expected: PASS. If `test_accounting_invariants_phase1.py:161` fails, it reads `engine.settings.default_leverage` to derive its expectation — the expectation is still correct because the test opens and closes within one leverage setting; investigate before editing it.

- [ ] **Step 13: Commit**

```bash
git add services/trading-engine/app/paper_trading.py \
        services/trading-engine/app/position_manager.py \
        services/trading-engine/app/repositories.py \
        services/trading-engine/app/auto_trader.py \
        services/trading-engine/tests/test_posted_margin_ledger.py \
        services/trading-engine/tests/unit/test_restart_balance_restore.py \
        services/trading-engine/tests/standalone/test_accounting_fixes.py
git commit -m "fix(trading-engine): credit back the margin a position posted, not the current global

paper_trading.py:253 read settings.default_leverage at CLOSE time and :325
credited entry_price*close_qty/that value. When DEFAULT_LEVERAGE dropped
10.0 -> 1.0 on 2026-08-04, every position opened at 10x returned 10x the
margin it posted. Reconstructed exactly against the live DB, this fabricated
~\$177 of cash on a \$100 account - and because sizing and the 10% cap are
both fractions of that same balance, the cap stopped binding.

Margin is now a dollar amount stamped at open and consumed proportionally,
mirroring the _consume_entry_fee ledger. A dollar amount rather than a
leverage ratio because scale_in rewrites entry_price to a weighted average,
which a single stored ratio cannot reconcile.

Also: paper_trading now honors leverage_enabled (auto_trader always did),
and the commission /100 no longer happens in float before the Decimal wrap." -- \
  services/trading-engine/app/paper_trading.py \
  services/trading-engine/app/position_manager.py \
  services/trading-engine/app/repositories.py \
  services/trading-engine/app/auto_trader.py \
  services/trading-engine/tests/test_posted_margin_ledger.py \
  services/trading-engine/tests/unit/test_restart_balance_restore.py \
  services/trading-engine/tests/standalone/test_accounting_fixes.py
```

---

### Task 4: One-time cash-ledger repair

**GATED.** Do not start unless `.planning/evidence/cash-ledger-reconciliation-2026-08-07.md` line 1 reads `VERDICT: RECONCILED`. If it reads `UNRECONCILED`, stop and report — `AUDIT.md §8.1` declined a repair at the $4.23 magnitude and there is no owner ruling at $177 against an unexplained delta.

**Files:**
- Create: `database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql`
- Test: `services/trading-engine/tests/test_cash_conservation_invariant.py` (new)

**Interfaces:**
- Consumes: Task 1's verdict; Task 3's `posted_margin` semantics.
- Produces: a corrected `portfolios.cash_balance`, and a standing invariant test.

Note the repair script goes in `one_time_repairs/`, **not** as `009_`: `setup_database.sh` globs `$MIGRATIONS_DIR/*.sql` non-recursively, and that directory boundary is what keeps repairs off the auto-run path.

- [ ] **Step 1: Write the invariant test first, against a synthetic ledger**

The invariant cannot be asserted against the live row until the repair lands, and `.claude/rules/testing.md:28` forbids `xfail`-ing to green a suite. Assert it over an in-memory round trip instead — the same technique `test_accounting_invariants_phase1.py` already uses. This test is permanent and must survive the repair.

Create `services/trading-engine/tests/test_cash_conservation_invariant.py`:

```python
"""
Standing cash-conservation invariant (Stage 0, 2026-08-07).

    cash
  + SUM(posted_margin on open)
  + SUM(unconsumed entry fee on open)
  == initial_balance + SUM(realized_pnl over ALL positions)

Both extra terms are load-bearing and the obvious two-term form is WRONG:

  * the cash ledger debits the whole entry fee at open, while
    position.realized_pnl nets only the CONSUMED portion, so an open position
    with a partial exit leaves the difference stranded;
  * realized P&L accrues onto OPEN positions via partial exits, so summing
    only closed ones under-counts. portfolios.realized_pnl has the same blind
    spot by construction - it is written only by record_position_close.

Asserted over an in-memory round trip rather than the live portfolios row,
because the live row carried a ~$177 break at the time this was written and a
test that fails on real data teaches nothing. The one-time repair is
database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql.
"""

from decimal import Decimal

import pytest

from tests.test_posted_margin_ledger import (  # noqa: F401  - fixture reuse
    _drain_tasks,
    _order,
    stack,
)
from app.models import OrderSide


def _unconsumed_entry_fees(manager) -> Decimal:
    """Entry commission already out of cash but not yet charged to any leg's P&L.

    This term is NOT optional. The cash ledger debits the whole entry fee at
    open, while position.realized_pnl is net of only the CONSUMED portion
    (close_position/reduce_position call _consume_entry_fee per exit leg). Drop
    it and the identity holds only for positions with nothing open.
    """
    total = Decimal("0")
    for p in manager.get_open_positions():
        total += manager._entry_fees.get(p.id, Decimal("0")) - manager._entry_fees_consumed.get(
            p.id, Decimal("0")
        )
    return total


def _identity_holds(engine, manager) -> bool:
    open_margin = sum(
        (p.posted_margin or Decimal("0")) for p in manager.get_open_positions()
    )
    # ALL positions, not just closed ones: a partial exit accrues realized P&L
    # onto a position that is still OPEN. Live proof that this matters -
    # portfolios.realized_pnl reads -0.41002416 while SUM over all positions is
    # -0.28337306, the gap being position 64's +0.1266511 partial exit.
    realized = sum(
        p.realized_pnl
        for p in list(manager.get_open_positions()) + list(manager.get_closed_positions())
    )
    return (
        engine.balance + open_margin + _unconsumed_entry_fees(manager)
        == engine.initial_balance + realized
    )


async def test_identity_holds_after_open(stack):
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()

    assert _identity_holds(engine, manager)
    # And the fee term is genuinely load-bearing here, not decorative:
    assert _unconsumed_entry_fees(manager) == engine.calculate_commission(Decimal("70"))


async def test_identity_holds_after_full_round_trip(stack):
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    engine.settings.default_leverage = 1.0
    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "1", position_id=pos.id, reduce_only=True),
        Decimal("77"),
    )
    await _drain_tasks()

    assert _identity_holds(engine, manager)


async def test_identity_survives_partial_exits(stack):
    engine, manager = stack.engine, stack.manager
    engine.settings.leverage_enabled = True
    engine.settings.default_leverage = 10.0

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    for qty, px in (("0.3", "72"), ("0.3", "74"), ("0.4", "76")):
        await engine.execute_market_order(
            _order("SOLUSDT", OrderSide.SELL, qty, position_id=pos.id, reduce_only=True),
            Decimal(px),
        )
        await _drain_tasks()

    assert _identity_holds(engine, manager)
```

Note: `tests/` has an `__init__.py`, so the `from tests.test_posted_margin_ledger import ...` fixture reuse resolves. If it does not, copy the fixture rather than adding a conftest — the autouse `mock_database_connection` fixture's `sys.modules` teardown makes conftest changes here fragile.

- [ ] **Step 2: Run it**

Run: `cd services/trading-engine && python3 -m pytest tests/test_cash_conservation_invariant.py --no-cov -q`
Expected: PASS, 3 tests. It passes immediately because Task 3 made the identity true in code.

- [ ] **Step 3: Back up the three tables before writing anything**

```bash
mkdir -p .planning/evidence/backups
docker exec crypto-bot-postgres pg_dump -U cryptobot -d cryptobot \
  -t positions -t trades -t portfolios \
  > .planning/evidence/backups/pre-cash-repair-2026-08-07.sql
wc -l .planning/evidence/backups/pre-cash-repair-2026-08-07.sql
```

Expected: a non-trivial line count. Do not proceed on an empty or truncated dump.

- [ ] **Step 4: Write the repair script**

Create `database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql`. Substitute the value derived in Task 1 — do not hardcode a number copied from this plan. Follow the BEFORE/AFTER `\echo` shape of `scripts/repair_testnet_pollution.sql` (007 itself carries no verification block, so that is the template for one):

```sql
-- ==========================================
-- ONE-TIME REPAIR 2026-08-07: paper cash-ledger reset
-- ==========================================
-- Reconciliation: .planning/evidence/cash-ledger-reconciliation-2026-08-07.md
-- Root cause fixed in code by the posted_margin ledger (Stage 0). This repairs
-- the historical damage only; without it the engine keeps sizing every trade
-- off an inflated balance, because both the size and the 10% cap are fractions
-- of the same number.
--
-- NOT a numbered migration: database/scripts/setup_database.sh globs
-- $MIGRATIONS_DIR/*.sql non-recursively and re-applies everything on every
-- run. A cash overwrite must never be on that path.
--
-- Backup taken first:
--   .planning/evidence/backups/pre-cash-repair-2026-08-07.sql
--
-- Apply:
--   docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
--     -f - < database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql
-- ==========================================

-- THREE TERMS, and the obvious two-term form is wrong:
--   * realized P&L must sum over ALL positions, not just CLOSED ones - a
--     partial exit accrues realized P&L onto a position that is still open.
--     portfolios.realized_pnl has that blind spot by construction (it is
--     written only by record_position_close), which is why the live row reads
--     -0.41002416 while SUM over all positions is -0.28337306.
--   * unconsumed entry fee must be subtracted: cash was debited the WHOLE
--     entry fee at open, while realized_pnl nets only the consumed portion.
--     For an open row that is entry_fee * remaining_quantity / quantity - the
--     same reconstruction load_positions_from_db uses, exact whenever no
--     scale-in intervened between partial exits.

\echo '=== BEFORE ==='
SELECT portfolio_id, initial_balance, cash_balance, realized_pnl, updated_at
FROM portfolios;

SELECT
    COALESCE((SELECT SUM(realized_pnl) FROM positions), 0)            AS realized_all,
    COALESCE((SELECT SUM(posted_margin) FROM positions
              WHERE status = 'OPEN'), 0)                              AS open_margin,
    COALESCE((SELECT SUM(entry_fee * remaining_quantity / NULLIF(quantity, 0))
              FROM positions WHERE status = 'OPEN'), 0)               AS unconsumed_entry_fee;

BEGIN;

-- Computed, not hardcoded, so re-running after a further close stays correct.
UPDATE portfolios p
SET cash_balance = p.initial_balance
                 + COALESCE((SELECT SUM(realized_pnl) FROM positions), 0)
                 - COALESCE((SELECT SUM(posted_margin) FROM positions
                             WHERE status = 'OPEN'), 0)
                 - COALESCE((SELECT SUM(entry_fee * remaining_quantity / NULLIF(quantity, 0))
                             FROM positions WHERE status = 'OPEN'), 0),
    updated_at = NOW()
WHERE p.portfolio_id = 'paper_trading';

COMMIT;

\echo '=== AFTER (invariant must return t) ==='
SELECT portfolio_id, initial_balance, cash_balance, realized_pnl, updated_at
FROM portfolios;

SELECT (p.cash_balance
        + COALESCE((SELECT SUM(posted_margin) FROM positions WHERE status = 'OPEN'), 0)
        + COALESCE((SELECT SUM(entry_fee * remaining_quantity / NULLIF(quantity, 0))
                    FROM positions WHERE status = 'OPEN'), 0)
        = p.initial_balance
        + COALESCE((SELECT SUM(realized_pnl) FROM positions), 0)) AS invariant_holds
FROM portfolios p WHERE p.portfolio_id = 'paper_trading';
```

- [ ] **Step 5: Apply it and paste the proof**

```bash
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
  -f - < database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql
```

Expected: `invariant_holds` returns `t`. Paste the full BEFORE/AFTER output into the commit message. If it returns `f`, roll back from the Step 3 dump and stop.

- [ ] **Step 6: Recreate the engine so it reloads the repaired ledger**

Per CLAUDE.md §7, a config or data change is not proven until the service that caches it is recreated — and `sync_balance_with_positions` runs at startup.

```bash
docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine
sleep 20
docker logs crypto-bot-trading --tail 40 2>&1 | grep -E "Balance restored|Restored balance|posted_margin is NULL"
curl -s http://localhost:8005/api/v1/performance | python3 -m json.tool
```

Expected: `Restored balance` matches the repaired `cash_balance`, no `posted_margin is NULL` lines, and `/api/v1/performance` `current_balance` agrees with the DB. Paste all three.

- [ ] **Step 7: Commit**

```bash
git add database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql \
        services/trading-engine/tests/test_cash_conservation_invariant.py
git commit -m "fix(db): repair the paper cash ledger and pin the conservation invariant

One-time repair of the historical damage from the leverage-at-close defect,
gated on the reconciliation in .planning/evidence/. Sets cash_balance to
initial_balance + realized_pnl - posted margin on open positions, computed
rather than hardcoded so it stays correct if a position closes first.

Filed under one_time_repairs/ rather than as 009_ because setup_database.sh
re-applies every numbered migration on every run, and a cash overwrite must
never sit on that path.

The invariant test asserts over an in-memory round trip, not the live row." -- \
  database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql \
  services/trading-engine/tests/test_cash_conservation_invariant.py
```

---

### Task 5: `ExitKind` rides `OrderBase` into the database

Full closes only. Partial exits stay out of scope (owner decision 2026-08-07): `reduce_position` has no reason parameter and `record_reduction` has no reason column, so covering them roughly doubles the task.

**Files:**
- Modify: `services/trading-engine/app/models/order.py` (`OrderBase` `:14-35`)
- Modify: `services/trading-engine/app/paper_trading.py` (close branch, `:336-359`)
- Modify: `services/trading-engine/app/position_manager.py` (`close_position` `:377-492`)
- Modify: `services/trading-engine/app/live_trading.py` (`close_position` `:428-484`)
- Test: `services/trading-engine/tests/test_exit_kind_persistence.py` (new)

**Interfaces:**
- Consumes: `ExitKind` and the `exit_kind` column from Task 2; `PositionRepository.close(..., exit_kind=)` from Task 2 Step 9.
- Produces:
  - `OrderBase.exit_kind: Optional[ExitKind] = None`.
  - `PositionManager.close_position(position_id, close_price, reason=None, close_commission=Decimal("0"), exit_kind: Optional[ExitKind] = None)`.
  - `LiveTradingEngine.close_position(..., exit_kind: Optional[ExitKind] = None)`.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_exit_kind_persistence.py`:

```python
"""
Stage 0: the structured close reason must reach positions.exit_kind.

Two traps this pins:
  * The field MUST live on OrderBase, not OrderCreate. paper_trading.py:255
    does Order(**order.model_dump(), ...) and Order inherits OrderBase;
    pydantic v2 extra='ignore' would silently drop an OrderCreate-only field
    with no ValidationError.
  * In PAPER mode the routed prose reason never reaches the DB at all - the
    persisted exit_reason is synthesized at paper_trading.py:343-345. The enum
    is a second, independent channel; exit_reason is left untouched.
"""

from decimal import Decimal

import pytest

from app.models import OrderCreate, OrderSide, OrderType
from app.models.enums import ExitKind
from tests.test_posted_margin_ledger import (  # noqa: F401
    _drain_tasks,
    _order,
    stack,
)


def test_exit_kind_is_declared_on_orderbase_not_ordercreate():
    """If it lands on OrderCreate only, model_dump() drops it at the Order()
    construction and the whole feature is a silent no-op."""
    from app.models.order import Order, OrderBase

    assert "exit_kind" in OrderBase.model_fields
    assert "exit_kind" in Order.model_fields

    order = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        exit_kind=ExitKind.HARD_STOP,
    )
    assert order.exit_kind == ExitKind.HARD_STOP
    assert order.model_dump()["exit_kind"] == ExitKind.HARD_STOP


def test_unknown_field_on_ordercreate_is_still_silently_dropped():
    """Documents WHY the field must be on OrderBase. If this ever starts
    raising, pydantic's extra policy changed and the reasoning should be
    revisited."""
    order = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        definitely_not_a_field=123,
    )
    assert "definitely_not_a_field" not in order.model_dump()


async def test_full_close_persists_exit_kind(stack):
    engine, manager, repo = stack.engine, stack.manager, stack.position_repo

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    close = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        strategy="stop_loss_limit",
        position_id=pos.id,
        reduce_only=True,
        exit_kind=ExitKind.HARD_STOP,
    )
    await engine.execute_market_order(close, Decimal("68.6"))
    await _drain_tasks()

    repo.close.assert_awaited_once()
    assert repo.close.await_args.kwargs["exit_kind"] == "HARD_STOP"


async def test_prose_exit_reason_is_left_untouched(stack):
    """exit_reason is API-visible via TradeHistoryResponse; the enum is
    additive, not a replacement."""
    engine, manager, repo = stack.engine, stack.manager, stack.position_repo

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    close = OrderCreate(
        symbol="SOLUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        strategy="auto_close",
        position_id=pos.id,
        reduce_only=True,
        exit_kind=ExitKind.MAX_HOLD,
    )
    await engine.execute_market_order(close, Decimal("71"))
    await _drain_tasks()

    kwargs = repo.close.await_args.kwargs
    assert kwargs["exit_kind"] == "MAX_HOLD"
    assert kwargs["exit_reason"] == "Market sell order (LONG close) [auto_close]"


async def test_close_without_exit_kind_persists_none(stack):
    """The live path and every legacy caller must keep working."""
    engine, manager, repo = stack.engine, stack.manager, stack.position_repo

    await engine.execute_market_order(_order("SOLUSDT", OrderSide.BUY, "1"), Decimal("70"))
    await _drain_tasks()
    pos = manager.get_open_positions()[0]

    await engine.execute_market_order(
        _order("SOLUSDT", OrderSide.SELL, "1", position_id=pos.id, reduce_only=True),
        Decimal("70"),
    )
    await _drain_tasks()

    assert repo.close.await_args.kwargs["exit_kind"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_exit_kind_persistence.py --no-cov -q`
Expected: FAIL — `assert 'exit_kind' in OrderBase.model_fields`.

- [ ] **Step 3: Add the field to `OrderBase`**

In `services/trading-engine/app/models/order.py`, inside `class OrderBase(BaseModel)` after the `reduce_only` field:

```python
    # Stage 0 (2026-08-07): structured close reason. MUST live on OrderBase,
    # not OrderCreate — paper_trading.py:255 does Order(**order.model_dump())
    # and Order inherits OrderBase, so an OrderCreate-only field is silently
    # dropped there (pydantic v2 extra='ignore', no ValidationError).
    exit_kind: Optional[ExitKind] = Field(
        default=None,
        description="Why this order closes a position (full closes only); "
                    "None for entries and partial exits",
    )
```

Add `ExitKind` to the `app.models.enums` import on line 11.

- [ ] **Step 4: Accept it on `close_position` and forward it**

In `services/trading-engine/app/position_manager.py`, extend `close_position` (`:377`):

```python
        exit_kind: Optional[ExitKind] = None,
```

Document it, then in the existing `self.position_repo.close(...)` persist call add:

```python
                exit_kind=exit_kind.value if exit_kind else None,
```

Import `ExitKind` at the top of the module alongside the existing enum imports. Also set `position.exit_kind = exit_kind` next to the existing `position.exit_reason = reason` so the in-memory object matches the row, and include it in the close log line.

- [ ] **Step 5: Thread it through the paper engine**

In `services/trading-engine/app/paper_trading.py`, in the full-close branch, pass the order's field straight through:

```python
                closed_position = self.position_manager.close_position(
                    target.id,
                    fill_price,
                    reason=f"Market {order.side.value.lower()} order "
                    f"({target.side.value} close)"
                    + (f" [{order.strategy}]" if order.strategy else ""),
                    close_commission=close_commission,
                    exit_kind=order.exit_kind,
                )
```

The prose `reason` is unchanged — deliberately. `exit_reason` is API-visible through `handlers/trades.py:55` → `TradeHistoryResponse`, and the 17 existing rows are not backfilled.

- [ ] **Step 6: Close the LIVE asymmetry**

`live_trading.py:483` passes the routed prose reason straight into `position_manager.close_position`, so PAPER and LIVE write structurally different values for the same event today. Add the same optional kwarg to `LiveTradingEngine.close_position` (`:428-435`, whose current default is `reason: str = "manual"` — an eighth vocabulary value that appears nowhere else) and forward it. `ExitKind.MANUAL` exists for exactly that default.

- [ ] **Step 7: Run the new tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_exit_kind_persistence.py --no-cov -q`
Expected: PASS, 5 tests.

- [ ] **Step 8: Commit**

```bash
git add services/trading-engine/app/models/order.py \
        services/trading-engine/app/paper_trading.py \
        services/trading-engine/app/position_manager.py \
        services/trading-engine/app/live_trading.py \
        services/trading-engine/tests/test_exit_kind_persistence.py
git commit -m "feat(trading-engine): persist a structured ExitKind on full closes

positions.exit_reason cannot answer 'which exit killed this trade'. In PAPER
mode the routed reason never reaches the DB at all - the stored value is
synthesized from order.side + order.strategy, collapsing {max-hold, TP, TP3}
into auto_close and {hard stop, trailing stop} into stop_loss_limit.

ExitKind is a second, additive channel on a new nullable column. The prose
exit_reason is deliberately untouched: it is API-visible through
TradeHistoryResponse and the existing rows are not backfilled.

The field lives on OrderBase, not OrderCreate: paper_trading.py:255 does
Order(**order.model_dump()) and Order inherits OrderBase, so an
OrderCreate-only field would be dropped there with no error." -- \
  services/trading-engine/app/models/order.py \
  services/trading-engine/app/paper_trading.py \
  services/trading-engine/app/position_manager.py \
  services/trading-engine/app/live_trading.py \
  services/trading-engine/tests/test_exit_kind_persistence.py
```

---

### Task 6: Every close site supplies its `ExitKind`

Task 5 built the channel. This fills it, and retires substring matching as the *record* — the two predicates may remain as routing, but must no longer be the source of truth.

**Files:**
- Modify: `services/trading-engine/app/auto_trader.py` (`:2583-2595`, `:2856-2888`, `:2974-3052`, `:3054-3075`, `:3184-3465`)
- Test: `services/trading-engine/tests/test_exit_kind_routing.py` (new)
- Modify: `services/trading-engine/tests/test_sizing_caps_phase1.py` (`:450`, `:478-487`, `:511-523`, `:526-535`, `:543`)

**Interfaces:**
- Consumes: `OrderBase.exit_kind`, `PositionManager.close_position(..., exit_kind=)`.
- Produces: `AutoTrader._exit_kind_for(reason: str) -> Optional[ExitKind]` — a single mapping function replacing two divergent inline predicates.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_exit_kind_routing.py`:

```python
"""
Stage 0: one mapping from the producers' reason strings to ExitKind.

Today TWO predicates read one string and they disagree:
  auto_trader.py:2883  -> "stop" or "loss"                (limit vs market close)
  auto_trader.py:3073  -> "stop" or "loss" or "max_hold"  (SL cooldown)

Producers (position_manager.py:731-776, auto_trader.py:2583-2595):
  "Stop loss triggered"   "Trailing stop triggered"   -> both match :2883
  "Take profit triggered" "TP3 - Full exit"           -> neither matches
  "MAX_HOLD_TIME_EXCEEDED (49.0h > 48h)"              -> matches :3073 only
"""

import pytest

from app.models.enums import ExitKind


@pytest.fixture
def mapper():
    from app.auto_trader import AutoTrader

    return AutoTrader._exit_kind_for


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("Stop loss triggered", ExitKind.HARD_STOP),
        ("stop_loss", ExitKind.HARD_STOP),
        ("stop_loss (limit order @ $97.90)", ExitKind.HARD_STOP),
        ("Trailing stop triggered", ExitKind.TRAILING_STOP),
        ("Take profit triggered", ExitKind.TAKE_PROFIT),
        ("TP3 - Full exit", ExitKind.TAKE_PROFIT),
        ("MAX_HOLD_TIME_EXCEEDED (49.0h > 48h)", ExitKind.MAX_HOLD),
        ("manual", ExitKind.MANUAL),
    ],
)
def test_every_live_producer_string_maps(mapper, reason, expected):
    assert mapper(reason) == expected


def test_trailing_is_not_swallowed_by_the_hard_stop_predicate(mapper):
    """'Trailing stop triggered' contains 'stop'. Order of tests matters."""
    assert mapper("Trailing stop triggered") == ExitKind.TRAILING_STOP


def test_non_exit_diagnostics_do_not_map(mapper):
    """check_all_exit_conditions returns these for NON-exits (:752, :755, :776).
    An ExitKind cannot model them and must not invent one."""
    for reason in ("Position not found", "Position not open", "No exit conditions met"):
        assert mapper(reason) is None


def test_unknown_reason_maps_to_none_not_a_guess(mapper):
    assert mapper("something nobody has written yet") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_exit_kind_routing.py --no-cov -q`
Expected: FAIL — `AttributeError: type object 'AutoTrader' has no attribute '_exit_kind_for'`.

- [ ] **Step 3: Add the single mapping function**

In `services/trading-engine/app/auto_trader.py`, add as a `@staticmethod` on `AutoTrader`, placed immediately above `_close_position`:

```python
    @staticmethod
    def _exit_kind_for(reason: Optional[str]) -> Optional[ExitKind]:
        """Map a producer's reason string to a structured ExitKind.

        Stage 0 (2026-08-07). Replaces two divergent inline predicates
        (:2883 tested "stop"/"loss"; :3073 also tested "max_hold") as the
        SOURCE OF TRUTH. Those predicates may remain as ROUTING - they decide
        limit-vs-market close and whether to arm the SL cooldown - but the
        persisted record now comes from here.

        Returns None for anything unrecognised, including the non-exit
        diagnostics check_all_exit_conditions returns ('Position not found',
        'Position not open', 'No exit conditions met'). Never guess: a wrong
        ExitKind is worse than a null one, because the whole point is to be
        able to measure which exit destroys edge.
        """
        if not reason:
            return None
        low = reason.lower()

        # Order matters: "Trailing stop triggered" also contains "stop".
        if "trailing" in low:
            return ExitKind.TRAILING_STOP
        if "max_hold" in low or "max hold" in low:
            return ExitKind.MAX_HOLD
        if "stop" in low or "stop_loss" in low or "loss" in low:
            return ExitKind.HARD_STOP
        if "take profit" in low or "take_profit" in low or low.startswith("tp"):
            return ExitKind.TAKE_PROFIT
        if "reversal" in low:
            return ExitKind.SIGNAL_REVERSAL
        if "liquidat" in low:
            return ExitKind.LIQUIDATION
        if "manual" in low:
            return ExitKind.MANUAL
        return None
```

Import `ExitKind` from `app.models.enums` at the top of `auto_trader.py`.

- [ ] **Step 4: Populate `exit_kind` at both paper close sites**

In `_close_position` (`:2974-3052`), where the `OrderCreate` is built for the paper path, add `exit_kind=self._exit_kind_for(reason),`. Do the same in `_close_position_with_limit_order` (`:3184-3465`) — note it decorates the reason (`f"{reason} (limit order @ ${actual_fill})"`), so call `_exit_kind_for` on the **undecorated** `reason` before decoration.

For the LIVE branches in both methods, pass `exit_kind=self._exit_kind_for(reason)` into `live_engine.close_position`.

- [ ] **Step 5: Leave the routing predicates in place, annotated**

Do **not** delete the `:2883` or `:3073` predicates in this task. Changing what they route is a behavior change with its own risk — in particular max-hold's current escape from the limit-order path is that `_check_position_hold_time` calls `_close_position` directly, bypassing `:2883`. Add above each:

```python
        # Stage 0: this predicate ROUTES (limit vs market close). It is no
        # longer the record — positions.exit_kind comes from _exit_kind_for.
        # Deliberately left divergent from the :3073 cooldown predicate;
        # unifying them changes which exits arm the cooldown.
```

- [ ] **Step 6: Update the tests that assert the literal strings**

`tests/test_sizing_caps_phase1.py` asserts on the tags and prose at `:450`, `:478-487`, `:511-523`, `:526-535`, `:543`. Those strings are unchanged by this task, so the assertions should still hold — **run them and confirm** rather than editing preemptively. Where an assertion now has a stronger form available, add (do not replace) an `exit_kind` assertion beside it.

- [ ] **Step 7: Run the tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_exit_kind_routing.py tests/test_exit_kind_persistence.py tests/test_sizing_caps_phase1.py --no-cov -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/trading-engine/app/auto_trader.py \
        services/trading-engine/tests/test_exit_kind_routing.py \
        services/trading-engine/tests/test_sizing_caps_phase1.py
git commit -m "refactor(trading-engine): one mapping from reason string to ExitKind

Two predicates read one free-text string and disagreed: :2883 matched
'stop'/'loss' to route limit-vs-market closes, :3073 also matched 'max_hold'
to arm the SL cooldown. Neither was the persisted record.

_exit_kind_for is now the single source of truth for what gets stored. The
two predicates stay as routing and stay deliberately divergent - unifying
them changes which exits arm the cooldown, which is a behavior change with
its own risk. Unknown and non-exit strings map to None rather than a guess." -- \
  services/trading-engine/app/auto_trader.py \
  services/trading-engine/tests/test_exit_kind_routing.py \
  services/trading-engine/tests/test_sizing_caps_phase1.py
```

---

### Task 7: Stops actually persist

Prerequisite for Task 8. Without it, stops set after the fill look correct in memory and silently revert to the risk-manager default on the next restart, because `load_positions_from_db` re-reads the create-time DB value.

**Files:**
- Modify: `services/trading-engine/app/repositories.py` (new `PositionRepository.update_stops`)
- Modify: `services/trading-engine/app/position_manager.py` (`set_position_stops` `:778-830`)
- Test: `services/trading-engine/tests/test_stops_persistence.py` (new)

**Interfaces:**
- Consumes: nothing from Tasks 3–6.
- Produces: `PositionRepository.update_stops(position_id: UUID, stop_loss: Optional[Decimal] = None, take_profit: Optional[Decimal] = None) -> None` (async). `set_position_stops` stays **synchronous** and fires the persist via `_spawn_persist`.

Only `stop_loss` and `take_profit` persist. `take_profit_1/2/3`, `trailing_stop`, `trailing_stop_enabled`, `tp1/2/3_hit`, `highest_price` and `lowest_price` have **no columns** and are not restored today; adding them is a schema decision outside this plan's scope. Say so in the docstring so the gap is documented rather than forgotten.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_stops_persistence.py`:

```python
"""
Stage 0: set_position_stops must persist, not just mutate memory.

Before this task: set_position_stops (position_manager.py:778-830) mutated the
in-memory Position and returned. PositionRepository had no update-stops method
at all, and stop_loss reached the DB at exactly one line repo-wide
(repositories.py:73, inside create()). So every post-fill refinement - the
ATR/regime stops at auto_trader.py:2383, the ATR trailing update at :2786, the
breakeven stop at :2841 - was discarded on restart and replaced by the flat
default_stop_loss_pct value written at INSERT time.
"""

import asyncio
from decimal import Decimal

import pytest

from app.models.enums import PositionSide
from tests.test_posted_margin_ledger import _drain_tasks, stack  # noqa: F401


async def test_set_position_stops_persists(stack):
    manager, repo = stack.manager, stack.position_repo
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("72.68"),
        quantity=Decimal("0.3"),
    )
    await _drain_tasks()

    manager.set_position_stops(
        position_id=pos.id,
        stop_loss=Decimal("70.10"),
        take_profit=Decimal("77.20"),
    )
    await _drain_tasks()

    repo.update_stops.assert_awaited_once()
    kwargs = repo.update_stops.await_args.kwargs
    assert kwargs["stop_loss"] == Decimal("70.10")
    assert kwargs["take_profit"] == Decimal("77.20")


async def test_set_position_stops_is_still_synchronous(stack):
    """Callers do not await it - auto_trader.py:2383 and :2786 call it bare."""
    manager = stack.manager
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("72.68"),
        quantity=Decimal("0.3"),
    )
    result = manager.set_position_stops(position_id=pos.id, stop_loss=Decimal("70"))
    assert not asyncio.iscoroutine(result)
    assert result.stop_loss == Decimal("70")
    await _drain_tasks()


async def test_partial_update_does_not_null_the_other_side(stack):
    manager, repo = stack.manager, stack.position_repo
    pos = manager.create_position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("72.68"),
        quantity=Decimal("0.3"),
        stop_loss=Decimal("71"),
        take_profit=Decimal("76"),
    )
    await _drain_tasks()

    manager.set_position_stops(position_id=pos.id, stop_loss=Decimal("73"))
    await _drain_tasks()

    kwargs = repo.update_stops.await_args.kwargs
    assert kwargs["stop_loss"] == Decimal("73")
    assert kwargs.get("take_profit") is None    # omitted, not overwritten
    assert manager.positions[pos.id].take_profit == Decimal("76")
```

Add `repo.update_stops = AsyncMock()` to `_mock_position_repo()` in `tests/test_posted_margin_ledger.py` (it is the shared fixture source).

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_stops_persistence.py --no-cov -q`
Expected: FAIL — `AssertionError: Expected 'update_stops' to have been awaited once. Awaited 0 times.`

- [ ] **Step 3: Add the repository method**

In `services/trading-engine/app/repositories.py`, in `PositionRepository`, next to `update_price`, following the `close()` optional-kwarg idiom exactly:

```python
    async def update_stops(
        self,
        position_id: UUID,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ):
        """Persist refined stop / target levels for an open position.

        Stage 0 (2026-08-07). Before this existed, stop_loss reached the
        database at exactly one line repo-wide — inside create() — so every
        post-fill refinement was lost on restart and replaced by the
        risk-manager default written at INSERT time.

        Only the two columns that exist are written. take_profit_1/2/3,
        trailing_stop, trailing_stop_enabled, tp1/2/3_hit, highest_price and
        lowest_price have NO columns on positions and are still lost on
        restart — a schema decision deliberately out of this change's scope.

        A None argument is OMITTED from the UPDATE, never written as NULL.
        """
        values = {"updated_at": datetime.now(timezone.utc)}
        if stop_loss is not None:
            values["stop_loss"] = stop_loss
        if take_profit is not None:
            values["take_profit"] = take_profit
        if len(values) == 1:
            return

        try:
            async with self.db.get_async_session() as session:
                stmt = (
                    update(DBPosition)
                    .where(DBPosition.position_id == position_id)
                    .values(**values)
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update stops for position {position_id}: {e}")
            raise
```

- [ ] **Step 4: Fire it from `set_position_stops`**

In `services/trading-engine/app/position_manager.py`, at the end of `set_position_stops`, immediately before `return position`:

```python
        # Stage 0 (2026-08-07): persist. This method used to be memory-only,
        # so load_positions_from_db re-read the create-time risk-manager
        # default and every post-fill refinement vanished on restart.
        _spawn_persist(
            self.position_repo.update_stops(
                position_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
            ),
            "position stops update",
        )
```

The method stays synchronous — `auto_trader.py:2383`, `:2786`, `:2841` and `:3764` all call it bare.

- [ ] **Step 5: Run the tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_stops_persistence.py tests/test_posted_margin_ledger.py --no-cov -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/trading-engine/app/repositories.py \
        services/trading-engine/app/position_manager.py \
        services/trading-engine/tests/test_stops_persistence.py \
        services/trading-engine/tests/test_posted_margin_ledger.py
git commit -m "fix(trading-engine): persist refined stops instead of only mutating memory

set_position_stops mutated the in-memory Position and returned; there was no
update-stops method on PositionRepository at all, and stop_loss reached the
database at exactly one line repo-wide - inside create(). Every post-fill
refinement (ATR/regime stops, trailing updates, the breakeven move) was
discarded on the next restart, because load_positions_from_db re-reads the
create-time risk-manager default.

Only stop_loss and take_profit persist. take_profit_1/2/3, trailing_stop and
the tp*_hit flags have no columns and are still lost on restart - documented
in the docstring rather than silently left as a surprise." -- \
  services/trading-engine/app/repositories.py \
  services/trading-engine/app/position_manager.py \
  services/trading-engine/tests/test_stops_persistence.py \
  services/trading-engine/tests/test_posted_margin_ledger.py
```

---

### Task 8: The ensemble path applies its own stop and target

**Files:**
- Modify: `services/trading-engine/app/auto_trader.py` (`_check_and_trade_ensemble`, after the fill at `~:4515`)
- Test: `services/trading-engine/tests/test_ensemble_stops_applied.py` (new)

**Interfaces:**
- Consumes: `PositionManager.set_position_stops` (now persisting, Task 7).
- Produces: `AutoTrader._ensemble_stops_are_consistent(action, entry, stop_loss, take_profit) -> bool`.

Do **not** add `stop_loss=`/`take_profit=` to the `OrderCreate` at `:4504` — neither `OrderBase` nor `OrderCreate` declares those fields and pydantic v2 `extra='ignore'` drops them with no error. The result would be a clean run, green logs, a filled order, and still no stops.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_ensemble_stops_applied.py`:

```python
"""
Stage 0: the ensemble path must apply the stop and target its own strategy
computed, and must refuse an inverted pair.

Before this task, ens_signal.stop_loss / take_profit were read exactly twice -
both inside the Telegram notify_trade_open call at auto_trader.py:4550-4551.
The position itself fell through to risk_manager.calculate_stop_loss, i.e. the
flat default_stop_loss_pct=2.0 / default_take_profit_pct=4.0. All 19 live rows
show exactly entry x0.98 and x1.04, while the aggregator was concurrently
emitting per-symbol ATR levels (BNB SL=587.27, BTC SL=63788.76 TP=67092.18).
So the operator got a Telegram message quoting levels the position did not have.

Inversion guard: EnsembleSignal inherits stop_loss/take_profit verbatim from
whichever leg had the largest absolute contribution
(multi_strategy_ensemble.py:277-284), with no check that they sit on the
correct side of entry for the ensemble's chosen action. A weighted-vote BUY
whose dominant leg fired SELL yields an inverted pair. Precedent: the Jan 2026
inverted-R/R bug (380a674).
"""

from decimal import Decimal

import pytest

from app.models.enums import SignalAction


@pytest.fixture
def guard():
    from app.auto_trader import AutoTrader

    return AutoTrader._ensemble_stops_are_consistent


def test_valid_long_pair_passes(guard):
    assert guard(SignalAction.BUY, 72.68, 71.22, 75.58) is True


def test_valid_short_pair_passes(guard):
    assert guard(SignalAction.SELL, 602.69, 614.74, 578.58) is True


def test_inverted_long_pair_is_rejected(guard):
    """Stop ABOVE entry on a LONG - the dominant leg fired the other way."""
    assert guard(SignalAction.BUY, 72.68, 75.58, 71.22) is False


def test_inverted_short_pair_is_rejected(guard):
    assert guard(SignalAction.SELL, 602.69, 578.58, 614.74) is False


def test_stop_equal_to_entry_is_rejected(guard):
    """A zero-distance stop makes R undefined and every R-multiple infinite."""
    assert guard(SignalAction.BUY, 72.68, 72.68, 75.58) is False


def test_non_positive_levels_are_rejected(guard):
    assert guard(SignalAction.BUY, 72.68, 0.0, 75.58) is False
    assert guard(SignalAction.BUY, 72.68, 71.22, 0.0) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_ensemble_stops_applied.py --no-cov -q`
Expected: FAIL — `AttributeError: type object 'AutoTrader' has no attribute '_ensemble_stops_are_consistent'`.

- [ ] **Step 3: Add the guard**

In `services/trading-engine/app/auto_trader.py`, as a `@staticmethod` on `AutoTrader`, immediately above `_check_and_trade_ensemble`:

```python
    @staticmethod
    def _ensemble_stops_are_consistent(
        action: SignalAction,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> bool:
        """True if the stop/target pair is on the correct side of entry.

        Stage 0 (2026-08-07). EnsembleSignal inherits both levels verbatim
        from whichever leg contributed most in absolute terms
        (multi_strategy_ensemble.py:277-284) and validates nothing. A
        weighted-vote BUY whose dominant leg fired SELL produces an inverted
        pair — the Jan 2026 inverted-R/R bug (380a674) is the precedent for
        why that must never reach a position.

        A stop exactly at entry is also rejected: R would be zero, making
        every downstream R-multiple infinite.
        """
        if stop_loss <= 0 or take_profit <= 0 or entry_price <= 0:
            return False
        if action == SignalAction.BUY:
            return stop_loss < entry_price < take_profit
        if action == SignalAction.SELL:
            return take_profit < entry_price < stop_loss
        return False
```

- [ ] **Step 4: Apply the stops after the fill**

In `_check_and_trade_ensemble`, immediately after the `self.total_trades_executed += 1` / execution log block and **before** the leg-attribution block, insert. Note `set_position_stops` is synchronous — do not `await` it — and mirror the `_execute_trade_with_setup:2370-2408` shape: guarded on `executed_order.position_id`, wrapped in `try/except` so a stops failure cannot unwind a filled order.

```python
            # ================================================================
            # Stage 0 (2026-08-07): apply the ensemble's OWN stop/target.
            # Previously these were read only inside the Telegram call below,
            # so the position carried risk_manager's flat 2%/4% default while
            # the operator was told an ATR level. Do NOT try to do this by
            # adding stop_loss=/take_profit= to the OrderCreate above —
            # OrderBase declares neither and pydantic v2 extra='ignore' drops
            # them silently, with no error and no stops.
            # ================================================================
            if executed_order.position_id:
                if not self._ensemble_stops_are_consistent(
                    ens_signal.action,
                    float(current_price),
                    float(ens_signal.stop_loss),
                    float(ens_signal.take_profit),
                ):
                    logger.error(
                        f"[ENSEMBLE][STOPS] {symbol}: INCONSISTENT stop/target for "
                        f"{ens_signal.action.value} — entry={current_price} "
                        f"sl={ens_signal.stop_loss} tp={ens_signal.take_profit}. "
                        f"Dominant leg fired {ens_signal.leg_actions}. Keeping the "
                        f"risk-manager default; NOT applying the ensemble levels."
                    )
                else:
                    try:
                        position_mgr.set_position_stops(
                            position_id=executed_order.position_id,
                            stop_loss=Decimal(str(ens_signal.stop_loss)),
                            take_profit=Decimal(str(ens_signal.take_profit)),
                            enable_trailing=False,
                        )
                        logger.info(
                            f"[ENSEMBLE][STOPS] {symbol}: applied SL="
                            f"{ens_signal.stop_loss} TP={ens_signal.take_profit} "
                            f"(entry {current_price})"
                        )
                    except Exception as stop_error:
                        logger.warning(
                            f"[ENSEMBLE][STOPS] {symbol}: failed to apply stops "
                            f"— position keeps the risk-manager default: {stop_error}"
                        )
```

Deliberately **not** raising on inconsistency: the order is already filled, and an unstopped position is worse than a default-stopped one. The `logger.error` is the alarm.

- [ ] **Step 5: Run the tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_ensemble_stops_applied.py tests/test_stops_persistence.py --no-cov -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/trading-engine/app/auto_trader.py \
        services/trading-engine/tests/test_ensemble_stops_applied.py
git commit -m "fix(trading-engine): ensemble path applies its own stop and target

ens_signal.stop_loss / take_profit were read exactly twice, both inside the
Telegram notification - so the operator was told an ATR level while the
position carried the flat risk-manager 2%/4% default. All 19 live rows are
exactly entry x0.98 and x1.04, while the aggregator was concurrently emitting
per-symbol ATR stops.

Applied via set_position_stops, not via OrderCreate: OrderBase declares no
stop fields and pydantic v2 extra='ignore' would drop them with no error.

Added a side-consistency guard - EnsembleSignal inherits both levels verbatim
from the dominant leg with no validation, so a weighted-vote BUY whose
dominant leg fired SELL yields an inverted pair. Precedent: 380a674." -- \
  services/trading-engine/app/auto_trader.py \
  services/trading-engine/tests/test_ensemble_stops_applied.py
```

---

### Task 9: The ensemble path enforces the gates it skips

**Files:**
- Modify: `services/trading-engine/app/auto_trader.py` (`_check_and_trade_ensemble`, gate block before sizing)
- Test: `services/trading-engine/tests/test_ensemble_gates.py` (new)

**Interfaces:**
- Consumes: existing `_check_daily_trade_limit`, `_claim_open_slot`, `_release_open_slot`, `portfolio_heat_manager.can_open_trade`, `settings.min_signal_confidence`, `settings.short_min_confidence`, `settings.allowed_trade_sides`, `settings.short_trading_enabled`.
- Produces: `AutoTrader._ensemble_passes_signal_gates(symbol, ens_signal) -> bool` — one sync method holding the confidence and side gates, so the 8-early-return method gains one call, not four.

- [ ] **Step 1: Write the failing test**

Create `services/trading-engine/tests/test_ensemble_gates.py`:

```python
"""
Stage 0: the ensemble path enforces the gates every other entry path does.

Live evidence: trades.signal_confidence on ensemble entry legs reads
0.3804, 0.2995, 0.2680, 0.2818, 0.2960, 0.2357, 0.1730, 0.2695 - SEVEN of
eight below the configured min_signal_confidence of 0.30. The floor is real
(config.py:408) but it is read in exactly one function, RiskManager.
validate_signal, whose only production caller is the REST /signal endpoint.
No autonomous path has ever consulted it.
"""

from types import SimpleNamespace

import pytest

from app.models.enums import SignalAction


def _signal(action=SignalAction.BUY, confidence=0.55):
    return SimpleNamespace(
        action=action,
        confidence=confidence,
        stop_loss=71.0,
        take_profit=76.0,
        position_size_pct=0.10,
        leg_actions={"simple_rsi": "BUY"},
    )


@pytest.fixture
def trader(monkeypatch):
    from app.auto_trader import AutoTrader

    t = AutoTrader.__new__(AutoTrader)
    t.settings = SimpleNamespace(
        min_signal_confidence=0.30,
        short_min_confidence=0.70,
        short_trading_enabled=True,
        allowed_trade_sides="BOTH",
    )
    t.total_trades_rejected = 0
    return t


def test_long_below_the_confidence_floor_is_rejected(trader):
    assert trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.1730)) is False


def test_long_above_the_floor_passes(trader):
    assert trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.55)) is True


def test_short_uses_the_higher_short_floor(trader):
    """0.55 clears min_signal_confidence but not short_min_confidence=0.70."""
    sig = _signal(action=SignalAction.SELL, confidence=0.55)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_short_above_the_short_floor_passes(trader):
    sig = _signal(action=SignalAction.SELL, confidence=0.75)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is True


def test_short_blocked_when_shorts_disabled(trader):
    trader.settings.short_trading_enabled = False
    sig = _signal(action=SignalAction.SELL, confidence=0.95)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_short_blocked_by_allowed_trade_sides(trader):
    trader.settings.allowed_trade_sides = "LONG_ONLY"
    sig = _signal(action=SignalAction.SELL, confidence=0.95)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_missing_short_floor_setting_does_not_silently_open_the_gate(trader):
    """auto_trader.py:3919 uses getattr(..., 0.0) — a rename would disable the
    gate rather than raise. The ensemble copy must fail CLOSED."""
    del trader.settings.short_min_confidence
    sig = _signal(action=SignalAction.SELL, confidence=0.35)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_gate_rejections_increment_the_rejection_counter_once(trader):
    trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.1))
    assert trader.total_trades_rejected == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/trading-engine && python3 -m pytest tests/test_ensemble_gates.py --no-cov -q`
Expected: FAIL — `AttributeError: 'AutoTrader' object has no attribute '_ensemble_passes_signal_gates'`.

- [ ] **Step 3: Add the consolidated gate**

In `services/trading-engine/app/auto_trader.py`, as a method on `AutoTrader` above `_check_and_trade_ensemble`:

```python
    def _ensemble_passes_signal_gates(self, symbol: str, ens_signal) -> bool:
        """Confidence and side gates for the ensemble entry path.

        Stage 0 (2026-08-07). These exist on the default path at :3895-3934
        and were never applied here. Live evidence: seven of eight ensemble
        entries fired below min_signal_confidence=0.30, at confidences down
        to 0.1730.

        Consolidated into one method because _check_and_trade_ensemble already
        has 8 early returns; four more inline gates would make the
        _release_open_slot bookkeeping in the next step unmanageable.

        Fails CLOSED on a missing short floor. The default path uses
        getattr(self.settings, "short_min_confidence", 0.0), so a rename or
        typo there silently sets the floor to zero rather than raising — that
        is a footgun, not a pattern to copy.
        """
        conf = float(ens_signal.confidence)
        action = ens_signal.action

        floor = float(getattr(self.settings, "min_signal_confidence", 0.30))
        if conf < floor:
            logger.info(
                f"[ENSEMBLE][GATE] {symbol}: confidence {conf:.4f} < "
                f"min_signal_confidence {floor:.2f} — rejecting"
            )
            self.total_trades_rejected += 1
            return False

        if action == SignalAction.SELL:
            allowed = str(getattr(self.settings, "allowed_trade_sides", "BOTH")).upper()
            if allowed not in ("BOTH", "SHORT_ONLY"):
                logger.info(
                    f"[ENSEMBLE][GATE] {symbol}: SHORT blocked by "
                    f"allowed_trade_sides={allowed} — rejecting"
                )
                self.total_trades_rejected += 1
                return False

            if not getattr(self.settings, "short_trading_enabled", False):
                logger.info(
                    f"[ENSEMBLE][GATE] {symbol}: SHORT blocked — "
                    f"short_trading_enabled is False"
                )
                self.total_trades_rejected += 1
                return False

            short_floor = getattr(self.settings, "short_min_confidence", None)
            if short_floor is None:
                logger.error(
                    f"[ENSEMBLE][GATE] {symbol}: short_min_confidence is not "
                    f"configured — refusing the SHORT rather than defaulting "
                    f"the floor to zero"
                )
                self.total_trades_rejected += 1
                return False
            if conf < float(short_floor):
                logger.info(
                    f"[ENSEMBLE][GATE] {symbol}: SHORT confidence {conf:.4f} < "
                    f"short_min_confidence {float(short_floor):.2f} — rejecting"
                )
                self.total_trades_rejected += 1
                return False

        return True
```

- [ ] **Step 4: Call it, plus the daily limit and portfolio heat**

In `_check_and_trade_ensemble`, immediately after the existing symbol-cooldown check and **before** the leverage/sizing block:

```python
            if not self._ensemble_passes_signal_gates(symbol, ens_signal):
                return

            if not self._check_daily_trade_limit():
                logger.info(f"[ENSEMBLE][GATE] {symbol}: daily trade limit reached")
                self.total_trades_rejected += 1
                return

            # portfolio_heat_manager.can_open_trade is SYNCHRONOUS. Pass side=
            # — the existing call site at :1831 omits it, so the pyramiding /
            # no-hedging branch (portfolio_heat.py:499-502) never fires there.
            heat_ok, heat_reason = self.portfolio_heat_manager.can_open_trade(
                symbol=symbol,
                proposed_risk_pct=float(ens_signal.position_size_pct) * 100.0,
                side="LONG" if ens_signal.action == SignalAction.BUY else "SHORT",
            )
            if not heat_ok:
                logger.info(f"[ENSEMBLE][GATE] {symbol}: portfolio heat — {heat_reason}")
                self.total_trades_rejected += 1
                return
```

Confirm the exact signature and return shape before writing the call:

```bash
sed -n '455,480p' services/trading-engine/app/trading_enhancements/portfolio_heat.py
sed -n '1419,1440p' services/trading-engine/app/auto_trader.py
```

- [ ] **Step 5: Close the open-slot race**

The ensemble path guards duplicates with a non-atomic `any(p.symbol == symbol for p in position_mgr.get_open_positions())` scan — exactly the race `_claim_open_slot` exists to close. Replace that scan with the claim, and add the release.

Because the method has **8 early returns**, the claim must be paired with a `try/finally`. Do not add a bare `self.total_trades_rejected += 1` at the call site — `_claim_open_slot` already increments internally before returning False:

```python
            if not await self._claim_open_slot(symbol):
                # _claim_open_slot already incremented total_trades_rejected.
                return

            opened = False
            try:
                ... entire remainder of the method ...
                opened = True
            finally:
                self._release_open_slot(symbol, opened=opened)
```

Verify the exact `_release_open_slot` signature first (`auto_trader.py:1661-1781`) — the setup path's usage at `:1800` is the reference.

- [ ] **Step 6: Run the tests**

Run: `cd services/trading-engine && python3 -m pytest tests/test_ensemble_gates.py tests/test_ensemble_stops_applied.py tests/test_sizing_caps_phase1.py --no-cov -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite and compare against the known baseline**

Run: `cd services/trading-engine && python3 -m pytest tests/ --no-cov -q 2>&1 | tail -30`
Expected: the 13 known pre-existing failures (2 connector-envelope, 11 `pairs_trading` pandas `freq='H'`) and **nothing else**. Any additional failure is a regression from this plan — fix it before committing rather than accepting a new baseline.

- [ ] **Step 8: Commit**

```bash
git add services/trading-engine/app/auto_trader.py \
        services/trading-engine/tests/test_ensemble_gates.py
git commit -m "fix(trading-engine): ensemble path enforces the five gates it skipped

Live evidence: seven of eight ensemble entries fired below
min_signal_confidence=0.30, down to 0.1730. The floor is real (config.py:408)
but is read only by RiskManager.validate_signal, whose sole production caller
is the REST /signal endpoint - no autonomous path ever consulted it.

Adds min_signal_confidence, allowed_trade_sides, short_trading_enabled,
short_min_confidence, _check_daily_trade_limit and portfolio heat. Replaces
the non-atomic duplicate-symbol scan with _claim_open_slot plus a
try/finally release - the method has 8 early returns and would otherwise
leak the slot.

The short floor fails CLOSED here. The default path's
getattr(..., 'short_min_confidence', 0.0) silently disables the gate on a
rename; that is a footgun, not a pattern to copy.

can_open_trade is called WITH side= - the existing call site at :1831 omits
it, so its pyramiding/no-hedging branch never fires." -- \
  services/trading-engine/app/auto_trader.py \
  services/trading-engine/tests/test_ensemble_gates.py
```

---

## Completion criteria

Stage 0 is done when all of the following hold. Per CLAUDE.md §7, an HTTP 200 is not proof.

1. `cd services/trading-engine && python3 -m pytest tests/ --no-cov -q` introduces **no new failure family** against the 2026-08-08 baseline (1638 passed / 36 failed / 795 skipped — see Global Constraints), **and** every test file this plan touched passes **in isolation**. Do not gate on the raw count; it drifts with unrelated work and the bulk of the 36 is singleton pollution that disappears in isolated runs.
2. The invariant query returns `t` — all three terms, realized summed over **all** positions:
   ```bash
   docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
   SELECT (p.cash_balance
           + COALESCE((SELECT SUM(posted_margin) FROM positions WHERE status='OPEN'),0)
           + COALESCE((SELECT SUM(entry_fee * remaining_quantity / NULLIF(quantity,0))
                       FROM positions WHERE status='OPEN'),0)
           = p.initial_balance
           + COALESCE((SELECT SUM(realized_pnl) FROM positions),0)) AS invariant_holds
   FROM portfolios p WHERE p.portfolio_id='paper_trading';"
   ```
3. `docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine` is followed by a `Restored balance` log line agreeing with the DB, and no `posted_margin is NULL` errors.
4. A `SELECT` proving a newly-opened position carries a non-default `stop_loss` (not `entry × 0.98`), a non-zero `posted_margin`, and a non-NULL `entry_signal_confidence`.
5. A `SELECT` proving a newly-closed position carries a non-NULL `exit_kind`.
6. `.planning/evidence/cash-ledger-reconciliation-2026-08-07.md` exists and is committed.

**Do not resume the auto-trader until criteria 1–3 pass.** Resume is two steps: `rm safety/EMERGENCY_STOP`, then `POST /api/trading/start`. A file-triggered halt sets `is_running=False` and exits the loop; it does not auto-restart.

## What Stage 0 explicitly does not do

It creates no edge. The signal is measured at chance (H4 REJECT: 49.07% directional accuracy, DSR 0.0, n=12,387) and its gross edge of 0.0488%/trade is 2.3–4.1× smaller than the 21–31 bp round-trip cost. Stage 0 makes the instrument honest so the next plan — the cost model and the hurdle-first screen, `docs/superpowers/plans/2026-08-07-cost-model-and-edge-screen.md` — can render a verdict worth believing.

Deferred to Stage 2 and untouched here: funding accrual (E10), the 1h-bar price source and optimistic stop fills (E9), exit legs bypassing min-notional and qty_step (E6), the self-disabling trailing stop (E7) and its mispriced fill (E8), the 0.8:1 TP1 ladder geometry (E11), partial-exit P&L reported gross (E12), `PerformanceMetrics` never computing PF/avg-win/drawdown (E13), and the BNB tick size of 0.01 against the venue's 0.10 (E14).
