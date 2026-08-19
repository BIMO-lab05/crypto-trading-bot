# Cash-ledger repair — APPLIED 2026-08-08

Owner authorized the write directly (the permission gate had denied the subagent; the owner
instruction is the authorization that gate exists to require).

Script: `database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql`
Backup: `.planning/evidence/backups/pre-cash-repair-2026-08-07.sql`
  — verified before applying: 3 COPY blocks (portfolios, positions, trades), the portfolios
    row carrying the pre-repair `255.97305338`, and all 19 position rows.

## Re-derived, not copied

Recomputed from live state immediately before the write:

```
 initial | cash_now     | realized_all | open_margin | unconsumed_fee
 100.00  | 255.97305338 | -0.28337306  | 20.63558000 | 0.011349574
 -> coherent cash = 79.06969737
```

Matches the figure Task 1 derived independently on 2026-08-07. Note `realized_all` sums over
**ALL** positions (-0.28337306), not `portfolios.realized_pnl` (-0.41002416) — the
+0.1266511 gap is position 64's partial exit, which accrues onto a still-OPEN row and which
`record_position_close` never writes.

## Applied

Engine stopped first so nothing could write the ledger mid-repair.

```
BEFORE  cash_balance = 255.97305338
UPDATE 1 / COMMIT
AFTER   cash_balance = 79.06969737
        residual = 0.000000004      invariant_holds = t
```

The 4e-9 residual is the predicted artefact of an 8dp column storing a 9dp computation. It is
exactly why the original exact-equality check was wrong: `=` would have returned `f` on this
correct repair, and the plan then said "roll back and stop". The tolerance form (1e-6, with the
raw residual printed beside it) is what makes this verifiable.

## Proven end-to-end

Engine recreated; `sync_balance_with_positions` reconstructed the value from the repaired row:

```
Balance restored from persisted ledger: $79.07 (as of 2026-08-08 18:51:53)
  Open positions: 2, of which opened after last write: 0
  Restored balance: $79.07
CRITICAL - EMERGENCY_STOP file present at /app/safety/EMERGENCY_STOP
```

No `posted_margin is 0 on OPEN position` errors. Kill-switch respected across the restart —
the trader did not resume.

Post-recreate: `cash_balance` still `79.06969737` with `updated_at` unchanged (nothing
overwrote it), invariant holds, positions 61 (`6.02690000`) and 64 (`14.60868000`) intact,
container healthy.

Note `/api/v1/performance` is NOT evidence here: `handlers/performance.py:79` computes
`initial_balance + realized_pnl` from closed-only P&L and never reads `cash_balance`.

## Expected divergence, by design

`portfolios.realized_pnl` stays `-0.41002416` (closed-only) while cash now derives from
`-0.28337306` (all positions). The two columns disagree by position 64's `+0.1266511` until it
closes. Documented in the script comment so a later reader does not mistake it for a new break.
