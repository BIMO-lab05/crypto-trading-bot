# Phase 14: Mobile Responsive Dashboard - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the React dashboard usable on phone-sized viewports (down to iPhone SE 375×667) without horizontal scroll, with single-column reflow ≤768px across `Dashboard.jsx`, `PathToLiveTile.jsx`, `KeyMetricsStrip`, and `pages/TournamentDashboard.jsx`. Zero information loss (no `display: none` shortcuts). Establish standardized Tailwind breakpoint tokens and a repo-wide responsive audit artifact. Pytest-playwright Chromium matrix at iPhone SE + iPad portrait asserts no horizontal scroll and ≥44px touch targets per WCAG.

Pure frontend layout work over existing components. No new compose services, no backend changes, no new dependencies beyond existing Tailwind + pytest-playwright stack.

</domain>

<decisions>
## Implementation Decisions

### Breakpoints & Audit Surface
- Keep `frontend/tailwind.config.js` (current filename); add explicit `theme.screens` block declaring `sm: 640px`, `md: 768px`, `lg: 1024px`, `xl: 1280px`. Do NOT rename to `.cjs` — Vite already imports the `.js` file successfully; rename = unnecessary risk. SPEC literal `tailwind.config.cjs` reads as a non-load-bearing typo; satisfied by the breakpoint declaration regardless of extension.
- Viewport meta tag already present at `frontend/index.html:19` (`<meta name="viewport" content="width=device-width, initial-scale=1.0" />`). No change required; audit confirms presence.
- New `scripts/audit_responsive.py` (matches existing `scripts/` Python convention) walks `frontend/src/components/**/*.jsx` and `frontend/src/pages/**/*.jsx`; emits `responsive-audit.json` at repo root with shape `[{"file": "...", "line": N, "rule": "no-hardcoded-width", "snippet": "..."}]`. Patterns flagged: hardcoded `width: NNNpx` in style attrs, `w-[NNNpx]` Tailwind arbitrary widths, fixed-min-width grid templates. Allowlist entries permitted only with explicit `reason` field.
- Audit script committed; CI integration deferred to Phase 15's `plan.validate` work (out of this phase's scope).

### Per-Component Reflow Pattern
- `Dashboard.jsx`: existing grid container collapses to `flex flex-col gap-N md:grid md:grid-cols-N` at ≤768px. Tile render order preserved. `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8` outer padding pattern retained.
- `PathToLiveTile.jsx`: 6 PREFLIGHT chip rows + 5 carry-in rows render as `flex-col md:flex-row md:flex-wrap`; each row spans `w-full md:w-auto` ≤768px so chips wrap to full-width-per-row. Banner DO-NOT-FLIP / ALMOST / READY state-token remains the first visible element.
- `KeyMetricsStrip.jsx`: existing horizontal-scroll layout becomes `grid grid-cols-2 gap-N md:flex md:overflow-x-auto md:gap-N` at ≤768px (2-col grid; no horizontal scroll on phone). Metric cards keep their `data-testid` markers.
- `pages/TournamentDashboard.jsx`: table reflows to stacked-card list ≤768px via dual render (`<div className="md:hidden">` cards + `<table className="hidden md:table">`). Filter chips (`TournamentFilterChips.jsx`) get `flex-wrap` so they wrap onto multiple lines instead of horizontal-scrolling. All `data-testid` attributes preserved across both render branches.

### Test Matrix & Anti-Regression
- Single test file `tests/e2e/test_responsive_dashboard.py` (pytest-playwright). Reuses `.github/workflows/dashboard-smoke.yml` matrix infrastructure — adds Chromium × {iPhone SE 375×667, iPad portrait 768×1024} via Playwright `device` descriptors.
- Hard zero-tolerance no-horizontal-scroll assertion: for each viewport, query `document.querySelectorAll("[data-testid]")` and fail if any element's `boundingBox.x + boundingBox.width > window.innerWidth`. No float tolerance — float-rounding edge cases get tracked as bugs.
- Touch-target assertion: every `<button>`, `<a>`, `[role="button"]` has computed `min-height >= 44px` (WCAG 2.5.5 Level AAA tappable target).
- PathToLiveTile banner state-token assertion: `[data-testid="path-to-live-banner"]` visible without scroll at both viewports.
- Anti-`hidden`-on-mobile grep gate: new `tests/integration/test_no_mobile_hidden_data.py` walks `frontend/src/**/*.jsx` and fails on any element with `data-testid="(metric|tile|chip|row)-*"` that also has `display: none` or `hidden (sm|md|lg|xl):block` (the "hide on mobile, show on desktop" anti-pattern). `md:hidden` (and the rest of the `<bp>:hidden` family) is **permitted** — it is "hide on desktop, show on mobile" and is load-bearing for `TournamentDashboard.jsx` dual-render (cards visible <768px via `md:hidden`, table visible ≥768px via `hidden md:table`). Allowlist by exact `data-testid` string with `reason` field.

