"""
Audit-driven dashboard smoke (Phase 7 / DASH-06).

This test boots the recorded-tape stack via the Phase 2 `bootstrap_stack` +
`tape_reset` fixtures (D-19), seeds a deterministic tournament snapshot
(D-08), and walks every row in
`.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json`
asserting each tile renders according to its verdict (D-15):

    FIXED         -> tile is visible AND inner_text is non-empty
    LABELED_STALE -> tile is visible AND contains tile-stale-badge
    REMOVED       -> tile is absent

There is NO escape hatch: every non-REMOVED audit row MUST carry a
`data_testid` field (Plan 03 wires this); if any row is missing one, the
hard gate below fails the smoke at setup time, not silently skips (B-1).

The smoke targets the gateway origin http://localhost:8000 — NOT the vite
dev origin :3000 — so it exercises the same ingress the production frontend
goes through (UI-SPEC Claude's Discretion).

Browser scope is Chromium-only (D-18). Failure artifacts (screenshots,
videos, traces, HAR) are configured at the pytest-playwright CLI level
(`--screenshot=only-on-failure --video=retain-on-failure` etc., wired by
Plan 06 in CI). No explicit capture inside the test body.

References:
  - Phase 7 plan 05: .planning/phases/07-tournament-view-smoke-test/07-05-PLAN.md
  - Audit JSON:      .planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json
  - StatusBar shape: frontend/src/components/StatusBar.jsx
"""

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect


# ---------------------------------------------------------------------------
# Route mapping (BL-1 fix).
#
# The frontend registers `/`, `/phase1`, `/phase3`, `/performance`, `/portfolio`,
# `/settings`, `/tournament` (see frontend/src/App.jsx). Three audit rows are
# PAGE-LEVEL composites that live on their own routes (NOT on `/`):
# Phase1Dashboard, Phase3Dashboard, and the page-level Portfolio row.
#
# PAGE_LEVEL_ROUTE_OVERRIDE is keyed by tile name and wins over PAGE_ROUTES;
# component-level tiles fall back to PAGE_ROUTES (keyed by audit `page` field).
# ---------------------------------------------------------------------------
PAGE_LEVEL_ROUTE_OVERRIDE = {
    "Phase1Dashboard": "/phase1",
    "Phase3Dashboard": "/phase3",
    # The page-level Portfolio row (verdict=LABELED_STALE) — NOT PortfolioCard,
    # which is the component-level tile on the Dashboard ('/').
    "Portfolio": "/portfolio",
}

PAGE_ROUTES = {
    "Performance": "/",
    "Portfolio": "/",  # component-level tiles on the Dashboard (e.g. PortfolioCard)
    "Phase1": "/",  # component-level tiles on the Dashboard
    "Phase3": "/phase3",
    "Tournament": "/tournament",
}

