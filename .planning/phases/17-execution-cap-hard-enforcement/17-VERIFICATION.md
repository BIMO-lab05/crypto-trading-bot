---
phase: 17-execution-cap-hard-enforcement
verified: 2026-05-24T03:10:00Z
status: gaps_found
score: 12/14 must-haves verified
overrides_applied: 0
gaps:
  - truth: "TE-CAP-02 / TE-CAP-05 status flipped to [x] Satisfied in .planning/REQUIREMENTS.md"
    status: failed
    reason: "Plan 02 Task 3 Step D + Plan 02 Verification Gate 3 explicitly required flipping `- [ ] **TE-CAP-05**` to `[x]` and `TE-CAP-05 | Phase 17 | Pending` to `Satisfied`. Plan 01 implicitly required the same for TE-CAP-02 (its success criteria state it as satisfied). Both REQ IDs still show `[ ]` / `Pending` in REQUIREMENTS.md. No `docs(17): mark TE-CAP-05 satisfied` commit exists in git log."
    artifacts:
      - path: ".planning/REQUIREMENTS.md"
        issue: "Line ~25: `- [ ] **TE-CAP-02**`; Line ~26: `- [ ] **TE-CAP-05**`; cross-ref table rows still show `TE-CAP-02 | Phase 17 | Pending` and `TE-CAP-05 | Phase 17 | Pending`"
    missing:
      - "Flip `- [ ] **TE-CAP-02**` → `- [x] **TE-CAP-02**`"
      - "Flip `- [ ] **TE-CAP-05**` → `- [x] **TE-CAP-05**`"
      - "Update cross-ref table: `TE-CAP-02 | Phase 17 | Pending` → `TE-CAP-02 | Phase 17 | Satisfied`"
      - "Update cross-ref table: `TE-CAP-05 | Phase 17 | Pending` → `TE-CAP-05 | Phase 17 | Satisfied`"
      - "Commit as `docs(17): mark TE-CAP-02 + TE-CAP-05 satisfied after Phase 17 ships`"
  - truth: "Live `POST http://localhost:8005/api/v1/orchestrator/emergency-stop` returns HTTP 404 against the running trading-engine container"
    status: failed
    reason: "Current live response is HTTP 200 with body `{\"success\":true,\"message\":\"Already in emergency stop\",...}` — the deployed `crypto-bot-trading` container was built BEFORE commit `f2aaa77` and the application source is NOT bind-mounted (only `logs/` and `safety/` are). The route deletion exists on disk in this branch but the running container still serves the pre-deletion code path. 17-01-SUMMARY explicitly documents this as a `[Environmental]` deferral and the verification block in 17-01-PLAN.md lists `curl :8005 → 404` as gate 5. The runtime CWE-306 vector is therefore still open against the live stack."
    artifacts:
      - path: "(running container: crypto-bot-trading on host port 8005)"
        issue: "Container Up 15h healthy but built from main pre-Phase-17. HTTP 200 returned by deleted route → live unauthenticated kill-switch still wired."
    missing:
      - "Merge `gsd/v1.3-ta-engine-correctness` branch to main (181 commits ahead per git log main..HEAD)"
      - "Rebuild trading-engine via `docker compose -f docker-compose.unified.yml up -d --build trading-engine`"
      - "Wait for container to reach `(healthy)` status"
      - "Re-run `curl -s -o /dev/null -w '%{http_code}\\n' -X POST http://localhost:8005/api/v1/orchestrator/emergency-stop` → must return 404"
      - "Record live 404 proof in updated SUMMARY (replacing the DEFERRED row in 17-01-SUMMARY verification table)"
---

# Phase 17: Execution-Cap Hard Enforcement Verification Report

**Phase Goal:** Execution-Cap Hard Enforcement v1.3 Phase 17 — (a) TE-CAP-02 emergency-stop HTTP admin auth (delete unauthenticated trading-engine route + api-gateway becomes sole admin entry); (b) TE-CAP-05 bare-except cleanup in order path (5 REQ-named broad-except sites rewritten per D-08 M/P/R taxonomy + cap-violation log-survival regression test). TE-CAP-01/03/04 demoted as audit-satisfied (no code work owed). Cap-check block at `auto_trader.py:1972-1986` (pre-rewrite numbering) UNCHANGED — Phase 16 AUDIT-01 satisfied.

