-- Migration 0002: MLGATE evidence columns (run_date, psr_ci_published)
-- Purpose: Add MLGATE-01 evidence-loop columns to the leaderboard table.
--   * run_date              -- ISO-8601 UTC string; nullable so existing rows survive.
--   * psr_ci_published      -- 0|1 flag flipped by scripts/forward_paper_test/run_evidence_loop.py
--                              after the ≥7-day accrual window closes and PSR-CI is computed.
-- Phase: 09-01 — ML Re-enablement Gate
-- Date: 2026-05-17
-- Author: MLGATE-01 (Phase 9, plan 01)
--
-- IDEMPOTENCY NOTE
-- ----------------
-- This file is intended to be applied via services/tournament-harness/app/leaderboard/db.py::run_migrations,
-- which is itself idempotent: it reads `schema_version` and skips already-applied versions
-- (see db.py:94-105). The ALTER TABLE ADD COLUMN statements below are therefore safe to
-- include without an inline IF NOT EXISTS guard — SQLite has no native ADD COLUMN IF NOT EXISTS,
-- and `executescript` cannot do conditional DDL.
--
-- Decision D-09-01-02 (Plan 09-01): non-destructive ALTER TABLE on existing `leaderboard`
-- (the rejected alternative was a tournament_results view/alias which would have split the
-- read surface and broken the TOURN-07 grep gate scope).
--
-- TABLE NAME DECISION (D-09-01-01)
-- --------------------------------
-- REQUIREMENTS.md wording references a `tournament_results` table; the actual schema
-- (see 0001_initial.sql lines 9-43) defines `leaderboard`. Phase 9 reads and writes
-- `leaderboard` directly per 08-CONTEXT.md lines 95-101. The REQUIREMENTS.md wording
-- will be corrected in a follow-up docs commit.

-- ============================================================================
-- ALTER 1: run_date — ISO-8601 UTC string, NULL until backfilled.
-- Existing rows acquire NULL retroactively — survives nullability.
-- ============================================================================
ALTER TABLE leaderboard ADD COLUMN run_date TEXT;

-- ============================================================================
-- ALTER 2: psr_ci_published — 0|1 publication flag.
-- DEFAULT 0 so existing rows acquire 0 retroactively.
-- CHECK constraint mirrors the 0001_initial.sql style for train_window_includes_contaminated.
-- ============================================================================
ALTER TABLE leaderboard ADD COLUMN psr_ci_published INTEGER NOT NULL DEFAULT 0
    CHECK (psr_ci_published IN (0, 1));

-- ============================================================================
-- INDEX: support MLGATE-02 lookup
--   SELECT ... FROM leaderboard WHERE psr_ci_published = 1 AND dsr > 0.95
--   ORDER BY run_date DESC LIMIT 1
-- The (psr_ci_published, run_date DESC) order matches the WHERE+ORDER BY shape.
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_leaderboard_psr_published
    ON leaderboard(psr_ci_published, run_date DESC);

-- ============================================================================
-- SCHEMA VERSION (D-17): record migration as applied.
-- Matches the pattern from 0001_initial.sql line 69.
-- ============================================================================
INSERT OR IGNORE INTO schema_version (version, description)
VALUES (2, 'MLGATE evidence columns (run_date, psr_ci_published)');
