-- RES-01 one-time repair: backfill-correct pre-epoch trades.realized_pnl
-- (2026-08-16, operator-approved; record: .planning/evidence/resume-2026-08-16.md)
--
-- Defect: trades rows written before the 2026-08-05/2026-08-12 ledger repairs
-- disagree with the corrected positions ledger by +3.37253896 in total:
--   Group A (positions 46-56, single full exit): exit rows stored GROSS of fees
--     while positions are NET — drift equals entry_fee+exit_fee exactly.
--   Group B (positions 57, 59, 60, partial-exit era): first partial exits
--     stored gross, later ones net; and pos-59's final close (trade id 93)
--     records the phantom FULL quantity (H5 bug) instead of the remaining leg,
--     inflating its P&L by ~1.70 and reported volume by ~0.595 SOL.
--
-- Convention of record (matches every position opened >= 2026-08-06):
--   exit trade realized_pnl = gross leg P&L
--                             - entry_fee * exited_qty / original_qty
--                             - exit trade fee
--   entry trades carry NULL.
--
-- Safety: full trades backup in trades_backup_res01; every touched row gets
--   metadata res01_corrected / res01_prev_* provenance. Revert:
--     UPDATE trades t SET realized_pnl=b.realized_pnl, quantity=b.quantity,
--            total_value=b.total_value, metadata=b.metadata
--     FROM trades_backup_res01 b WHERE b.id=t.id;
--     DROP TABLE trades_backup_res01;
--
-- Run: docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot \
--        -v ON_ERROR_STOP=1 < scripts/repair_res01_trades_pnl.sql

\set ON_ERROR_STOP on
BEGIN;

-- 0. Backup. Refuses to run twice.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_name = 'trades_backup_res01') THEN
    RAISE EXCEPTION 'trades_backup_res01 already exists — repair already ran. Drop it manually to force.';
  END IF;
END $$;
CREATE TABLE trades_backup_res01 AS SELECT * FROM trades;

-- 1a. Precondition, group A: exactly one exit row per position and the drift
--     equals both-leg fees (fails on re-run — the drift is gone after repair).
DO $$
DECLARE bad int;
BEGIN
  SELECT count(*) INTO bad FROM (
    SELECT p.id
    FROM positions p
    JOIN trades tr ON tr.metadata->>'position_id' = p.position_id::text
    WHERE p.status = 'CLOSED' AND p.id BETWEEN 46 AND 56
    GROUP BY p.id, p.realized_pnl, p.entry_fee, p.exit_fee
    HAVING count(*) FILTER (WHERE tr.realized_pnl IS NOT NULL) <> 1
        OR abs(coalesce(sum(tr.realized_pnl), 0) - p.realized_pnl
               - (p.entry_fee + p.exit_fee)) > 0.00000002
  ) x;
  IF bad > 0 THEN
    RAISE EXCEPTION 'RES-01 group-A precondition failed on % positions (already repaired?)', bad;
  END IF;
END $$;

-- 1b. Precondition, group B: pos-59 phantom quantity still present, and each
--     of 57/59/60 has exactly one entry (NULL-pnl) trade.
DO $$
DECLARE q_entry numeric; q_final numeric; bad int;
BEGIN
  SELECT quantity INTO q_entry FROM trades WHERE id = 87;  -- pos 59 entry
  SELECT quantity INTO q_final FROM trades WHERE id = 93;  -- pos 59 final close
  IF q_entry IS NULL OR q_final IS NULL OR q_final <> q_entry THEN
    RAISE EXCEPTION 'RES-01 group-B precondition failed: pos-59 phantom qty absent (already repaired?)';
  END IF;
  SELECT count(*) INTO bad FROM (
    SELECT p.id FROM positions p
    JOIN trades tr ON tr.metadata->>'position_id' = p.position_id::text
    WHERE p.id IN (57, 59, 60)
    GROUP BY p.id
    HAVING count(*) FILTER (WHERE tr.realized_pnl IS NULL) <> 1
  ) x;
  IF bad > 0 THEN
    RAISE EXCEPTION 'RES-01 group-B precondition failed: % positions without exactly one entry trade', bad;
  END IF;
END $$;

-- 2. Group A: single full exit -> exit row net = position net.
UPDATE trades t
SET realized_pnl = p.realized_pnl,
    metadata = coalesce(t.metadata, '{}'::jsonb)
               || jsonb_build_object('res01_corrected', '2026-08-16',
                                     'res01_prev_pnl', t.realized_pnl)
FROM positions p
WHERE p.status = 'CLOSED' AND p.id BETWEEN 46 AND 56
  AND t.metadata->>'position_id' = p.position_id::text
  AND t.realized_pnl IS NOT NULL;

-- 3. Pos-59 final close: replace phantom full quantity with the true
--    remaining leg (entry qty minus the two partial exits).
UPDATE trades t
SET quantity    = e.q - x.exited_before,
    total_value = round((e.q - x.exited_before) * t.price, 8),
    metadata = coalesce(t.metadata, '{}'::jsonb)
               || jsonb_build_object('res01_qty_corrected', '2026-08-16',
                                     'res01_prev_quantity', t.quantity,
                                     'res01_prev_total_value', t.total_value)
FROM (SELECT quantity AS q FROM trades WHERE id = 87) e,
     (SELECT sum(quantity) AS exited_before FROM trades WHERE id IN (90, 92)) x
