-- Migration 0001: Initial Tournament Leaderboard Schema
-- Purpose: Create leaderboard rows + tournaments + schema_version tables (TOURN-02, TOURN-04)
-- Date: 2026-05-08
-- Author: Tournament Harness (Phase 3)

-- ============================================================================
-- LEADERBOARD ROWS (TOURN-02: PK = architecture, symbol, horizon, target_mode, hp_hash, run_id)
-- ============================================================================
CREATE TABLE IF NOT EXISTS leaderboard (
    -- Identity
    run_id              TEXT NOT NULL,
    tournament_id       TEXT NOT NULL,
    architecture        TEXT NOT NULL CHECK (architecture IN ('gru','lstm','transformer','tcn')),
    symbol              TEXT NOT NULL,
    horizon             INTEGER NOT NULL CHECK (horizon >= 1 AND horizon <= 256),
    target_mode         TEXT NOT NULL CHECK (target_mode IN ('price','log_returns')),
    hp_hash             TEXT NOT NULL,
    -- Honest skill-on-returns metrics (TOURN-02 column list — every field nullable for failed rows)
    r2_returns          REAL,
    dir_acc_corrected   REAL,
    oos_sharpe          REAL,
    psr                 REAL,
    dsr                 REAL,
    cpcv_dsr            REAL,
    train_seconds       REAL,
    -- Reproducibility stamps (D-13, D-07, D-08)
    git_sha             TEXT NOT NULL,
    tournament_start_ts TEXT NOT NULL,
    train_window_includes_contaminated INTEGER NOT NULL DEFAULT 0 CHECK (train_window_includes_contaminated IN (0, 1)),
    -- Failure semantics (D-15, TOURN-04: failed runs ALSO get a row)
    status              TEXT NOT NULL CHECK (status IN ('success','failed')),
    failure_reason      TEXT CHECK (failure_reason IS NULL OR failure_reason IN
                            ('oom_killed','nan_loss','timeout','exit_nonzero','train_diverged','db_unreachable','unknown')),
    failure_stderr_tail TEXT,
    -- Audit
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
);

CREATE INDEX IF NOT EXISTS idx_leaderboard_tournament ON leaderboard(tournament_id);
CREATE INDEX IF NOT EXISTS idx_leaderboard_dsr        ON leaderboard(tournament_id, dsr DESC);
CREATE INDEX IF NOT EXISTS idx_leaderboard_arch_sym   ON leaderboard(architecture, symbol);
CREATE INDEX IF NOT EXISTS idx_leaderboard_status     ON leaderboard(status);

-- ============================================================================
-- TOURNAMENTS (one row per tournament — full YAML stored verbatim for reproducibility)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tournaments (
    tournament_id          TEXT PRIMARY KEY,
    started_at             TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at           TEXT,
    config_yaml            TEXT NOT NULL,
    git_sha                TEXT NOT NULL,
    seed                   INTEGER NOT NULL,
    n_experiments_total    INTEGER,
    n_experiments_success  INTEGER,
    n_experiments_failed   INTEGER
);

-- ============================================================================
-- SCHEMA VERSION TRACKING (D-17)
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_version (version, description)
VALUES (1, 'Initial leaderboard + tournaments + schema_version tables');
