-- Align portfolios table with SQLAlchemy ORM in
-- services/trading-engine/app/database/models.py.
--
-- Drift introduced after 001_initial_schema.sql when the ORM gained 6 columns
-- (realized_pnl, unrealized_pnl, is_active, trading_mode, risk_per_trade,
-- max_daily_loss) without a paired migration. portfolio-manager queries fail
-- with: "column portfolios.realized_pnl does not exist".
--
-- Idempotent: safe to re-apply.

BEGIN;

ALTER TABLE portfolios
    ADD COLUMN IF NOT EXISTS realized_pnl   DECIMAL(20, 8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_active      BOOLEAN        DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS trading_mode   VARCHAR(20)    DEFAULT 'PAPER',
    ADD COLUMN IF NOT EXISTS risk_per_trade DECIMAL(5, 4)  DEFAULT 0.02,
    ADD COLUMN IF NOT EXISTS max_daily_loss DECIMAL(5, 4)  DEFAULT 0.05;

-- ORM CheckConstraint check_trading_mode
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'check_trading_mode'
    ) THEN
        ALTER TABLE portfolios
            ADD CONSTRAINT check_trading_mode
            CHECK (trading_mode IN ('PAPER', 'LIVE'));
    END IF;
END$$;

-- ORM Index idx_portfolios_active
CREATE INDEX IF NOT EXISTS idx_portfolios_active ON portfolios (is_active);

COMMIT;
