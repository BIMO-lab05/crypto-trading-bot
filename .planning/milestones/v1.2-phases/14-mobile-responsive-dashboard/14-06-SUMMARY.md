---
phase: 14-mobile-responsive-dashboard
plan: 06
subsystem: ui
tags: [react, tailwind, playwright, ci, github-actions, evidence-capture]

# Dependency graph
requires:
  - phase: 14-01
    provides: Tailwind theme.screens tokens + responsive-audit.json + scripts/audit_responsive.py
  - phase: 14-02
    provides: tests/e2e/test_responsive_dashboard.py + anti-hidden grep gate
  - phase: 14-03
    provides: Dashboard.jsx + KeyMetricsStrip.jsx verified single-column at md:
  - phase: 14-04
    provides: PathToLiveTile.jsx flex-col → md:flex-row row reflow
  - phase: 14-05
    provides: TournamentDashboard dual-render + TournamentFilterChips min-h-[44px]
provides:
  - .github/workflows/dashboard-smoke.yml extended with paths filter + responsive matrix step (Option A; co-runs Path-to-LIVE + Responsive smokes on PRs touching frontend/api-gateway/preflight)
  - .planning/evidence/MOBILE-03/iphone-se-screenshot.png (375x667 — single-column reflow visible)
  - .planning/evidence/MOBILE-03/ipad-portrait-screenshot.png (768x1024 — md: breakpoint engaged)
  - .planning/evidence/MOBILE-03/test-output.txt (pytest local run; bootstrap fixture operator-blocked — 14 errors, captured honestly)
  - .planning/evidence/MOBILE-03/verify-stack-report.txt (4-check frontend-adapted report)
affects: [v1.2 milestone close, Phase 15 planning-tooling, OP-04 CI billing carry-in]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CI workflow paths filter extension — additive (Option A) to preserve existing Path-to-LIVE job, separate Run smoke step for the responsive matrix"
    - "Frontend rebuild → bundle-token grep → headless screenshot capture as a 3-step verify-stack equivalent for pure-frontend phases"

key-files:
  created:
    - .planning/evidence/MOBILE-03/iphone-se-screenshot.png
    - .planning/evidence/MOBILE-03/ipad-portrait-screenshot.png
    - .planning/evidence/MOBILE-03/test-output.txt
    - .planning/evidence/MOBILE-03/verify-stack-report.txt
  modified:
    - .github/workflows/dashboard-smoke.yml

key-decisions:
  - "Honest test-output.txt: captured the bootstrap_stack fixture failure as-is (14 errors at setup). No fabricated green log — the blocker is OP-04 + INFRA-02 carry-ins, both already tracked."
  - "Frontend rebuilt before screenshot capture. Discovered post-hoc that the previous agent's screenshots were taken against a stale May-20 nginx image — required no-cache rebuild + force-recreate to land Phase 14 dist (new hashes index-DiUc_6fW.css + index-UUYDe7Sn.js confirmed in container)."
  - "verify-stack-report.txt adapted from the 4-check (live exchange URL / real notification / DB row / restart-after-config) to a frontend equivalent (rebuild / bundle tokens / screenshots / pytest matrix). 3/4 PASS with the 4th blocked-with-mitigation."

patterns-established:
  - "Stale-build trap: docker compose --build alone reuses cache when only frontend/src changed (Dockerfile copies pre-built dist/). Must run `cd frontend && npm run build` first, then `--no-cache` rebuild, then `--force-recreate` — three steps, not one."
  - "Evidence-honesty rule: when pytest is operator-blocked, capture the actual error trace (not a workaround that masks the block). Pair with token-grep + screenshot mitigations in verify-stack-report."

requirements-completed:
  - MOBILE-03

# Metrics
duration: ~45min (executor: ~16 min before truncation; orchestrator rescue: ~25 min including frontend rebuild + recapture)
completed: 2026-05-22
---

# Phase 14 Plan 06 Summary

**Phase 14 CI surface extended to run the responsive matrix on every frontend PR; local-run evidence captured against a freshly-rebuilt frontend container (not the stale image the executor first hit).**

## What shipped

### `.github/workflows/dashboard-smoke.yml` extended
- Paths filter now triggers on `frontend/**`, `tests/e2e/test_responsive_dashboard.py`, `frontend/tailwind.config.js`, `scripts/audit_responsive.py` (in addition to the existing Path-to-LIVE triggers).
- New `Run smoke (responsive)` step added per Pattern A from PATTERNS.md line 649; existing `Run smoke (path-to-live)` step preserved.
- Both smokes share the same Playwright service stack — no new compose service, no new healthcheck dependency.
- CI execution gated on OP-04 (GH Actions billing); workflow is RED-on-main by design until billing resolves.

### `.planning/evidence/MOBILE-03/` (4 artifacts)

