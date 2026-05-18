---
phase: 10
slug: path-to-live-dashboard
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-17
---

# Phase 10 — Validation Strategy

> Per-phase validation contract reconstructed from artifacts after phase execution. State B (no prior VALIDATION.md, three SUMMARY files present). Behavioral coverage added retroactively via `gsd-nyquist-auditor`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest 7.4.4 (api-gateway uses `services/api-gateway/pytest.ini`; container python 3.14) |
| **Frontend framework** | vitest 1.6 + @testing-library/react 14.2 + jest-dom 6.4 |
| **E2E framework** | pytest-playwright (Chromium; CI-only via `.github/workflows/dashboard-smoke.yml`) |
| **Config files** | `pytest.ini`, `pyproject.toml`, `services/api-gateway/pytest.ini`, `frontend/package.json` |
| **Quick backend command** | `docker exec crypto-bot-api-gateway pytest tests/test_preflight_carry_ins.py -v` |
| **Quick frontend command** | `cd frontend && npx vitest run src/hooks/__tests__/useCarryIns.test.jsx src/hooks/__tests__/useLiveReadiness.test.jsx src/components/__tests__/PathToLiveTile.test.jsx` |
| **Quick gates command** | `pytest tests/integration/test_dashlive_grep_gates.py -v` |
| **Full smoke (CI only)** | `pytest tests/e2e/test_path_to_live_smoke.py --screenshot=only-on-failure --video=retain-on-failure -v` |
| **Estimated quick runtime** | ~30 s (backend 0.5 s + frontend 26 s + gates 2 s) |
| **Estimated full runtime** | ~5–10 min (CI smoke with bootstrap.sh boot) |

**Per CLAUDE.md gotcha:** api-gateway test suite must run inside the container — host pip has fastapi 0.136 (HTTPBearer returns 401), deployed container pins fastapi 0.109 (returns 403). The carry-ins endpoint is unauth so host pytest also works for it, but container is canonical.

---

## Sampling Rate

- **After every task commit:** Run the matching quick command (backend OR frontend OR gates).
- **After every plan wave:** Run all three quick commands (~30 s total).
- **Before `/gsd-verify-work`:** All three quick suites green + CI smoke green on the PR.
- **Max feedback latency:** ~30 seconds (quick suites). CI smoke deferred to PR-trigger only.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | DASHLIVE-02 | T-10-01-03 | Atomic file write; bind-mount targets parent dir not file; env defaults present | structural | `jq + grep + docker compose config` (PLAN inline verify) | ✅ | ✅ green |
| 10-01-02 | 01 | 1 | DASHLIVE-02 | T-10-01-03 / T-10-01-04 / T-10-01-06 | D-10-04 response shape; D-10-07 reset rule; D-10-08 UNKNOWN-as-not-PASS; D-10-11 graceful degradation; atomic temp+rename; file-read fallback | integration | `docker exec crypto-bot-api-gateway pytest tests/test_preflight_carry_ins.py -v` | ✅ (16 tests) | ✅ green |
| 10-01-03 | 01 | 1 | DASHLIVE-02 | T-10-01-06 | include_router registration noqa-pinned against autoflake | structural | `grep + ast.parse` (PLAN inline verify) | ✅ | ✅ green |
| 10-02-01 | 02 | 1 | DASHLIVE-01, DASHLIVE-03 | T-10-02-04 | useCarryIns + useLiveReadiness: queryKey, path, D-10-15 cadence, D-10-16 authority JSDoc | unit | `cd frontend && npx vitest run src/hooks/__tests__/useCarryIns.test.jsx src/hooks/__tests__/useLiveReadiness.test.jsx` | ✅ (7 tests) | ✅ green |
| 10-02-02 | 02 | 1 | DASHLIVE-01, DASHLIVE-03 | T-10-02-02 / T-10-02-03 / T-10-02-04 | Banner reads server `overall` (no client recompute, D-10-04+D-10-16); locked Tailwind tokens; testid contracts; PREFLIGHT check fallback chain; carry-in chip colors; ALMOST subtitle; error path via TileState | unit | `cd frontend && npx vitest run src/components/__tests__/PathToLiveTile.test.jsx` | ✅ (13 tests) | ✅ green |
| 10-03-01 | 03 | 2 | DASHLIVE-01..04 | T-10-03-05 / T-10-03-07 | All 7 D-10-18 smoke assertions (tile visible, 6 PREFLIGHT chips, 5 carry-ins open, banner matches endpoint, endpoint shape, DSR row, 24h window fast-forward); LIVE-mode override scoped to trading-engine only; MARKET_DATA_SOURCE absent for tape safety | smoke (CI) | `pytest tests/e2e/test_path_to_live_smoke.py --screenshot=only-on-failure --video=retain-on-failure -v` (via dashboard-smoke.yml) | ✅ (4 tests collected) | ⚠️ CI-only |
| 10-03-02 | 03 | 2 | DASHLIVE-04 | T-10-03-01 / T-10-03-02 / T-10-03-04 | Defence-in-depth grep gates with narrow scope; PR-paths-filtered workflow with pinned actions @v4/@v5; no nightly cron (Phase 12 owns) | integration | `pytest tests/integration/test_dashlive_grep_gates.py -v` | ✅ (2 tests) | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky/environment-gated*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. vitest, pytest, pytest-playwright, and CI runner already installed at session start.*

