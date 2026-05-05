# Accessibility Audit: Crypto Trading Bot Frontend

**Standard:** WCAG 2.1 AA · **Date:** 2026-05-02 · **Scope:** `frontend/src/**` (React 18 + Vite + Tailwind, dark-mode default)
**Method:** Source-code audit. No live browser/SR walk-through — the stack wasn't running. Numeric contrast computed from declared tokens; runtime values may differ where blends/overlays composite over the gradient body.

---

## Summary

| Severity | Count |
|---|---|
| 🔴 Critical (blocks users) | 6 |
| 🟡 Major (significantly degrades) | 11 |
| 🟢 Minor (polish) | 8 |

Headline: the dashboard is keyboard-reachable but not keyboard-livable. Modals trap nothing and release nothing. Charts are invisible to screen readers. The brand-feature gradient buttons fail contrast at `2.4:1`. Forms have visible labels but no programmatic association — every input on the Settings page is anonymous to assistive tech.

---

## Findings — Perceivable

| # | Issue | Where | WCAG | Severity | Fix |
|---|---|---|---|---|---|
| P1 | Primary CTA gradient (`from-cyan-500 to-blue-500` + white text) fails contrast: 2.43:1 at gradient start, 3.68:1 at end. Used on Save Settings, Export, every primary action. | `index.css` `.btn-primary`; `Settings.jsx`, `ExportPanel.jsx` | 1.4.3 | 🔴 | Replace gradient with a solid fill of at least 4.5:1 against white (e.g. `bg-blue-700` #1d4ed8 = 8.6:1, `bg-cyan-700` #0e7490 = 5.5:1). Or keep gradient and switch text to `font-semibold` *and* `text-base` (≥18.66px) so 3:1 is the bar — still fails at 2.43, so really: kill the gradient. |
| P2 | Footer / hint text uses `text-slate-400` on white in light mode = 2.56:1. | `App.jsx` footer; `Dashboard.jsx` hints | 1.4.3 | 🔴 | Move muted text to `text-slate-600` (#475569) = 7.6:1, or `text-slate-500` = 4.8:1 (passes). |
| P3 | Recharts `<AreaChart>` / line / bar wrappers render no `role="img"`, no `aria-label`, no inline `<title>`/`<desc>`, no text-table fallback. The equity curve, drawdown chart, returns distribution, correlation heatmap, and price chart are entirely invisible to screen readers. | `EquityCurveChart.jsx`, `DrawdownChart.jsx`, `ReturnsDistribution.jsx`, `CorrelationHeatmap.jsx`, `DailyPnLChart.jsx`, `PriceChart.jsx` | 1.1.1, 1.3.1 | 🔴 | Wrap each chart in `<figure role="img" aria-label="Equity curve, $X to $Y over period Z, ending +N%">` with summary stats. Provide a `<details><summary>View as table</summary><table>…</table></details>` text alternative below each chart. |
| P4 | Performance page axis tick text `--perf-text-3` (#65645e) on `--perf-bg` (#0a0a0b) = 3.33:1. Axis labels are critical chart info, not decoration. | `performance-theme.css` `.recharts-cartesian-axis-tick-value` | 1.4.3 | 🟡 | Bump `--perf-text-3` to `#8a8881` (4.6:1) or use `--perf-text-2` (#a09e98 = 7.4:1) for ticks specifically. |
| P5 | `--perf-text-4` (#3d3c38) = 1.79:1 on perf bg — fails even non-text 3:1. If used for any UI affordance (border, separator, icon stroke) it's invisible. | `performance-theme.css` | 1.4.11 | 🟡 | Either redefine to ≥3:1 (`#5a5851` ≈ 3.0:1) or restrict use to pure decoration with no semantic load. |
| P6 | Light-mode `text-slate-500` (#64748b) on `bg-slate-800` cards in dark mode = 3.07:1 (used as muted card text on `slate-800/50` cards). | `Dashboard.jsx`, `ActiveTrades.jsx`, `TradeHistory.jsx` (every "Entry Price" / "Position Size" label) | 1.4.3 | 🟡 | Use `text-slate-400` (#94a3b8) on `bg-slate-800` = 5.7:1. |
| P7 | Pulsing-green/red status dot is the only signal of "Connected" / "LIVE" / position direction in some places. Mostly paired with text — but the equity-curve tooltip uses color alone to distinguish gain/loss. P&L percent in `ActiveTrades` lacks `+/−` prefix in some renders (relies on `text-emerald-400` vs `text-rose-400`). | `Dashboard.jsx` footer; `EquityCurveChart.jsx` tooltip; `ActiveTrades.jsx` percent | 1.4.1 | 🟡 | Always pair color with a glyph (`+` / `−`, `↑` / `↓`) or text label. Already done well in some spots — make it universal. |
| P8 | Decorative SVG icons missing `aria-hidden="true"` (Dashboard logo, EmergencyStop alert triangle, ActiveTrades empty-state arrow, ExportPanel close X). Screen readers read SVG paths as garbage. | `Dashboard.jsx`, `EmergencyStop.jsx`, `ActiveTrades.jsx`, `ExportPanel.jsx` | 1.1.1 | 🟢 | Add `aria-hidden="true"` to every decorative SVG. Already applied correctly in `App.jsx` hamburger and `ThemeToggle.tsx` — copy that pattern. |
| P9 | Trade-detail labels at `text-[10px]` (TP1/TP2/TP3 percent allocations, "TRAILING", "TP1 HIT" badges). Below 11px, fails when text is resized to 200%. | `ActiveTrades.jsx` lines ~228–298 | 1.4.4, 1.4.12 | 🟢 | Lift to `text-xs` (12px) minimum. |

---

## Findings — Operable

| # | Issue | Where | WCAG | Severity | Fix |
|---|---|---|---|---|---|
| O1 | No "Skip to main content" link. Keyboard users must tab through 5 nav links + theme toggle on every page before reaching the dashboard. | `App.jsx` | 2.4.1 | 🔴 | Add `<a href="#main" className="sr-only focus:not-sr-only ...">Skip to main content</a>` as first child of `<body>`/`<App>`. Give `<main>` `id="main"`. |
| O2 | `*:focus { outline: none }` strips the browser's default focus ring globally. `focus-visible` re-applies a `ring-2 ring-cyan-500/50` ring but: (a) the 50% alpha drops the ring contrast to ~3.6:1 (passes 3:1 non-text but is the floor), (b) browsers without `:focus-visible` support get nothing, (c) `:focus` is also legitimate for non-keyboard contexts. | `index.css` `:focus { outline: none }` | 2.4.7 | 🔴 | Don't strip `:focus` blanket-style. Use `*:focus-visible { @apply ring-2 ring-cyan-500 ring-offset-2 }` (full opacity) and leave `:focus` alone. |
| O3 | `ExportPanel.jsx` modal has no `role="dialog"`, no `aria-modal="true"`, no `aria-labelledby`, no focus trap, no Escape-to-close, no return-focus on close, no initial-focus management. Background content remains tab-reachable through the overlay. Same pattern in `EmergencyStop.jsx` confirm view (which is a pseudo-modal rendered inline). | `ExportPanel.jsx`, `EmergencyStop.jsx` | 2.1.1, 2.1.2, 2.4.3, 4.1.2 | 🔴 | Use a dialog primitive (Radix UI, Headless UI, or React Aria) and migrate both. Stopgap: add `role="dialog" aria-modal="true" aria-labelledby="..."`, focus the close button on mount, trap Tab inside the dialog, listen for Escape, restore focus to the trigger on close. |
| O4 | Mobile menu opens but doesn't trap focus, doesn't close on Escape, doesn't return focus to the hamburger on close. | `App.jsx` `MobileMenu` | 2.1.2, 2.4.3 | 🟡 | Same dialog-primitive fix, or wire up an Escape listener + focus management manually. |
| O5 | `select` for symbol picker in `Dashboard.jsx` header (line 106) has no `<label htmlFor>` or `aria-label`. The visible "Chart:" span is unconnected. | `Dashboard.jsx` | 3.3.2, 4.1.2 | 🟡 | Add `aria-label="Chart symbol"` to the `<select>`, or wrap in `<label className="...">Chart: <select>...</select></label>` (label can stay visible). |
| O6 | Touch targets: hamburger button is `p-2` on a 24×24 SVG ≈ 40×40 — under the 44×44 minimum. Theme toggle in `sm` size = 32×32. Trade-card "Retry" button = ~28px high. | `App.jsx`, `ThemeToggle.tsx`, `ActiveTrades.jsx`, `TradeHistory.jsx` | 2.5.5 | 🟡 | Bump padding so each interactive target is ≥44×44 CSS pixels in viewports without hover. |
| O7 | Equity-curve / drawdown / price charts are not keyboard-navigable. Recharts ships with no built-in keyboard story; tab passes over the chart entirely. Data points are unreachable. | All chart components | 2.1.1 | 🟡 | Either swap to a charting lib with keyboard support (Highcharts, Visx with custom handlers) or pair every chart with the text-table fallback from P3. |

---

## Findings — Understandable

| # | Issue | Where | WCAG | Severity | Fix |
|---|---|---|---|---|---|
| U1 | Settings inputs have visible labels but no `htmlFor` linking label to input. Every `<label>` in `Settings.jsx` is a bare `<label>` element with no `htmlFor` attribute — the input has an `id` but the label doesn't reference it. Screen readers announce inputs as "edit text" with no name. Affects: `paper-trading`, `default-timeframe`, `max-position-size`, `stop-loss`, `take-profit`, `email/push/trade/price/system-notifications`, `api-key`, `api-secret`. | `Settings.jsx` `SettingsRow` | 1.3.1, 3.3.2, 4.1.2 | 🔴 | In `SettingsRow`, accept an `htmlFor` prop and apply it: `<label htmlFor={htmlFor}>{label}</label>`. Pass the input `id` from each row. |
| U2 | `Toggle` component uses `role="switch"` with `aria-checked` ✓ but its visible label sits in a sibling `<label>` (which itself isn't connected). The sr-only "Toggle setting" announcement is generic — every toggle on the page reads the same. | `Settings.jsx` `Toggle` | 4.1.2 | 🟡 | Either use `aria-labelledby` on the button pointing at the visible label's id, or make the visible label a real `<label>` with `htmlFor={id}` (browsers do connect `<label>` to a `role="switch"` button when `htmlFor` matches). |
| U3 | Status messages are not in `aria-live` regions: "Settings saved successfully!", "Export complete!", "Export failed", error banners on `ActiveTrades`/`TradeHistory`, P&L updates, position changes. Screen reader users have no way to know an action succeeded or that data refreshed. | `Settings.jsx`, `ExportPanel.jsx`, `ActiveTrades.jsx`, `TradeHistory.jsx` | 4.1.3 | 🔴 | Wrap success/error banners in `<div role="status" aria-live="polite">…</div>` (or `role="alert"` for errors). For ticker/P&L updates, use a single live region per dashboard with `aria-live="polite" aria-atomic="false"` and inject summarized changes. |
| U4 | Active nav link communicates state via border-color and text-color only — no `aria-current="page"`. SR users don't know which page they're on. | `App.jsx` `NavLink`, `MobileMenu` | 1.3.1, 4.1.2 | 🟡 | Add `aria-current={isActive ? 'page' : undefined}` to both. |
| U5 | `ThemeSelector` (3-button segmented control) has no `role="radiogroup"`, no `aria-pressed` on the active button. Active state shown by background color alone. | `ThemeToggle.tsx` | 1.3.1, 4.1.2 | 🟡 | Either give the wrapper `role="radiogroup" aria-label="Theme"` and each button `role="radio" aria-checked={...}`, or add `aria-pressed={...}` to each button. |
| U6 | Performance page period switcher uses custom `data-active='true'` attribute — invisible to assistive tech. | `performance-theme.css` `.perf-pill[data-active='true']`, `Phase1Dashboard.tsx` | 4.1.2 | 🟡 | Replace with `aria-pressed={isActive}` (or `aria-current="true"`) and adjust the CSS selector to `.perf-pill[aria-pressed='true']`. |
| U7 | "EMERGENCY STOP" button text is all-caps in markup (not via `text-transform`). Some screen readers spell out caps letter-by-letter. | `EmergencyStop.jsx` line 124 | 1.3.1 | 🟢 | Use `<span className="uppercase">Emergency stop</span>` so the underlying text remains sentence case. |
| U8 | Destructive "Delete Data" button in Settings has no confirmation dialog despite copy claiming "this action cannot be undone." | `Settings.jsx` line ~825 | 3.3.4 (AAA, but baseline UX) | 🟡 | Wire up a confirmation dialog (re-use the same dialog primitive from O3). |
| U9 | API Key and API Secret inputs are `type="password"` ✓ but lack `autocomplete="current-password"` / `autocomplete="off"`. Browsers may auto-fill saved passwords into them. | `Settings.jsx` lines 720–739 | 1.3.5 | 🟢 | Add `autoComplete="off"` (or specific `autocomplete` token if appropriate). |

---

## Findings — Robust

| # | Issue | Where | WCAG | Severity | Fix |
|---|---|---|---|---|---|
| R1 | Nested landmarks: `App.jsx` renders `<header>`, `<main>`, `<footer>`. `Dashboard.jsx` renders its own `<header>`, `<main>`, `<footer>` *inside* the outer `<main>`. Multiple `<main>` elements is invalid; nested headers/footers break landmark navigation. | `App.jsx` + `Dashboard.jsx` | 1.3.1, 4.1.1 | 🔴 | Drop `<header>`, `<main>`, `<footer>` from `Dashboard.jsx` — use plain `<div>` or `<section aria-labelledby>`. The outer App-level landmarks are sufficient. |
| R2 | Loading skeletons (`animate-pulse` divs) have no `role="status"` or accessible name. Screen readers announce nothing while data loads, then abruptly read the populated content. | `ActiveTrades.jsx`, `TradeHistory.jsx`, `KeyMetricsStrip.jsx`, `MetricsCard.jsx`, etc. | 4.1.3 | 🟡 | Wrap loading state in `<div role="status" aria-live="polite"><span className="sr-only">Loading active trades…</span>…skeleton…</div>`. |
| R3 | Loading spinners in `Settings.jsx`, `ExportPanel.jsx`, `EmergencyStop.jsx` are decorative SVGs with no `role="progressbar"` or `aria-label`. Button text changes to "Saving…" / "Stopping…" — visible only. | Multiple | 4.1.2 | 🟢 | Add `role="status"` or `role="progressbar"` with `aria-label="Saving settings"` to the spinner wrapper. |
| R4 | `ExportPanel` close X button has no accessible name (only an SVG). | `ExportPanel.jsx` line 459 | 4.1.2 | 🟡 | `<button aria-label="Close export panel" type="button">…svg…</button>`. |
| R5 | `EmergencyStop.jsx` button elements have no `type="button"` (default would be `submit`, harmless without a form, but a regression hazard if ever placed inside one). | `EmergencyStop.jsx` lines 51, 59, 100 | — | 🟢 | Add `type="button"` to all non-submit buttons. |

---

## Color Contrast — Computed

Computed against declared tokens. Effective ratios at runtime may shift where overlays composite over the body gradient (`#0a0f1a → #111827 → #0f172a`) — pessimistic-pick the gradient endpoint nearest the surface.

### Dark mode (bg ≈ `#0f172a` / `#1e293b`)

| Foreground | Background | Context | Ratio | 4.5:1 | 3:1 |
|---|---|---|---|---|---|
| `#f1f5f9` slate-100 | `#0f172a` | Primary text | **16.30:1** | ✅ | ✅ |
| `#9ca3af` (token `--text-secondary`) | `#0f172a` | Secondary text | **7.03:1** | ✅ | ✅ |
| `#6b7280` (token `--text-muted`) | `#0f172a` | Muted text token | **3.69:1** | ❌ | ✅ |
| `#94a3b8` slate-400 | `#1e293b` slate-800 | Card muted | **5.71:1** | ✅ | ✅ |
| `#64748b` slate-500 | `#1e293b` slate-800 | Tiny labels (Settings rows) | **3.07:1** | ❌ | ✅ |
| `#475569` slate-600 | `#0f172a` | Decorative borders | **2.36:1** | ❌ | ❌ |
| `#22d3ee` cyan-400 | `#0f172a` | Accent / version banner | **9.88:1** | ✅ | ✅ |
| `#34d399` emerald-400 | `#0f172a` | P&L positive | **9.29:1** | ✅ | ✅ |
| `#fb7185` rose-400 | `#0f172a` | P&L negative | **6.63:1** | ✅ | ✅ |
| `#fcd34d` amber-300 | `#0f172a` | Warning text | **12.38:1** | ✅ | ✅ |

### Light mode (bg = `#ffffff`)

| Foreground | Background | Context | Ratio | 4.5:1 | 3:1 |
|---|---|---|---|---|---|
| `#0f172a` slate-900 | `#ffffff` | Primary text | **17.85:1** | ✅ | ✅ |
| `#475569` slate-600 | `#ffffff` | Secondary | **7.58:1** | ✅ | ✅ |
| `#94a3b8` slate-400 | `#ffffff` | Muted/footer | **2.56:1** | ❌ | ❌ |
| `#64748b` slate-500 | `#ffffff` | Inactive nav | **4.76:1** | ✅ | ✅ |
| `#2563eb` blue-600 | `#ffffff` | Active nav, primary buttons | **5.17:1** | ✅ | ✅ |
| `#d97706` amber-600 | `#ffffff` | Warning text | **3.19:1** | ❌ | ✅ |
| `#059669` emerald-600 | `#ffffff` | Success text | **3.77:1** | ❌ | ✅ |
| `#e11d48` rose-600 | `#ffffff` | Danger text | **4.70:1** | ✅ | ✅ |
| `#dc2626` red-600 | `#ffffff` | Delete button bg w/white text | **4.83:1** | ✅ | ✅ |

### Performance page (bg = `#0a0a0b`)

| Foreground | Context | Ratio | 4.5:1 | 3:1 |
|---|---|---|---|---|
| `#f5f3ee` perf-text | Primary | **17.85:1** | ✅ | ✅ |
| `#a09e98` perf-text-2 | Secondary | **7.39:1** | ✅ | ✅ |
| `#65645e` perf-text-3 | Axis ticks, eyebrow | **3.33:1** | ❌ | ✅ |
| `#3d3c38` perf-text-4 | Decorative | **1.79:1** | ❌ | ❌ |
| `#5eead4` perf-gain (viridian) | Gain values | **13.38:1** | ✅ | ✅ |
| `#fb7185` perf-loss (warm rose) | Loss values | **7.35:1** | ✅ | ✅ |
| `#d4af6a` perf-gold | Highlight | **9.56:1** | ✅ | ✅ |

### Gradient buttons (the headline failure)

| Foreground | Background | Context | Ratio | 4.5:1 | 3:1 |
|---|---|---|---|---|---|
| `#ffffff` | `#06b6d4` cyan-500 (gradient start) | `.btn-primary` | **2.43:1** | ❌ | ❌ |
| `#ffffff` | `#3b82f6` blue-500 (gradient end) | `.btn-primary` | **3.68:1** | ❌ | ✅ |

### Focus ring (non-text 3:1 target)

| Foreground | Background | Context | Ratio | 3:1 |
|---|---|---|---|---|
| `#1a78a3` (cyan-500 @ α 0.5 over slate-900) | `#0f172a` | `*:focus-visible` ring | **3.62:1** | ✅ |

---

## Priority fixes (in order)

1. **Kill the gradient on `.btn-primary`.** Solid `bg-blue-700` for blue, or `bg-cyan-700`. Affects every primary CTA in the app — single CSS change, biggest surface coverage. (P1)
2. **Wire `htmlFor` through `SettingsRow`.** All twelve settings inputs become identifiable to assistive tech. ~10-line change. (U1)
3. **Add `role="dialog"` + focus trap + Escape-to-close to ExportPanel and EmergencyStop confirm view.** Pull in Radix UI Dialog or Headless UI Dialog — replacing the custom modal eliminates a class of bugs at once. (O3)
4. **Wrap charts in `<figure role="img" aria-label>` + provide a text-table `<details>` fallback.** Charts are the entire value of the dashboard and currently invisible to SR users. (P3)
5. **Skip-to-main link + `aria-current="page"` on nav.** Two trivial additions, large keyboard-UX upgrade. (O1, U4)
6. **Drop the global `*:focus { outline: none }` and use full-opacity `focus-visible` ring.** (O2)
7. **Add `aria-live` regions for status messages and error banners.** "Settings saved", "Export complete", connection/load errors. (U3)
8. **De-nest the landmarks in `Dashboard.jsx`.** Strip the inner `<header>/<main>/<footer>`. (R1)
9. **Light-mode footer text from slate-400 → slate-600.** One-token change. (P2)
10. **Bump `text-[10px]` labels in `ActiveTrades` to `text-xs` (12px).** Already smallish-comfortable on a high-density dashboard but at least passes resize. (P9)

---

## Out of scope / not verified

- **Real screen-reader testing** (NVDA / VoiceOver / JAWS): not run. This audit catches structural failures but a live SR pass will surface things static analysis can't (announcement order, table verbosity, chart fallback usability).
- **Keyboard walk-through against the running stack**: the bot is dormant per `progress.md` / `REVIVAL_PLAN_2026-05-02.md`. Once the frontend is back up at `localhost:3000`, do a tab-through of Dashboard → Settings → Export modal and confirm the fixes above.
- **Zoom to 200% / 400%**: not measured. Recharts' `ResponsiveContainer` should reflow but the `sticky top-0 z-50` header may obscure content at high zoom. Re-test after.
- **Reduced-motion preference**: `performance-theme.css` honors `prefers-reduced-motion` for `.perf-reveal` but the global `index.css` doesn't gate `animate-pulse`, `animate-glow`, `animate-pulse-glow`, status-dot pulse, gradient shimmer. Add a `@media (prefers-reduced-motion: reduce)` block disabling these.
- **i18n / RTL**: dashboard is English-only. Not assessed.
- **Cognitive load**: the Dashboard composes 13 panels on one route; this is a UX concern, not a WCAG one — flagged here so it doesn't get lost.
