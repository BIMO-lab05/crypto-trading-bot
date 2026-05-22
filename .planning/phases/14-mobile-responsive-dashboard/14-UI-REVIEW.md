---
phase: 14
slug: mobile-responsive-dashboard
audited: 2026-05-22
baseline: UI-SPEC.md (status: draft — used as the build contract regardless of approval status)
screenshots: captured pre-fix (see note below)
---

# Phase 14 — UI Review

**Audited:** 2026-05-22
**Baseline:** `14-UI-SPEC.md` (design contract; `status: draft`, signed off used as build contract)
**Screenshots:** `.planning/evidence/MOBILE-03/` files exist but are PRE-FIX. Screenshots were captured at commit `852ce98` (2026-05-22 22:24); the CR-01/02/03 + WR-01..07 fixes landed in commits `a50c5a3` through `5621109` (22:55–23:30). Visual evidence therefore shows the 7-field mobile card (pre-WR-01), the `display:contents` testid wrapper (pre-CR-02), and stale bundle (pre-CR-01). All pillar analysis below is based on the current source code (post-fix HEAD), with explicit notes where screenshots diverge.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Phase 14 introduced zero new strings; all existing copy preserved verbatim per spec scope |
| 2. Visuals | 2/4 | Mobile card is a tall single-column list (~15 inline grid rows per card at 375px); no disclosure toggle exists despite additional_context description |
| 3. Color | 2/4 | 42 hardcoded hex literals across 4 reflow files diverge from UI-SPEC slate/cyan/emerald/rose semantic palette; two competing palettes coexist |
| 4. Typography | 3/4 | Type scale preserved; `text-[9px]` and `text-[10px]` arbitrary sizes used in PathToLiveTile/KeyMetricsStrip outside the declared spec scale |
| 5. Spacing | 2/4 | Touch-target 44px rule met on all filter chips; tournament-refresh button (~22-24px effective height) is unallowlisted and violates WCAG 2.5.5 |
| 6. Experience Design | 2/4 | All 14 e2e tests failed at fixture setup (bootstrap_stack operator-blocked); zero machine-verified responsive assertions; WR-08 deferred |

**Overall: 15/24**

---

## Top 3 Priority Fixes

1. **Tournament Refresh button fails WCAG 2.5.5 touch-target contract** — Mobile operators cannot reliably tap Refresh to reload tournament data on phones; the inline `padding: '4px 12px'` + `fontSize: 11` computes to ~22-24px, below the 44px floor. Fix: add `min-h-[44px] md:min-h-0 py-3 md:py-0` to the button's className, matching the chip pattern from TournamentFilterChips.jsx:186, or add the button to `touch-target-allowlist.json` with a documented reason if deferral is intentional.

2. **WR-08 deferred: zero e2e verification of responsive reflow** — Every one of the 14 parametrized responsive Playwright tests exited at fixture setup (`bootstrap_stack` operator-blocked per OP-04/INFRA-02). There is no machine evidence that the Phase 14 reflow classes actually produce single-column layout at 375×667 or ≥44px touch targets in a live browser. Fix: introduce a `vite_preview_server` fixture for pure-layout tests so the no-h-scroll, touch-target, single-column, and dual-render assertions can run without the full docker stack.

3. **Mobile tournament cards are tall walls of text with no visual hierarchy relief** — WR-01 restores all 14 fields inline (correct for information preservation) but at 375px each card renders ~15 label/value grid rows without any grouping, truncation, or disclosure. Primary metrics (DSR, OOS Sharpe, PSR) are visually indistinct from secondary investigative metrics (R² Returns, Dir Acc, Train Sec). Fix: group fields into "primary" (always visible) and "secondary" (rendered inside a `<details>` closed by default), or apply visual weight differentiation via font-size, color, or a divider between action-relevant fields and investigation fields.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)

UI-SPEC §Copywriting declares every row N/A with explicit rationale: "Phase 14 scope is responsive layout reflow over existing components. No new strings are introduced." Code analysis confirms:

