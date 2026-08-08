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
--     a weighted average, which a ratio maintained only at open cannot
--     reconcile. (Since 2026-08-08 scale_in DOES re-derive `leverage` — but
--     only because the dollar amount exists to derive it from. The dollar
--     amount remains the authoritative direction.)
--   * leverage is recorded for AUDIT ONLY. No arithmetic READS it; scale_in
--     re-derives it FROM posted_margin so a mixed-leverage row still
--     reconciles (2026-08-08).
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
    'Effective leverage of the quantity still open: entry_price * '
    'remaining_quantity / posted_margin. Equals the leverage in force at open '
    'for a single-leg position, and is RE-BLENDED on scale-in (2026-08-08) so '
    'a row whose legs opened at different leverage still reconciles with that '
    'formula. Added by 008. AUDIT ONLY — no code path reads this '
    'arithmetically; it is derived FROM posted_margin, never the reverse. '
    'INFERRED for rows predating 008.';
COMMENT ON COLUMN positions.exit_kind IS
    'Structured close reason (app.models.enums.ExitKind). Added by 008. '
    'Stored alongside the free-text exit_reason, which is unchanged and not '
    'backfilled. NULL on every pre-008 row and while OPEN.';

-- Backfill: leverage inferred from the flip bound described in the header.
-- Explicit TIMESTAMPTZ + UTC offset (not a naive TIMESTAMP) so the bound
-- means the same instant regardless of the connecting session's TimeZone
-- setting (this deployment's session TimeZone is UTC today, but the SQL
-- should not depend on that staying true).
--
-- ONLY the pre-flip statement below does real work. Its post-flip mirror
-- (`SET leverage = 1 WHERE opened_at >= ...`) was deleted 2026-08-08 in
-- code review: the column is `NOT NULL DEFAULT 1`, so every row this
-- statement could touch already holds 1 the moment it's inserted. An
-- unconditional UPDATE with no "still at default" guard is a standing
-- liability, not a no-op forever -- nothing stops a future column default
-- change or a future migration from giving `leverage` a different resting
-- value, at which point this statement would silently start overwriting
-- real data on every `setup_database.sh` reapply. Deleting it removes the
-- risk instead of guarding it.
UPDATE positions SET leverage = 10
WHERE opened_at < TIMESTAMPTZ '2026-08-05 02:03:05+00' AND leverage = 1;

-- Backfill: closed positions have nothing posted. Also deleted 2026-08-08:
-- `posted_margin` is `NOT NULL DEFAULT 0`, so this was a no-op against the
-- column default from the moment the column existed, for the same reason
-- as the leverage statement above.

-- Backfill: open positions carry margin on their REMAINING quantity, at the
-- inferred leverage. Both live open rows post-date the flip (leverage 1), so
-- this equals their remaining notional.
--
-- setup_database.sh globs and reapplies every *.sql on every run, including
-- this one, indefinitely into the future -- this is not a one-time script.
-- Once Task 3 makes posted_margin authoritative, the live engine posts and
-- consumes it directly, including through scale_in, which rewrites
-- entry_price to a size-weighted average across postings that may have
-- opened at different leverage.
--
-- CORRECTED 2026-08-08: this passage used to say entry_price*qty/leverage
-- "does NOT reconstruct that history". Task 3's fix round made scale_in
-- re-blend the stored leverage, so for any row the ENGINE wrote, the formula
-- below now round-trips exactly. The conclusion is unchanged and the reason
-- is stronger: `leverage` is INFERRED for every pre-008 row (see the backfill
-- above), so recomputing posted_margin from it would overwrite a real ledger
-- with a guess — and for engine-written rows the recomputation is at best a
-- no-op and at worst a rounding-loss round trip. A stored dollar amount, not
-- a stored ratio, remains the authoritative direction (see header).
-- `posted_margin = 0` is the primary guard —
-- under the design this migration implements, a live OPEN position's margin
-- is consumed proportionally and only reaches zero at the same moment the
-- row closes, so an OPEN row with posted_margin = 0 should only ever be one
-- this migration itself has not yet backfilled. The opened_at cutoff is
-- defense in depth on top of that, not a fix for a gap in it: it protects
-- against a bug in Task 3's future code, or against this migration being
-- reapplied against a database state it cannot reason about, by refusing to
-- touch anything opened after the boundary below regardless of what
-- posted_margin holds. 2026-08-07 18:00:00 UTC is not this migration's
-- authoring instant (008 was authored and first applied earlier that day) —
-- it is a cutoff chosen, when this guard was added in code review, to sit
-- after every row 008 has ever backfilled (latest opened_at among live rows:
-- 2026-08-07 00:00:40) and before the fix landed (2026-08-08 01:16 UTC).
-- Any position opened at or after that instant must get posted_margin from
-- the engine, never from this migration.
UPDATE positions
SET posted_margin = ROUND(
        entry_price * COALESCE(remaining_quantity, quantity) / leverage, 8)
WHERE status = 'OPEN'
  AND posted_margin = 0
  AND opened_at < TIMESTAMPTZ '2026-08-07 18:00:00+00';

COMMIT;
