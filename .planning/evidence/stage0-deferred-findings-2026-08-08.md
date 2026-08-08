# Deferred findings — Stage 0

Triage list for the final whole-branch review. Nothing here blocked a task; each was
found during Stage 0, judged out of the task's scope, and recorded rather than silently
dropped. Ordered by my estimate of value, not by when they were found.

---

## 1. `test_accounting_fixes.py` poisons ~21 of 36 suite failures and contributes zero tests

**Controller-verified.** `services/trading-engine/tests/standalone/test_accounting_fixes.py`
executes `sys.modules["app.repositories"] = repo_stub` **at module import time** (~line 59),
replacing `PositionRepository` / `TradeRepository` / `PortfolioRepository` with a bare
`_FakeRepoClasses`. pytest merely *importing* the file poisons `app.repositories` for every
module collected afterwards in the same session — the direct cause of the
`'_FakeRepoClasses' object has no attribute 'db'` failures in `tests/unit/test_repositories.py`.

And `--collect-only` on that file returns **`collected 0 items`**.

So one file contributing no coverage causes roughly 21 of the suite's 36 failures.
`tests/unit/test_repositories.py` passes **21/21 in isolation**; `test_signal_cache.py`
passes **33/33** alone.

**Proposed fix (~10 minutes):** stop pytest collecting it — rename off the `test_*.py`
pattern, or guard the `sys.modules` install behind `if __name__ == "__main__"`.
**Why it matters:** it would make the suite's real signal visible for the first time. Every
"36 failures" figure in this ledger is mostly this one file.

---

## 2. `load_positions_from_db` fails silently to zero positions

`position_manager.py:943` wraps the **entire** hydration loop in
`except Exception: logger.error(...); return 0`. One malformed row and the engine boots
believing it has **zero open positions**: none monitored, none stopped, none max-hold closed,
and `sync_balance_with_positions` then reconstructs cash against an empty book.

Surfaced by Task 2's fixture failure, which presented exactly as `0 loaded` with no error
reaching the caller. Not blocking — the Stage 0 columns are `NOT NULL DEFAULT`, so real rows
cannot trigger it — but it is a live silent-failure defect of the same family as everything
Stage 0 repaired.

---

## 3. `_exit_kind_for` will mislabel a future kill-switch close

The `"loss"` substring branch would stamp a hypothetical *"daily loss limit"* kill-switch
close as `HARD_STOP`. The Task 6 implementer enumerated all three non-recursive callers of
the two close methods and confirmed **no such caller exists today**, so this is a standing
design risk rather than a defect. It matters because `exit_kind` exists specifically to
measure which exit destroys edge — a mislabelled row corrupts that measurement silently.

---

## 4. An invalid `exit_kind` string raises on read

`handlers/trades.py:73` does `ExitKind(db_pos.exit_kind)`. Verified:
`ExitKind('LEGACY_JUNK')` raises `ValueError`, uncaught — which would break
`db_position_to_app_position` and therefore `GET` trade-history for that row.

Unreachable today: the only writer is `exit_kind.value if exit_kind else None`, always a real
member or NULL, and the column deliberately has no CHECK constraint (documented at
`database/models.py:140-142`, dodging the stale-CHECK trap that already burns
`trades.order_type`). A future member rename or a manual edit makes it live.
**Consider:** fall back to `None` with a log rather than raising.

---

## 5. LIVE positions open with `posted_margin = 0`

`live_trading.py` opens without stamping margin and closes without consuming it. No cash is
fabricated — LIVE has no simulated ledger, the exchange holds the margin — but it makes
zero-margin-on-an-OPEN-position **reachable**, which is the premise Task 3's new guard rests
on. The Task 3 reviewer established this fires on the **first restart after the first live
fill**, since `load_positions_from_db` runs unconditionally at lifespan startup
(`app/lifespan/data.py:55`), not gated on `TRADING_MODE`.

Log noise rather than corruption, and moot while LIVE is mechanically impossible at $100
(2% cap = $2 < $5 venue minimum). Cheapest fix: have the live path stamp `posted_margin` too
— it is the same computation.

---

## 6. Migration 008 cutoff comment omits the fact that pins it

The `2026-08-07 18:00:00+00` cutoff is justified in the header as "after every backfilled row,
before the fix landed" (~25h of slack). The fact that actually pins it is that the auto-trader
halted at **2026-08-07 16:55 UTC**, so no row can exist opened after that. Worth one sentence
for the six-month reader.

---

## 7. Unexplained `+3` in the intermediate test-count accounting

Between the post-Task-3 measurement (1650) and the post-Task-5 measurement (1658), the suite
gained 8 passing tests while commit `fa2d0e7` adds exactly **5** test functions (verified by
diff) and `test_paper_slippage.py` gained only 3 *lines*, no tests.

**Bounded, not ignored:** no failure family changed across the entire branch, every touched
file passes in isolation, and the end state reconciles across three independent measurements
(1669 → 1672 → 1678, each delta matching its task's new tests exactly). Recorded as
unexplained rather than given a manufactured cause.

---

## 8. `live_trading.py` diff carries formatter reflow

+89/-44 for a 3-line semantic change in Task 5. The reviewer verified the dropped `OrderType`
import is genuinely unused. Blame-noise, not correctness.
