# Phase 6: Dashboard Audit & Safety State - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 06-dashboard-audit-safety-state
**Areas discussed:** Audit deliverable shape, Safety-state surfacing, Safety-state backend wiring, Empty/error state pattern

---

## Audit deliverable shape

### Q1 — Audit deliverable: how do we prove every tile maps to a working endpoint?

| Option | Description | Selected |
|--------|-------------|----------|
| Inventory + runtime probe | Markdown table + scripts/audit_tiles.py runtime probe against running stack | ✓ |
| Inventory markdown only | Hand-verified once with curl; no regression guard | |
| Runtime probe only | No human-readable artifact | |

**User's choice:** Inventory + runtime probe.
**Notes:** Markdown is operator artifact; script is regression gate for future CI against recorded-tape stack.

### Q2 — How are 'stale' or broken tiles handled in this phase?

| Option | Description | Selected |
|--------|-------------|----------|
| Fix-or-label per-tile | FIXED / LABELED_STALE / REMOVED verdict per audit row, reviewed before commit | ✓ |
| Fix everything broken | Phase 6 doesn't ship until every tile renders live | |
| Label all, fix only blockers | Default stale badge; fix only safety-state read | |

**User's choice:** Fix-or-label per-tile, reviewed before commit.
**Notes:** Keeps Phase 6 finite; rolls Phase-7-dependent tiles into Phase 7 backlog.

### Q3 — What goes in the 'safety state' read — minimum vs everything?

| Option | Description | Selected |
|--------|-------------|----------|
| All 5 named flags | TRADING_MODE, auto_trading_enabled, kill-switch, EMERGENCY_STOP, ENABLE_ML_PREDICTIONS | ✓ |
| All 5 + per-trade-cap + daily-loss state | Adds risk caps + daily P&L vs circuit-breaker | |
| Minimum: PAPER/LIVE + EMERGENCY_STOP | Only the two flags that matter for "is this safe right now" | |

**User's choice:** All 5 named flags.
**Notes:** Matches ROADMAP success criterion 2 verbatim. Per-trade cap + daily-P&L belong in risk tile, not safety strip.

### Q4 — Stale-data detection: when do tiles render the 'stale' badge?

| Option | Description | Selected |
|--------|-------------|----------|
| Backend-driven last_updated_at | Backend includes last_updated_at; per-tile threshold drives badge | ✓ |
| Frontend React Query isStale + isFetching | Built-in stale time per query; no backend changes | |
| No stale badge — only no-data / error | Defer staleness detection | |

**User's choice:** Backend-driven last_updated_at.
**Notes:** Source of truth on server. Add the field per tile only where audit verdict requires it (incremental).

---

## Safety-state surfacing

### Q5 — Where does the safety-state header render?

| Option | Description | Selected |
|--------|-------------|----------|
| Extend bottom StatusBar | Add 3 cells to existing StatusBar.jsx | ✓ |
| New fixed-top SafetyHeader bar | Separate component above main content | |
| Both: top SafetyHeader + StatusBar | Maximum prominence, two strips | |

**User's choice:** Extend bottom StatusBar.
**Notes:** Minimum new code; operator already knows to look there; consistent aesthetic.

### Q6 — How is PAPER vs LIVE visually called out?

| Option | Description | Selected |
|--------|-------------|----------|
| Color-coded pill + persistent border | Pill in StatusBar AND red 1-2px viewport border when LIVE | ✓ |
| Pill only, no border | Pill in StatusBar; easy to miss during scroll | |
| Pill + modal-on-first-LIVE-load | Modal blocks until acknowledged | |

**User's choice:** Color-coded pill + persistent border.
**Notes:** Border is the primary "cannot miss" affordance. Modal rejected — adds friction in PAPER→LIVE smoke tests.

### Q7 — What does the EMERGENCY_STOP file presence indicator show?

| Option | Description | Selected |
|--------|-------------|----------|
| Active/Inactive + last-modified timestamp | Renders mtime so operator sees freshness | ✓ |
| Boolean badge only | Just ACTIVE / INACTIVE | |
| Active/Inactive + reason text | Requires reason persistence; file currently empty | |

**User's choice:** Active/Inactive + last-modified timestamp.
**Notes:** mtime is enough for "is this stop fresh?". Reason text deferred — needs backend write change.

### Q8 — Kill-switch state — what does that flag mean in this dashboard?

| Option | Description | Selected |
|--------|-------------|----------|
| 5% daily-loss circuit-breaker armed/tripped | Maps to RISK-01 daily-loss breaker | ✓ |
| Consec-losses limit state | Maps to 5-in-a-row limit | |
| Combined daily-loss + consec-losses badge | Single ARMED/TRIPPED for whichever fired first | |

**User's choice:** 5% daily-loss circuit-breaker armed/tripped.
**Notes:** Daily-loss breaker is the actual safety primitive operator cares about. Consec-losses lives in a risk tile.

---

## Safety-state backend wiring

### Q9 — How does the frontend GET the 5 safety flags?

