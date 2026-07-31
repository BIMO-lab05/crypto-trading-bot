---
id: 260731-ooe
slug: fix-restart-balance-rebase
date: 2026-07-31
status: in-progress
---

# Fix restart cash fabrication + max-hold clock reset (audit DL-2 / T-8)

## Symptom

Across the 2026-07-31 14:26 restart, with **zero trades in between**, the paper
balance moved:

```
2026-07-30 20:12:38  ✓ SHORT closed: ETHUSDT ... Balance: $80.7027
2026-07-31 14:26:08  Adjusted balance: $83.48        <-- restart
2026-07-31 14:26:11  KillSwitch balance initialized: $83.48
```

Gap = **2.78133** = realized P&L 2.5737 + close commissions 0.10511 + open
commissions of the two closed legs 0.10254. Exact to the cent.

## Root cause

`paper_trading.py:104`:

```python
self.balance = self.initial_balance - total_position_cost
```

It reconstructs cash from `initial_balance` minus the cost of *currently open*
positions. It never applies realized P&L, and never applies any commission ever
paid on a closed leg. So every restart resets the book toward par.

Consequence beyond cosmetics: `auto_trader.py:853` seeds the kill switch from
this number. An account bleeding toward the 20% drawdown threshold is nudged
back toward par by any restart or crash-loop, and the drawdown breaker re-arms
against the fabricated baseline. In LIVE that silently disarms it.

## Why the obvious fix is wrong

"Just read `portfolios.cash_balance`" is incomplete. That column is written
**only on position close** (`position_manager.py:348`, inside `close_position`)
— never on open. So the stored value is the engine balance *as of the last
close*. Any position opened after that close has had its margin debited in
memory but not persisted.

Correct reconstruction:

```
balance = portfolios.cash_balance
          - (margin + commission) for positions opened AFTER portfolios.updated_at
```

That needs `Position.opened_at` to be real — which is defect T-8.

## T-8 must be fixed first (and is a real bug in its own right)

`position_manager.py:782-792` rebuilds `Position(...)` without `opened_at` or
`realized_pnl`, so `models/position.py:65` `default_factory=now()` applies.
Verified:

```
DB:  position_id 826f5b17... opened_at 2026-07-29 20:00:42.322091
API: "opened_at": "2026-07-31T14:26:08.069372Z"     <-- restart time
```

Both columns exist in the live schema and are simply not read. Independently of
DL-2 this defeats the 48h max-hold force-close (`auto_trader.py:2429-2430`): a
position survives indefinitely as long as the service restarts inside each
window. That is the 185h-SOLUSDT failure the Jan 2026 fix (`380a674`) targeted.

## Changes

1. `position_manager.load_positions_from_db` — restore `opened_at` (DB column is
   `timestamp without time zone`; attach UTC so comparisons against
   timezone-aware `now()` don't raise) and `realized_pnl`.
2. `paper_trading.sync_balance_with_positions` — seed from the persisted
   `cash_balance` and deduct only positions opened after the portfolio row's
   last write. Fall back to the old reconstruction if the portfolio row is
   unreadable, and say so loudly rather than silently guessing.

## Out of scope

- `remaining_quantity` / `tp1_hit` / `highest_price` are **not columns in the
  live `positions` table** (audit DL-6), so partial-exit state still cannot
  survive a restart. That needs a migration; filed, not done here.
- Persisting cash on *open* as well as close. That would make the reconstruction
  trivial, but it widens the write path on the hot trade loop — deliberately
  left as a follow-up so this change stays reviewable.

## Verification

- Baseline `pytest services/trading-engine/tests/` is 36 failed / 1449 passed /
  842 skipped. Must not regress.
- Unit-level: assert a restart with a known `cash_balance` and pre-existing
  positions reproduces the persisted balance, not `initial_balance - cost`.
- **Not deployed.** Deploying requires a trading-engine restart, which mutates
  the live paper book. Operator's call.