### Claude's Discretion
- Exact gap/padding values on reflowed grids (Tailwind utility selection)
- Internal column count for `Dashboard.jsx` grid at `md:` and `lg:` breakpoints (preserve existing density)
- Card content reordering inside `TournamentDashboard.jsx` mobile card view (column-heading → primary-metric → secondary-metrics seems natural; final order at implementation time)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Tailwind tokens** already include semantic dark/light color palette (`primary`, `success`, `danger`, `warning`, `dark`, `light` color families) at `frontend/tailwind.config.js` — extend `theme.screens` not `theme.colors`.
- **Responsive padding pattern** already in use: `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8` (Dashboard.jsx). Reuse on reflowed containers.
- **`useSafetyState` idiom** (5s react-query poll, retry=2) reused by `useLiveReadiness` + `useCarryIns` in Phase 10. Mobile work doesn't need new hooks.
- **`data-testid` discipline** established by Phase 7/10 Playwright work — every tile already has a testid. Mobile assertions key off these.
- **`dashboard-smoke.yml`** workflow infrastructure (Phase 10 DASHLIVE-04) — add viewport matrix entries rather than spinning up a new workflow.
- **`TournamentFilterChips.jsx`** + `TournamentLeaderboard.jsx` exist as separate components — chip wrap and table-to-card swap can be localized.

### Established Patterns
- Tailwind utility-first (no CSS-in-JS, no SCSS modules). All breakpoint work via `sm:`/`md:`/`lg:`/`xl:` utility prefixes.
- Class-based dark mode (`darkMode: 'class'`); already wired. No light-mode regression risk from breakpoint additions.
- React 18 functional components + hooks; no class components.
- Vite as bundler; PostCSS pipeline at `frontend/postcss.config.js` for Tailwind processing.

### Integration Points
- `frontend/src/components/Dashboard.jsx` — root layout, includes PathToLiveTile + KeyMetricsStrip + 6 other panels.
- `frontend/src/components/PathToLiveTile.jsx` — Phase 10 component; 6 PREFLIGHT chip rows + 5 carry-in rows already structured for row-wise reflow.
- `frontend/src/components/KeyMetricsStrip.jsx` — currently horizontal layout; target 2-col grid ≤768px.
- `frontend/src/pages/TournamentDashboard.jsx` — page-level (not component-level) — uses `TournamentLeaderboard.jsx` (table) + `TournamentFilterChips.jsx`.
- `frontend/index.html` — viewport meta tag (no change).
- `frontend/tailwind.config.js` — breakpoint declaration target.
- `tests/e2e/` — pytest-playwright location.
- `.github/workflows/dashboard-smoke.yml` — extend matrix.

</code_context>

<specifics>
## Specific Ideas

- SPEC literal `tailwind.config.cjs` is **non-load-bearing**: the file is currently `tailwind.config.js`, Vite resolves it, no `.cjs`-specific behavior needed. Plan acknowledges discrepancy in writing rather than chasing a rename.
- SPEC literal `<meta name="viewport" content="width=device-width, initial-scale=1">` differs from actual `initial-scale=1.0`. Functionally equivalent — no rewrite.
- `TournamentDashboard` lives at `frontend/src/pages/TournamentDashboard.jsx` (not `frontend/src/components/` as one reading of ROADMAP implies). Plan operates on the page-level file.
- Dashboard.jsx already responsive-pattern-aware (`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`); reflow work extends the pattern rather than introducing it.
- `responsive-audit.json` lives at repo root (not under `.planning/`) — ROADMAP SC#1 literal.

</specifics>

<deferred>
## Deferred Ideas

- Native iOS/Android app — explicit Out of Scope per REQUIREMENTS.md.
- Full PWA (offline, installable, service worker) — explicit Out of Scope per REQUIREMENTS.md.
- Web push notifications — explicit Out of Scope per REQUIREMENTS.md.
- Tailwind framework swap — explicit Out of Scope per REQUIREMENTS.md.
- CI integration of `audit_responsive.py` as a hard gate — defer to Phase 15's `plan.validate` work, which owns CI grep-gate scaffolding for the milestone.
- Touch-gesture support (swipe, long-press) — out of scope; tappable target compliance only.
- Landscape-orientation specific tweaks — covered implicitly by md: breakpoint logic; no separate orientation queries.

</deferred>
