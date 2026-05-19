---
phase: 09-ml-re-enablement-gate
plan: 03-reason-enum-and-digest
subsystem: ml-gate
tags:
  - mlgate
  - reason-enum
  - logging
  - telegram-digest
  - notification-service
  - grep-gates
  - cross-service-wiring
  - phase-9
requires: []  # Wave 1; this plan EXPORTS to Plan 09-02 via cross-plan import
provides:
  - "app.aggregation.ml_gate_reasons module (5-member enum + in-process counter + set_current_reason/get_current_reason cross-plan cache — D-09-03-06)"
  - "Structured-reason log emissions at all 3 trading-engine ML-disabled branch points (E1: enhanced_aggregator __init__; E2: enhanced_aggregator parallel-fetch else-branch; E3: signal_aggregator fallback)"
  - "Unauthenticated read-only observability endpoint GET /api/preflight/ml-gate-reason-counts (Phase 8 D-09 precedent)"
  - "notification-service scheduled fetcher (scheduler/ml_gate_digest.py) — pulls counts via httpx + forwards to send_daily_summary"
  - "alert_manager.send_daily_summary(ml_gate_reason_counts=...) extension with canonical-ordered template render"
  - "CI grep gate tests/integration/test_mlgate_reason_grep_gate.py"
affects:
  - "phase 09-02 (auto-flip imports set_current_reason from THIS plan's module — D-09-03-06)"
  - "phase 10 DASHLIVE (dashboard tile can read AlertCreate.metadata.ml_gate_reason_counts or poll /api/preflight/ml-gate-reason-counts directly)"
  - "phase 11 LIVECLOSE (operator-visible reason counts in daily digest contribute to pre-LIVE-flip evidence audit)"
tech-stack:
  added:
    - "respx (already a project dep — used for httpx-AsyncClient mocking in scheduler integration tests)"
  patterns:
    - "Stdlib-only helper module (mirrors app.preflight) — no circular-import risk for lifespan/aggregator co-callers"
    - "Counter-backed in-process counter with snapshot-returns-copy semantics"
    - "Module-level mutable state for cross-plan cache (single-writer, GIL-atomic read-mostly)"
    - "FastAPI APIRouter sibling-handler pattern (mirror of handlers/preflight.py)"
    - "respx + asyncio integration test pattern for cross-service HTTP — no PYTHONPATH cross-import"
    - "Self-avoiding grep gate diagnostic message (variable-assembled at runtime — Phase 8 self-avoidance discipline)"
key-files:
  created:
    - services/trading-engine/app/aggregation/ml_gate_reasons.py
    - services/trading-engine/app/handlers/ml_gate_reasons.py
    - services/trading-engine/tests/test_ml_gate_reasons.py
    - services/trading-engine/tests/test_ml_gate_reasons_endpoint.py
    - tests/integration/test_mlgate_reason_grep_gate.py
    - services/notification-service/app/scheduler/__init__.py
    - services/notification-service/app/scheduler/ml_gate_digest.py
    - services/notification-service/tests/test_daily_digest_ml_gate.py
    - services/notification-service/tests/test_ml_gate_digest_scheduler.py
  modified:
    - services/trading-engine/app/aggregation/__init__.py
    - services/trading-engine/app/aggregation/enhanced_aggregator.py
    - services/trading-engine/app/signal_aggregator.py
    - services/trading-engine/app/main.py
    - services/notification-service/app/alert_manager.py
    - services/notification-service/app/routers/alerts.py
    - services/notification-service/app/main.py
decisions:
  - "D-09-03-01: Wording-bug locus correction — MLGATE-03 emissions land in trading-engine (NOT technical-analysis) — REQUIREMENTS.md wording cleanup deferred to follow-up"
  - "D-09-03-02: Reason enum lives at services/trading-engine/app/aggregation/ml_gate_reasons.py; Literal + tuple pattern mirroring Phase 8 Status enum"
  - "D-09-03-03: Log literal contract — every emission carries the contiguous substring 'ML predictions disabled reason=' (f-string starting with the literal is OK)"
  - "D-09-03-04: Digest aggregation via HTTP-pull from new endpoint; canonical reason-order tuple duplicated in notification-service (decoupling > deduplication)"
  - "D-09-03-06: Cross-plan reason-state cache — set_current_reason (writer, Plan 09-02) + get_current_reason (default-fallback reader); module-level _current_reason defaults to 'manual_override' (closes checker Blocker 1 — emissions name the truthful cause)"
  - "D-09-03-07: Cross-service wiring contract — GET /api/preflight/ml-gate-reason-counts unauthenticated read-only on trading-engine; notification-service scheduled fetcher pulls via httpx; graceful degradation on fetch failure (closes checker Blocker 2 — SC#4 delivered THIS phase, no v1.2 deferral)"