**Verified:** 2026-05-24T03:10:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /api/v1/orchestrator/emergency-stop returns 404 after route handler deleted (unit-level) | ✓ VERIFIED | `grep -c '@router.post("/emergency-stop"' handlers/orchestration.py` → 0; `pytest test_orchestration_emergency_stop_removed.py` → 2 passed (3.92s) |
| 2 | api-gateway admin-guarded route at main.py:1747-1804 remains sole entry, existing tests green | ✓ VERIFIED | `grep -c "Depends(get_current_admin_user)" services/api-gateway/app/main.py` → 1; route + `Depends(get_current_admin_user)` + `stop_file.write_text()` confirmed at :1747-1804; existing emergency_stop tests present in test_gateway_80_coverage.py + test_main.py |
| 3 | Auth-note comment at :725-727 no longer makes the false "all admin routes protected upstream" claim | ✓ VERIFIED | `grep -c 'all admin routes are'` → 0; `grep -c 'DELETED in Phase 17'` → 1; new comment at :692-700 names what each sibling router actually protects (rolling-confidence gate / TRADING_MODE=LIVE refusal) |
| 4 | No regression in non-emergency-stop trading-engine routes | ✓ VERIFIED | Sibling routes confirmed present: 4 `@router.post` decorators remain on orchestration_router (strategy/register, signals/resolve, rebalance, signals/submit); admin_indicator_router and admin_force_signal_router both intact at :708 + :812 |
| 5 | D-03: admin_indicator_router (:735) and admin_force_signal_router (:839) explicitly UNTOUCHED | ✓ VERIFIED | Both routers present; rolling-confidence gate + TRADING_MODE=LIVE refusal gate referenced in new comment at :699-700 |
| 6 | Forcing position_value > cap_value produces literal `[RISK_GATE] PER_TRADE_CAP BREACH` CRITICAL log in caplog.records | ✓ VERIFIED | `pytest test_te_cap_05_log_survival.py::test_per_trade_cap_breach_log_survives_to_caplog` → PASSED |
| 7 | risk_limit_breaches_total.labels(breach_type="position_size").inc() invoked exactly once during breach path | ✓ VERIFIED | Asserted via Counter._value.get() before/after pattern in same test; PASSED |
| 8 | 5 REQ-named broad-except sites rewritten per D-08 taxonomy, no longer silently pass | ✓ VERIFIED | `:1551` → `(InvalidOperation, ValueError, TypeError) as e:` + warning log; `:1593` → `(ImportError, ValueError, AttributeError) as e:` + warning log (post-WR-02); `:1609` → `(ImportError, ValueError, AttributeError) as e:` + warning log (post-WR-02); `:2498` → `(AttributeError, aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as notif_err:` + error log (post-WR-01); `:3196` → same family (post-WR-01) |
| 9 | Every broad-except in :1500-3210 classified in M/P/R/default table | ✓ VERIFIED | D-09 classification table in 17-02-PLAN.md lines 199-237 enumerates all 32 sites with category + disposition + rationale (5 rewritten, 27 kept-as-is) |
| 10 | CRITICAL log line at :1978-1984 and cap-check block :1962-1986 UNCHANGED | ✓ VERIFIED | Block intact at shifted lines :1989-2003 (drift due to imports added above): `[RISK_GATE] PER_TRADE_CAP BREACH` log literal present; `risk_limit_breaches_total.labels(breach_type="position_size").inc()` literal present; no try/except introduced between cap-check and the `return` statement |
| 11 | Sibling files live_trading.py, bybit_adapter.py, paper_trading.py UNCHANGED (D-06) | ✓ VERIFIED | `git log --all --oneline --since 2026-05-23 -- services/trading-engine/app/live_trading.py services/trading-engine/app/exchanges/bybit_adapter.py services/trading-engine/app/paper_trading.py` → empty; only auto_trader.py + handlers/orchestration.py + tests changed in trading-engine app code |
| 12 | D-11: cap-violation log line REQ-CAP-05 asserts on is the literal `[RISK_GATE] PER_TRADE_CAP BREACH` CRITICAL emit | ✓ VERIFIED | Test asserts `any("[RISK_GATE] PER_TRADE_CAP BREACH" in rec.message for rec in caplog.records)`; test PASSED; TE-CAP-01 demotion noted in REQUIREMENTS.md row |
| 13 | TE-CAP-02 + TE-CAP-05 status flipped to `[x] Satisfied` in REQUIREMENTS.md | ✗ FAILED | Both still show `- [ ]` and cross-ref table rows `\| TE-CAP-02 \| Phase 17 \| Pending \|` + `\| TE-CAP-05 \| Phase 17 \| Pending \|`. Plan 02 Task 3 Step D explicitly required this flip; no `docs(17): mark TE-CAP-05 satisfied` commit landed. |
| 14 | Live POST :8005/api/v1/orchestrator/emergency-stop returns 404 against running container (17-01-PLAN.md gate 5) | ✗ FAILED | Live curl against running `crypto-bot-trading` container returns HTTP 200 with body `{"success":true,"message":"Already in emergency stop",...}`. Container built before commit `f2aaa77` and application source NOT bind-mounted — runtime route still active. CWE-306 vector still open against live stack. |

