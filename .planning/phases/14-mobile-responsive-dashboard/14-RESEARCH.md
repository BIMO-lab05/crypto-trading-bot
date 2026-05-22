# Phase 14: Mobile Responsive Dashboard - Research

**Researched:** 2026-05-22
**Domain:** Frontend responsive layout (React 18 + Tailwind v3.3.6 + pytest-playwright)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Breakpoints & Audit Surface**
- Keep `frontend/tailwind.config.js` (current filename); add explicit `theme.screens` block declaring `sm: 640px`, `md: 768px`, `lg: 1024px`, `xl: 1280px`. Do NOT rename to `.cjs` — Vite already imports the `.js` file successfully; rename = unnecessary risk. SPEC literal `tailwind.config.cjs` reads as a non-load-bearing typo; satisfied by the breakpoint declaration regardless of extension.
- Viewport meta tag already present at `frontend/index.html:19` (`<meta name="viewport" content="width=device-width, initial-scale=1.0" />`). No change required; audit confirms presence. *(Actual line: 17 — UI-SPEC reports 17; CONTEXT.md reports 19; load-bearing fact is "already present", not the line number.)*
- New `scripts/audit_responsive.py` (matches existing `scripts/` Python convention) walks `frontend/src/components/**/*.jsx` and `frontend/src/pages/**/*.jsx`; emits `responsive-audit.json` at repo root with shape `[{"file": "...", "line": N, "rule": "no-hardcoded-width", "snippet": "..."}]`. Patterns flagged: hardcoded `width: NNNpx` in style attrs, `w-[NNNpx]` Tailwind arbitrary widths, fixed-min-width grid templates. Allowlist entries permitted only with explicit `reason` field.
- Audit script committed; CI integration deferred to Phase 15's `plan.validate` work (out of this phase's scope).

**Per-Component Reflow Pattern**
- `Dashboard.jsx`: existing grid container collapses to `flex flex-col gap-N md:grid md:grid-cols-N` at ≤768px. Tile render order preserved. `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8` outer padding pattern retained.
- `PathToLiveTile.jsx`: 6 PREFLIGHT chip rows + 5 carry-in rows render as `flex-col md:flex-row md:flex-wrap`; each row spans `w-full md:w-auto` ≤768px so chips wrap to full-width-per-row. Banner DO-NOT-FLIP / ALMOST / READY state-token remains the first visible element.
- `KeyMetricsStrip.jsx`: existing horizontal-scroll layout becomes `grid grid-cols-2 gap-N md:flex md:overflow-x-auto md:gap-N` at ≤768px (2-col grid; no horizontal scroll on phone). Metric cards keep their `data-testid` markers.
- `pages/TournamentDashboard.jsx`: table reflows to stacked-card list ≤768px via dual render (`<div className="md:hidden">` cards + `<table className="hidden md:table">`). Filter chips (`TournamentFilterChips.jsx`) get `flex-wrap` so they wrap onto multiple lines instead of horizontal-scrolling. All `data-testid` attributes preserved across both render branches.

**Test Matrix & Anti-Regression**
- Single test file `tests/e2e/test_responsive_dashboard.py` (pytest-playwright). Reuses `.github/workflows/dashboard-smoke.yml` matrix infrastructure — adds Chromium × {iPhone SE 375×667, iPad portrait 768×1024} via Playwright `device` descriptors.
- Hard zero-tolerance no-horizontal-scroll assertion: for each viewport, query `document.querySelectorAll("[data-testid]")` and fail if any element's `boundingBox.x + boundingBox.width > window.innerWidth`. No float tolerance — float-rounding edge cases get tracked as bugs.
- Touch-target assertion: every `<button>`, `<a>`, `[role="button"]` has computed `min-height >= 44px` (WCAG 2.5.5 Level AAA tappable target).
- PathToLiveTile banner state-token assertion: `[data-testid="path-to-live-banner"]` visible without scroll at both viewports.
- Anti-`hidden`-on-mobile grep gate: new `tests/integration/test_no_mobile_hidden_data.py` walks `frontend/src/**/*.jsx` and fails on any element with `data-testid="(metric|tile|chip|row)-*"` that also has `display: none` or `hidden (sm|md|lg|xl):block` (the "hide on mobile, show on desktop" anti-pattern). `md:hidden` (and the rest of the `<bp>:hidden` family) is **permitted** — it is "hide on desktop, show on mobile" and is load-bearing for `TournamentDashboard.jsx` dual-render. Allowlist by exact `data-testid` string with `reason` field.

### Claude's Discretion

- Exact gap/padding values on reflowed grids (Tailwind utility selection)
- Internal column count for `Dashboard.jsx` grid at `md:` and `lg:` breakpoints (preserve existing density)
- Card content reordering inside `TournamentDashboard.jsx` mobile card view (column-heading → primary-metric → secondary-metrics seems natural; final order at implementation time)

### Deferred Ideas (OUT OF SCOPE)

- Native iOS/Android app — explicit Out of Scope per REQUIREMENTS.md.
- Full PWA (offline, installable, service worker) — explicit Out of Scope per REQUIREMENTS.md.
- Web push notifications — explicit Out of Scope per REQUIREMENTS.md.
- Tailwind framework swap — explicit Out of Scope per REQUIREMENTS.md.
- CI integration of `audit_responsive.py` as a hard gate — defer to Phase 15.
- Touch-gesture support (swipe, long-press) — out of scope; tappable target compliance only.
- Landscape-orientation specific tweaks — covered implicitly by md: breakpoint logic; no separate orientation queries.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MOBILE-01 | Viewport meta + Tailwind breakpoint tokens established; `responsive-audit.json` lists hardcoded-width violations | `theme.screens` Option A verified safe (zero `2xl:` usage); viewport meta already at `frontend/index.html:17`; audit script pattern set defined below; out-of-phase-scope hits documented (Pitfall 1) |
| MOBILE-02 | Single-column reflow ≤768px across Dashboard.jsx / PathToLiveTile.jsx / KeyMetricsStrip / TournamentDashboard.jsx with zero info loss | Per-component reflow class signatures locked in CONTEXT.md; dual-render pattern verified against existing TournamentLeaderboard structure (Pitfall 5); anti-hidden gate scope verified safe against existing codebase (Pitfall 2) |
| MOBILE-03 | pytest-playwright Chromium matrix at 375×667 + 768×1024 asserts no h-scroll + state-token visibility + ≥44px touch targets, runs in dashboard-smoke.yml | Existing fixture pattern at `tests/e2e/test_path_to_live_smoke.py` extends via `pytest.mark.parametrize("browser_context_args", [...])` (verified at Playwright docs); device descriptors `iPhone SE`/`iPad` don't match required viewports (Pitfall 3) — must use raw viewport dicts; workflow extension shape defined below |
</phase_requirements>

## Summary

Phase 14 is a contract-bound responsive reflow with most design decisions already locked. The research surface is therefore narrow: (1) verify the locked decisions don't conflict with existing code; (2) confirm the pytest-playwright matrix mechanism the planner will write tasks against; (3) surface non-obvious collateral risk the planner needs to address explicitly.

Five load-bearing findings emerged from the codebase audit, all detailed in the Pitfalls section:

