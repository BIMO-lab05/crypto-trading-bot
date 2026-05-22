---
phase: 14
slug: mobile-responsive-dashboard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-22
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-playwright + jest (existing frontend) |
| **Config file** | `pyproject.toml` (pytest) + `frontend/vitest.config.js` (jest) + `.github/workflows/dashboard-smoke.yml` (matrix runner) |
| **Quick run command** | `cd frontend && npm test -- --run` (unit, ~10s) |
| **Full suite command** | `pytest tests/e2e/test_responsive_dashboard.py tests/integration/test_no_mobile_hidden_data.py` |
| **Estimated runtime** | ~45s (Playwright Chromium headless × 2 viewports + grep integration) |

---

## Sampling Rate

- **After every task commit:** Run `npm test -- --run` (frontend unit) + relevant grep test if anti-hidden gate touched
- **After every plan wave:** Run full Playwright matrix (`pytest tests/e2e/test_responsive_dashboard.py`)
- **Before `/gsd-verify-work`:** Full suite must be green; manual visual scan of dashboard at 375×667 + 768×1024 via local browser DevTools or Playwright headed mode
- **Max feedback latency:** 60 seconds (Playwright matrix worst case)

---

## Per-Task Verification Map

> Filled by planner. Each Plan/task gets a row. Test commands map to MOBILE-01..03 acceptance criteria.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | MOBILE-01 | — / — | tailwind.config.js declares 4 breakpoints | unit | `grep -q "screens" frontend/tailwind.config.js` | ❌ W0 | ⬜ pending |
| 14-01-02 | 01 | 1 | MOBILE-01 | — / — | audit script produces responsive-audit.json | integration | `python3 scripts/audit_responsive.py --out responsive-audit.json && test -f responsive-audit.json` | ❌ W0 | ⬜ pending |
| 14-02-01 | 02 | 2 | MOBILE-02 | — / — | Dashboard.jsx flex-col md:grid at ≤768px | playwright | `pytest tests/e2e/test_responsive_dashboard.py::test_dashboard_single_col_375` | ❌ W0 | ⬜ pending |
| 14-02-02 | 02 | 2 | MOBILE-02 | — / — | PathToLiveTile 6+5 rows wrap to full-width-per-row | playwright | `pytest tests/e2e/test_responsive_dashboard.py::test_path_to_live_row_wrap_375` | ❌ W0 | ⬜ pending |
| 14-02-03 | 02 | 2 | MOBILE-02 | — / — | KeyMetricsStrip grid-cols-2 at ≤768px | playwright | `pytest tests/e2e/test_responsive_dashboard.py::test_key_metrics_2col_375` | ❌ W0 | ⬜ pending |
| 14-02-04 | 02 | 2 | MOBILE-02 | — / — | TournamentDashboard table → cards via dual render | playwright | `pytest tests/e2e/test_responsive_dashboard.py::test_tournament_card_list_375` | ❌ W0 | ⬜ pending |
| 14-03-01 | 03 | 3 | MOBILE-03 | — / — | Zero element with bbox.x+width > window.innerWidth | playwright | `pytest tests/e2e/test_responsive_dashboard.py::test_no_horizontal_scroll` | ❌ W0 | ⬜ pending |
| 14-03-02 | 03 | 3 | MOBILE-03 | — / — | All tappable elements min-height >= 44px | playwright | `pytest tests/e2e/test_responsive_dashboard.py::test_touch_target_44px` | ❌ W0 | ⬜ pending |
| 14-03-03 | 03 | 3 | MOBILE-03 | — / — | Anti-hidden grep gate green | unit | `pytest tests/integration/test_no_mobile_hidden_data.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Detailed task IDs are placeholders — planner refines during plan-phase.*

---

## Wave 0 Requirements

- [ ] `tests/e2e/test_responsive_dashboard.py` — Playwright Chromium × {iPhone SE 375×667, iPad portrait 768×1024} via raw `browser_context_args` dict (NOT `playwright.devices['iPhone SE']` — that descriptor is 320×667 not 375×667 per RESEARCH.md Pitfall 2)
- [ ] `tests/integration/test_no_mobile_hidden_data.py` — `frontend/src/**/*.jsx` walk + regex `hidden (sm|md|lg|xl):block` block; allowlist by exact `data-testid` string with `reason` field
- [ ] `scripts/audit_responsive.py` — Python walker emitting `responsive-audit.json` at repo root with `[{"file","line","rule","snippet"}]` shape; pre-populated allowlist with `reason: "out-of-phase-14-scope"` for ~20+ existing hits per RESEARCH.md Pitfall 1
- [ ] `.github/workflows/dashboard-smoke.yml` — add `pytest tests/e2e/test_responsive_dashboard.py` step; reuse existing Playwright Chromium install

*Existing infrastructure (`dashboard-smoke.yml` Playwright workflow, `pyproject.toml` pytest config, `frontend/package.json` jest+vitest deps) covers the runtime; new files above are this phase's Wave 0 deliverables.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual taste check — reflow looks good at iPhone SE | MOBILE-02 | Tests assert no-h-scroll + touch targets but cannot assert aesthetic; operator must eyeball | Open Chrome DevTools → toggle device toolbar → iPhone SE (375×667) → load `http://localhost:3000` → scroll full dashboard; confirm tiles stack legibly, PathToLive chips wrap cleanly, TournamentDashboard cards read naturally |
| Visual taste check — reflow looks good at iPad portrait | MOBILE-02 | Same as above for larger phone/tablet boundary | DevTools → iPad portrait (768×1024); confirm `md:` boundary triggers cleanly, no tile overflows, filter chips wrap |
| Touch interaction feel on real device | MOBILE-03 | Playwright touch-target assertion is geometric (>=44px); cannot test actual finger comfort | Load dashboard on operator's iPhone/Android via local IP; tap PathToLiveTile chips, KeyMetricsStrip cards, TournamentDashboard buttons; confirm no missed taps from too-small targets |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