- No new CTAs introduced in any of the 4 reflow files (TournamentDashboard.jsx, PathToLiveTile.jsx, TournamentFilterChips.jsx, KeyMetricsStrip.jsx).
- Existing CTAs preserved: "Refresh" (`TournamentDashboard.jsx:344`), "Clear filters" (`TournamentFilterChips.jsx:300`), "Emergency Stop" (Dashboard.jsx, not touched by Phase 14).
- Empty-state copy in TileState ("No data yet", `TileState.jsx:141`) unchanged.
- All copy visible at ≥1280px remains visible at ≤768px — code analysis confirms no string is conditionally hidden without a paired visible branch.
- No generic label regressions: no "Submit", "Click Here", "OK" literals introduced.

Score rationale: contract rows are N/A and the invariant (existing copy preserved) holds. 4/4.

---

### Pillar 2: Visuals (2/4)

**Finding V-01 (WARNING): Mobile card has no visual hierarchy — all 14 fields rendered as flat inline grid rows.**

File: `frontend/src/pages/TournamentDashboard.jsx:481-630`

WR-01 correctly restores zero information loss, but the implementation is a single `display:grid; grid-template-columns: 1fr auto` block with 9 label+value pairs back-to-back after the DSR hero row. At 375×667:

- Each card contains: symbol/DSR header, then OOS Sharpe, PSR, Architecture, Target Mode, Dir. Acc., R² Returns, Significance, Train Sec, Status — 9 rows in a dense grid — plus a conditional failure_reason block.
- Primary decision metrics (DSR, OOS Sharpe, PSR) carry the same visual weight as investigative fields (Train Sec, R² Returns).
- Operators scanning for a quick go/no-go signal must visually parse the entire card per row.

The additional_context description says "expandable 'More details' disclosure that surfaces previously-hidden fields including failure_reason." This description does not match the current code. There is no `<details>`, `<summary>`, or expansion toggle. All fields are always rendered flat. The additional_context is inaccurate relative to the HEAD code.

**Finding V-02 (WARNING): PathToLiveTile banner verified correct as first element.**

`PathToLiveTile.jsx:143-167`: `data-testid="path-to-live-banner"` is the first JSX child inside `TileState`, above the body block at line 170. Banner state-token (DO NOT FLIP/ALMOST/READY) renders above the fold on initial load. Contract satisfied for this specific requirement.

**Finding V-03 (INFO): Pre-fix screenshots show 7-field mobile card — no post-fix visual evidence.**

The iphone-se screenshot at `.planning/evidence/MOBILE-03/iphone-se-screenshot.png` was captured before WR-01 landed. The visual shows the 7-field pre-fix card. No screenshot of the 14-field post-fix card exists in the evidence directory. The current code has the correct fields, but there is no screenshot proof of what the 14-field card looks like on a real 375px viewport (density, overflow risk, readability).

**Finding V-04 (INFO): No visual evidence of dual-render switching at the md: boundary.**

The ipad-portrait screenshot (768×1024) shows the existing desktop table layout. No screenshot was captured at exactly 767px (below the md: boundary) or 769px (above it) to confirm the dual-render branch is toggling correctly. Only code analysis (confirmed `hidden md:block` / `md:hidden` present) provides evidence of correct switching.

Score rationale: information-preservation invariant met in code; visual hierarchy of the restored mobile card is weak; no post-fix screenshot evidence; pre-fix screenshot shows the old broken state. 2/4.

---

### Pillar 3: Color (2/4)

**Finding C-01 (WARNING): Two competing color palettes coexist in the dashboard.**

UI-SPEC §Color declares the canonical semantic palette:
- Dominant: `#0f172a` slate-900 (`bg-slate-900`)
- Secondary: `#1e293b` slate-800
- Accent info/brand: `#22d3ee` cyan-400
- Accent success: `#34d399` emerald-400
- Accent danger: `#f87171` rose-400
- Accent warning: `#fbbf24` amber-400

The 4 reflow files use the Editorial Trading Floor warm palette via inline-style hardcoded hex:
- `#0a0a0b` (near-black, vs spec `#0f172a`)
- `#18181c` (warm dark surface, vs spec `#1e293b`)
- `#5eead4` (viridian teal, vs spec `#34d399` emerald)
- `#fb7185` (warm rose, vs spec `#f87171`)
- `#d4af6a` (gold — no equivalent in UI-SPEC palette at all)
- `#a09e98`, `#8a8982` (warm grays, vs spec `#94a3b8` / `#64748b`)