Retroactive Nyquist test files created by `gsd-nyquist-auditor` on 2026-05-17:

- `services/api-gateway/tests/test_preflight_carry_ins.py` — 16 tests (D-10-04/07/08/11 + atomic write + file-read fallback)
- `frontend/src/hooks/__tests__/useCarryIns.test.jsx` — 4 tests (queryKey + path + cadence + D-10-16 JSDoc)
- `frontend/src/hooks/__tests__/useLiveReadiness.test.jsx` — 3 tests (queryKey + path + cadence parity)
- `frontend/src/components/__tests__/PathToLiveTile.test.jsx` — 13 tests (banner tokens, testids, fallback chain, chip colors, ALMOST subtitle, error path, D-10-16 adversarial discriminator)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| D-10-18 #1..#7 end-to-end smoke (tile renders against live stack) | DASHLIVE-01..04 | Requires Chromium driver + booted docker compose stack — not available in WSL2 dev env. Runs in `dashboard-smoke.yml` on PRs that match the six-path filter, plus `workflow_dispatch`. | Wait for PR CI green on `dashboard-smoke` job, OR run locally with `docker compose -f docker-compose.unified.yml up -d` → `playwright install chromium` → `pytest tests/e2e/test_path_to_live_smoke.py -v`. |
| 24h continuous-PASS window (D-10-18 #7) without fast-forward override | DASHLIVE-02 | Real 86400 s window — not exercised in any automated test. Fast-forward env override (`PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1`) gives 2 s proxy for the same logic; the production cadence is operator-observed on the live dashboard. | After flipping `PAPER_TRADING_MODE=false` etc., watch dashboard tile transition DO_NOT_FLIP → ALMOST (immediately) → READY (after 24h) over the live operator window. Optional: scrape `/api/preflight/carry-ins.window.elapsed_seconds` periodically. |
| WR-03 cleanup: `all_preflight_checks_passing` teardown lacks `--no-deps` | DASHLIVE-04 | Non-blocking warning carried from 10-VERIFICATION.md. Real impact only surfaces when CI restart races against postgres/redis/rabbitmq teardown. Smoke-suite empirical pass-rate is the signal. | Watch `dashboard-smoke` job for retry/flaky failures; add `--no-deps` to teardown compose call if CI flake rate climbs. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has a quick command; only 10-03-01 e2e smoke is CI-gated, with 10-03-02 grep gates as defence-in-depth)
- [x] Wave 0 covers all MISSING references (4 retroactive test files added 2026-05-17 by `gsd-nyquist-auditor`)
- [x] No watch-mode flags (`vitest run`, not `vitest`; `pytest` plain)
- [x] Feedback latency < 30 s for quick suites
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-17 — 36/36 behavioral tests green across backend + frontend + gates; e2e smoke shipped and CI-gated.

---

## Validation Audit 2026-05-17

| Metric | Count |
|--------|-------|
| Gaps found | 4 |
| Resolved | 4 |
| Escalated | 0 |
| Tests added | 36 |
| Files added | 4 |

### Notable

- **Adversarial discriminator (Gap 4):** PathToLiveTile test mocks `useCarryIns.data.overall = "READY"` while `useLiveReadiness.data.checks` are all FAIL. If the component recomputed `overall` client-side, banner would render `bg-rose-700` (DO_NOT_FLIP). Test asserts `bg-emerald-700` (READY) and passes — confirms D-10-16 authority rule (server-computed `overall` wins; client never recomputes).
- **WARNING — Reproducibility for Gap 1:** `docker exec crypto-bot-api-gateway pytest tests/test_preflight_carry_ins.py` requires a container rebuild (`docker compose -f docker-compose.unified.yml build api-gateway && docker compose -f docker-compose.unified.yml up -d api-gateway`) when running against a stale image — the routes package was missing from the initial container. `docker cp` is blocked by the EMERGENCY_STOP bind-mount WSL2 quirk; the auditor used `cat | docker exec -i` stdin injection as a one-shot workaround.