WHERE t.id = 93;

-- 4. Group B: recompute every exit row from first principles.
--    NOTE: fee on trade 93 stays as recorded (computed on the phantom qty) —
--    positions.exit_fee for pos 59 includes it, so the identity below only
--    holds with the recorded fee. Documented residue, not an oversight.
WITH pos AS (
  SELECT p.id AS pid, p.position_id, p.entry_fee, p.side
  FROM positions p WHERE p.id IN (57, 59, 60)
), entry AS (
  SELECT pos.pid, tr.price AS entry_price, tr.quantity AS entry_qty
  FROM pos
  JOIN trades tr ON tr.metadata->>'position_id' = pos.position_id::text
                AND tr.realized_pnl IS NULL
), nets AS (
  SELECT pos.pid, t.id AS tid,
         round( (CASE pos.side WHEN 'LONG' THEN t.price - entry.entry_price
                               ELSE entry.entry_price - t.price END) * t.quantity
                - pos.entry_fee * t.quantity / entry.entry_qty
                - t.fee
              , 8) AS net
  FROM pos
  JOIN entry ON entry.pid = pos.pid
  JOIN trades t ON t.metadata->>'position_id' = pos.position_id::text
               AND t.realized_pnl IS NOT NULL
)
UPDATE trades t
SET realized_pnl = nets.net,
    metadata = coalesce(t.metadata, '{}'::jsonb)
               || jsonb_build_object('res01_corrected', '2026-08-16',
                                     'res01_prev_pnl', t.realized_pnl)
FROM nets
WHERE t.id = nets.tid;

-- 5a. Residual sanity: recomputation must land within rounding distance.
DO $$
DECLARE mx numeric;
BEGIN
  SELECT max(abs(p.realized_pnl - t.s)) INTO mx
  FROM positions p
  JOIN LATERAL (
    SELECT coalesce(sum(realized_pnl), 0) AS s
    FROM trades tr WHERE tr.metadata->>'position_id' = p.position_id::text
  ) t ON true
  WHERE p.id IN (57, 59, 60);
  IF mx > 0.001 THEN
    RAISE EXCEPTION 'RES-01 residual too large (%) — recomputation wrong, aborting', mx;
  END IF;
END $$;

-- 5b. Residual snap: absorb 1e-8-scale rounding into each position's latest
--     exit so the per-position identity is EXACT.
WITH sums AS (
  SELECT p.id AS pid, p.position_id,
         p.realized_pnl - sum(tr.realized_pnl) AS residual
  FROM positions p
  JOIN trades tr ON tr.metadata->>'position_id' = p.position_id::text
               AND tr.realized_pnl IS NOT NULL
  WHERE p.id IN (57, 59, 60)
  GROUP BY p.id, p.position_id, p.realized_pnl
), last_exit AS (
  SELECT DISTINCT ON (s.pid) s.pid, tr.id AS tid, s.residual
  FROM sums s
  JOIN trades tr ON tr.metadata->>'position_id' = s.position_id::text
               AND tr.realized_pnl IS NOT NULL
  ORDER BY s.pid, tr.executed_at DESC
)
UPDATE trades t
SET realized_pnl = t.realized_pnl + le.residual
FROM last_exit le
WHERE t.id = le.tid AND le.residual <> 0;

-- 6. Postconditions (hard): abort the whole transaction on any failure.
DO $$
DECLARE bad int; g_tr numeric; g_pos numeric; g_port numeric;
        f_now numeric; f_bak numeric;
BEGIN
  SELECT count(*) INTO bad
  FROM positions p
  JOIN LATERAL (
    SELECT coalesce(sum(realized_pnl), 0) AS s
    FROM trades tr WHERE tr.metadata->>'position_id' = p.position_id::text
  ) t ON true
  WHERE p.status = 'CLOSED' AND t.s <> p.realized_pnl;
  IF bad > 0 THEN
    RAISE EXCEPTION 'RES-01 postcondition failed: % closed positions still drift', bad;
  END IF;

  SELECT sum(realized_pnl) INTO g_tr  FROM trades;
  SELECT sum(realized_pnl) INTO g_pos FROM positions WHERE status = 'CLOSED';
  SELECT realized_pnl      INTO g_port FROM portfolios WHERE portfolio_id = 'paper_trading';
  IF g_tr <> g_pos OR g_tr <> g_port THEN
    RAISE EXCEPTION 'RES-01 postcondition failed: sums differ (trades % / positions % / portfolio %)',
      g_tr, g_pos, g_port;
  END IF;

  SELECT sum(fee) INTO f_now FROM trades;
  SELECT sum(fee) INTO f_bak FROM trades_backup_res01;
  IF f_now <> f_bak THEN
    RAISE EXCEPTION 'RES-01 postcondition failed: fee column changed (% vs %)', f_now, f_bak;
  END IF;
END $$;

COMMIT;

-- Post-commit report.
SELECT 'corrected rows' AS what, count(*) AS n
FROM trades WHERE metadata ? 'res01_corrected'
UNION ALL
SELECT 'qty-corrected rows', count(*) FROM trades WHERE metadata ? 'res01_qty_corrected'
UNION ALL
SELECT 'global trades pnl = positions pnl = portfolio pnl',
       (SELECT count(*) FROM portfolios
        WHERE portfolio_id = 'paper_trading'
          AND realized_pnl = (SELECT sum(realized_pnl) FROM trades));