1. **Audit script will find ~20+ hardcoded-width hits OUTSIDE the 4 reflow surfaces** (in `frontend/src/components/performance/` and `PerformanceDashboard/`). The plan must decide between scoping the walk path or pre-creating allowlist entries. Recommend allowlist with `reason: "out-of-phase-14-scope; not in 4 reflow surfaces"` — keeps the audit's discovery value, defers refactor.
2. **Anti-`hidden`-bp gate is safe** — no existing `hidden md:*` / `hidden sm:*` / `hidden lg:*` class carriers in the codebase also carry the `data-testid="(metric|tile|chip|row)-*"` pattern. Verified by grep (Dashboard.jsx, CommandPalette.jsx, StatusBar.jsx, KeyMetricsStrip.jsx, App.jsx). No preexisting cleanup needed.
3. **Playwright device descriptors do NOT match the locked viewports.** `playwright.devices['iPhone SE']` is 320×568 (1st gen); UI-SPEC requires 375×667 (2nd gen). No `iPad portrait 768×1024` descriptor exists either. Tests must use raw viewport dicts via `pytest.mark.parametrize("browser_context_args", [...])`, NOT `playwright.devices[...]`.
4. **Touch-target 44px is visual surgery, not a one-line add.** TournamentFilterChips renders chips at ~22-24px (inline-style padding 4px 10px); PathToLiveTile rows are `py-0.5` (8px). Going to 44px is 2-5x current size. Per-surface verification required.
5. **TournamentDashboard dual-render lives in `TournamentDashboard.jsx`, not in `TournamentLeaderboard.jsx`.** Leaderboard stays a pure `<table>` component receiving `rows`; the wrapping page composes the new mobile-card-list as a sibling.

