---
phase: 16-validated-set-re-audit
plan: 04
subsystem: audit
tags: [audit, track-c1, infra, dashboard, data, exec, ui, test]
requires:
  - .planning/evidence/AUDIT-01/validated-reaudit.json
  - .planning/evidence/AUDIT-01/_schema.json
provides:
  - .planning/evidence/AUDIT-01/track-C1-deltas.json
affects:
  - Plan 16-06 (merges deltas into canonical file)
tech-stack:
  added: []
  patterns: [evidence-based-audit, file-line-citation, CONTEXT-D-10-taxonomy]
key-files:
  created:
    - .planning/evidence/AUDIT-01/track-C1-deltas.json
  modified:
    - .planning/phases/16-validated-set-re-audit/16-04-SUMMARY.md
decisions:
  - "CLAUDE-VALIDATED-SYMBOLS: market-data-service ingests 14 symbols vs CLAUDE.md 5 — DRIFT"
  - "DASH-01 + DASH-06: 06-TILE-AUDIT.json archived without retention — DRIFT (script + smoke broken)"
  - "INFRA-01/02: harness shipped, operator wall-clock blocked — satisfied per CONTEXT D-10"
metrics:
  duration_minutes: 35
  tasks_completed: 3
  files_audited: 24
  rows_emitted: 24
  completed_date: "2026-05-23"
---

# Phase 16 Plan 04: Track C1 Re-Audit Summary

**One-liner:** Track C1 (Infra + Data + Dashboard + EXEC + UI + TEST + CLAUDE-* execution claims) re-audited against real code with file:line citations; 21/24 satisfied, 3 drift, 0 missing.

## Status Counts

| Status | Count | REQs |
|--------|-------|------|
| satisfied | 21 | EXEC-01, EXEC-02, DATA-01, DATA-02, UI-01, TEST-01, CLAUDE-EXEC-MAINNET-PRICES, INFRA-01..06, DASH-02, DASH-03, DASH-04, DASH-05, DASHLIVE-01..04 |
| drift | 3 | CLAUDE-VALIDATED-SYMBOLS, DASH-01, DASH-06 |
| missing | 0 | — |

## Per-REQ Verdict Table

