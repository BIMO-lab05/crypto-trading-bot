-- LIVECLOSE-03 PSR-evidence fixture
--
-- Three sections, separated by lines beginning with `-- SECTION:`. Tests
-- load whichever section they need via tests/closure/test_liveclose_03_psr_evidence.py's
-- load_fixture_section() helper.
--
-- Schema mirrors services/tournament-harness/migrations/0001_initial.sql
-- + 0002_mlgate_evidence_columns.sql (the run_date + psr_ci_published
-- columns ALTER-added in 0002 are inlined into the CREATE TABLE here so
-- the fixture is single-statement-friendly for sqlite executescript()).

-- SECTION: schema
CREATE TABLE IF NOT EXISTS leaderboard (
    -- Identity (0001_initial.sql lines 9-17)
    run_id              TEXT NOT NULL,
    tournament_id       TEXT NOT NULL,
    architecture        TEXT NOT NULL CHECK (architecture IN ('gru','lstm','transformer','tcn')),
    symbol              TEXT NOT NULL,
    horizon             INTEGER NOT NULL CHECK (horizon >= 1 AND horizon <= 256),
    target_mode         TEXT NOT NULL CHECK (target_mode IN ('price','log_returns')),
    hp_hash             TEXT NOT NULL,
    -- Honest skill-on-returns metrics
    r2_returns          REAL,
    dir_acc_corrected   REAL,
    oos_sharpe          REAL,
    psr                 REAL,
    dsr                 REAL,
    cpcv_dsr            REAL,
    train_seconds       REAL,
    -- Reproducibility stamps
    git_sha             TEXT NOT NULL,
    tournament_start_ts TEXT NOT NULL,
    train_window_includes_contaminated INTEGER NOT NULL DEFAULT 0 CHECK (train_window_includes_contaminated IN (0, 1)),
    -- Failure semantics
    status              TEXT NOT NULL CHECK (status IN ('success','failed')),
    failure_reason      TEXT CHECK (failure_reason IS NULL OR failure_reason IN
                            ('oom_killed','nan_loss','timeout','exit_nonzero','train_diverged','db_unreachable','unknown')),
    failure_stderr_tail TEXT,
    -- Audit
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    -- 0002_mlgate_evidence_columns.sql additions (inlined here for fixture)
    run_date            TEXT,
    psr_ci_published    INTEGER NOT NULL DEFAULT 0 CHECK (psr_ci_published IN (0, 1)),
    PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
);

-- SECTION: pass_fixture
-- 7 consecutive UTC calendar days, single natural-key group:
--   (architecture='gru', symbol='SOLUSDT', horizon=5, target_mode='log_returns', hp_hash='abc123')
-- Each row has psr_ci_published=1 and plausible DSR/PSR/Sharpe floats.
INSERT INTO leaderboard (
    run_id, tournament_id, architecture, symbol, horizon, target_mode, hp_hash,
    r2_returns, dir_acc_corrected, oos_sharpe, psr, dsr, cpcv_dsr, train_seconds,
    git_sha, tournament_start_ts, train_window_includes_contaminated,
    status, failure_reason, failure_stderr_tail, run_date, psr_ci_published
) VALUES
('run-pass-01', 'tour-pass', 'gru', 'SOLUSDT', 5, 'log_returns', 'abc123',
 0.005, 0.52, 1.2, 0.85, 0.92, 0.90, 120.0,
 'deadbeef01', '2026-05-01T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-01T00:00:00Z', 1),
('run-pass-02', 'tour-pass', 'gru', 'SOLUSDT', 5, 'log_returns', 'abc123',
 0.006, 0.53, 1.21, 0.86, 0.93, 0.91, 121.0,
 'deadbeef02', '2026-05-02T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-02T00:00:00Z', 1),
('run-pass-03', 'tour-pass', 'gru', 'SOLUSDT', 5, 'log_returns', 'abc123',
 0.007, 0.54, 1.22, 0.87, 0.94, 0.92, 122.0,
 'deadbeef03', '2026-05-03T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-03T00:00:00Z', 1),
('run-pass-04', 'tour-pass', 'gru', 'SOLUSDT', 5, 'log_returns', 'abc123',
 0.008, 0.55, 1.23, 0.88, 0.95, 0.93, 123.0,
 'deadbeef04', '2026-05-04T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-04T00:00:00Z', 1),
('run-pass-05', 'tour-pass', 'gru', 'SOLUSDT', 5, 'log_returns', 'abc123',
 0.009, 0.56, 1.24, 0.89, 0.96, 0.94, 124.0,
 'deadbeef05', '2026-05-05T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-05T00:00:00Z', 1),
('run-pass-06', 'tour-pass', 'gru', 'SOLUSDT', 5, 'log_returns', 'abc123',
 0.010, 0.57, 1.25, 0.90, 0.97, 0.95, 125.0,
 'deadbeef06', '2026-05-06T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-06T00:00:00Z', 1),