Hardcoded hex counts: TournamentDashboard.jsx: 11, TournamentFilterChips.jsx: 11, KeyMetricsStrip.jsx: 11, PathToLiveTile.jsx: 9. Total: 42 hardcoded literals across Phase 14 reflow surfaces.

This palette divergence pre-dates Phase 14 (introduced in earlier performance dashboard work). Phase 14 did not introduce new colors — it inherited the warm palette across the reflow components. However, the UI-SPEC §Color contract is the audit baseline and these files diverge from it materially.

**Finding C-02 (INFO): PathToLiveTile.jsx uses Tailwind semantic tokens (mostly compliant).**

`PathToLiveTile.jsx` uses Tailwind class tokens (`bg-rose-700`, `bg-amber-600`, `bg-emerald-700`, `text-emerald-300`, `text-rose-300`, etc.) for the banner and chip states. These are closer to the UI-SPEC palette than the warm-hex approach in the other three files. 9 hardcoded hex values appear in inline styles for the body background (`#18181c`) and decorative text colors.

**Finding C-03 (PASS): No new colors introduced by Phase 14 reflow work.**

UI-SPEC contract: "Phase 14 introduces no new colors." Confirmed — all hex values in Phase 14 files pre-date Phase 14. The breakpoint class additions (`flex-col md:flex-row`, `min-h-[44px]`, `hidden md:block`) contain no color tokens. Contract satisfied.

Score rationale: palette divergence from UI-SPEC is material (42 hardcoded literals diverging from declared semantic system); gold color token has no UI-SPEC equivalent; but Phase 14 itself introduced zero new colors (inherited divergence). The audit baseline is the spec, not intent. 2/4.

---

### Pillar 4: Typography (3/4)

**Finding T-01 (WARNING): `text-[9px]` and `text-[10px]` arbitrary sizes outside UI-SPEC declared scale.**

UI-SPEC §Typography declares: `text-xs` (12px), `text-sm` (14px), `text-base` (16px), `text-lg` (18px), with one micro-label exception: `text-[10px]` at `Dashboard.jsx:278` (explicitly documented in the spec table).

PathToLiveTile.jsx uses `text-[9px]` at lines 177, 213, 249 (section eyebrow labels for "PREFLIGHT checks" and "Carry-ins"). This size is not in the UI-SPEC declared scale and not documented as a spec exception. At 9px on mobile, these section labels are below legible threshold on low-DPI displays.

`text-[10px]` appears in KeyMetricsStrip.jsx:115 (Cell eyebrow label) — this matches the spec's documented exception at `Dashboard.jsx:278`. Compliant.

**Finding T-02 (PASS): Font sizes do not shrink at smaller viewports.**

UI-SPEC rule: "font sizes do NOT shrink at smaller viewports. Use `truncate` + `min-w-0` not smaller font." No `sm:text-xs` or `md:text-xs` responsive font-size reduction found in any Phase 14 file. `truncate` appears at PathToLiveTile.jsx:200, 236 for detail text overflow. Contract satisfied.

**Finding T-03 (PASS): Font weight discipline maintained.**

Phase 14 reflow files use: `font-semibold` (PathToLiveTile.jsx:102, 226, 89). Inline `fontWeight: 600/700/500` for numeric/display values. No new Tailwind weight classes introduced. UI-SPEC allows `font-semibold` (600) and `font-bold` (700); the weights in use are within contract.

**Finding T-04 (INFO): Inline `fontSize` values in TournamentDashboard.jsx diverge from Tailwind scale.**

Mobile card uses inline `fontSize: 15` (symbol heading), `fontSize: 13` (DSR value), `fontSize: 11` (grid labels). These are not on the Tailwind 4-step scale (12/14/16/18px) but are within a reasonable editorial tight-scale range. Pre-existing pattern from the Editorial Trading Floor design; not introduced by Phase 14.

