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
-- OWNER OVERRIDE. The reconciliation verdict reads UNRECONCILED, on a residual
-- of -$0.33900231 against a break of +$176.90335601. The owner authorized this
-- repair anyway on 2026-08-08: the leverage mechanism reconciles to 1e-8, and
-- the residual is a separate, older, negative discrepancy dated on or before
-- 2026-08-04 16:07:16 -- inside the window whose one documented repair
-- (2026-08-04-fee-backfill-and-balance-repair.sql) was executed interactively
-- and never captured verbatim. AUDIT.md section 8.1 accepted a residual 12x
-- larger ($4.23) on 2026-08-05. Decisively: the residual does NOT change the
-- value written below, which is computed from current state either way.
--
-- Run with the trading-engine container STOPPED. It caches cash in memory and
-- persists it on position close; a close landing between the UPDATE and the
-- container recreate would write the stale figure straight back.
--
-- Apply:
--   docker compose -f docker-compose.unified.yml stop trading-engine
--   docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
--     -f - < database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql
--   docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine
-- ==========================================

-- THREE TERMS, and the obvious two-term form is wrong:
--   * realized P&L must sum over ALL positions, not just CLOSED ones - a
--     partial exit accrues realized P&L onto a position that is still open.
--     portfolios.realized_pnl has that blind spot by construction (it is
--     written only by record_position_close), which is why the live row reads
--     -0.41002416 while SUM over all positions is -0.28337306. That divergence
--     SURVIVES this repair by design: this statement does not touch
--     realized_pnl, so the column keeps its closed-only meaning while
--     cash_balance is now derived from the all-positions sum.
--   * unconsumed entry fee must be subtracted: cash was debited the WHOLE
--     entry fee at open, while realized_pnl nets only the consumed portion.
--     For an open row that is
--       entry_fee * COALESCE(remaining_quantity, quantity) / NULLIF(quantity, 0)
--     - the same reconstruction load_positions_from_db uses, exact whenever no
--     scale-in intervened between partial exits. (Controller-verified: no
--     position in this database has ever been scaled into.)
--     The COALESCE is MANDATORY, not defensive. remaining_quantity is nullable
--     (007 added it without NOT NULL) and the engine treats NULL as "full"
--     (paper_trading.py:97-101). A bare `entry_fee * remaining_quantity / ...`
--     yields NULL on such a row and SUM SILENTLY DROPS IT - under-subtracting
--     the unconsumed fee and setting cash_balance too HIGH. Both live open rows
--     happen to be populated today, so the bug is latent; this statement
--     re-derives at execution time, when that may no longer hold.

\echo '=== BEFORE ==='
SELECT portfolio_id, initial_balance, cash_balance, realized_pnl, updated_at
FROM portfolios;

SELECT
    COALESCE((SELECT SUM(realized_pnl) FROM positions), 0)            AS realized_all,
    COALESCE((SELECT SUM(posted_margin) FROM positions
              WHERE status = 'OPEN'), 0)                              AS open_margin,
    COALESCE((SELECT SUM(entry_fee * COALESCE(remaining_quantity, quantity) / NULLIF(quantity, 0))
              FROM positions WHERE status = 'OPEN'), 0)               AS unconsumed_entry_fee;

BEGIN;

-- Computed, not hardcoded, so re-running after a further close stays correct.
UPDATE portfolios p
SET cash_balance = p.initial_balance
                 + COALESCE((SELECT SUM(realized_pnl) FROM positions), 0)
                 - COALESCE((SELECT SUM(posted_margin) FROM positions
                             WHERE status = 'OPEN'), 0)
                 - COALESCE((SELECT SUM(entry_fee * COALESCE(remaining_quantity, quantity) / NULLIF(quantity, 0))
                             FROM positions WHERE status = 'OPEN'), 0),
    updated_at = NOW()
WHERE p.portfolio_id = 'paper_trading';

COMMIT;

\echo '=== AFTER (residual must be under a cent; invariant_holds must return t) ==='
SELECT portfolio_id, initial_balance, cash_balance, realized_pnl, updated_at
FROM portfolios;

-- Why this is a TOLERANCE and not an exact `=`.
-- portfolios.cash_balance is numeric(20,8), but the unconsumed-fee term carries
-- more scale than that: entry_fee * remaining_quantity / quantity currently
-- evaluates to 0.011349574 (9 decimals). The computed cash is therefore
-- 79.069697366, which STORES as 79.06969737. Re-adding the full-scale terms to
-- the rounded column leaves a ~4e-9 residual, so an exact `=` would return f on
-- a perfectly correct repair and send the operator into a needless rollback.
-- 1e-6 is six orders of magnitude below a cent and four above the storage
-- granularity. The residual is printed alongside so the check cannot hide a
-- real break behind the tolerance.
SELECT
    (p.cash_balance
     + COALESCE((SELECT SUM(posted_margin) FROM positions WHERE status = 'OPEN'), 0)
     + COALESCE((SELECT SUM(entry_fee * COALESCE(remaining_quantity, quantity) / NULLIF(quantity, 0))
                 FROM positions WHERE status = 'OPEN'), 0))
    - (p.initial_balance + COALESCE((SELECT SUM(realized_pnl) FROM positions), 0))
        AS residual,
    abs((p.cash_balance
         + COALESCE((SELECT SUM(posted_margin) FROM positions WHERE status = 'OPEN'), 0)
         + COALESCE((SELECT SUM(entry_fee * COALESCE(remaining_quantity, quantity) / NULLIF(quantity, 0))
                     FROM positions WHERE status = 'OPEN'), 0))
        - (p.initial_balance + COALESCE((SELECT SUM(realized_pnl) FROM positions), 0)))
        < 0.000001 AS invariant_holds
FROM portfolios p WHERE p.portfolio_id = 'paper_trading';