('run-pass-07', 'tour-pass', 'gru', 'SOLUSDT', 5, 'log_returns', 'abc123',
 0.011, 0.58, 1.26, 0.91, 0.98, 0.96, 126.0,
 'deadbeef07', '2026-05-07T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-07T00:00:00Z', 1);

-- SECTION: insufficient_fixture
-- 6 consecutive UTC calendar days, different natural-key group:
--   (architecture='gru', symbol='BTCUSDT', horizon=5, target_mode='log_returns', hp_hash='def456')
-- All have psr_ci_published=1 but the streak is one day short of the
-- ACCRUAL_WINDOW_DAYS=7 threshold.
INSERT INTO leaderboard (
    run_id, tournament_id, architecture, symbol, horizon, target_mode, hp_hash,
    r2_returns, dir_acc_corrected, oos_sharpe, psr, dsr, cpcv_dsr, train_seconds,
    git_sha, tournament_start_ts, train_window_includes_contaminated,
    status, failure_reason, failure_stderr_tail, run_date, psr_ci_published
) VALUES
('run-insuf-01', 'tour-insuf', 'gru', 'BTCUSDT', 5, 'log_returns', 'def456',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'cafef00d01', '2026-05-08T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-08T00:00:00Z', 1),
('run-insuf-02', 'tour-insuf', 'gru', 'BTCUSDT', 5, 'log_returns', 'def456',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'cafef00d02', '2026-05-09T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-09T00:00:00Z', 1),
('run-insuf-03', 'tour-insuf', 'gru', 'BTCUSDT', 5, 'log_returns', 'def456',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'cafef00d03', '2026-05-10T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-10T00:00:00Z', 1),
('run-insuf-04', 'tour-insuf', 'gru', 'BTCUSDT', 5, 'log_returns', 'def456',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'cafef00d04', '2026-05-11T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-11T00:00:00Z', 1),
('run-insuf-05', 'tour-insuf', 'gru', 'BTCUSDT', 5, 'log_returns', 'def456',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'cafef00d05', '2026-05-12T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-12T00:00:00Z', 1),
('run-insuf-06', 'tour-insuf', 'gru', 'BTCUSDT', 5, 'log_returns', 'def456',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'cafef00d06', '2026-05-13T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-13T00:00:00Z', 1);

-- SECTION: gap_fixture
-- 8 rows split into two 4-day streaks with a gap in the middle.
-- Natural key: (architecture='gru', symbol='ETHUSDT', horizon=5, target_mode='log_returns', hp_hash='ghi789')
-- Longest consecutive streak is 4 < ACCRUAL_WINDOW_DAYS=7.
INSERT INTO leaderboard (
    run_id, tournament_id, architecture, symbol, horizon, target_mode, hp_hash,
    r2_returns, dir_acc_corrected, oos_sharpe, psr, dsr, cpcv_dsr, train_seconds,
    git_sha, tournament_start_ts, train_window_includes_contaminated,
    status, failure_reason, failure_stderr_tail, run_date, psr_ci_published
) VALUES
('run-gap-01', 'tour-gap', 'gru', 'ETHUSDT', 5, 'log_returns', 'ghi789',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'beadface01', '2026-05-14T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-14T00:00:00Z', 1),
('run-gap-02', 'tour-gap', 'gru', 'ETHUSDT', 5, 'log_returns', 'ghi789',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'beadface02', '2026-05-15T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-15T00:00:00Z', 1),
('run-gap-03', 'tour-gap', 'gru', 'ETHUSDT', 5, 'log_returns', 'ghi789',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'beadface03', '2026-05-16T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-16T00:00:00Z', 1),
('run-gap-04', 'tour-gap', 'gru', 'ETHUSDT', 5, 'log_returns', 'ghi789',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'beadface04', '2026-05-17T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-17T00:00:00Z', 1),
-- gap: 2026-05-18 missing
('run-gap-05', 'tour-gap', 'gru', 'ETHUSDT', 5, 'log_returns', 'ghi789',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'beadface05', '2026-05-19T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-19T00:00:00Z', 1),
('run-gap-06', 'tour-gap', 'gru', 'ETHUSDT', 5, 'log_returns', 'ghi789',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'beadface06', '2026-05-20T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-20T00:00:00Z', 1),
('run-gap-07', 'tour-gap', 'gru', 'ETHUSDT', 5, 'log_returns', 'ghi789',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'beadface07', '2026-05-21T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-21T00:00:00Z', 1),
('run-gap-08', 'tour-gap', 'gru', 'ETHUSDT', 5, 'log_returns', 'ghi789',
 0.004, 0.51, 1.1, 0.80, 0.91, 0.88, 110.0,
 'beadface08', '2026-05-22T00:00:00Z', 0,
 'success', NULL, NULL, '2026-05-22T00:00:00Z', 1);