metrics:
  duration: "~36 min"
  completed: "2026-05-17T00:57:14Z"
  tasks: 3
  files_created: 9
  files_modified: 7
---

# Phase 9 Plan 03: Reason Enum + Daily Digest Summary

**One-liner:** Five-member structured-reason enum (`no_evidence`, `dsr_below_gate`, `evidence_stale`, `regime_shift`, `manual_override`) with cross-plan in-process cache wired into every trading-engine ML-disabled emission site, exposed via a new unauthenticated `/api/preflight/ml-gate-reason-counts` endpoint, and rendered in the daily Telegram digest via a new notification-service scheduled fetcher (respx-mocked integration test verifies end-to-end delivery).

## Goal

Deliver MLGATE-03: turn "ML is off" from a single bit into actionable diagnostic state. The 5-member enum names the cause; the cross-plan cache propagates the truthful reason from Plan 09-02's auto-flip into every per-cycle log emission; the daily digest aggregates the 24h counts into a Telegram-shipped summary. Closes both checker Blockers (Blocker 1: enum-reachability via cross-plan cache; Blocker 2: SC#4 cross-service delivery via HTTP-pull scheduler).

## Tasks Executed

| # | Task | Commit | Files |
| - | ---- | ------ | ----- |
| 1 | Create reason enum module + helper + in-process counter + cross-plan reason-state cache (+ 15 unit tests, 22 parametrize expansions) | `f93001d` | `services/trading-engine/app/aggregation/ml_gate_reasons.py` (NEW); `services/trading-engine/app/aggregation/__init__.py`; `services/trading-engine/tests/test_ml_gate_reasons.py` (NEW) |
| 2 | Wire emissions at every `use_ml=False` branch (default-reason fallback) + unauthenticated read-only observability endpoint + CI grep gate | `f7f8bb2` | `services/trading-engine/app/aggregation/enhanced_aggregator.py`; `services/trading-engine/app/signal_aggregator.py`; `services/trading-engine/app/handlers/ml_gate_reasons.py` (NEW); `services/trading-engine/app/main.py`; `services/trading-engine/tests/test_ml_gate_reasons_endpoint.py` (NEW); `tests/integration/test_mlgate_reason_grep_gate.py` (NEW) |
| 3 | Cross-service daily-digest wiring — notification-service scheduled fetcher + template render + integration test | `7634fe6` | `services/notification-service/app/alert_manager.py`; `services/notification-service/app/routers/alerts.py`; `services/notification-service/app/main.py`; `services/notification-service/app/scheduler/__init__.py` (NEW); `services/notification-service/app/scheduler/ml_gate_digest.py` (NEW); `services/notification-service/tests/test_daily_digest_ml_gate.py` (NEW); `services/notification-service/tests/test_ml_gate_digest_scheduler.py` (NEW) |

## Verification