| REQ-ID | Era | Verdict | Evidence | Notes |
|--------|-----|---------|----------|-------|
| EXEC-01 | pre-v1 | satisfied | docker-compose.unified.yml:33-928 | 17 services vs claim 15 (surface grew) |
| EXEC-02 | pre-v1 | satisfied | bybit-connector/config.py:32-35 | BYBIT_TESTNET=false + PAPER_TRADING_MODE=true defaults |
| DATA-01 | pre-v1 | satisfied | market-data-service/database.py:169-174 | is_mainnet column on klines (tickers not in column_migrations — claim's 'tickers' mention partial) |
| DATA-02 | pre-v1 | satisfied | backtesting/run_walk_forward_ensemble.py:563-571 | ADR-013 testnet-taint filter active |
| UI-01 | pre-v1 | satisfied | useGatewayWebSocket.js:11-38 | REST polling dominant; WS opt-in flag-gated |
| TEST-01 | pre-v1 | satisfied | tests/ + services/*/tests/ | 337 test files; claim ~101 was snapshot |
| CLAUDE-VALIDATED-SYMBOLS | pre-v1 | **drift** | market-data-service/config.py:77-86 | 14 symbols ingested vs 5 declared in CLAUDE.md |
| CLAUDE-EXEC-MAINNET-PRICES | pre-v1 | satisfied | docker-compose.unified.yml:288-399 | Both flags pinned correctly |
| INFRA-01 | v1.0 | satisfied (D-10) | tests/integration/test_fresh_clone_round_trip.py | Harness shipped; OP-04 GH Actions billing blocks wall-clock |
| INFRA-02 | v1.0 | satisfied (D-10) | bootstrap.sh:1-136 | Harness shipped; SC-1+SC-3 operator checkpoint never executed |
| INFRA-03 | v1.0 | satisfied | bybit-connector/tape_replay_client.py:1-100 | 5-symbol JSONL tape + BYBIT_PRICE_SOURCE log line |
| INFRA-04 | v1.0 | satisfied | scripts/iter-fix.sh:1-30 | Per-fix granularity + anti-mock guard + no-auto-retry |
| INFRA-05 | v1.0 | satisfied | RUNBOOK.md:23-254 | 7 Symptom sections (claim was 4) |
| INFRA-06 | v1.0 | satisfied | RUNBOOK.md:403-411 | 3 bugs FIXED/DOCUMENTED with file refs |
| DASH-01 | v1.0 | **drift** | scripts/audit_tiles.py:43-50 | Hardcoded inventory path missing (archived in d1daa1a without retention) |
| DASH-02 | v1.0 | satisfied | frontend/vite.config.js:38-59 | DASH-02 env-var convention documented |
| DASH-03 | v1.0 | satisfied | services/api-gateway/app/main.py:1049-1180 | /api/config/safety-state + useSafetyState 5s poll + StatusBar pills |
| DASH-04 | v1.0 | satisfied | frontend/src/pages/TournamentDashboard.jsx:17-118 | 679-line page + 4 companion components |
| DASH-05 | v1.0 | satisfied | TileState.jsx:4-82 | D-13 empty/error precedence; stale-overlay can't silence errors |
| DASH-06 | v1.0 | **drift** | tests/integration/test_dashboard_smoke.py:83-127 | Same root cause as DASH-01 — missing inventory |
| DASHLIVE-01 | v1.1 | satisfied | PathToLiveTile.jsx:1-250 | Banner + 6 PREFLIGHT chips + 5 carry-in rows + 24h footer |
| DASHLIVE-02 | v1.1 | satisfied | preflight_carry_ins.py:81-105 | GET /api/preflight/carry-ins + file-backed state |
| DASHLIVE-03 | v1.1 | satisfied | useLiveReadiness.js:38-48 | 5s poll, retry=2, retryDelay=1000 |
| DASHLIVE-04 | v1.1 | satisfied | tests/e2e/test_path_to_live_smoke.py:1-21 | 7 D-10-18 assertions + dashboard-smoke.yml CI |

## Drift → Downstream Owner Mappings

| REQ-ID | Drift Type | Downstream Owner | Fix Path |
|--------|-----------|------------------|----------|
| CLAUDE-VALIDATED-SYMBOLS | Config divergence | market-data-service maintainers OR CLAUDE.md curator | Either trim default_symbols to 5 OR amend CLAUDE.md rule to reflect 14-symbol ingest-vs-trade split |
| DASH-01 | Missing artifact reference | Dashboard regression-gate owner | Restore 06-TILE-AUDIT.json under .planning/milestones/v1.0-phases/06-*/ + update scripts/audit_tiles.py:44-50 hardcoded path |
| DASH-06 | Missing artifact reference (same as DASH-01) | Dashboard smoke test owner | Same fix as DASH-01 OR rewrite test_dashboard_smoke.py to use a current inventory source |

## Refinements vs Forensic Audit

Plan suspect-table predictions vs actual findings:

- **DASH-04 path correction**: plan said `frontend/src/components/TournamentDashboard.jsx`; actual `frontend/src/pages/TournamentDashboard.jsx`. Updated evidence.
- **DASH-06 path correction**: plan said `tests/e2e/test_dashboard_smoke.py`; actual `tests/integration/test_dashboard_smoke.py`. Updated evidence.
- **EXEC-01 service count**: plan suggested "spirit is microservices stack exists" — verified 17 services (vs claim 15). Surface grew with tournament-harness, risk-metrics retention. Satisfied per guidance.
- **CLAUDE-VALIDATED-SYMBOLS**: plan expected `satisfied (expected)`. Found drift — market-data-service still ingests 14 symbols (BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,ARBUSDT,OPUSDT,SUIUSDT,APTUSDT,DOTUSDT,LTCUSDT,POLUSDT) with comment claiming "14 ACTIVE symbols (2026-05-03)" — directly contradicts CLAUDE.md "5 active as of 2026-05-03". Trading-engine is correct (5 symbols). Ingest scope drift not previously surfaced.
- **DASH-01, DASH-06**: plan expected `satisfied`. Both DRIFT — archive of v1.0 phase 06 in commit d1daa1a (2026-05-16) did NOT migrate 06-TILE-AUDIT.json under milestones/v1.0-phases/, but two pieces of live code (`scripts/audit_tiles.py:44-50` and `tests/integration/test_dashboard_smoke.py:94`) still reference the original archived path. Probe + smoke both exit at fixture load.

## Deviations from Plan

None — read-only audit executed as specified. Three drift findings (1 ingest-config, 2 archive-orphans) recorded under the standard CONTEXT D-10 taxonomy.

## Files + Commits

**Files:**
- `.planning/evidence/AUDIT-01/track-C1-deltas.json` (24 rows, validates against AUDIT-01 schema)
- `.planning/phases/16-validated-set-re-audit/16-04-SUMMARY.md` (this file)

**Commits:**
- `319cc7e` — docs(audit): track-C1 EXEC + DATA + UI + TEST + CLAUDE-* (8 rows)
- `e2ea7ed` — docs(audit): track-C1 INFRA + DASH + DASHLIVE (16 rows)
- (final) — docs(phase-16): track-C1 audit summary — 21 satisfied + 3 drift + 0 missing

## Self-Check: PASSED

- track-C1-deltas.json exists: FOUND
- track-C1-deltas.json validates against _schema.json: PASS
- track-C1-deltas.json rows == 24: PASS
- All required REQ-IDs present, no extras: PASS
- All drift/missing rows carry non-null notes: PASS (3 drift rows all have notes citing divergence)
- Commits 319cc7e + e2ea7ed exist: FOUND