**Score:** 12/14 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `services/trading-engine/app/handlers/orchestration.py` | Route table without `@router.post("/emergency-stop")`; updated comment at :725-727 | ✓ VERIFIED | `grep -c '@router.post("/emergency-stop"' → 0`; `grep -c '^async def emergency_stop' → 0`; new comment block at :691-700 contains `DELETED in Phase 17` (1 occurrence) |
| `services/trading-engine/tests/test_orchestration_emergency_stop_removed.py` | Negative test asserting 404 | ✓ VERIFIED | File exists (3170 bytes); 2 test functions including `test_emergency_stop_route_deleted_returns_404`; imports `router as orchestration_router` from `app.handlers.orchestration`; both tests PASS in 3.92s |
| `services/trading-engine/app/auto_trader.py` | Order path with broad-excepts rewritten; cap-check block :1962-1986 untouched | ✓ VERIFIED | `[RISK_GATE] PER_TRADE_CAP BREACH` log literal present; `risk_limit_breaches_total.labels(breach_type="position_size").inc()` literal present; 5 rewritten sites confirmed; 26 broad-except in :1500-3250 (off-by-one from plan's 27 expectation due to outer except at :3252 drifting past the awk gate ceiling — substantively correct, only ceiling-window artifact) |
| `services/trading-engine/tests/test_te_cap_05_log_survival.py` | Forward-going regression — BREACH log to caplog + counter increment | ✓ VERIFIED | File exists (12889 bytes); 2 tests; PASSED in pytest (test_per_trade_cap_breach_log_survives_to_caplog + test_per_trade_cap_within_limit_does_not_emit_breach_log) |
| `services/trading-engine/tests/test_te_cap_05_metric_emit_survival.py` (added by WR-03 fix) | Category-M regression — Counter ValueError survives to logger.warning | ✓ VERIFIED | File exists; 2 tests; PASSED in pytest (test_min_qty_reject_survives_value_error_from_counter_inc + test_min_notional_reject_survives_value_error_from_counter_inc) |
| `services/api-gateway/app/main.py:1747-1804` | Admin-guarded sole entry preserved | ✓ VERIFIED | Route + `Depends(get_current_admin_user)` + `stop_file.write_text()` confirmed UNCHANGED at :1747-1804 |
| `.planning/REQUIREMENTS.md` | TE-CAP-02 + TE-CAP-05 flipped to `[x] Satisfied` | ✗ STUB | File exists but contents not updated — see Gap #13 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| orchestration.py router | FastAPI default unmatched-route handler | route table absence → 404 | ✓ WIRED | `grep -c '@router.post("/emergency-stop"' → 0`; FastAPI default handler returns 404 (proven by passing test) |
| api-gateway main.py:1747-1804 | kill-switch file safety/EMERGENCY_STOP | pathlib.Path.write_text + Depends(get_current_admin_user) | ✓ WIRED | Both elements present; route is sole writer per D-04 |
| auto_trader.py _execute_trade_with_setup | logger.critical at :1978-1984 (now shifted to :1995-2001) | cap-check at :1972-1986 (no intervening swallow) | ✓ WIRED | No try/except introduced between `if position_value > cap_value:` and `return`; verified via Read of block at shifted :1989-2003 |
| auto_trader.py :1975 (now :1992) | core/metrics.py:228 risk_limit_breaches_total | deferred import inside cap-check block | ✓ WIRED | `from app.core.metrics import risk_limit_breaches_total` + `.labels(breach_type="position_size").inc()` present; Counter increment verified by passing D-10 test |
| Phase 17 commits → main branch deployment | running trading-engine container | docker compose up -d --build | ✗ NOT_WIRED | 181 commits ahead of main on branch `gsd/v1.3-ta-engine-correctness`; running container built from pre-Phase-17 main; live curl proves stale code |
| Phase 17 satisfied claims → REQUIREMENTS.md tracking | `[x] Satisfied` row entries | docs commit (planned, not landed) | ✗ NOT_WIRED | TE-CAP-02 + TE-CAP-05 both still `[ ] Pending`; no `docs(17): mark ...` commit in git log |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Plan 01 negative test asserts 404 on deleted route | `cd services/trading-engine && pytest tests/test_orchestration_emergency_stop_removed.py --no-cov -q` | `2 passed in 3.92s` | ✓ PASS |
| Plan 02 D-10 cap-breach log survival | `cd services/trading-engine && pytest tests/test_te_cap_05_log_survival.py --no-cov -v` | `2 passed in ~34s` | ✓ PASS |
| Plan 02 WR-03 Category-M regression | `cd services/trading-engine && pytest tests/test_te_cap_05_metric_emit_survival.py --no-cov -v` | `2 passed (combined run with log-survival: 4 passed in 34.03s)` | ✓ PASS |
| Zero bare-except in :1500-3250 of auto_trader.py | `awk 'NR>=1500 && NR<=3250 && /^[[:space:]]*except:[[:space:]]*$/' ... \| wc -l` | `0` (was 2 pre-rewrite at :2498, :3196) | ✓ PASS |
| Zero silent `except Exception: pass` in :1500-3250 | awk two-line match | `0` (was 2 pre-rewrite at :1593, :1609) | ✓ PASS |
| `InvalidOperation` imported from decimal | `grep -E "^from decimal import .*InvalidOperation" auto_trader.py` | `from decimal import Decimal, InvalidOperation` (1 hit) | ✓ PASS |
| `aiohttp` imported (post-WR-01; replaced `httpx`) | `grep -n "^import aiohttp" auto_trader.py` | `30:import aiohttp` | ✓ PASS |
| Cap-check log literal present | `grep -F '[RISK_GATE] PER_TRADE_CAP BREACH' auto_trader.py` | 1 hit at :1996 (drift from documented :1978) | ✓ PASS |
| Cap-check metric literal present | `grep -F 'risk_limit_breaches_total.labels(breach_type="position_size").inc()' auto_trader.py` | 1 hit at :1994 | ✓ PASS |
| ADR-010 paper-mode 10% cap config intact | `grep -A 1 "max_risk_per_trade: float = Field" config.py` | `default=0.10` confirmed at config.py:321-332 | ✓ PASS |
| Live curl on :8005 returns 404 | `curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8005/api/v1/orchestrator/emergency-stop` | `200` (stale container — pre-deletion route active) | ✗ FAIL |
| api-gateway sole entry route + admin guard intact | `grep -c "Depends(get_current_admin_user)" api-gateway/main.py` + read of :1747-1804 | 1 hit; full route block intact with `stop_file.write_text()` | ✓ PASS |
| D-06 boundary (sibling files unchanged) | `git log --since 2026-05-23 -- live_trading.py bybit_adapter.py paper_trading.py` | empty | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TE-CAP-02 | 17-01-PLAN | Emergency-stop HTTP admin auth | ✓ SATISFIED (code) / ✗ BLOCKED (REQ doc + runtime) | Route deleted on disk; 2 unit tests green; api-gateway admin guard sole entry. BLOCKED on: (a) REQUIREMENTS.md status flip (Gap #13); (b) live runtime stale-container (Gap #14) |
| TE-CAP-05 | 17-02-PLAN | Bare-except cleanup in order path | ✓ SATISFIED (code) / ✗ BLOCKED (REQ doc) | 5 sites rewritten per D-08 taxonomy; 4 regression tests green; cap-check unchanged. BLOCKED on REQUIREMENTS.md status flip (Gap #13) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `services/trading-engine/tests/test_te_cap_05_log_survival.py` | 284-289 | `try: await trader._execute_trade_with_setup(...) except Exception: pass` (IN-02 from iter-2 REVIEW) | ℹ️ Info | Documented in REVIEW.md iter-2 (carry-forward from iter-1) — bare swallow around SUT in negative-complement test; intentional but smelly; out of fix_scope=critical_warning. Not blocking. |
| `services/trading-engine/app/main.py` | 127-130 | Stale comment listing `emergency-stop` under `/api/v1/orchestrator/*` after deletion (IN-01) | ℹ️ Info | Out of iter-2 file scope. Cosmetic doc-rot — non-functional. Not blocking. |
| `services/trading-engine/app/auto_trader.py` | :861-866 | Same silent `except Exception: pass` pattern as B-2/B-3 in `_check_emergency_stop_file` method | ℹ️ Info (out-of-scope by D-06) | Outside `:1500-3210` rewrite window; flagged by Plan 02 D-09 for deferred hygiene phase. Not blocking. |

### Human Verification Required

None required at the verification level — all 14 truths resolve programmatically. Both gaps have mechanical closure paths (REQ doc edit; container rebuild post-merge); neither requires judgment-call human verification.

### Gaps Summary

Phase 17 ships both deliverables at the code level:

- **TE-CAP-02 (Plan 01):** Route deletion + comment rewrite + 404 negative test are all in place on disk; unit tests pass; api-gateway sole-entry intact; D-03 sibling routes untouched.
- **TE-CAP-05 (Plan 02):** 5 REQ-named broad-except sites rewritten with iteration-2 typed-except families (aiohttp.ClientError+AttributeError for notif sites per WR-01; ImportError+ValueError+AttributeError for Prometheus sites per WR-02); cap-check block at :1962-1986 (now :1989-2003 due to imports added above) UNCHANGED; 4 regression tests (D-10 log-survival + WR-03 Category-M) pass; D-06 sibling-file boundary held (no changes to live_trading.py / bybit_adapter.py / paper_trading.py); ADR-010 paper-mode 10% cap config + LIVE 2% per-trade cap unchanged.

**Two unresolved gaps prevent declaring the phase fully shipped:**

1. **Documentation/tracking miss (REQUIREMENTS.md):** Plan 02 Task 3 Step D explicitly required flipping `- [ ] **TE-CAP-05**` → `- [x]` and the cross-ref table row from `Pending` to `Satisfied`. Plan 01's success criteria implied the same for TE-CAP-02. Neither flip landed; no `docs(17): mark ... satisfied` commit appears in `git log main..HEAD`. This is a one-commit fix.

2. **Runtime/deployment miss (live :8005):** 17-01-PLAN Task 3 verification gate 5 requires `curl :8005 → 404` against the running container. Current live response is HTTP 200 with `{"success":true,"message":"Already in emergency stop",...}` — the deployed `crypto-bot-trading` container was built before commit `f2aaa77` and the trading-engine application source is not bind-mounted. 17-01-SUMMARY documents this as `[Environmental] DEFERRED` to orchestrator post-merge because rebuilding from the worktree would collide on host port :8005 with the running stack. **The CWE-306 vector that TE-CAP-02 targets is still open at runtime against the live trading-engine.** Closure path is mechanical: merge `gsd/v1.3-ta-engine-correctness` (181 commits ahead of main) to main, then `docker compose -f docker-compose.unified.yml up -d --build trading-engine`, wait for healthy, re-curl.

Neither gap requires re-planning; both are mechanical follow-ups. The orchestrator should:
- Land a `docs(17): mark TE-CAP-02 + TE-CAP-05 satisfied` commit flipping REQUIREMENTS.md as listed in Gap #13's `missing:` section.
- After merging this branch to main, execute the rebuild + re-curl sequence and record the live 404 proof in 17-01-SUMMARY's verification table (replacing the DEFERRED row).

The code-level Phase 17 deliverables (route deletion, 5 typed-except rewrites, 6 new pytest assertions across 3 files) are correct and tested. The runtime exposure window remains open until deployment closes the loop.

---

_Verified: 2026-05-24T03:10:00Z_
_Verifier: Claude (gsd-verifier)_