| Option | Description | Selected |
|--------|-------------|----------|
| New /api/config/safety-state aggregated endpoint | Single read, single source of truth | ✓ |
| Extend /api/trading/status | Mixes config flags with runtime status | |
| Multiple existing endpoints, frontend aggregates | 3 polls, 3 failure modes | |

**User's choice:** New /api/config/safety-state aggregated endpoint.
**Notes:** Easy to mock in tests; doesn't bloat /trading/status.

### Q10 — What service owns the new /api/config/safety-state endpoint?

| Option | Description | Selected |
|--------|-------------|----------|
| api-gateway aggregates + proxies | Reads its own env + proxies trading-engine | ✓ |
| trading-engine owns it | Gateway proxies through | |
| New tiny config-service | Standalone 12th service | |

**User's choice:** api-gateway aggregates + proxies.
**Notes:** Single hop from frontend. Matches existing prod-ingress pattern.

### Q11 — EMERGENCY_STOP file read — which container actually reads it?

| Option | Description | Selected |
|--------|-------------|----------|
| Re-use trading-engine's existing bind-mount | trading-engine reads, gateway proxies | ✓ |
| Mount the file into api-gateway too | Second RO bind-mount; two readers | |
| Store presence in Redis, both read Redis | Decoupled but adds latency | |

**User's choice:** Re-use trading-engine's existing bind-mount.
**Notes:** Zero new bind-mounts; preserves RISK-03 single-reader pattern.

### Q12 — Poll cadence for safety-state on the frontend?

| Option | Description | Selected |
|--------|-------------|----------|
| 5s React Query staleTime, same as StatusBar | Matches existing UI cadence | ✓ |
| 1s ultra-tight polling | 86k req/day from one tab; wasteful | |
| Initial fetch + SSE/WebSocket push | Lowest latency; depends on /ws route not in scope | |

**User's choice:** 5s React Query staleTime.
**Notes:** All safety/status visuals refresh together. No mixed cadences.

---

## Empty/error state pattern

### Q13 — What's the empty/error rendering pattern across tiles?

| Option | Description | Selected |
|--------|-------------|----------|
| Shared <TileState/> wrapper component | One component, four modes (loading/empty/error/stale) | ✓ |
| Per-tile inline if/else | 16 tiles → 16 drift opportunities | |
| Error boundary + global toast | Doesn't satisfy "each tile renders an explicit message" literal | |

**User's choice:** Shared <TileState/> wrapper.
**Notes:** One consistent look, one place to tweak.

### Q14 — What signals does <TileState/> distinguish?

| Option | Description | Selected |
|--------|-------------|----------|
| loading / empty / error / stale | Four explicit states | ✓ |
| loading / empty / error (no stale) | Stale handled by separate <StaleBadge/> | |
| loading / non-loading only | Internal rendering decides; defeats the point | |

**User's choice:** loading / empty / error / stale.
**Notes:** Maps cleanly to DASH-05 + Q4 stale-detection decision.

### Q15 — Error rendering — how much detail does the operator see?

| Option | Description | Selected |
|--------|-------------|----------|
| Status code + short message + retry | Helps operator debug | ✓ |
| Generic 'Endpoint failed' only | Worst diagnostic | |
| Full Axios error.message | Can leak internals; ugly long strings | |
| Status code + retry, no message | Compact; less drift | |

**User's choice:** Status code + short message + retry button.
**Notes:** Retry calls React Query refetch. No stack traces.

### Q16 — Config-driven URLs (DASH-02) — scope of this phase?

| Option | Description | Selected |
|--------|-------------|----------|
| Migrate 1 ws://localhost + add VITE_API_BASE_URL convention | Smallest passing change; documented convention | ✓ |
| Full frontend/src/config.js module + migrate everything | New module for one URL today | |
| Just the grep gate — fix the one violation | Leaves next "just localhost" uncaught | |

**User's choice:** Migrate 1 ws://localhost + add VITE_API_BASE_URL convention.
**Notes:** Documented in vite.config.js comment block. Grep gate stays clean.

---

## Claude's Discretion

- Exact column order + sort order in `06-TILE-AUDIT.md`
- `<TileState/>` visual styling (match Editorial Trading Floor aesthetic)
- Exact per-tile staleness thresholds (defaults: ticker 60s, performance 5m, signals 30s)
- Whether new gateway endpoint requires auth (recommend no — read-only config disclosure)
- `scripts/audit_tiles.py` CLI shape (single-binary, PASS/FAIL per tile, non-zero exit on FAIL)

## Deferred Ideas

- Tournament view tile (DASH-04) — Phase 7
- Playwright smoke test for dashboard (DASH-06) — Phase 7
- WebSocket push for safety state — v2 / Phase 7+ (server-side /ws/metrics doesn't exist)
- Reason text for EMERGENCY_STOP — backend persistence change; later phase
- Full frontend/src/config.js module — wait until more direct-service endpoints exist
- Modal-on-LIVE-flip — rejected for friction
- Per-trade-cap + daily-P&L in safety strip — belongs in risk tile, not strip
- Auth on /api/config/safety-state — defer until gateway grows public exposure