| File | Bytes | Source | Purpose |
|---|---|---|---|
| `iphone-se-screenshot.png` | 449,059 | Playwright Chromium @ 375x667 vs rebuilt http://localhost:3000 | Visual proof of single-column reflow |
| `ipad-portrait-screenshot.png` | 458,825 | Playwright Chromium @ 768x1024 vs rebuilt http://localhost:3000 | Visual proof of md: breakpoint engagement |
| `test-output.txt` | 14,650 | `PYTHONPATH=. pytest tests/e2e/test_responsive_dashboard.py -v` | Honest record of 14 errors at bootstrap_stack fixture (operator-blocked) |
| `verify-stack-report.txt` | ~3500 | Hand-authored 4-check report | Adapted /verify-stack for pure-frontend phase: 3/4 PASS, 1/4 BLOCKED with mitigation |

## Verification gates passed

- [x] `.github/workflows/dashboard-smoke.yml` contains `test_responsive_dashboard.py` reference
- [x] Workflow paths filter includes the 3 required entries (test file + Tailwind config + audit script)
- [x] `.planning/evidence/MOBILE-03/iphone-se-screenshot.png` exists (375x667 viewport, full-page)
- [x] `.planning/evidence/MOBILE-03/ipad-portrait-screenshot.png` exists (768x1024 viewport, full-page)
- [x] `.planning/evidence/MOBILE-03/test-output.txt` exists (captures actual pytest result, not a fabricated green log)
- [x] `.planning/evidence/MOBILE-03/verify-stack-report.txt` exists (>200 bytes; documents 3 PASS + 1 BLOCKED with operator-block citation + mitigation)
- [x] Frontend container rebuilt with Phase 14 source before screenshot capture (verified via bundle hash delta + token grep)
- [x] No modifications to STATE.md or ROADMAP.md (orchestrator owns those writes)

## Issues encountered & resolutions

### Issue 1 — Executor truncated mid-task

The `gsd-executor` Agent returned a truncated completion message ("Let me look at iPad portrait quickly.") after committing only `feat(14-06): wire test_responsive_dashboard.py into dashboard-smoke.yml`. SUMMARY.md, test-output.txt, and verify-stack-report.txt were not created; screenshots existed but were uncommitted.

**Resolution:** Orchestrator picked up the partial work directly in the worktree (lock prevented removal, but file ops + commits still worked). Re-ran pytest, re-captured screenshots after frontend rebuild, authored verify-stack-report + SUMMARY, committed.

### Issue 2 — Stale frontend container

Discovered the screenshots the executor captured were against `crypto-trading-bot-frontend` image built 2026-05-20 (3 days stale; pre-Phase-14). The bundle inside that image contained `md:flex-row` (already in older code) but **NOT** the three Phase 14 reflow tokens (`flex-col md:flex-row`, `min-h-[44px]`, `tournament-mobile-card`).

**Resolution:** 3-step rebuild:
1. `cd frontend && npm run build` — produced new `dist/` with all Phase 14 reflow class strings (`vite build` succeeded in 27.98s, 2635 modules transformed)
2. `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build --no-cache frontend` — produced new image `crypto-trading-bot-frontend:latest` with the fresh dist
3. `docker compose -f docker-compose.unified.yml up -d --force-recreate frontend` — kicked the existing container, which started with image hash `fb2d1b416f2a` (vs prior cached image)

Confirmed by `docker exec crypto-bot-frontend sh -c "grep -oE '...' /usr/share/nginx/html/assets/index*.js"` showing all 3 expected tokens.

**Lesson:** `docker compose --build` alone is insufficient when the Dockerfile copies a pre-built `dist/` folder. `frontend/Dockerfile` is a thin nginx wrapper — the actual build happens in `npm run build`, and that step is NOT triggered by `docker compose build`. The "Stale in-memory state = most common false-pass" CLAUDE.md rule applies one layer up: stale `dist/` produces a false-clean image build.

### Issue 3 — pytest blocked at bootstrap_stack

`tests/e2e/test_responsive_dashboard.py` parametrized 14 cases — all errored at session-scoped `bootstrap_stack` fixture (tests/integration/conftest.py:136). The fixture invokes `./bootstrap.sh` against a fresh `/tmp` clone per INFRA-02 contract; the fresh clone has no per-service `.env` files, so bootstrap exits 1.

**Resolution:** This is an OPEN operator-blocked carry-in (INFRA-02 checkpoint + OP-04 GH Actions billing per STATE.md). Not a Phase 14 regression. Captured the error trace honestly in test-output.txt, then mitigated via Check 2 (bundle token grep) + Check 3 (screenshots) in verify-stack-report.txt.

## Deferred / out of scope

- Real CI run via the new `dashboard-smoke.yml` job — gated on OP-04 (GH Actions billing). Already a v1.2 carry-in; not a Phase 14 blocker.
- Tests/e2e fixture refactor to skip bootstrap_stack on visual-only assertions — would unblock pytest matrix locally without waiting for INFRA-02. Out of Phase 14 scope; queue as a planning-tooling follow-up under Phase 15 or its own quick.