**Primary recommendation:** Adopt CONTEXT.md verbatim; resolve the audit-allowlist question as a planner decision (recommend allowlist over scope-narrowing); encode the raw-viewport pytest pattern (not device descriptors); plan touch-target compliance as a per-surface verification task with screenshot evidence.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tailwind breakpoint declaration | Build config (Vite + Tailwind PostCSS) | — | `theme.screens` is consumed by PostCSS at build time; affects every utility class emitted into bundled CSS |
| Per-component class reflow | Browser / Client (React component JSX) | — | Pure layout-time CSS; React renders class strings, browser computes the media-query-matched style |
| Hardcoded-width audit | Build-time static analysis (Python script) | — | `scripts/audit_responsive.py` walks source JSX before any runtime; emits artifact |
| Anti-`hidden`-on-data static gate | CI static analysis (Python pytest) | — | `tests/integration/test_no_mobile_hidden_data.py` walks `frontend/src/**/*.jsx`; no React runtime needed |
| Zero-h-scroll + touch-target invariants | E2E browser test (pytest-playwright Chromium) | Stack boot (docker compose) | Requires real browser + rendered DOM + computed styles; depends on `bootstrap.sh` for stack up |
| CI execution | GitHub Actions workflow | — | `.github/workflows/dashboard-smoke.yml` extended with viewport matrix; pull_request trigger |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Tailwind CSS | 3.3.6 [VERIFIED: `frontend/package.json:31`] | Utility-first responsive class system | Already locked; project rule "No CSS-in-JS, no SCSS modules"; `theme.screens` is the canonical breakpoint declaration mechanism [CITED: https://tailwindcss.com/docs/responsive-design] |
| React | 18.2.0 [VERIFIED: `frontend/package.json:24`] | Component renderer | Already locked |
| Vite | 5.0.7 [VERIFIED: `frontend/package.json:40`] | Bundler; reads `tailwind.config.js` via PostCSS pipeline | Already locked |
| pytest-playwright | (pip-installed at CI time; not pinned in repo) [VERIFIED: `.github/workflows/dashboard-smoke.yml:72`] | E2E test runner with Chromium driver | Already used by Phase 10 smoke; reuse fixture pattern |
| Playwright (Python) | (pip-installed at CI time; not pinned in repo) [VERIFIED: `.github/workflows/dashboard-smoke.yml:47`] | Browser automation | Same install path as existing smoke |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | (pip-installed) [VERIFIED: existing smoke pattern] | HTTP probe in tests | If new test needs to seed `/api/preflight/*` state; for pure layout tests, not needed |
| lucide-react | 0.294.0 [VERIFIED: `frontend/package.json:27`] | Icon library | Inherited; no new icons in Phase 14 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw viewport dicts in `browser_context_args` | `playwright.devices['iPhone SE']` | Device descriptor for iPhone SE is **320×568** (1st gen); spec requires **375×667** (2nd gen) — descriptor would silently render at wrong viewport. NO 768×1024 iPad descriptor exists. **Use raw dicts.** [CITED: github.com/microsoft/playwright deviceDescriptorsSource.json] |
| `@pytest.mark.parametrize` on test function | `@pytest.mark.parametrize("browser_context_args", ...)` (fixture-level) | Fixture-level is the documented pattern for cross-viewport runs [CITED: https://playwright.dev/python/docs/test-runners]; test-function parametrize would require `page.set_viewport_size()` AFTER `goto()`, which has a known media-query rematch gotcha (see Pitfall 3) |
| `theme.extend.screens` (additive, Option B) | `theme.screens` (Option A, replaces defaults) | Option A is **safe** — verified zero `2xl:` usage in codebase [VERIFIED: grep returned empty]. Option B preserves Tailwind's default `2xl: '1536px'` but adds maintenance noise (now two declarations to keep in sync). UI-SPEC recommends Option A; executor MUST re-grep at implementation time per UI-SPEC gating step. |

**Installation:** No new dependencies. Tailwind, React, pytest-playwright already locked.

**Version verification (2026-05-22):**
- `tailwindcss@3.3.6` — published 2023-12-05 [VERIFIED: package.json + npm registry pattern]. Tailwind v3.3+ supports `theme.screens` as documented [CITED: https://tailwindcss.com/docs/screens].
- `react@18.2.0` — current stable [VERIFIED: package.json].
- pytest-playwright — installed at CI runtime via pip; intentionally unpinned per existing workflow pattern.

## Architecture Patterns

### System Architecture Diagram

```
                       ┌────────────────────────────────┐
                       │ Operator (phone or desktop)    │
                       └─────────────┬──────────────────┘
                                     │ HTTP
                                     ▼
                       ┌────────────────────────────────┐
                       │ api-gateway :8000 (Nginx-style)│
                       │ serves frontend bundle + /api/*│
                       └─────────────┬──────────────────┘
                                     │ static assets
                                     ▼
                       ┌────────────────────────────────┐
                       │ Vite-built React bundle (CSS+JS)│
                       │ - tailwind.config.js → PostCSS │
                       │   emits responsive utility CSS │
                       └─────────────┬──────────────────┘
                                     │ media-query match
                                     ▼
            ┌────────────────────────────────────────────┐
            │ Browser viewport @ 375 / 768 / 1280+ px    │
            │  ┌──────────────────────────────────────┐  │
            │  │ PathToLiveTile (first child)         │  │
            │  │   banner + 6 PREFLIGHT + 5 carry-in  │  │
            │  ├──────────────────────────────────────┤  │
            │  │ KeyMetricsStrip                      │  │
            │  │   ≤768: 2-col grid                   │  │
            │  │   ≥768: horizontal flex              │  │
            │  ├──────────────────────────────────────┤  │
            │  │ Dashboard grid sections              │  │
            │  │   ≤768: flex-col stacked tiles       │  │
            │  │   ≥md: md:grid md:grid-cols-N        │  │
            │  └──────────────────────────────────────┘  │
            └────────────────────────────────────────────┘

       /tournament route (separate page composition):
            ┌────────────────────────────────────────────┐
            │ TournamentDashboard.jsx page               │
            │  ┌──────────────────────────────────────┐  │
            │  │ Sticky header + Refresh button       │  │
            │  ├──────────────────────────────────────┤  │
            │  │ TournamentSelector                   │  │
            │  ├──────────────────────────────────────┤  │
            │  │ TournamentFilterChips (flex-wrap)    │  │
            │  ├──────────────────────────────────────┤  │
            │  │ DUAL-RENDER:                         │  │
            │  │  <div md:hidden> mobile cards </div> │  │
            │  │  <table hidden md:table> rows </tbl> │  │
            │  └──────────────────────────────────────┘  │
            └────────────────────────────────────────────┘

       CI test pipeline (.github/workflows/dashboard-smoke.yml):
            ┌────────────────────────────────────────────┐
            │ pull_request → matrix [phone | tablet]     │
            │     bootstrap.sh → docker compose up       │
            │     pytest tests/e2e/test_responsive_*.py  │
            │     ↓ assertions:                          │
            │       - boundingBox.x + width ≤ innerWidth │
            │       - min-height ≥ 44px on a/button      │
            │       - banner visible without scroll      │
            └────────────────────────────────────────────┘
```

### Recommended Project Structure

```
crypto-trading-bot/
├── frontend/
│   ├── tailwind.config.js              # add theme.screens (Option A)
│   ├── index.html                      # viewport meta already at line 17
│   └── src/
│       ├── components/
│       │   ├── Dashboard.jsx           # reflow grid sections (flex-col → md:grid)
│       │   ├── PathToLiveTile.jsx      # chip-row reflow (flex-col → md:flex-row md:flex-wrap)
│       │   ├── KeyMetricsStrip.jsx     # 2-col grid → md:flex overflow-x-auto
│       │   ├── TournamentFilterChips.jsx # add flex-wrap (already has it inline; verify)
│       │   └── TournamentLeaderboard.jsx # UNCHANGED — stays as pure <table>
│       └── pages/
│           └── TournamentDashboard.jsx # wrap TournamentLeaderboard with dual-render
├── scripts/
│   └── audit_responsive.py             # NEW — walks src/**/*.jsx, emits responsive-audit.json
├── responsive-audit.json               # NEW — committed to repo root per ROADMAP SC#1
├── tests/
│   ├── e2e/
│   │   └── test_responsive_dashboard.py    # NEW — Playwright matrix at 375x667 + 768x1024
│   └── integration/
│       └── test_no_mobile_hidden_data.py   # NEW — grep gate
└── .github/workflows/
    └── dashboard-smoke.yml             # EXTEND with viewport matrix
```

### Pattern 1: Tailwind `theme.screens` declaration (Option A — replaces defaults)

**What:** Override default Tailwind breakpoints with an explicit minimum set so future utilities cannot drift.
**When to use:** When the project has zero `2xl:` usage (verified 2026-05-22) and wants a contract-locked breakpoint surface.
**Example:**
```js
// Source: https://tailwindcss.com/docs/screens (CITED)
// frontend/tailwind.config.js
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: 'class',
  theme: {
    screens: {                    // ← REPLACES Tailwind defaults
      sm: '640px',
      md: '768px',
      lg: '1024px',
      xl: '1280px',
    },
    extend: {
      colors: { /* existing palette */ },
      spacing: { '18': '4.5rem', '88': '22rem', '112': '28rem', '128': '32rem' },
      fontFamily: { /* existing */ },
      // ...etc
    }
  }
}
```

### Pattern 2: pytest-playwright viewport-matrix fixture

**What:** Run the same test body twice with different browser_context_args.
**When to use:** Every test in `test_responsive_dashboard.py` that must run at both viewports.
**Example:**
```python
# Source: https://playwright.dev/python/docs/test-runners (CITED)
# tests/e2e/test_responsive_dashboard.py

import pytest
from playwright.sync_api import Page, expect

VIEWPORTS = [
    {"viewport": {"width": 375, "height": 667},  "label": "iphone-se"},
    {"viewport": {"width": 768, "height": 1024}, "label": "ipad-portrait"},
]

@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,           # ← routes to the fixture, not the test arg
    ids=[v["label"] for v in VIEWPORTS],
)
def test_no_horizontal_scroll(page: Page, browser_context_args):
    page.goto("http://localhost:8000/", wait_until="networkidle")
    overflowing = page.evaluate("""
        () => {
          const innerW = window.innerWidth;
          const violators = [];
          document.querySelectorAll('[data-testid]').forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.x + rect.width > innerW) {
              violators.push({
                testid: el.getAttribute('data-testid'),
                right: rect.x + rect.width,
                innerWidth: innerW,
              });
            }
          });
          return violators;
        }
    """)
    assert overflowing == [], (
        f"{len(overflowing)} elements overflow window.innerWidth: {overflowing[:5]}"
    )
```

### Pattern 3: Touch-target compliance assertion

**What:** Iterate over every `<button>`, `<a>`, and `[role="button"]`; assert computed `min-height ≥ 44px`.
**When to use:** Every test viewport in the matrix.
**Example:**
```python
def test_touch_targets_44px(page: Page, browser_context_args):
    page.goto("http://localhost:8000/", wait_until="networkidle")
    failures = page.evaluate("""
        () => {
          const out = [];
          document.querySelectorAll('button, a, [role="button"]').forEach(el => {
            const h = el.getBoundingClientRect().height;
            // Use bounding box height, not min-height style, to catch all rendered targets
            if (h < 44 && el.offsetParent !== null) {
              out.push({tag: el.tagName, text: el.innerText.slice(0, 30), height: h});
            }
          });
          return out;
        }
    """)
    assert failures == [], f"{len(failures)} interactive targets below 44px: {failures[:5]}"
```

### Anti-Patterns to Avoid

- **`page.set_viewport_size()` AFTER `page.goto()`:** Chromium may not retrigger media-query matching, causing the page to render at desktop layout while the assertion math runs at the new viewport size. The test passes (bounding boxes fit) but the page never actually rendered at the mobile layout. **Set viewport BEFORE navigation via `browser_context_args` fixture.**
- **`overflow-x: hidden` on body or root container:** Hides the real bug. The no-h-scroll assertion still trips on bounding-box math, but operators see no scrollbar, masking the issue. Don't add `overflow-x-hidden` as a quick fix.
- **`hidden md:block` on a data-bearing element:** Mobile-hiding pattern that drops information. Anti-pattern gate (`test_no_mobile_hidden_data.py`) will catch this if the element carries a `data-testid` matching the gate regex.
- **`flex-shrink: 0` on inner children of a horizontal container:** Children with `flex-shrink-0` blow out the parent's width even on small viewports, causing horizontal scroll. The CSS works as authored but conflicts with the no-h-scroll contract.
- **Using `playwright.devices['iPhone SE']`:** Descriptor is iPhone SE 1st gen (320×568), not 2nd gen (375×667). Will render at wrong viewport.
- **Using `text-xs` to fit content on mobile:** Don't shrink fonts. Use `min-w-0 truncate` per UI-SPEC Typography rule.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-viewport test runs | Custom test-runner loop that calls one test multiple times | `@pytest.mark.parametrize("browser_context_args", VIEWPORTS, indirect=True)` | Standard pytest-playwright pattern; rich reporting, screenshot-per-failure, native CI integration [CITED: https://playwright.dev/python/docs/test-runners] |
| Per-tile h-scroll check | Multiple Python loops with `page.locator(testid).bounding_box()` (slow round-trips) | Single `page.evaluate()` JS block that walks `[data-testid]` in one DOM pass | One JS round-trip vs N. Cuts test time from ~10s to ~50ms |
| Touch-target compliance check | Manual list of `data-testid` interactive elements | `document.querySelectorAll('button, a, [role="button"]')` in `page.evaluate()` | Don't maintain a list — selector catches new interactive elements automatically |
| Mobile-card layout for tournament rows | Custom CSS grid template with hand-tuned column counts | Stacked `<div>` cards via Tailwind `md:hidden` + paired `hidden md:table` for desktop | Dual-render preserves `data-testid` for both branches; one set of source data, two CSS-driven presentations |
| Hardcoded-width detection | Regex over all `.jsx` files mid-test | Build-time `scripts/audit_responsive.py` writes JSON artifact; test reads artifact | Separates discovery from assertion; artifact is operator-readable diff |
| Tailwind PostCSS plumbing | Custom CSS preprocessor | Existing `frontend/postcss.config.js` pipeline | Already wired; no change needed |

**Key insight:** Every component in this phase is reflow over existing structure. The temptation to "rewrite for mobile" is the most expensive trap — preserve the JSX tree, change only the className strings. The dual-render in `TournamentDashboard.jsx` is the ONE exception, and it's bounded (one new `<div className="md:hidden">` sibling).

## Runtime State Inventory

> Phase 14 is greenfield reflow work over existing components. No data migration, no service config, no OS-registered state. The "runtime state" inventory below is included for protocol completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no database schema or stored-value changes | None |
| Live service config | None — no service env vars or compose changes (dashboard-smoke.yml workflow gets new matrix entries, but that's CI config, not runtime) | None |
| OS-registered state | None — no scheduled tasks, no pm2/launchd/systemd | None |
| Secrets/env vars | None — no new env keys; no key rename | None |
| Build artifacts | Vite rebuilds `frontend/dist/` on next `npm run build`. Tailwind CSS bundle will be ~unchanged in size (no new utility classes, only different breakpoint mappings) | Rebuild frontend container on deploy (`bash scripts/deploy.sh frontend` or equivalent) |

**Caveman note (Cave-rebuild):** new Tailwind config affects every compiled CSS rule. Stale browser cache may serve old CSS — operator should hard-refresh phone browser after deploy. Document in plan's verification step.

## Common Pitfalls

### Pitfall 1: Audit script will find ~20+ hardcoded-width hits OUTSIDE Phase 14 scope
**What goes wrong:** `scripts/audit_responsive.py` walks `frontend/src/components/**/*.jsx` per CONTEXT.md. The walk catches hits in `frontend/src/components/performance/` (DailyPnLChart, DrawdownChart, EquityCurveChart, RecentTrades, ReturnsDistribution, CorrelationHeatmap) and `frontend/src/components/PerformanceDashboard/` (ExportPanel, StrategyAttribution) that are not in the 4 reflow surfaces.
**Why it happens:** Phase 14 scope is 4 specific components; audit walks all 100+ components.
**How to avoid:** Pre-create allowlist entries with `reason: "out-of-phase-14-scope; not in 4 reflow surfaces; defer refactor"` for every hit outside `Dashboard.jsx`, `PathToLiveTile.jsx`, `KeyMetricsStrip.jsx`, `TournamentDashboard.jsx`, `TournamentFilterChips.jsx`. Confirmed hits the planner must address:
- `frontend/src/components/StatusBar.jsx:127` — `max-w-[1600px]`
- `frontend/src/components/performance/CorrelationHeatmap.jsx:417` — `min-w-[200px]`
- `frontend/src/components/performance/DailyPnLChart.jsx:107` — `min-w-[200px]`
- `frontend/src/components/performance/DrawdownChart.jsx:83` — `min-w-[200px]`
- `frontend/src/components/performance/EquityCurveChart.jsx:110` — `min-w-[180px]`
- `frontend/src/components/performance/RecentTrades.jsx:205-365` — multiple `w-[NNNpx]` table-column widths
- `frontend/src/components/performance/ReturnsDistribution.jsx:109` — `min-w-[180px]`
- `frontend/src/components/PerformanceDashboard/ExportPanel.jsx:370` — `width: 200px` (in PDF export inline-CSS template — likely legitimately fixed; allowlist with `reason: "PDF export inline CSS, not viewport-bound"`)
- `frontend/src/components/PerformanceDashboard/StrategyAttribution.jsx:106,150` — `min-w-[200px]`
**Warning signs:** First `pytest tests/integration/test_responsive_audit_count.py` (or whatever the count-zero gate is named) returns failure with 15-20 hits. Operator panics; reads finding here; allowlists them.

### Pitfall 2: Anti-`hidden`-bp gate regex collateral (VERIFIED SAFE)
**What goes wrong:** Naively-written regex catches `hidden md:flex` / `hidden sm:inline` on decorative elements that don't carry data, false-flagging valid mobile-density patterns.
**Why it happens:** The pattern `hidden md:block` is dual-use — it's an anti-pattern on data, but a valid density pattern on decoration.
**How to avoid:** The regex MUST match `data-testid="..."` adjacency on the SAME JSX element. Verified codebase scan (2026-05-22): every existing `hidden (sm|md|lg):*` usage is on decorative elements with NO `data-testid` matching `(metric|tile|chip|row)-*`:

| File | Line | Class | Has data-testid? | Status |
|------|------|-------|------------------|--------|
| `frontend/src/App.jsx` | 187 | `hidden sm:ml-6 sm:flex sm:space-x-8` | No | Safe (nav decoration) |
| `frontend/src/components/CommandPalette.jsx` | 218 | `hidden sm:flex` (FAB button) | No `data-testid="(metric\|tile\|chip\|row)-*"` | Safe |
| `frontend/src/components/CommandPalette.jsx` | 278 | `hidden sm:inline-flex` (keybind hint) | No | Safe |
| `frontend/src/components/Dashboard.jsx` | 113 | `hidden lg:block` (RegimeIndicator wrapper) | No | Safe |
| `frontend/src/components/Dashboard.jsx` | 117 | `hidden md:flex` (symbol-select wrapper) | No | Safe |
| `frontend/src/components/Dashboard.jsx` | 249-250 | `hidden sm:inline` (footer separators + "Paper Trading Mode") | No | Safe |
| `frontend/src/components/KeyMetricsStrip.jsx` | 233 | `hidden sm:inline` (italic subtitle) | No (the wrapper has `data-testid="key-metrics-strip"` two levels up, not on this `<span>`) | Safe |
| `frontend/src/components/KeyMetricsStrip.jsx` | 260 | `hidden md:inline` (clock display) | No | Safe |
| `frontend/src/components/StatusBar.jsx` | 152 | `hidden sm:inline` (eyebrow text) | No | Safe |
| `frontend/src/components/StatusBar.jsx` | 209 | `hidden md:flex` (sub-group) | No | Safe |

**No preexisting cleanup needed.** Gate ships green on first run. Pin this verification table into the plan's task notes so future regex tightening doesn't accidentally trip these.
**Warning signs:** First `pytest tests/integration/test_no_mobile_hidden_data.py` fails with one of these 10 hits — means the regex is too loose; tighten it to require `data-testid="(metric|tile|chip|row)-*"` proximity on the same element.

### Pitfall 3: Playwright device descriptors don't match locked viewports
**What goes wrong:** Plan uses `playwright.devices['iPhone SE']` per CONTEXT.md `"via Playwright device descriptors"`. Descriptor is 320×568 (iPhone SE 1st gen), not 375×667 (2nd gen) [VERIFIED: github.com/microsoft/playwright deviceDescriptorsSource.json]. Tests run at wrong viewport. Worse, there's NO `iPad portrait 768×1024` descriptor at all (gen 7 is 810×1080).
**Why it happens:** CONTEXT.md says "Playwright device descriptors" as shorthand but the spec mandates specific dimensions.
**How to avoid:** Use raw viewport dicts in `browser_context_args` — DO NOT use `playwright.devices[...]`:
```python
VIEWPORTS = [
    {"viewport": {"width": 375, "height": 667},  "label": "iphone-se"},
    {"viewport": {"width": 768, "height": 1024}, "label": "ipad-portrait"},
]
```
The "labels" are for human-readable test IDs (`ids=[v["label"] for v in VIEWPORTS]`). Test runs report as `test_no_horizontal_scroll[iphone-se]` and `test_no_horizontal_scroll[ipad-portrait]`.
**Warning signs:** CI matrix runs report `viewport: 320x568` in test logs, OR no iPad row exists in the report at all.

### Pitfall 4: Touch-target compliance is per-component visual surgery
**What goes wrong:** Plan adds a blanket `min-h-[44px]` to every button. Existing chip components (TournamentFilterChips, PathToLiveTile rows) are visually compact at ~22-24px; doubling height to 44px breaks the layout density.
**Why it happens:** WCAG 2.5.5 AAA is a binary contract — element is either ≥44px or it fails. There's no middle ground.
**How to avoid:** Per-surface compliance via one of:
- **`min-h-[44px]` with vertical padding** — keeps visual size while increasing tap area (e.g., transparent click target larger than visual chip).
- **Reflow at mobile only** — chips render compact at `≥md:` but full-tap-target at `≤md` via responsive classes (`py-3 md:py-1`).
- **Pseudo-element extension** — `::before` with absolute positioning extends tap area without affecting layout.

Recommend approach: `py-3 md:py-1` (responsive padding) on the chip element itself for visual clarity. UI-SPEC Section "Touch-target exception" already permits this via `min-h-11` (44px = 2.75rem in Tailwind's default 4px scale). Plan must include a per-surface verification task: screenshot evidence that mobile-viewport chips are tap-comfortable AND desktop-viewport chips remain dense.
**Warning signs:** Test passes (heights ≥ 44px) but operator screenshot shows chips spaced too far apart on phone, making the layout feel "phone-app-like" when desktop density was intentional.

### Pitfall 5: TournamentDashboard dual-render lives in the page, not in the leaderboard
**What goes wrong:** Plan tries to modify `TournamentLeaderboard.jsx` to add mobile cards. The component receives `rows` as a prop and renders a pure `<table>` — adding cards there couples leaderboard rendering to layout concerns.
**Why it happens:** UI-SPEC says "`TournamentDashboard.jsx` (table view) — `<table className="hidden md:table">`" which could be misread as "modify the leaderboard component to conditionally render."
**How to avoid:** Dual render lives in `TournamentDashboard.jsx` page file — the page composes BOTH:
1. A new `<div className="md:hidden">` containing a `.map()` over `sortedRows` rendering stacked cards (the data is already sorted/filtered in the page; reuse it)
2. The existing `<TournamentLeaderboard rows={sortedRows} ... />` wrapped in `<div className="hidden md:table">` (or wrap the component invocation in `<div className="hidden md:block">` since the existing leaderboard renders a `<table>` internally)

`TournamentLeaderboard.jsx` stays unchanged. State this explicitly in the plan.
**Warning signs:** PR diff shows modifications to `TournamentLeaderboard.jsx` body. Plan should call out: file is read-only for this phase.

### Pitfall 6: Inline-style widths bypass Tailwind utility audit
**What goes wrong:** `TournamentLeaderboard.jsx:50-67` defines column widths in a JS object (`{ width: 96 }`) and renders them via `style={{ width }}`. The audit regex `w-\[NNNpx\]` doesn't catch these.
**Why it happens:** Two encoding paths for the same conceptual concern.
**How to avoid:** Audit script MUST also match `width:\s*[0-9]+` patterns in JS object literals (or accept the limitation explicitly in `responsive-audit.json` rule description: "audit catches Tailwind arbitrary-width AND CSS-style attrs; does not catch JS-object-literal widths that flow into inline styles"). Recommend documenting the limitation rather than chasing the regex — the inline-style widths in TournamentLeaderboard are out-of-phase-14-scope anyway (component is read-only).
**Warning signs:** Audit reports 0 violations but TournamentLeaderboard still horizontal-scrolls on mobile (it lives behind `hidden md:table` so it doesn't render below md anyway — this is OK).

## Code Examples

### Example 1: tailwind.config.js with theme.screens (Option A)

```js
// Source: https://tailwindcss.com/docs/screens (CITED)
// File: frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: 'class',
  theme: {
    screens: {                    // ← TOP-level, replaces defaults
      sm: '640px',
      md: '768px',
      lg: '1024px',
      xl: '1280px',
    },
    extend: {
      // colors, spacing, fontFamily, etc. — ALL existing extend content moves here intact
      colors: { /* existing */ },
      spacing: { '18': '4.5rem', /* etc */ },
      fontFamily: { sans: [/* existing */], mono: [/* existing */] },
      animation: { 'pulse-slow': /* existing */ },
      // ...etc, verbatim from current file
    }
  },
  plugins: [],
}
```

**Migration mechanics:** open existing `tailwind.config.js`; before the `extend:` block (line 65), add `screens: {...}` as a top-level theme property. Leave `extend` and its contents UNTOUCHED.

### Example 2: Anti-`hidden`-bp grep gate (Python)

```python
# File: tests/integration/test_no_mobile_hidden_data.py
"""Phase 14 MOBILE-02 anti-pattern gate.

Forbids `hidden <bp>:block` (and friends) on elements that ALSO carry a
data-testid matching the data-carrier pattern. PERMITS `md:hidden` and
the rest of the `<bp>:hidden` family (these are desktop-hide branches of
dual-render pairs and are load-bearing for TournamentDashboard reflow).
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
ALLOWLIST_PATH = REPO_ROOT / ".planning" / "phases" / "14-mobile-responsive-dashboard" / "mobile-hidden-allowlist.json"

# Forbidden: `hidden md:block`, `hidden md:flex`, `hidden lg:grid`, etc.
# Permitted: `md:hidden`, `sm:hidden`, etc. (desktop-hide family)
MOBILE_HIDE_PATTERN = re.compile(
    r'\bhidden\s+(?:sm|md|lg|xl):(?:block|flex|grid|table|inline|inline-block|inline-flex)\b'
)
DATA_TESTID_DATA_CARRIER = re.compile(
    r'data-testid="(metric|tile|chip|row)-[^"]+"'
)

def _load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()
    entries = json.loads(ALLOWLIST_PATH.read_text())
    return {e["data_testid"] for e in entries if "reason" in e and e["reason"]}

def test_no_hidden_md_on_data_carrier():
    allowlist = _load_allowlist()
    violations = []
    for jsx_file in FRONTEND_SRC.rglob("*.jsx"):
        for lineno, line in enumerate(jsx_file.read_text().splitlines(), start=1):
            if not MOBILE_HIDE_PATTERN.search(line):
                continue
            testid_match = DATA_TESTID_DATA_CARRIER.search(line)
            if not testid_match:
                continue   # decorative element, not a data carrier — PERMITTED
            testid = testid_match.group(0).split('"')[1]
            if testid in allowlist:
                continue
            violations.append({
                "file": str(jsx_file.relative_to(REPO_ROOT)),
                "line": lineno,
                "testid": testid,
                "snippet": line.strip()[:120],
            })
    assert violations == [], (
        f"{len(violations)} mobile-hidden-on-data violations:\n"
        + "\n".join(f"  {v['file']}:{v['line']} — {v['testid']}: {v['snippet']}" for v in violations)
    )
```

### Example 3: Audit script skeleton (Python)

```python
# File: scripts/audit_responsive.py
"""Phase 14 MOBILE-01: walk frontend JSX, emit responsive-audit.json.

Detects hardcoded-width violations:
  - `width: NNNpx` in style attrs / JS objects
  - `w-[NNNpx]` Tailwind arbitrary widths
  - `min-w-[NNNpx]`, `max-w-[NNNpx]` arbitrary widths

Allowlist entries (with required `reason` field) suppress hits.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
ALLOWLIST = REPO_ROOT / ".planning" / "phases" / "14-mobile-responsive-dashboard" / "responsive-audit-allowlist.json"
OUT = REPO_ROOT / "responsive-audit.json"

PATTERNS = [
    ("no-hardcoded-width-tailwind",    re.compile(r'\bw-\[(\d+)px\]')),
    ("no-hardcoded-min-width-tailwind", re.compile(r'\bmin-w-\[(\d+)px\]')),
    ("no-hardcoded-max-width-tailwind", re.compile(r'\bmax-w-\[(\d+)px\]')),
    ("no-hardcoded-width-style",       re.compile(r'\bwidth:\s*(\d+)px\b')),
]

def _load_allowlist() -> dict[str, str]:
    if not ALLOWLIST.exists():
        return {}
    return {
        f"{e['file']}:{e['line']}": e["reason"]
        for e in json.loads(ALLOWLIST.read_text())
        if e.get("reason")
    }

def main() -> int:
    allowlist = _load_allowlist()
    hits = []
    for jsx_file in sorted(FRONTEND_SRC.rglob("*.jsx")):
        for lineno, line in enumerate(jsx_file.read_text().splitlines(), start=1):
            for rule, pattern in PATTERNS:
                if pattern.search(line):
                    rel = str(jsx_file.relative_to(REPO_ROOT))
                    key = f"{rel}:{lineno}"
                    hits.append({
                        "file": rel,
                        "line": lineno,
                        "rule": rule,
                        "snippet": line.strip()[:120],
                        "allowlisted": key in allowlist,
                        "reason": allowlist.get(key, ""),
                    })
    OUT.write_text(json.dumps(hits, indent=2))
    unallowlisted = [h for h in hits if not h["allowlisted"]]
    print(f"audit: {len(hits)} total hits, {len(unallowlisted)} unallowlisted")
    return 0 if not unallowlisted else 1

if __name__ == "__main__":
    raise SystemExit(main())
```

### Example 4: dashboard-smoke.yml extension (viewport matrix)

```yaml
# Source: existing .github/workflows/dashboard-smoke.yml extended per Phase 14 MOBILE-03
# Adds a strategy matrix; same boot/cleanup steps run for each viewport.

jobs:
  dashboard-smoke:
    name: Path-to-LIVE smoke + responsive (Phase 10 + 14)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        include:
          - test_target: tests/e2e/test_path_to_live_smoke.py
            label: path-to-live
          - test_target: tests/e2e/test_responsive_dashboard.py
            label: responsive-mobile

    steps:
      - name: Checkout
        uses: actions/checkout@v4
      # ... existing setup steps unchanged ...
      - name: Run ${{ matrix.label }}
        run: |
          pip install pytest-playwright
          pytest ${{ matrix.test_target }} --screenshot=only-on-failure --video=retain-on-failure -v
      # ... existing log + cleanup steps unchanged ...
```

The viewport parametrization itself lives INSIDE `test_responsive_dashboard.py` (via `@pytest.mark.parametrize("browser_context_args", ...)`), not at the workflow level — that's cleaner and keeps the test self-describing. Each test reports as e.g. `test_no_horizontal_scroll[iphone-se]` / `test_no_horizontal_scroll[ipad-portrait]` in CI output.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tailwind v2 `theme.screens.replace` semantics ambiguity | Tailwind v3+ `theme.screens` always replaces defaults; `theme.extend.screens` always extends | Tailwind v3.0 (Dec 2021) | Locked behavior — Option A vs B is a deliberate choice [CITED: https://tailwindcss.com/docs/screens] |
| `playwright.devices['iPhone SE']` matching latest hardware | Descriptor pinned to iPhone SE 1st gen (320×568) historically | Playwright (unchanged) | Plan must use raw viewports, not device descriptors |
| pytest-playwright using only one browser_context_args per session | `pytest.mark.parametrize` on `browser_context_args` for cross-context matrix | pytest-playwright stable feature [CITED: https://playwright.dev/python/docs/test-runners] | Standard pattern |

**Deprecated/outdated:**
- WCAG 2.5.5 Level AA "Target Size" used to be 44px — UPDATED in WCAG 2.2 to 24px AA / 44px AAA [CITED: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html]. Phase 14 contract is AAA (44px) per UI-SPEC — stricter than current AA. Keep at 44px per UI-SPEC.

## Project Constraints (from CLAUDE.md)

| Constraint | Source | Phase 14 Compliance Note |
|------------|--------|--------------------------|
| Conventional commits (`feat(service): ...`, `fix(service): ...`) | CLAUDE.md `## Project rules` | All commits as `feat(frontend): ...` or `feat(tests): ...` |
| Branch naming `feature/<service>-<desc>` | CLAUDE.md `## Project rules` | Phase branch already exists via worktree per `gsd-quick`/phase template; respect config.json `phase_branch_template` |
| Verification: "No declare features 'working end-to-end' on curl/HTTP 200 alone" | CLAUDE.md `## Verification standards` | Phase verification needs: bootstrap.sh stack-up + `pytest tests/e2e/test_responsive_dashboard.py` green AT BOTH VIEWPORTS + screenshot evidence + `responsive-audit.json` committed |
| `/verify-stack` skill before "shipped" claim | CLAUDE.md `## Verification standards` | Run before `/gsd-verify-work` close-out; report PASS/FAIL per check |
| pytest-playwright must run with stack booted | Inferred from existing `bootstrap_stack` fixture pattern at `tests/e2e/test_path_to_live_smoke.py:73` | Reuse the same fixture; new test file imports it from `tests/e2e/conftest.py` |
| WSL2 + Docker Desktop: `default` context, not `desktop-linux` | CLAUDE.md `## Environment` | No phase-14 docker work, but if local verification chooses to boot stack, document the context check |
| TimescaleDB has mixed testnet/mainnet history (2026-04-25 flip) | CLAUDE.md `## Gotchas` | N/A — Phase 14 is pure frontend, no DB queries |
| `data-testid` discipline established by Phase 7/10 | CLAUDE.md inferred + verified at PathToLiveTile.jsx | Phase 14 MUST preserve all existing `data-testid` markers across reflow; verified plan target preserves them per CONTEXT.md decision |
| GSD workflow enforcement (no direct edits outside GSD) | CLAUDE.md `## GSD Workflow Enforcement` | Phase work happens under `/gsd-execute-phase`; no direct edits |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Touch-target compliance is satisfied by `min-h-[44px]` + `py-3 md:py-1` responsive padding on chip elements | Pitfall 4 | Visual surgery: chips may look too spaced on mobile; alternative is `::before` pseudo-element extension or absolutely-positioned tap target. Confirm with operator on first PR review. |
| A2 | The 8 hits in `frontend/src/components/performance/` and 1 in `PerformanceDashboard/` are out-of-phase-14-scope and should be allowlisted, not refactored | Pitfall 1 | If operator wants the audit to drive a broader cleanup, Phase 14 scope grows. Default recommendation: allowlist with `defer to future phase` reason — preserves audit's discovery value. |
| A3 | `<button>` and `<a>` selector in touch-target test covers all interactive elements; nothing uses bare `onClick` on `<div>` for primary actions | Pattern 3 | If a primary-action `<div>` exists with `onClick` (common React anti-pattern), it won't be tested. Quick grep at plan time will confirm. |
| A4 | Dual-render `data-testid` strategy: SAME `data-testid` string on both mobile card and desktop table-row branches | Pitfall 5 / UI-SPEC line 167-170 | Playwright `expect(locator).to_be_visible()` may match the WRONG branch if both render. Plan must verify only ONE branch is visible at each viewport (CSS-hidden elements still in DOM). Recommend `expect(locator).to_have_count(1)` for visibility-aware count check, or use `.first` selector with explicit viewport-conditional assertion. |
| A5 | `responsive-audit.json` lives at repo root (not under `.planning/`) per CONTEXT.md "Specifics" — but this means it gets git-committed and shows up in every PR diff. May want to add to `.gitignore` after Phase 15 wires CI to regenerate on commit. | Pattern + Pitfall 1 | If operator wants the artifact ephemeral, generation moves to CI-only and root file becomes ephemeral. Default: commit it as PR-readable evidence per ROADMAP SC#1 literal. |

**If operator confirms or denies any of A1-A5 during discuss-phase, planner gains a locked decision.** If operator silent, A1-A5 become Claude's discretion at plan time and revisit during code review.

## Open Questions

1. **Should `responsive-audit.json` be committed to git or gitignored?**
   - What we know: ROADMAP SC#1 says "`responsive-audit.json` exists at repo root listing every fixed-width violation"
   - What's unclear: Whether "exists" means "committed in repo" or "regenerated on CI run"
   - Recommendation: Commit it for Phase 14 (per ROADMAP literal). Phase 15 can move generation to CI and gitignore it.

2. **Audit script — walk path scope?**
   - What we know: CONTEXT.md says walk `frontend/src/components/**/*.jsx` AND `frontend/src/pages/**/*.jsx`
   - What's unclear: Whether to scope-narrow to just the 4 reflow surfaces
   - Recommendation: Keep the broad walk (per CONTEXT.md), use allowlist for out-of-scope hits. This preserves discovery value for future phases.

3. **Touch-target compliance approach for compact chips?**
   - What we know: WCAG 2.5.5 AAA = 44px; existing TournamentFilterChips render at ~22-24px
   - What's unclear: Which mechanism — extended tap target via padding, pseudo-element extension, or full visual resize?
   - Recommendation: Responsive padding (`py-3 md:py-1`) — straightforward, no CSS hacks, no visual regression on desktop. Plan to verify with screenshot at first PR review.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js + npm | Vite build, `npm run build` | Assumed (existing project) | — | None — Phase 14 cannot ship without it |
| Python 3.12 | pytest, audit script | Assumed (existing CI uses it) | 3.12 per `.github/workflows/dashboard-smoke.yml:42` | None |
| Chromium (Playwright auto-install) | E2E tests | Installed by `playwright install --with-deps chromium` in CI [VERIFIED: existing workflow line 48] | — | None |
| Docker (bootstrap.sh) | Stack-up for E2E tests | Local dev requires it; CI runs `bash bootstrap.sh` [VERIFIED: existing workflow line 68] | — | Local devs without docker can skip E2E, run audit + grep-gate only |
| GitHub Actions | CI workflow | Currently BLOCKED by OP-04 billing (per STATE.md) | — | Local pytest run gates Phase 14 close; CI run lands when OP-04 resolves |

**Missing dependencies with no fallback:**
- None for normal dev path.

**Missing dependencies with fallback:**
- GitHub Actions (OP-04 billing) → local pytest run + screenshot evidence demonstrates green; CI runs deferred to billing-resolution.

## Validation Architecture

> Nyquist validation enabled per `.planning/config.json` (`workflow.nyquist_validation: true`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7+ with pytest-playwright (browser=Chromium) [VERIFIED: existing workflow + test patterns] |
| Config file | `tests/e2e/conftest.py` (existing — provides `bootstrap_stack` fixture); `tests/integration/conftest.py` (existing) |
| Quick run command | `pytest tests/integration/test_no_mobile_hidden_data.py -x` (~2s, no docker) |
| Full suite command | `pytest tests/integration/test_no_mobile_hidden_data.py tests/e2e/test_responsive_dashboard.py -v` (~5-10min with stack boot) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MOBILE-01 | `tailwind.config.js` has `theme.screens` block | unit (file content check) | `pytest tests/integration/test_no_mobile_hidden_data.py::test_tailwind_screens_declared` | Wave 0 (new) |
| MOBILE-01 | Viewport meta present at `frontend/index.html` | unit (file content check) | `pytest tests/integration/test_no_mobile_hidden_data.py::test_viewport_meta_present` | Wave 0 (new) |
| MOBILE-01 | `responsive-audit.json` exists at repo root with required shape | unit (artifact content check) | `pytest tests/integration/test_responsive_audit_shape.py` | Wave 0 (new) |
| MOBILE-01 | Audit unallowlisted-violation count is 0 (or every entry has reason) | unit (artifact content check) | `pytest tests/integration/test_responsive_audit_count_zero.py` | Wave 0 (new) |
| MOBILE-02 | Dashboard.jsx grid collapses to single column ≤768px | e2e | `pytest tests/e2e/test_responsive_dashboard.py::test_dashboard_single_column_mobile[iphone-se]` | Wave 0 (new) |
| MOBILE-02 | PathToLiveTile 6+5 rows wrap to full-width ≤768px | e2e | `pytest tests/e2e/test_responsive_dashboard.py::test_path_to_live_rows_full_width[iphone-se]` | Wave 0 (new) |
| MOBILE-02 | KeyMetricsStrip renders 2-col grid ≤768px (no h-scroll) | e2e | `pytest tests/e2e/test_responsive_dashboard.py::test_key_metrics_2col[iphone-se]` | Wave 0 (new) |
| MOBILE-02 | TournamentDashboard renders cards ≤768px, table ≥768px | e2e | `pytest tests/e2e/test_responsive_dashboard.py::test_tournament_dual_render` (matrix) | Wave 0 (new) |
| MOBILE-02 | Anti-`hidden`-bp on data: zero violations | unit (static grep) | `pytest tests/integration/test_no_mobile_hidden_data.py::test_no_hidden_md_on_data_carrier` | Wave 0 (new) |
| MOBILE-03 | Zero-h-scroll invariant for `[data-testid]` at both viewports | e2e (matrix) | `pytest tests/e2e/test_responsive_dashboard.py::test_no_horizontal_scroll` (parametrized) | Wave 0 (new) |
| MOBILE-03 | Touch-target ≥44px at both viewports | e2e (matrix) | `pytest tests/e2e/test_responsive_dashboard.py::test_touch_targets_44px` (parametrized) | Wave 0 (new) |
| MOBILE-03 | PathToLive banner visible without scroll at both viewports | e2e (matrix) | `pytest tests/e2e/test_responsive_dashboard.py::test_banner_visible_without_scroll` (parametrized) | Wave 0 (new) |
| MOBILE-03 | dashboard-smoke.yml workflow includes responsive test target | unit (workflow YAML check) | `pytest tests/integration/test_dashboard_smoke_workflow_extended.py` | Wave 0 (new) |

### Sampling Rate

- **Per task commit:** `pytest tests/integration/test_no_mobile_hidden_data.py tests/integration/test_responsive_audit_shape.py tests/integration/test_responsive_audit_count_zero.py -x` (~3-5s, no docker, pure static gate)
- **Per wave merge:** `bash bootstrap.sh && pytest tests/e2e/test_responsive_dashboard.py -v` (~5-10min with stack boot at both viewports)
- **Phase gate:** Full suite green + `responsive-audit.json` committed + dashboard-smoke.yml viewport matrix entries land + screenshot evidence under `.planning/evidence/MOBILE-03/{iphone-se,ipad-portrait}-screenshot.png` + `/verify-stack` skill PASS

### Wave 0 Gaps

- [ ] `tests/e2e/test_responsive_dashboard.py` — covers MOBILE-02, MOBILE-03 (parametrized matrix)
- [ ] `tests/integration/test_no_mobile_hidden_data.py` — covers MOBILE-02 anti-pattern gate; also hosts MOBILE-01 file-content checks (Tailwind config, viewport meta)
- [ ] `tests/integration/test_responsive_audit_shape.py` — verifies `responsive-audit.json` schema
- [ ] `tests/integration/test_responsive_audit_count_zero.py` — verifies count of unallowlisted hits is 0
- [ ] `tests/integration/test_dashboard_smoke_workflow_extended.py` — verifies the matrix entry exists in `.github/workflows/dashboard-smoke.yml`
- [ ] `.planning/phases/14-mobile-responsive-dashboard/responsive-audit-allowlist.json` — allowlist for out-of-phase-14-scope hits (Pitfall 1)
- [ ] `.planning/phases/14-mobile-responsive-dashboard/mobile-hidden-allowlist.json` — empty initially (no preexisting violations per Pitfall 2)

**False-positive risks (Nyquist sampling correctness):**

1. **The test passes but the page rendered at desktop layout.** Cause: `page.set_viewport_size()` called AFTER `page.goto()`. Defense: viewport set via `browser_context_args` BEFORE navigation. Defense-in-depth: log `window.innerWidth` in test assertion message — if logs show `375` consistently, viewport applied; if `1280`, fixture didn't take.
2. **The test asserts on hidden elements.** Cause: dual-render leaves BOTH branches in DOM; `page.locator('[data-testid="..."]')` returns the wrong one. Defense: assert `locator.first.is_visible()` AND check that exactly ONE element with the testid is visible (use `expect(locator).to_have_count(2)` then filter `:visible`, or use viewport-conditional assertion: at 375px expect mobile card visible, at 768px expect table row visible).
3. **The audit script ships green because all hits are allowlisted, but the contract spirit is violated.** Cause: Phase 14 surfaces themselves get allowlisted "to ship". Defense: allowlist entries MUST include `reason` field; require manual review of allowlist additions for any of the 4 reflow surfaces (block via code review, not test).
4. **Touch-target test passes but on a viewport where the chip wraps to multiple lines (each line being one chip ≥44px) — visually broken layout that still satisfies the height check.** Cause: per-element height assertion doesn't validate layout. Defense: combine with no-h-scroll assertion + screenshot evidence; add subjective visual review at phase close.
5. **`responsive-audit.json` exists and shows 0 unallowlisted hits, but the audit script silently failed.** Cause: script bug → empty output. Defense: count-zero gate also asserts `len(audit_artifact) > 0` (any hits, allowlisted or not) — proves the script ran and walked files.

## Security Domain

> Required when `security_enforcement: true` per `.planning/config.json`. Phase 14 is pure frontend layout work — security surface is minimal but documented.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | no | No new architectural decisions; existing dashboard architecture preserved |
| V2 Authentication | no | No authentication changes; `<button>`/`<a>` reflow doesn't touch auth flows |
| V3 Session Management | no | No session changes |
| V4 Access Control | no | No new endpoints, no new RBAC |
| V5 Input Validation | no | No new inputs (no forms added); existing TournamentDashboard URL params already validated by `clampSort`/`clampDir`/`parseList` [VERIFIED at TournamentDashboard.jsx:54-64] |
| V6 Cryptography | no | None |
| V7 Error Handling | no | No new error paths |
| V8 Data Protection | no | No new PII fields |
| V9 Communication | no | No new endpoints |
| V10 Malicious Code | no | No new dynamic code execution |
| V11 Business Logic | no | No business logic changes |
| V12 Files | no | No file upload/download; `responsive-audit.json` is a build artifact written by trusted script |
| V13 API | no | No new API surfaces; tests probe existing `/api/preflight/*` (read-only) |
| V14 Configuration | no | Tailwind config change is build-time; no runtime config surface |

**Conclusion:** No applicable ASVS controls for Phase 14. Layout reflow does not introduce attack surface.

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via JSX text interpolation | Tampering | React escapes by default [VERIFIED at PathToLiveTile.jsx:21-24 security comment]; no raw-HTML injection props introduced by Phase 14 |
| Inline-style injection from user input | Tampering | Phase 14 adds NO user-input-driven inline styles; reflow class strings are static |
| Audit artifact path traversal | Tampering | `responsive-audit.json` path is hardcoded at repo root; script does not accept user-controlled file paths |
| CSRF on test-driven API probes | Repudiation | Phase 14 tests probe `/api/preflight/*` (read-only GET) — no state-mutating requests; existing CSRF protections inherited |

**No new threats introduced by Phase 14.** All layout work is over existing components with no new data inputs.

## Sources

### Primary (HIGH confidence)
- CONTEXT.md (locked decisions) — all per-component reflow class signatures
- UI-SPEC.md (visual + interaction contract) — Responsive Contract section, breakpoint Option A vs B, anti-pattern gate scope
- `frontend/tailwind.config.js` (current state, line-by-line) — existing extend block
- `frontend/index.html` (viewport meta at line 17)
- `frontend/package.json` (Tailwind 3.3.6, React 18.2.0, Vite 5.0.7)
- `.github/workflows/dashboard-smoke.yml` (existing workflow shape; line 47 playwright install, line 72 pytest-playwright install, line 68 bootstrap.sh)
- `tests/e2e/test_path_to_live_smoke.py` (existing fixture pattern: `browser_context_args` session-scoped fixture for viewport)
- `frontend/src/components/{Dashboard,PathToLiveTile,KeyMetricsStrip,TournamentLeaderboard,TournamentFilterChips}.jsx` (codebase scout)
- `frontend/src/pages/TournamentDashboard.jsx` (codebase scout)
- Tailwind v3 official screens docs [CITED: https://tailwindcss.com/docs/screens]
- Playwright Python test-runners docs [CITED: https://playwright.dev/python/docs/test-runners]
- Playwright deviceDescriptorsSource.json [CITED: github.com/microsoft/playwright deviceDescriptorsSource.json]
- WCAG 2.2 Target Size [CITED: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html]

### Secondary (MEDIUM confidence)
- pytest-playwright `pytest.mark.parametrize` on `browser_context_args` — verified via official Playwright docs (Python test-runners page); standard pattern but exact example for indirect=True parametrize is inferred from pytest's general indirect-parametrization mechanism

### Tertiary (LOW confidence)
- None — all critical claims verified against Primary sources or codebase greps

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against `package.json`; Tailwind+Playwright APIs verified against official docs
- Architecture: HIGH — all 5 reflow surfaces read directly from codebase; per-component reflow patterns locked in CONTEXT.md
- Pitfalls: HIGH — 5 pitfalls verified via codebase greps (audit-scope hits, hidden-bp safety table, device descriptor mismatch); Pitfall 4 (touch-target surgery) is MEDIUM because visual judgment is required
- Tests: HIGH — Pattern 2 syntax verified against Playwright docs; Pattern 3 is straightforward DOM query

**Research date:** 2026-05-22
**Valid until:** 2026-06-21 (30 days for stable Tailwind v3 + Playwright Python ecosystem; revalidate if Tailwind v4 ships before then)
