# Roadmap: Crypto Trading Bot

## Milestones

- 🟡 **v1.3 TA + Engine Correctness** — Validated-set re-audit, execution-cap enforcement, Bybit-adapter contract fix, order reconciliation, paper-engine honesty, TA aggregator widening, round(price,N) kill, ML purge + V0-pattern eradication, operator-log + API hygiene (Phases 16-24) — in progress
- ✅ **v1.0** — Bootstrap & tape, integration suite, tournament harness, significance + auto-PR, ML post-V0 cleanup, dashboard safety + smoke (Phases 1, 2, 3, 4, 5, 6, 7, 7.1, 7.2) — shipped 2026-05-15
- ✅ **v1.1 Path to LIVE** — Pre-LIVE preflight, ML re-enablement gate, path-to-LIVE dashboard tile, carry-in closure harnesses, CI recovery (Phases 8, 9, 10, 11.1, 12 — Phase 11 superseded by 11.1) — shipped 2026-05-18
- ✅ **v1.2 Polish & Real-Time** — Bybit-connector centralization, mobile responsive dashboard, planning-tooling hardening (Phases 13, 14, 15) — shipped 2026-05-23

## Phases

<details>
<summary>✅ v1.0 (Phases 1–7.2) — SHIPPED 2026-05-15</summary>

- [x] Phase 1: Bootstrap & Recorded Tape (4/4 plans) — completed 2026-05-06
- [x] Phase 2: Integration Test Suite & RUNBOOK (10/10 plans) — completed 2026-05-08
- [x] Phase 3: Tournament Harness Core (9/9 plans) — completed 2026-05-09
- [x] Phase 4: Tournament Significance & Auto-PR (10/10 plans) — completed 2026-05-12
- [x] Phase 5: ML Cleanup (post-V0) (4/4 plans) — completed 2026-05-13
- [x] Phase 6: Dashboard Audit & Safety State (5/5 plans) — completed 2026-05-14
- [x] Phase 7: Tournament View & Smoke Test (6/6 plans) — completed 2026-05-14
- [x] Phase 7.1: Smoke Test Bugfixes (1/1 plan) — completed 2026-05-15
- [x] Phase 7.2: Phase3Dashboard Skeleton-Loader Fix (1/1 plan) — completed 2026-05-15