GATEWAY_ORIGIN = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Match the dashboard's native viewport (1440x900) so layout-dependent
    tiles render at the size the audit was captured against."""
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}}


@pytest.fixture(scope="session")
def tile_audit():
    """Load the session-of-truth audit roster from disk.

    The JSON is read at runtime (NOT inlined into the test) so any Plan 03
    audit edit is picked up by the smoke without re-shipping the test file.
    """
    audit_path = (
        Path(__file__).resolve().parents[2]
        / ".planning"
        / "phases"
        / "06-dashboard-audit-safety-state"
        / "06-TILE-AUDIT.json"
    )
    return json.loads(audit_path.read_text())


# ---------------------------------------------------------------------------
# The single audit-driven test
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack", "tape_reset", "tournament_snapshot_seeded")
def test_every_audited_tile_renders_per_verdict(page, tile_audit):
    """Walk 06-TILE-AUDIT.json and assert each tile per its verdict.

    Hard data_testid gate runs BEFORE navigation (B-1 fix). Per-page
    navigation runs at the top of every loop iteration (BL-1 fix).
    Tournament-specific assertions and StatusBar D-17 substring assertions
    run AFTER the verdict loop.
    """
    # ---- Step 1: hard data_testid gate (B-1) -------------------------------
    rows_needing_testid = [r for r in tile_audit["tiles"] if r["verdict"] != "REMOVED"]
    missing = [r for r in rows_needing_testid if not r.get("data_testid")]
    assert not missing, (
        f"audit-driven smoke contract broken: {len(missing)} non-REMOVED "
        f"tile(s) missing data_testid: {[r['tile'] for r in missing]}. "
        "Plan 03 must wire data-testid on every production tile."
    )

    # ---- Step 2: open the dashboard at the gateway origin + wait for StatusBar
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle", timeout=30000)
    page.wait_for_selector('[data-testid="statusbar"]', timeout=15000)

    # ---- Step 3: per-row verdict loop --------------------------------------
    for row in tile_audit["tiles"]:
        verdict = row["verdict"]
        # Tile-level override wins; fall back to the page mapping; default '/'.
        target = PAGE_LEVEL_ROUTE_OVERRIDE.get(
            row["tile"], PAGE_ROUTES.get(row["page"], "/")
        )
        page.goto(f"{GATEWAY_ORIGIN}{target}", wait_until="networkidle")

        if verdict == "REMOVED":
            # REMOVED rows may not have a data_testid (Plan 03 only required
            # it on non-REMOVED rows). When one is present, assert absence.
            testid = row.get("data_testid")
            if testid:
                expect(page.locator(f'[data-testid="{testid}"]')).to_have_count(0)
            continue

        testid = row["data_testid"]  # hard-asserted above for non-REMOVED rows
        if verdict == "FIXED":
            expect(page.locator(f'[data-testid="{testid}"]')).to_be_visible(
                timeout=10000
            )
            assert (
                page.locator(f'[data-testid="{testid}"]').inner_text().strip() != ""
            ), f"FIXED tile {row['tile']} on {target} renders empty inner_text"
        elif verdict == "LABELED_STALE":
            # Plan 03 wires a root-level data-testid on the tile component AND
            # tile-stale-badge inside <TileState/>. Phase 6 Plan 06-05 wraps
            # each LABELED_STALE tile in <TileState forceStale={true}/> so the
            # StaleBadge renders even when the backing endpoint returns 503
            # / empty under recorded tape. forceStale precondition is
            # asserted at smoke-construction time (acceptance bash loop in
            # 07-05-PLAN.md), NOT at smoke-run time.
            expect(
                page.locator(
                    f'[data-testid="{testid}"] [data-testid="tile-stale-badge"]'
                )
            ).to_be_visible()
        else:
            pytest.fail(f"unknown verdict {verdict!r} for tile {row['tile']}")

    # ---- Step 4: Tournament-page-specific assertions -----------------------
    page.goto(f"{GATEWAY_ORIGIN}/tournament", wait_until="networkidle")
    expect(page.locator('[data-testid="tournament-leaderboard"]')).to_be_visible()
    # Fixture has 7 rows; allow >= 6 as a conservative lower bound (the
    # filter UI may hide the failed row by default).
    assert page.locator('[data-testid^="tournament-row-"]').count() >= 6, (
        "expected at least 6 tournament-row-* entries (fixture has 7 rows)"
    )
    expect(page.locator('[data-testid="tournament-selector"]')).to_be_visible()
    selector_text = page.locator('[data-testid="tournament-selector"]').inner_text()
    assert "smoke-tape-fixture" in selector_text, (
        f"expected tournament selector to surface 'smoke-tape-fixture', "
        f"got: {selector_text!r}"
    )
    expect(page.locator('[data-testid="tournament-filter-status"]')).to_be_visible()
    expect(page.locator('[data-testid="tournament-refresh"]')).to_be_visible()
    expect(page.locator('[data-testid="tournament-footer"]')).to_be_visible()
    footer_text = page.locator('[data-testid="tournament-footer"]').inner_text()
    assert "exported" in footer_text.lower(), (
        f"expected tournament footer to mention 'exported', got: {footer_text!r}"
    )
    # contaminated-warning MUST be absent — every fixture row sets
    # train_window_includes_contaminated=false (UI-SPEC line 230).
    expect(page.locator('[data-testid="contaminated-warning"]')).to_have_count(0)
    # W-3 Path A: sidecars are seeded, so BOTH significance paths render.
    assert page.locator('[data-testid="significance-badge-pass"]').count() >= 1, (
        "expected at least 1 significance-badge-pass (SOL/GRU is ensemble "
        "member AND SOL.win_gate_passed=true)"
    )
    assert page.locator('[data-testid="significance-badge-none"]').count() >= 5, (
        "expected at least 5 significance-badge-none (other 5 success rows "
        "render em-dash + 1 failed row renders em-dash)"
    )

    # ---- Step 5: StatusBar D-17 substring assertions (B-4 fix) -------------
    # Substrings derived from frontend/src/components/StatusBar.jsx at
    # planning time and named in 07-05-PLAN.md, NOT re-derived here:
    #   MODE (line 173-179):       'PAPER'    — recorded-tape stack is PAPER
    #   KILL-SWITCH (line 182-187): 'ARMED'   — kill_switch.tripped=false in tape
    #   ML (line 190-195):          'OFF'     — ENABLE_ML_PREDICTIONS=false default
    #   EMERGENCY (line 198-204):   'INACTIVE' — no EMERGENCY_STOP file in tape
    #   state pill (line 132/149):  'idle'|'live' (NOT 'halted') under tape
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")
    statusbar = page.locator('[data-testid="statusbar"]')
    expect(statusbar).to_be_visible()

    mode_text = page.locator('[data-testid="statusbar-mode"]').inner_text()
    assert "PAPER" in mode_text, (
        f"expected MODE cell to contain 'PAPER', got: {mode_text!r}"
    )

    kill_text = page.locator('[data-testid="statusbar-kill-switch"]').inner_text()
    assert "ARMED" in kill_text, (
        f"expected KILL-SWITCH cell to contain 'ARMED', got: {kill_text!r}"
    )

    ml_text = page.locator('[data-testid="statusbar-ml"]').inner_text()
    assert "OFF" in ml_text, f"expected ML cell to contain 'OFF', got: {ml_text!r}"

    emergency_text = page.locator(
        '[data-testid="statusbar-emergency-stop"]'
    ).inner_text()
    assert "INACTIVE" in emergency_text, (
        f"expected EMERGENCY cell to contain 'INACTIVE', got: {emergency_text!r}"
    )

    state_text = page.locator('[data-testid="statusbar-trading-state"]').inner_text()
    state_lower = state_text.strip().lower()
    # The pill text concatenates the state ('idle'/'live'/'halted') with the
    # strategy_mode label and possibly a status dot; substring-match the state
    # word inside the rendered text.
    assert any(s in state_lower for s in ("idle", "live")), (
        f"expected trading-state pill to contain 'idle' or 'live' under "
        f"recorded tape (NOT 'halted'), got: {state_text!r}"
    )
