-- Align positions table with SQLAlchemy ORM in
-- services/trading-engine/app/database/models.py.
--
-- Drift: ORM defines `entry_signal_confidence DECIMAL(5,4)`, 4 CHECK
-- constraints, and 3 indexes that 001_initial_schema.sql never created.
-- Symptom: "column positions.entry_signal_confidence does not exist".
--
-- Idempotent: safe to re-apply.

BEGIN;

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS entry_signal_confidence DECIMAL(5, 4);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_positive_quantity') THEN
        ALTER TABLE positions
            ADD CONSTRAINT check_positive_quantity CHECK (quantity > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_positive_entry_price') THEN
        ALTER TABLE positions
            ADD CONSTRAINT check_positive_entry_price CHECK (entry_price > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_valid_side') THEN
        ALTER TABLE positions
            ADD CONSTRAINT check_valid_side CHECK (side IN ('LONG', 'SHORT'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_valid_status') THEN
        ALTER TABLE positions
            ADD CONSTRAINT check_valid_status CHECK (status IN ('OPEN', 'CLOSED'));
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_positions_portfolio        ON positions (portfolio_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol           ON positions (symbol);
CREATE INDEX IF NOT EXISTS idx_positions_portfolio_status ON positions (portfolio_id, status);

COMMIT;
