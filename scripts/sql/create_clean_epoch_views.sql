-- Clean-data epoch views (2026-08-20). Idempotent. Apply to the POSTGRES app
-- DB (cryptobot), not TimescaleDB:
--   docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
--     -f - < scripts/sql/create_clean_epoch_views.sql
-- Epoch: 2026-08-12T13:47:20Z — must agree with
-- scripts/forward_paper_test/epoch.py. Filter is on the POSITION's opened_at;
-- trades join through position_id so post-epoch closes of pre-epoch positions
-- (the two legacy sweeps at 13:47:27Z/13:47:35Z) are excluded.

CREATE OR REPLACE VIEW public.clean_epoch_positions AS
SELECT p.*
FROM public.positions p
WHERE p.opened_at >= TIMESTAMPTZ '2026-08-12T13:47:20Z';

CREATE OR REPLACE VIEW public.clean_epoch_trades AS
SELECT t.*
FROM public.trades t
JOIN public.positions p ON p.position_id = (t.metadata->>'position_id')::uuid
WHERE p.opened_at >= TIMESTAMPTZ '2026-08-12T13:47:20Z';
