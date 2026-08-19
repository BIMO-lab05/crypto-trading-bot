-- ==========================================
-- ONE-TIME REPAIR 2026-08-16: portfolio display + risk columns
-- ==========================================
-- Repairs two defects found in the 2026-08-16 trading-engine audit. The code
-- fixes land in the same change set; this file repairs the historical row.
--
--   RES-03  portfolios.total_value / total_pnl / unrealized_pnl were NEVER
--           maintained. total_value was not even ORM-mapped, so the engine
--           could not write it; total_pnl was mapped and never assigned. Only
--           cash_balance and realized_pnl ever moved. Every value in those
--           three columns today is stale by an unbounded amount.
--
--   RES-04  portfolios.risk_per_trade (0.0200) and max_daily_loss (0.0500)
--           are the DDL defaults and contradict ADR-010 (10% paper per-trade)
--           and ADR-028 (12% daily loss). Zero runtime readers exist, so this
--           is a truthfulness repair on a row an operator reads directly, not
--           a behaviour change.
--
-- NOT a numbered migration: database/scripts/setup_database.sh globs
-- $MIGRATIONS_DIR/*.sql NON-RECURSIVELY and re-applies everything on every
-- run. A value overwrite must never sit on that path. Living in
-- one_time_repairs/ is what keeps it off the glob.
--
-- PRECONDITION — FLAT BOOK. Run only when the portfolio has no OPEN
-- positions. The RES-03 backfill below sets unrealized_pnl = 0 and
-- total_value = cash_balance, which is exactly what the new code computes
-- (total_value = cash + SUM(unrealized_pnl) over OPEN positions) ONLY when
-- that sum is zero. With positions open the written values would be wrong the
-- moment they were written. Verify first:
--
--   SELECT count(*) FROM positions
--    WHERE portfolio_id = 'paper_trading' AND status = 'OPEN';   -- must be 0
--
-- Run with the trading-engine container STOPPED. It caches cash in memory and
-- restores the balance from this row on boot (paper_trading.py:176-187); a
-- close landing between the UPDATE and the container recreate would write a
-- stale figure straight back over it.
--
-- UNITS: max_daily_loss is stored as a FRACTION in a DECIMAL(5,4) column, so
-- ADR-028's 12% is written as 0.12 — the same percent -> fraction conversion
-- PortfolioRepository.get_or_create now performs on the code path. Writing
-- 12.0 here would overflow the column.
--
-- Apply:
--   docker compose -f docker-compose.unified.yml stop trading-engine
--   docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
--     -f - < database/migrations/one_time_repairs/2026-08-16-res03-total-value-backfill.sql
--   docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine
-- ==========================================

BEGIN;

-- RES-03 — backfill the three never-maintained display columns.
-- Under the flat-book precondition open unrealized P&L is zero, so:
--   total_value    = cash_balance + 0
--   total_pnl      = realized_pnl + 0
--   unrealized_pnl = 0
-- These mirror the engine's own definitions. Note total_value is
-- MARGIN-EXCLUSIVE by design, matching PaperTradingEngine.get_total_equity();
-- with a flat book no margin is posted, so the distinction is moot here.
UPDATE portfolios
   SET total_value    = cash_balance,
       total_pnl      = COALESCE(realized_pnl, 0),
       unrealized_pnl = 0,
       updated_at     = NOW()
 WHERE portfolio_id = 'paper_trading';

-- RES-04 — align the risk columns with ADR-010 / ADR-028.
-- The trading_mode guard is load-bearing: it makes it impossible for this
-- file to RELAX the risk cap on a LIVE row. LIVE stays at the 2% ceiling,
-- which is non-negotiable.
UPDATE portfolios
   SET risk_per_trade = 0.10,   -- ADR-010: 10% per-trade, PAPER only
       max_daily_loss = 0.12,   -- ADR-028: 12% daily, stored as a FRACTION
       updated_at     = NOW()
 WHERE portfolio_id = 'paper_trading'
   AND trading_mode = 'PAPER';

-- Verify before committing the transaction:
--   SELECT portfolio_id, trading_mode, cash_balance, realized_pnl,
--          unrealized_pnl, total_pnl, total_value,
--          risk_per_trade, max_daily_loss
--     FROM portfolios WHERE portfolio_id = 'paper_trading';
-- Expect total_value = cash_balance, total_pnl = realized_pnl,
-- unrealized_pnl = 0, risk_per_trade = 0.1000, max_daily_loss = 0.1200.

COMMIT;