| Acceptance criterion | Status | Evidence |
| -------------------- | ------ | -------- |
| `ML_GATE_REASONS` tuple has exactly 5 members | PASS | `len(ML_GATE_REASONS) == 5` asserted in `test_enum_tuple_has_exactly_five_members` (22 unit tests pass) |
| Log literal `"ML predictions disabled reason="` is a contiguous substring | PASS | `grep -c "ML predictions disabled reason=" services/trading-engine/app/aggregation/ml_gate_reasons.py` → 3 occurrences (docstrings + actual emission line); caplog assertion in `test_log_ml_disabled_emits_literal_with_reason` |
| `set_current_reason` + `get_current_reason` exported for Plan 09-02 | PASS | Runtime import smoke: `python3 -c "from app.aggregation.ml_gate_reasons import set_current_reason, get_current_reason"` succeeds; default `"manual_override"`; `set('dsr_below_gate')` propagates to `get()` |
| All 5 reasons reachable in production (closes Blocker 1) | PASS | Parametrized `test_all_five_reasons_reachable_via_explicit_arg` (5 PASS) + `test_all_five_reasons_reachable_via_set_current_reason` (5 PASS) — auto-flip-propagation path proven end-to-end |
| Emission sites delegate to `log_ml_disabled` with no hardcoded reason | PASS | `grep -cE 'log_ml_disabled\("manual_override"' services/trading-engine/app/aggregation/enhanced_aggregator.py services/trading-engine/app/signal_aggregator.py` → 0; default-fallback via `get_current_reason()` is the only path |
| Every `"ML predictions disabled"` line in TE app carries `reason=` | PASS | `grep -rn "ML predictions disabled" services/trading-engine/app/ --include="*.py" \| grep -v "/tests/" \| grep -vE "reason=" \| wc -l` → 0 (zero offenders) |
| Module imports stdlib only | PASS | `grep -E "^\s*(from\|import) " ml_gate_reasons.py` → `from __future__`, `import logging`, `from collections import Counter`, `from typing import Literal` only |
| New endpoint registered + smoke tests pass | PASS | `app/main.py` includes `ml_gate_reasons_router` (alongside `preflight_router`); 3/3 endpoint smoke tests pass (empty/populated/error→500) |
| CI grep gate enforces structured-reason discipline | PASS | `test_mlgate_reason_field_present` (gate 1) + `test_mlgate_reason_helper_imported_at_emission_sites` (gate 2) — both pass |
| Notification-service digest renders ML Gate Reasons section | PASS | 7/7 template tests pass: backward compat (kwarg absent + kwarg empty dict), section appears, canonical order via reverse-insertion, all-5-render, metadata carries dict, metadata omits key when None |
| Cross-service integration delivers SC#4 (closes Blocker 2) | PASS | 4/4 scheduler integration tests pass: happy path (HTTP 200 → counts in digest), trading-engine unreachable (ConnectError → graceful degrade, digest still ships), HTTP 500 (same shape), non-dict body (200 with JSON array → graceful degrade) |
| Phase 8 grep gate #1 still passes | PASS | `test_live_preflight_rejected_log_exists` PASS (the LIVE_PREFLIGHT_REJECTED literal survives in TE app) |
| Notification-service full test suite green | PASS | 166 passed (no regressions) |
| Trading-engine aggregator suite green | PASS | 45 passed, 32 pre-existing skips (PR#86 refactor — unrelated to this plan) |

## Manual Verification Records

Per Task 2 acceptance criteria (mirrors Phase 8 08-03-SUMMARY.md mutation-discipline):

**Mutation:** `sed -i` replaced `logger.info(f"ML predictions disabled reason={reason} detail={detail}")` in `ml_gate_reasons.py` with `logger.info(f"ML predictions disabled")` (stripped the `reason=` field).

```
--- after mutation ---
$ grep "ML predictions disabled" services/trading-engine/app/aggregation/ml_gate_reasons.py
    logger.info(f"ML predictions disabled")    <-- mutated line

$ pytest tests/integration/test_mlgate_reason_grep_gate.py::test_mlgate_reason_field_present
FAILED — Offenders:
  services/trading-engine/app/aggregation/ml_gate_reasons.py:134: logger.info(f"ML predictions disabled")
exit code = 1
```

**Restored:** copied backup back to original location.

```
--- restored ---
$ grep "ML predictions disabled" services/trading-engine/app/aggregation/ml_gate_reasons.py
    logger.info(f"ML predictions disabled reason={reason} detail={detail}")   <-- restored

$ pytest tests/integration/test_mlgate_reason_grep_gate.py::test_mlgate_reason_field_present
PASSED in 2.14s
exit code = 0
```

The grep gate correctly distinguishes structured-reason emissions (PASS) from bare disabled-event literals (FAIL) — manual failure-mode verification successful.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Initial comment text contained the literal grep-gate substring**

- **Found during:** Task 2 grep-gate test run (first attempt failed)
- **Issue:** My code comment in `signal_aggregator.py` at line 1137 contained the literal `"ML predictions disabled"` as part of an explanatory comment, which triggered the grep gate (the gate scans EVERY line, comments included, to catch open-coded log strings).
- **Fix:** Rewrote the comment to use `"ML-disabled branch"` instead of the bare literal. Functional behavior unchanged; comment intent preserved.
- **Files modified:** `services/trading-engine/app/signal_aggregator.py`
- **Commit:** included in Task 2 `f7f8bb2` (no separate commit — fix and original work landed together)

### Pre-existing Issues (NOT auto-fixed — scope-out)

**2. [Pre-existing] Phase 8 grep gate #2 (`test_preflight_module_imports_at_lifespan`) fails on host**

- **Found during:** post-Task-2 regression sweep
- **Issue:** This Phase 8 test attempts `import app.main as main_mod` which requires the `trading-engine` working directory on `PYTHONPATH`. Pre-existing failure on host pytest run (confirmed by `git stash` + re-run on the base commit — same failure, unrelated to my changes).
- **Why not fixed:** Out of scope per Rule 4 SCOPE BOUNDARY — failure exists on the parent branch before this plan landed. Per CLAUDE.md memory `feedback_api_gateway_test_env.md` pattern, this test was designed to run inside the container (`docker exec ... pytest`) where the import path resolves naturally. Logged here for visibility; will be addressed by a future deferred-items entry if not already tracked.

### Authentication Gates

None — this plan added an UNAUTHENTICATED read-only endpoint (per Phase 8 D-09 precedent for observability data).

### Architectural Changes

None — all changes were in-scope per the plan's `<tasks>` and `<files_modified>` fields.

## Cross-Plan Contract Verification (D-09-03-06)

Critical handoff for Plan 09-02 (Wave 2) — verified by runtime import smoke:

```python
from app.aggregation.ml_gate_reasons import set_current_reason, get_current_reason
# Default before any auto-flip
assert get_current_reason() == "manual_override"
# Plan 09-02's auto_flip_ml_predictions() call shape
set_current_reason("dsr_below_gate")
assert get_current_reason() == "dsr_below_gate"
```

Both functions are exported in `__all__`; both are importable as `from app.aggregation.ml_gate_reasons import ...`; both are importable via the package re-export `from app.aggregation import ...`. Plan 09-02 can land without import-time failures.

## Cross-Service Wiring Contract Verification (D-09-03-07)

End-to-end delivery proven by `test_scheduler_fetches_counts_and_dispatches_telegram`:

1. respx registers `GET http://trading-engine:8005/api/preflight/ml-gate-reason-counts` → 200 with JSON `{"no_evidence": 1, "dsr_below_gate": 1}`
2. `fetch_and_dispatch_digest(trading_engine_url=base_url, alert_manager=captured_am)` is called
3. The captured `AlertCreate.message` contains:
   - `"ML Gate Reasons (24h):"`
   - `"- no_evidence: 1"`
   - `"- dsr_below_gate: 1"`
4. Returned dispatch summary: `{"reason_counts": {"no_evidence": 1, "dsr_below_gate": 1}, "fetch_status": "ok", "dispatched": True}`

Graceful degradation also proven (ConnectError, HTTP 500, non-dict body → digest STILL dispatched with `ml_gate_reason_counts=None`; performance section intact; ML section absent).

## Known Stubs

The v1.1 `fetch_and_dispatch_digest` ships a stub daily-summary payload with zero placeholders for `total_pnl=0.0`, `total_trades=0`, `win_rate=0.0`, `balance=0.0` — the v1.1 scope is ONLY the ML-gate cross-service wiring (closing Blocker 2). The v1.2 follow-up (a) below wires real trading-engine balance / P&L / win-rate endpoints via the same HTTP-pull pattern. Documented in plan output section and `ml_gate_digest.py` module docstring; not a stub that prevents the plan's goal — the plan's goal was the ML-gate delivery clause, which IS delivered.

## Threat Flags

None — no new network surface introduced beyond the documented `GET /api/preflight/ml-gate-reason-counts` (covered by threat T-09-03-07 in the plan's threat register, disposition `accept` per Phase 8 D-09 unauthenticated-read-only precedent).

## Self-Check: PASSED

- File `services/trading-engine/app/aggregation/ml_gate_reasons.py` — FOUND
- File `services/trading-engine/app/handlers/ml_gate_reasons.py` — FOUND
- File `services/trading-engine/tests/test_ml_gate_reasons.py` — FOUND
- File `services/trading-engine/tests/test_ml_gate_reasons_endpoint.py` — FOUND
- File `tests/integration/test_mlgate_reason_grep_gate.py` — FOUND
- File `services/notification-service/app/scheduler/__init__.py` — FOUND
- File `services/notification-service/app/scheduler/ml_gate_digest.py` — FOUND
- File `services/notification-service/tests/test_daily_digest_ml_gate.py` — FOUND
- File `services/notification-service/tests/test_ml_gate_digest_scheduler.py` — FOUND
- Commit `f93001d` (Task 1) — verified via `git log --oneline | grep f93001d`
- Commit `f7f8bb2` (Task 2) — verified
- Commit `7634fe6` (Task 3) — verified

## Follow-ups

- (a) Wire trading-engine balance / P&L / win-rate endpoints into the digest scheduler so the daily summary is fully populated (currently zero placeholders).
- (b) Wiki ADR documenting the reason-order tuple duplication between trading-engine and notification-service (covered by threat T-09-03-04 in the plan; ADR provides discoverability for future contributors).
- (c) REQUIREMENTS.md MLGATE-03 wording cleanup — change `technical-analysis` references to `trading-engine` (D-09-03-01).
- (d) Optional v1.2 `apscheduler` dep for cron-string scheduling (v1.1 uses plain asyncio loop — sufficient for 24h cadence).
- (e) Fix pre-existing Phase 8 grep gate #2 host-vs-container PYTHONPATH issue (unrelated to this plan, but visible in the regression sweep).

## Commit Hashes

- Task 1: `f93001d` — `feat(09-03): add ML-gate reason enum + cross-plan reason-state cache`
- Task 2: `f7f8bb2` — `feat(09-03): wire ML-gate emissions + observability endpoint + CI grep gate`
- Task 3: `7634fe6` — `feat(09-03): cross-service ML-gate digest wiring (notification-service)`