Score rationale: `text-[9px]` is below legible minimum and undocumented in spec; all other typography within contract. 3/4.

---

### Pillar 5: Spacing (2/4)

**Finding S-01 (BLOCKER): Tournament Refresh button is a WCAG 2.5.5 touch-target violation with no allowlist entry.**

File: `frontend/src/pages/TournamentDashboard.jsx:316-345`

The `tournament-refresh` button uses `padding: '4px 12px'` (inline style) + `fontSize: 11` with default `line-height: normal` (~1.5). Computed effective height: `(11 * 1.5) + (4 * 2) = 24.5px`. This is 19.5px below the 44px contract minimum declared in UI-SPEC §Spacing.

The `touch-target-allowlist.json` contains only two entries:
- `button[data-testid='emergency-stop']` (kill-switch, out of Phase 14 scope)
- `a[href='/tournament']` (nav link, out of Phase 14 scope)

`tournament-refresh` is not in the allowlist. Plan 14-05 SUMMARY §"Final Touch-Target Test Results" flagged this as "out-of-Phase-14-scope per CONTEXT decision (header reflow is separate concern); allowlist if /tournament route is added to test_touch_targets_44px before Plan 14-06 lands." Plan 14-06 did add the route but did not add the allowlist entry. The violation ships unmitigated.

**Finding S-02 (PASS): All 13 filter chip buttons + Clear button meet 44px contract.**

`TournamentFilterChips.jsx`: All 4 interactive button surfaces (SYMBOLS ×5, ARCHITECTURE ×4, STATUS ×3, Clear ×1) carry `className="py-3 md:py-1 min-h-[44px] md:min-h-0"`. Belt-and-suspenders pattern: `py-3` (12+12=24px vertical padding) + `min-h-[44px]` ensures the strict `h >= 44` test passes regardless of line-height variability. Pattern verified at lines 186, 218, 260, 284.

**Finding S-03 (PASS): Spacing scale consistent with 8pt multiple for reflow additions.**

Phase 14 reflow additions use: `gap-1` (4px), `gap-3` (12px), `py-0.5` (2px), `py-3` (12px). These are all Tailwind default values on the 4px-multiple scale. No new arbitrary `[Npx]` spacing values introduced (the `min-h-[44px]` is a height contract, not a spacing value; documented in UI-SPEC).

**Finding S-04 (PASS): Outer container padding pattern preserved.**

`KeyMetricsStrip.jsx:237`: `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5` — Pattern S5 retained. No reflow file introduces a new outer padding convention.

**Finding S-05 (WARNING): PathToLiveTile check rows have `py-0.5` (2px) vertical padding per row.**

`PathToLiveTile.jsx:187, 223`: Row containers carry `gap-1 md:gap-3 py-0.5`. In mobile stacked layout, each row is a `flex-col` block with `py-0.5` (2px top/bottom). The label, chip, and detail text stack vertically with 4px gap between them. This is visually compact but functional. The row itself has no minimum height — if a check label is very short, the clickable area of the row might be small. However, these rows have no `onClick` handler and are not interactive, so the 44px rule does not apply per UI-SPEC ("Decorative icon-only spans without click handlers are not interactive elements").

Score rationale: One unallowlisted touch-target failure (tournament-refresh) directly contradicts the phase's WCAG 2.5.5 contract; all chips compliant; spacing scale preserved. 2/4.

---

### Pillar 6: Experience Design (2/4)

**Finding E-01 (BLOCKER): All 14 e2e tests failed at fixture setup — zero responsive assertions verified.**

File: `.planning/evidence/MOBILE-03/test-output.txt`

`pytest tests/e2e/test_responsive_dashboard.py` ran 14 tests (7 functions × 2 viewports). All 14 exited with `ERROR at setup of ...` due to `bootstrap_stack` fixture failure:

```
Failed: bootstrap.sh failed (exit=1) in /tmp/cb-test-93ff9df.
Per D-08, tmp clone preserved at: /tmp/cb-test-93ff9df
```

Root cause: `bootstrap.sh` requires per-service `.env` files in the tmp clone (`notification-service/.env: no such file or directory`). This is the OP-04/INFRA-02 carry-in.