Full milestone archive: [`.planning/milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
Audit: [`.planning/milestones/v1.0-MILESTONE-AUDIT.md`](milestones/v1.0-MILESTONE-AUDIT.md) (`gaps_found` — operator items + 1 unsatisfied REQ carried into v1.1)

</details>

<details>
<summary>✅ v1.1 Path to LIVE (Phases 8–12) — SHIPPED 2026-05-18</summary>

- [x] Phase 8: Pre-LIVE Preflight (5/5 plans) — completed 2026-05-16
- [x] Phase 9: ML Re-enablement Gate (3/3 plans) — completed 2026-05-17
- [x] Phase 10: Path-to-LIVE Dashboard (3/3 plans) — completed 2026-05-17
- [⊘] Phase 11: Carry-In Closure — *superseded by Phase 11.1*
- [x] Phase 11.1: Carry-In Closure Harnesses (LIVECLOSE-01..05) (7/7 plans) — completed 2026-05-18
- [x] Phase 12: CI Recovery (1/1 plan) — completed 2026-05-18

Full milestone archive: [`.planning/milestones/v1.1-ROADMAP.md`](milestones/v1.1-ROADMAP.md)
Audit: [`.planning/milestones/v1.1-MILESTONE-AUDIT.md`](milestones/v1.1-MILESTONE-AUDIT.md) (`gaps_found` reconciled at close — audit predates Phase 11.1 + 12 wave-3 verification; 17/19 deliverables shipped, 2 operator-blocked on OP-04 GH Actions billing)

**v1.1 carries into v1.2 as operator actions only (no code debt):**

- LIVECLOSE-01..05 harness execution (wall-clock-bound)
- CIRESTORE-01 + CIRESTORE-02 first green CI runs (blocked on OP-04)

</details>

<details>
<summary>✅ v1.2 Polish & Real-Time (Phases 13–15) — SHIPPED 2026-05-23</summary>

- [x] Phase 13: Bybit-Connector Market-Data Centralization (9/9 plans) — completed 2026-05-22
- [x] Phase 14: Mobile Responsive Dashboard (6/6 plans) — completed 2026-05-22
- [x] Phase 15: Planning-Tooling Hardening (4/4 plans) — completed 2026-05-23

Full milestone archive: [`.planning/milestones/v1.2-ROADMAP.md`](milestones/v1.2-ROADMAP.md)
Audit: [`.planning/milestones/v1.2-MILESTONE-AUDIT.md`](milestones/v1.2-MILESTONE-AUDIT.md) (`gaps_found` — 13/13 REQs satisfied at code level; 3 deferred items are documented operator carry-ins or intentional SDK-port forcing functions, not Phase work failures)

**v1.2 carries into v1.3 as operator actions only (no code debt):**

- BC-07 ml-prediction-service container-exec verification (Phase 13 — scipy/tensorflow not on host)
- MOBILE-03 pytest matrix execution (Phase 14 — blocked by pre-v1.2 INFRA-02 + OP-04)
- TOOL-02 + TOOL-03 SDK ports into `~/.claude/get-shit-done/workflows/complete-milestone.md` (Phase 15 — designed-RED forcing functions)

Plus 17 tech-debt items aggregated in the v1.2 milestone audit for v1.3 re-plan (mobile card visual hierarchy, focus-visible WCAG, hardcoded hex literals, vite_preview_server fixture, etc.).

</details>

### 🟡 v1.3 TA + Engine Correctness — In Progress

- [ ] Phase 16: Validated-Set Re-Audit (AUDIT-01) — gates Track A + Track B
- [ ] Phase 17: Execution-Cap Hard Enforcement (TE-CAP-01..05)
- [ ] Phase 18: Bybit-Adapter Contract Fix (BC-FIX-01..03)
- [ ] Phase 19: Order Reconciliation + Idempotency (RECON-01..02)
- [ ] Phase 20: Paper-Engine Honesty (PAPER-01..03)
- [ ] Phase 21: TA Aggregator Widening + Leakage Net (TA-AGG-01..04)
- [ ] Phase 22: round(price, N) Epidemic Kill (PRICE-01..02)
- [ ] Phase 23: ML Purge + V0-Pattern Eradication (ML-PURGE-01..05)
- [ ] Phase 24: Operator-Log + API Hygiene (HYG-01..04)

**Parallelization (after Phase 16 closes):**
- Track A (execution): Phases 17 → 18 → 19 → 20 (sequential within track)
- Track B (signal + ML): Phases 21, 22, 23 can run independently
- Cross-cutting: Phase 24 can run any time after Phase 16

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Bootstrap & Recorded Tape | v1.0 | 4/4 | Complete | 2026-05-06 |
| 2. Integration Test Suite & RUNBOOK | v1.0 | 10/10 | Complete | 2026-05-08 |
| 3. Tournament Harness Core | v1.0 | 9/9 | Complete | 2026-05-09 |
| 4. Tournament Significance & Auto-PR | v1.0 | 10/10 | Complete | 2026-05-12 |
| 5. ML Cleanup (post-V0) | v1.0 | 4/4 | Complete | 2026-05-13 |
| 6. Dashboard Audit & Safety State | v1.0 | 5/5 | Complete | 2026-05-14 |
| 7. Tournament View & Smoke Test | v1.0 | 6/6 | Complete | 2026-05-14 |
| 7.1. Smoke Test Bugfixes | v1.0 | 1/1 | Complete | 2026-05-15 |
| 7.2. Phase3Dashboard Skeleton-Loader Fix | v1.0 | 1/1 | Complete | 2026-05-15 |
| 8. Pre-LIVE Preflight | v1.1 | 5/5 | Complete | 2026-05-16 |
| 9. ML Re-enablement Gate | v1.1 | 3/3 | Complete | 2026-05-17 |
| 10. Path-to-LIVE Dashboard | v1.1 | 3/3 | Complete | 2026-05-17 |
| 11. Carry-In Closure | v1.1 | — | Superseded by 11.1 | — |
| 11.1. Carry-In Closure Harnesses | v1.1 | 7/7 | Complete | 2026-05-18 |
| 12. CI Recovery | v1.1 | 1/1 | Complete | 2026-05-18 |
| 13. Bybit-Connector Market-Data Centralization | v1.2 | 9/9 | Complete | 2026-05-22 |
| 14. Mobile Responsive Dashboard | v1.2 | 6/6 | Complete | 2026-05-22 |
| 15. Planning-Tooling Hardening | v1.2 | 4/4 | Complete | 2026-05-23 |
| 16. Validated-Set Re-Audit | v1.3 | 0/? | Pending | — |
| 17. Execution-Cap Hard Enforcement | v1.3 | 0/? | Pending | — |
| 18. Bybit-Adapter Contract Fix | v1.3 | 0/? | Pending | — |
| 19. Order Reconciliation + Idempotency | v1.3 | 0/? | Pending | — |
| 20. Paper-Engine Honesty | v1.3 | 0/? | Pending | — |
| 21. TA Aggregator Widening + Leakage Net | v1.3 | 0/? | Pending | — |
| 22. round(price, N) Epidemic Kill | v1.3 | 0/? | Pending | — |
| 23. ML Purge + V0-Pattern Eradication | v1.3 | 0/? | Pending | — |
| 24. Operator-Log + API Hygiene | v1.3 | 0/? | Pending | — |
