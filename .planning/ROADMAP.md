# Roadmap: Crypto Trading Bot

## Milestones

- ✅ **v1.0** — Bootstrap & tape, integration suite, tournament harness, significance + auto-PR, ML post-V0 cleanup, dashboard safety + smoke (Phases 1, 2, 3, 4, 5, 6, 7, 7.1, 7.2) — shipped 2026-05-15
- ✅ **v1.1 Path to LIVE** — Pre-LIVE preflight, ML re-enablement gate, path-to-LIVE dashboard tile, carry-in closure harnesses, CI recovery (Phases 8, 9, 10, 11.1, 12 — Phase 11 superseded by 11.1) — shipped 2026-05-18
- 📋 **v1.2** — TBD (carry over: operator wall-clock execution of LIVECLOSE-01..05 harnesses + CIRESTORE-01/02 first green CI runs after OP-04 billing recovery)

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

### 📋 v1.2 (Planning)

Next milestone scope TBD. Use `/gsd-new-milestone` to ratify v1.2 candidates (Future Requirements list in archived v1.1-REQUIREMENTS.md and v1.0-REQUIREMENTS.md) into an active milestone.

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