Consequence: there is no machine evidence that:
- The `grid-cols-2` KeyMetricsStrip renders two columns on iPhone SE (not vacuously zero columns via `display:contents` — CR-02 fixes this in code, but no browser proof)
- PathToLiveTile rows stack full-width at 375px
- TournamentDashboard dual-render switches at the md: boundary
- No horizontal scroll at either viewport
- Any post-fix interactive element actually has ≥44px height in Chromium

**Finding E-02 (WARNING): WR-08 deferred — bootstrap_stack coupling persists as the only e2e runner.**

The code review deferred WR-08 with the note "once a `vite_preview_server` fixture is introduced in a future phase, the layout-only subset can be split off from bootstrap_stack." That future phase has not materialized. Every Phase 14 layout test (no-h-scroll, single-column, 2-col, dual-render, banner visibility, touch-target) is gated behind `bootstrap_stack`. The layout assertions have no dependency on backend data — they only need a rendered HTML page — but they cannot run without the full 17-service docker stack.

**Finding E-03 (PASS): Static grep gates provide baseline quality signal.**

`tests/integration/test_no_mobile_hidden_data.py` — 5 static tests. All 5 pass locally without docker:
- `test_no_hidden_md_on_data_carrier`: GREEN (no mobile-hiding patterns on data-carrier testids)
- `test_tailwind_screens_declared`: GREEN (theme.screens block at tailwind.config.js:80)
- `test_viewport_meta_present`: GREEN (meta tag at index.html:17)
- `test_responsive_audit_shape`: GREEN (responsive-audit.json exists and valid)
- `test_responsive_audit_count_zero`: GREEN (all 33 hits allowlisted, exit 0)

These 5 static gates provide real signal within their scope (structural/file-level invariants), but they cannot substitute for browser-rendered geometry assertions.

**Finding E-04 (PASS): Loading and error states properly wired via TileState wrapper.**

All 4 reflow surfaces delegate loading/error/empty handling to `TileState`:
- `PathToLiveTile.jsx:134-140`: `TileState` wraps the tile; `isEmpty` predicate at line 139 returns true when `data.carry_ins` is absent.
- `KeyMetricsStrip.jsx:222-228`: `TileState` with `perfQuery` as the gating query; per-Cell `isLoading` skeleton at lines 126-130.
- `TournamentDashboard.jsx:367-372`: `TileState` with `isEmpty` predicate at line 370.
- `TournamentFilterChips.jsx`: purely declarative (no async state); does not require a TileState wrapper.

**Finding E-05 (PASS): Dual-render testid contract correct in post-fix code.**

Post CR-03 fix at `TournamentDashboard.jsx:405`: `const runId = row?.run_id ?? \`unknown-${idx}\``. Both mobile (`data-testid={\`tournament-row-${runId}\`}`) and desktop (`TournamentLeaderboard.jsx:361` with same pattern) produce unique keys even when `run_id` is null. The duplicate-DOM collision for null run_ids is resolved.

**Finding E-06 (INFO): No focus-visible ring on any interactive element in Phase 14 reflow files.**

Zero `focus-visible:` Tailwind utilities or `:focus-visible` inline styles in TournamentDashboard.jsx, TournamentFilterChips.jsx, PathToLiveTile.jsx, or KeyMetricsStrip.jsx. Keyboard users lose visual focus tracking when tabbing through filter chips, the Refresh button, or any interactive surface on these pages. IN-03 from the code review was deferred as info-severity. This is a real WCAG 2.4.7 gap that becomes more important as touch-target compliance (WCAG 2.5.5) is addressed — both are on the same a11y work surface.

Score rationale: zero browser-verified responsive assertions; WR-08 deferred with no resolution path; static gates pass but cover only structural invariants; loading/error/empty states correctly wired; post-fix code is structurally sound but unproven in a browser. 2/4.

---

## Additional Findings (beyond top 3)

