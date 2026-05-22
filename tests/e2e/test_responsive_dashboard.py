"""Phase 14 MOBILE-02 + MOBILE-03 — responsive layout matrix.

Playwright Chromium matrix at iPhone SE (375x667) and iPad portrait (768x1024).
Asserts: no horizontal scroll, >=44px touch targets, banner visible without scroll,
per-component reflow shapes (Dashboard.jsx, PathToLiveTile.jsx, KeyMetricsStrip.jsx,
TournamentDashboard.jsx).

IMPORTANT: Uses raw viewport dicts via browser_context_args parametrize, NOT
the Playwright device-descriptor table -- the iPhone SE descriptor is 320x568
(1st gen), not 375x667 (2nd gen) per RESEARCH Pitfall 3.

IMPORTANT: Viewport set BEFORE page.goto() via the fixture override. Never call
page.set_viewport_size() AFTER navigation -- Chromium may not retrigger media-query
matching (RESEARCH "Anti-Patterns to Avoid").

RED expectation (Wave-1 close):
  - Tests 1-7 ALL fail on Wave-1 dashboard (no mobile reflow yet)
  - Wave 2 plans (14-03/04/05) drive each test to GREEN by reflowing the
    corresponding component
  - Test 7 (test_tournament_dual_render) requires the LOCKED B2 testid contract
    on the tournament dashboard: tournament-mobile-card-list /
    tournament-desktop-table-wrapper / mirrored tournament-row-<runId>
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

GATEWAY_ORIGIN = "http://localhost:8000"
REPO_ROOT = Path(__file__).resolve().parents[2]
TOUCH_TARGET_ALLOWLIST_PATH = (
    REPO_ROOT
    / ".planning"
    / "phases"
    / "14-mobile-responsive-dashboard"
    / "touch-target-allowlist.json"
)

# Viewport matrix (RESEARCH Pattern 2 -- raw dicts, NOT the Playwright
# device-descriptor table; see module docstring).
# Each entry parametrizes browser_context_args via indirect=True.
VIEWPORTS = [
    {"viewport": {"width": 375, "height": 667}, "label": "iphone-se"},
    {"viewport": {"width": 768, "height": 1024}, "label": "ipad-portrait"},
]


def _load_touch_target_allowlist() -> list[dict[str, str]]:
    """Load touch-target allowlist; entries shape: [{selector, reason}]."""
    if not TOUCH_TARGET_ALLOWLIST_PATH.exists():
        return []
    entries = json.loads(TOUCH_TARGET_ALLOWLIST_PATH.read_text())
    # Only allowlist entries with a non-empty reason field (Pattern S3 discipline)
    return [e for e in entries if e.get("reason")]


# ---------------------------------------------------------------------------
# Test 1: No horizontal scroll at either viewport
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,
    ids=[v["label"] for v in VIEWPORTS],
)
def test_no_horizontal_scroll(page: Page, browser_context_args):
    """No element with [data-testid] overflows window.innerWidth.

    Single page.evaluate() round-trip walks the entire DOM (RESEARCH "Don't
    Hand-Roll" -- one round-trip, not N).
    """
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")
    overflowing = page.evaluate(
        """
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
        """
    )
    assert overflowing == [], (
        f"{len(overflowing)} elements overflow window.innerWidth at viewport "
        f"{browser_context_args['viewport']}: {overflowing[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 2: Touch targets >= 44px (WCAG 2.5.5 Level AAA)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,
    ids=[v["label"] for v in VIEWPORTS],
)
def test_touch_targets_44px(page: Page, browser_context_args):
    """Every visible <button>, <a>, [role="button"] has height >= 44px.

    Allowlist-aware: selectors in touch-target-allowlist.json with a non-empty
    `reason` field are filtered out of failures. Match is by substring of the
    `selector` string against a rendered element-selector hint (tag + testid +
    href).
    """
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")
    failures = page.evaluate(
        """
        () => {
          const out = [];
          document.querySelectorAll('button, a, [role="button"]').forEach(el => {
            const rect = el.getBoundingClientRect();
            const h = rect.height;
            if (h < 44 && el.offsetParent !== null) {
              const testid = el.getAttribute('data-testid') || '';
              const href = el.getAttribute('href') || '';
              const role = el.getAttribute('role') || '';
              const tag = el.tagName.toLowerCase();
              // Build a synthetic selector hint that allowlist entries can
              // match against via substring.
              const hint_parts = [tag];
              if (testid) hint_parts.push(`[data-testid='${testid}']`);
              if (href) hint_parts.push(`[href='${href}']`);
              if (role) hint_parts.push(`[role='${role}']`);
              out.push({
                tag: tag,
                text: (el.innerText || '').slice(0, 30),
                height: h,
                testid: testid,
                href: href,
                role: role,
                hint: hint_parts.join(''),
              });
            }
          });
          return out;
        }
        """
    )
    # Filter through allowlist: drop any failure whose `hint` contains an
    # allowlisted selector substring.
    allowlist = _load_touch_target_allowlist()
    filtered = []
    for f in failures:
        matched_allow = False
        for entry in allowlist:
            sel = entry["selector"]
            # Substring match against rendered hint (tag + testid + href).
            if sel and sel in f["hint"]:
                matched_allow = True
                break
            # Also match against bare data-testid/href tokens.
            if f["testid"] and f"data-testid='{f['testid']}'" in sel:
                matched_allow = True
                break
            if f["href"] and f"href='{f['href']}'" in sel:
                matched_allow = True
                break
        if not matched_allow:
            filtered.append(f)

    assert filtered == [], (
        f"{len(filtered)} interactive targets below 44px at viewport "
        f"{browser_context_args['viewport']}: {filtered[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 3: PathToLive banner visible without scroll
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,
    ids=[v["label"] for v in VIEWPORTS],
)
def test_banner_visible_without_scroll(page: Page, browser_context_args):
    """PathToLive banner state-token visible above the fold.

    Banner DO-NOT-FLIP / ALMOST / READY is the operator's first-glance answer
    and must never be below-the-fold on mobile (UI-SPEC Anti-Pattern Gate #4).
    """
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")

    banner = page.locator('[data-testid="path-to-live-banner"]')
    expect(banner).to_be_visible(timeout=15000)

    # Probe bbox y-position vs viewport height to confirm above-the-fold.
    bbox = banner.bounding_box()
    inner_height = page.evaluate("() => window.innerHeight")
    assert bbox is not None, "banner bounding_box returned None"
    assert bbox["y"] < inner_height, (
        f"banner top y={bbox['y']} is below viewport innerHeight={inner_height} "
        f"at viewport {browser_context_args['viewport']} -- must be above the fold"
    )


# ---------------------------------------------------------------------------
# Test 4: Dashboard single-column stack at iPhone SE
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,
    ids=[v["label"] for v in VIEWPORTS],
)
def test_dashboard_single_column_mobile(page: Page, browser_context_args):
    """Dashboard.jsx sections render in single-column stack at <=768px.

    Mobile-only assertion. The iPad-portrait parameter falls through to skip
    so the test reports cleanly across the matrix; only iphone-se runs the
    geometric checks.
    """
    if browser_context_args["viewport"]["width"] >= 768:
        pytest.skip("mobile-only assertion; ipad-portrait runs other tests")

    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")

    # Probe top-level dashboard sections that should each span the full
    # viewport width (>90% of innerWidth) when stacked single-column.
    widths = page.evaluate(
        """
        () => {
          const innerW = window.innerWidth;
          const probes = [
            '[data-testid="path-to-live-tile"]',
            '[data-testid="key-metrics-strip"]',
          ];
          return probes.map(sel => {
            const el = document.querySelector(sel);
            if (!el) return {selector: sel, found: false, width: 0, ratio: 0};
            const rect = el.getBoundingClientRect();
            return {
              selector: sel,
              found: true,
              width: rect.width,
              ratio: rect.width / innerW,
              innerWidth: innerW,
            };
          });
        }
        """
    )
    too_narrow = [w for w in widths if w["found"] and w["ratio"] < 0.90]
    missing = [w for w in widths if not w["found"]]
    assert not too_narrow, (
        f"Dashboard sections do not span >90% of innerWidth at iphone-se: {too_narrow}"
    )
    # Allow missing sections in RED phase; assert only when component present.
    if missing:
        pytest.fail(f"Expected dashboard sections not found in DOM: {missing}")


# ---------------------------------------------------------------------------
# Test 5: PathToLive rows span full width at iPhone SE
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,
    ids=[v["label"] for v in VIEWPORTS],
)
def test_path_to_live_rows_full_width(page: Page, browser_context_args):
    """6 PREFLIGHT chip rows + 5 carry-in rows span >90% of innerWidth.

    Mobile-only assertion. After Wave 2 reflow, each row stacks vertically and
    spans full-width-per-row at <=768px.
    """
    if browser_context_args["viewport"]["width"] >= 768:
        pytest.skip("mobile-only assertion; ipad-portrait runs other tests")

    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")

    row_widths = page.evaluate(
        """
        () => {
          const innerW = window.innerWidth;
          const out = [];
          const selectors = [
            '[data-testid^="path-to-live-check-"]',
            '[data-testid^="path-to-live-carry-in-"]',
          ];
          selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
              const rect = el.getBoundingClientRect();
              out.push({
                testid: el.getAttribute('data-testid'),
                width: rect.width,
                ratio: rect.width / innerW,
                innerWidth: innerW,
              });
            });
          });
          return out;
        }
        """
    )
    assert row_widths, (
        "No path-to-live-check-* or path-to-live-carry-in-* rows found in DOM "
        "-- PathToLiveTile may not be rendered or testids changed"
    )
    too_narrow = [r for r in row_widths if r["ratio"] < 0.90]
    assert not too_narrow, (
        f"{len(too_narrow)} PathToLive rows do not span >90% of innerWidth at "
        f"iphone-se: {too_narrow[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 6: KeyMetrics strip is 2-col grid on mobile
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,
    ids=[v["label"] for v in VIEWPORTS],
)
def test_key_metrics_2col(page: Page, browser_context_args):
    """KeyMetricsStrip cells distribute across at most 2 columns at <=768px.

    Mobile-only assertion. Probe child cells; group their bounding-box .right
    edges within 4px tolerance to count columns per row. Hero cells (which
    span 2 cols via inline gridColumn) are permitted to occupy a row alone.
    """
    if browser_context_args["viewport"]["width"] >= 768:
        pytest.skip("mobile-only assertion; ipad-portrait runs other tests")

    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")

    layout = page.evaluate(
        """
        () => {
          const strip = document.querySelector('[data-testid="key-metrics-strip"]');
          if (!strip) return {found: false, cells: []};
          // Find grid children: direct .Cell children OR descendants with data-testid
          // matching metric-*. Fall back to direct children.
          const candidates = Array.from(strip.querySelectorAll('[data-testid^="metric-"]'));
          const cells = candidates.length > 0
            ? candidates
            : Array.from(strip.children);
          return {
            found: true,
            innerWidth: window.innerWidth,
            cells: cells.map(c => {
              const rect = c.getBoundingClientRect();
              return {
                testid: c.getAttribute('data-testid') || '',
                top: rect.top,
                left: rect.left,
                right: rect.right,
                width: rect.width,
              };
            }),
          };
        }
        """
    )
    assert layout["found"], (
        "data-testid='key-metrics-strip' not found in DOM -- KeyMetricsStrip "
        "may not be rendered"
    )
    cells = layout["cells"]
    assert cells, "KeyMetricsStrip has no probeable child cells"

    # Group cells by row (top-edge within 4px tolerance), count distinct
    # right-edges per row.
    rows: list[list[dict]] = []
    for cell in cells:
        placed = False
        for row in rows:
            if abs(row[0]["top"] - cell["top"]) < 4:
                row.append(cell)
                placed = True
                break
        if not placed:
            rows.append([cell])

    over_2col = []
    for i, row in enumerate(rows):
        # Distinct right-edges within 4px tolerance count as columns.
        rights: list[float] = []
        for cell in row:
            r = cell["right"]
            if not any(abs(r - existing) < 4 for existing in rights):
                rights.append(r)
        if len(rights) > 2:
            over_2col.append({"row": i, "cols": len(rights), "rights": rights})

    assert not over_2col, (
        f"KeyMetricsStrip has rows with >2 columns at iphone-se: {over_2col}"
    )


# ---------------------------------------------------------------------------
# Test 7: Tournament dual-render (LOCKED B2 testid contract)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,
    ids=[v["label"] for v in VIEWPORTS],
)
def test_tournament_dual_render(page: Page, browser_context_args):
    """Tournament dashboard dual-render: mobile cards vs desktop table.

    LOCKED testid contract (Plan 14-05 implements verbatim):
      - Mobile-card wrapper:   data-testid="tournament-mobile-card-list"
      - Desktop-table wrapper: data-testid="tournament-desktop-table-wrapper"
      - Per-row testid:        data-testid="tournament-row-<runId>" mirrored
        on BOTH the desktop <tr> and the mobile card <div>; only one branch is
        display-visible per viewport via md:hidden vs hidden md:block, so
        [data-testid^="tournament-row-"] always resolves to the active rowset.

    The wrapper class toggling guarantees exactly one branch is rendered
    visible at each viewport; the mirrored row testid asserts the invariant.
    """
    page.goto(f"{GATEWAY_ORIGIN}/tournament", wait_until="networkidle")
    width = browser_context_args["viewport"]["width"]

    mobile_wrapper = page.locator('[data-testid="tournament-mobile-card-list"]')
    desktop_wrapper = page.locator('[data-testid="tournament-desktop-table-wrapper"]')
    any_row = page.locator('[data-testid^="tournament-row-"]').first

    if width < 768:
        # iphone-se: mobile cards visible, desktop table hidden via display:none
        expect(mobile_wrapper).to_be_visible(timeout=10000)
        expect(desktop_wrapper).not_to_be_visible()
    else:
        # ipad-portrait: desktop table visible, mobile cards hidden
        expect(desktop_wrapper).to_be_visible(timeout=10000)
        expect(mobile_wrapper).not_to_be_visible()

    # Same testid string lives on both branches; the visible branch satisfies
    # is_visible() at each viewport. Holds at BOTH viewports per the locked
    # checker B2 contract.
    assert any_row.is_visible(timeout=10000), (
        "tournament-row-<runId> testid not visible at viewport "
        f"{browser_context_args['viewport']}; the mirrored testid contract "
        "(same string on desktop <tr> and mobile card <div>) is broken"
    )
