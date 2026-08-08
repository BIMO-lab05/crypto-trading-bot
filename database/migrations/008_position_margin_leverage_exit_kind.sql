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
-- flip is bounded by row arithmetic, to 1e-8, to the window
-- 2026-08-04 16:07:16 .. 2026-08-05 02:03:05 (container observed at 10x at
-- 2026-08-04 16:07:16 and at 1x at 2026-08-05 02:03:05). Git history does
-- NOT bound this container's config: the running value came from a
-- gitignored .env override, not from docker-compose.unified.yml, and the
-- compose file's own change (commit a51e815, 2026-08-05 13:50:40 UTC) lands
-- roughly 11.8 hours AFTER the container had already flipped. Do not cite
-- that commit date as the flip date. Rows are classified by the row-arithmetic
-- bound above. No CHECK constraint on exit_kind: trades.order_type already
-- carries a CHECK that disagrees with its enum, and a stale CHECK rejects
-- valid writes.
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
-- Explicit TIMESTAMPTZ + UTC offset (not a naive TIMESTAMP) so the bound
-- means the same instant regardless of the connecting session's TimeZone
-- setting (this deployment's session TimeZone is UTC today, but the SQL
-- should not depend on that staying true).
UPDATE positions SET leverage = 10
WHERE opened_at < TIMESTAMPTZ '2026-08-05 02:03:05+00' AND leverage = 1;

UPDATE positions SET leverage = 1
WHERE opened_at >= TIMESTAMPTZ '2026-08-05 02:03:05+00';

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