### Finding A-01 (WARNING): Screenshots cannot serve as post-fix visual evidence
`.planning/evidence/MOBILE-03/iphone-se-screenshot.png` was captured at commit `852ce98` (22:24), before WR-01 (`33bb35b`, 23:02), CR-02 (`be48ad9`, 22:55), and CR-03 (`3f6677c`, 22:58). The screenshots show:
- 7-field mobile tournament card (pre-WR-01 state)
- `display:contents` wrapper on key-metrics-strip (pre-CR-02 state)
- Stale bundle without Phase 14 reflow tokens (pre-CR-01 state, per 14-06 SUMMARY Issue 2)

Any future QA based on these screenshots will compare against the wrong state. New screenshots must be captured against the post-fix HEAD for each of the 4 reflow surfaces.

### Finding A-02 (INFO): `text-[9px]` section labels in PathToLiveTile will render below 10px on 1×DPI displays
At 9px, "PREFLIGHT checks" and "Carry-ins" eyebrow labels (`PathToLiveTile.jsx:177, 213, 249`) are likely illegible on low-DPI Android devices. The UI-SPEC declares `text-[10px]` as the minimum micro-label size. 9px is undocumented and sub-minimum. Fix: replace `text-[9px]` with `text-[10px]` to match the spec's documented micro-label floor.

### Finding A-03 (INFO): `tournament-refresh` button also lacks `aria-label` as an accessible name for the icon
`TournamentDashboard.jsx:316-345`: The button wraps `<RefreshCw size={11} aria-hidden="true" />` and `<span>Refresh</span>`. The text "Refresh" is visible, so the accessible name is "Refresh" — this is fine. However, `title="Re-read tournament snapshot from disk"` is present as a tooltip for hover users. On mobile, tooltip hover is unreachable. This is acceptable per the spec's scope, but worth noting.

### Finding A-04 (INFO): `additional_context` description of "More details disclosure" is inaccurate
The additional_context block states: "The mobile card now renders an expandable 'More details' disclosure that surfaces previously-hidden fields including the operationally load-bearing `failure_reason`." The current code at `TournamentDashboard.jsx:481-654` renders all 14 fields as a flat always-visible inline grid with no disclosure toggle, no `<details>`, and no expansion state. The WR-01 fix implemented flat display, not a disclosure. No behavioral discrepancy — the code is correct for the information-preservation contract — but the additional_context description is wrong and may mislead downstream QA.

---

## Registry Safety

Registry audit: `components.json` not present at repo root or under `frontend/` (confirmed by UI-SPEC §Registry Safety). shadcn not initialized. No third-party UI registry blocks to audit. Not applicable.

---

## Files Audited

| File | Role | Phase 14 Change |
|------|------|-----------------|
| `frontend/src/pages/TournamentDashboard.jsx` | Tournament page — dual-render + mobile cards | Modified (Plans 14-05, CR-03, WR-01) |
| `frontend/src/components/PathToLiveTile.jsx` | Phase 10 live-readiness tile | Modified (Plan 14-04) |
| `frontend/src/components/TournamentFilterChips.jsx` | Filter chip row | Modified (Plan 14-05) |
| `frontend/src/components/KeyMetricsStrip.jsx` | Metric strip | Modified (CR-02) |
| `frontend/tailwind.config.js` | Breakpoint token declaration | Modified (Plan 14-01) |
| `frontend/src/components/Dashboard.jsx` | Root layout | Verified only (Plan 14-03) |
| `.github/workflows/dashboard-smoke.yml` | CI workflow | Modified (Plan 14-06, CR-01) |
| `tests/e2e/test_responsive_dashboard.py` | Playwright responsive matrix | Created (Plan 14-02) |
| `tests/integration/test_no_mobile_hidden_data.py` | Static anti-hidden grep gate | Created (Plan 14-02) |
| `scripts/audit_responsive.py` | Hardcoded-width walker | Created (Plan 14-01) |
| `.planning/evidence/MOBILE-03/` | Evidence artifacts | Created (Plan 14-06) — pre-fix, see note |
| `.planning/phases/14-mobile-responsive-dashboard/14-UI-SPEC.md` | Design contract | Reference only |
| `.planning/phases/14-mobile-responsive-dashboard/touch-target-allowlist.json` | Touch-target exceptions | Reference only |
