-- ==========================================
-- MIGRATION 007: Position fee + partial-exit accounting
-- ==========================================
-- Description: AUDIT.md 2026-08-04, findings 6.2/6.6, hypotheses H5 + H7.
--   * positions.realized_pnl was persisted GROSS of commissions while the
--     cash ledger subtracted them -> every DB row and dashboard overstated
--     P&L by the full fee load. New columns entry_fee / exit_fee make the
--     fee legs first-class, and realized_pnl is henceforth written NET of
--     both legs' commissions by the trading engine.
--   * positions had no remaining_quantity, so partial exits lived only in
--     process memory: a restart resurrected already-sold quantity (one
--     position's close P&L overstated by exactly $1.7029).
-- Date: 2026-08-04
-- Depends on: 002_create_tables.sql
--
-- Apply with an explicit database (do NOT rely on a \c directive; the live
-- deployment database is `cryptobot`, older migration headers referenced a
-- differently-named DB):
--   docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
--     -f - < database/migrations/007_position_fee_partial_exit_accounting.sql
--
-- Mirrors services/trading-engine/app/database/models.py::Position.
-- Idempotent: safe to re-run.
-- ==========================================

BEGIN;

-- Quantity still open after partial exits. NULL only on pre-migration rows;
-- backfilled below so the trading engine can rely on it after restart.
ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS remaining_quantity NUMERIC(20, 8);

-- Commission paid on the opening leg(s); scale-ins accumulate into it.
ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS entry_fee NUMERIC(20, 8) NOT NULL DEFAULT 0;

-- Accumulated commissions on reduce/close legs.
ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS exit_fee NUMERIC(20, 8) NOT NULL DEFAULT 0;

COMMENT ON COLUMN positions.remaining_quantity IS
    'Quantity still open after partial exits (0 once CLOSED). Added by 007; '
    'persisted on every reduce/close so restarts cannot resurrect sold quantity (AUDIT H5).';
COMMENT ON COLUMN positions.entry_fee IS
    'Commission charged on opening leg(s), quote currency. Added by 007 (AUDIT H7).';
COMMENT ON COLUMN positions.exit_fee IS
    'Accumulated commission charged on reduce/close legs, quote currency. Added by 007 (AUDIT H7).';
COMMENT ON COLUMN positions.realized_pnl IS
    'Realized P&L NET of entry_fee + exit_fee as of migration 007 (2026-08-04). '
    'Rows written before 007 held gross P&L until the one-time backfill.';

-- Baseline backfill (schema-level only; the trades-leg-derived refinement of
-- fees / net P&L / true remaining quantity for pre-existing rows is a
-- separate audited one-time data repair, executed 2026-08-04):
UPDATE positions SET remaining_quantity = 0
WHERE status = 'CLOSED' AND remaining_quantity IS NULL;

UPDATE positions SET remaining_quantity = quantity
WHERE status = 'OPEN' AND remaining_quantity IS NULL;

COMMIT;
