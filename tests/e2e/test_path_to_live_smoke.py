"""Phase 10 DASHLIVE-04 — Path-to-LIVE smoke. Covers D-10-18 #1..#7.

Assertions:
  #1  Tile visible at data-testid="path-to-live-tile" on / route.
  #2  Each of 6 PREFLIGHT rows renders with chip text matching the status
      from /api/preflight/live-readiness snapshot.
  #3  Each of 5 carry-in rows renders with state "open" (seeded fixture).
  #4  Banner text matches overall from /api/preflight/carry-ins
      (expected "DO NOT FLIP" in PAPER mode with no DSR row).
  #5  GET /api/preflight/carry-ins returns 200 with schema_version=1 and
      all required top-level keys.
  #6  After leaderboard_dsr_seeded: dsr_evidence.status=="PASS" and
      detail contains both "0.97" and the ISO run_date.
  #7  With all_preflight_checks_passing + PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1,
      the second carry-ins poll returns overall=="READY" and
      window.elapsed_seconds >= 1.

The smoke targets gateway origin http://localhost:8000 — NOT the vite dev
origin :3000 — so it exercises the same ingress the production frontend uses.
"""

from __future__ import annotations

import time
from datetime import date

import httpx
import pytest
from playwright.sync_api import expect

GATEWAY_ORIGIN = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Match the dashboard's native viewport so layout-dependent tiles render."""
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_preflight_live_readiness() -> dict:
    """Fetch /api/preflight/live-readiness and return the JSON body."""
    r = httpx.get(f"{GATEWAY_ORIGIN}/api/preflight/live-readiness", timeout=10)
    assert r.status_code == 200, (
        f"GET /api/preflight/live-readiness returned {r.status_code}: {r.text[:300]}"
    )
    return r.json()


def _get_carry_ins() -> dict:
    """Fetch /api/preflight/carry-ins and return the JSON body."""
    r = httpx.get(f"{GATEWAY_ORIGIN}/api/preflight/carry-ins", timeout=10)
    assert r.status_code == 200, (
        f"GET /api/preflight/carry-ins returned {r.status_code}: {r.text[:300]}"
    )
    return r.json()


# ---------------------------------------------------------------------------
# Test A: tile renders, preflight rows, carry-in rows, banner (D-10-18 #1..#4)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack", "tape_reset")
def test_path_to_live_tile_renders(page):
    """D-10-18 assertions #1, #2, #3, #4.

    #1  path-to-live-tile is visible after navigating to /.
    #2  Each of 6 PREFLIGHT rows renders with a status chip; chip text
        matches the status field from a /api/preflight/live-readiness snapshot.
    #3  Each of 5 carry-in rows renders with state "open".
    #4  Banner text matches overall from /api/preflight/carry-ins.
        Expected "DO NOT FLIP" in PAPER mode.
    """
    # Snapshot live-readiness BEFORE navigation (deterministic reference)
    lr_data = _get_preflight_live_readiness()
    checks = lr_data.get("checks", [])
    assert len(checks) == 6, (
        f"Expected 6 PREFLIGHT checks from /live-readiness, got {len(checks)}: "
        f"{[c.get('check') for c in checks]}"
    )

    # Snapshot carry-ins for banner reference
    ci_data = _get_carry_ins()
    expected_overall = ci_data.get("overall", "DO_NOT_FLIP")
    # Normalise: API uses DO_NOT_FLIP but UI displays "DO NOT FLIP"
    expected_banner_text = expected_overall.replace("_", " ")

    # Navigate to root
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle", timeout=30000)

    # Assertion #1 — tile is visible
    tile = page.locator('[data-testid="path-to-live-tile"]')
    expect(tile).to_be_visible(timeout=15000)

    # Assertion #2 — 6 PREFLIGHT rows with status-matched chip text
    for check in checks:
        check_name = check.get("check", "")
        check_status = check.get("status", "")
        chip_locator = page.locator(f'[data-testid="path-to-live-check-{check_name}"]')
        expect(chip_locator).to_be_visible(timeout=10000)
        chip_text = chip_locator.inner_text().strip()
        assert check_status in chip_text, (
            f"PREFLIGHT row '{check_name}': expected chip text to contain "
            f"'{check_status}', got: {chip_text!r}"
        )

    # Assertion #3 — 5 carry-in rows with state "open"
    carry_ins = ci_data.get("carry_ins", [])
    assert len(carry_ins) == 5, (
        f"Expected 5 carry-in items in /api/preflight/carry-ins, got {len(carry_ins)}"
    )
    for ci in carry_ins:
        ci_id = ci.get("id", "")
        ci_state = ci.get("state", "")
        assert ci_state == "open", (
            f"Carry-in '{ci_id}' expected state='open', got state={ci_state!r}"
        )
        row_locator = page.locator(f'[data-testid="path-to-live-carry-in-{ci_id}"]')
        expect(row_locator).to_be_visible(timeout=10000)

    # Assertion #4 — banner text matches overall
    banner = page.locator('[data-testid="path-to-live-banner"]')
    expect(banner).to_be_visible(timeout=10000)
    banner_text = banner.inner_text().strip()
    # Accept either underscored (DO_NOT_FLIP) or spaced (DO NOT FLIP) form
    normalised_banner = banner_text.replace("_", " ").upper()
    normalised_expected = expected_banner_text.upper()
    assert normalised_expected in normalised_banner, (
        f"Banner text mismatch: expected '{normalised_expected}' in "
        f"'{normalised_banner}'. /api/preflight/carry-ins.overall={expected_overall!r}"
    )


# ---------------------------------------------------------------------------
# Test B: endpoint shape (D-10-18 #5)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
def test_carry_ins_endpoint_shape():
    """D-10-18 assertion #5.

    GET /api/preflight/carry-ins returns 200, schema_version=1, and all
    required top-level keys including the joined live_readiness key (D-10-16).
    """
    data = _get_carry_ins()

    # schema_version
    assert data.get("schema_version") == 1, (
        f"schema_version expected 1, got {data.get('schema_version')!r}"
    )

    # Required top-level keys per D-10-04 (6 core + live_readiness from D-10-16)
    required_keys = {
        "schema_version",
        "evaluated_at",
        "overall",
        "carry_ins",
        "window",
        "preflight_summary",
        "live_readiness",
    }
    actual_keys = set(data.keys())
    missing_keys = required_keys - actual_keys
    assert not missing_keys, (
        f"GET /api/preflight/carry-ins response missing top-level keys: "
        f"{sorted(missing_keys)}. Got: {sorted(actual_keys)}"
    )

    # carry_ins is a list
    assert isinstance(data["carry_ins"], list), (
        f"carry_ins expected list, got {type(data['carry_ins'])}"
    )

    # window has required sub-keys
    window = data.get("window", {})
    for wk in ("elapsed_seconds", "required_seconds", "first_all_pass_at"):
        assert wk in window, f"window missing key '{wk}': {window}"


# ---------------------------------------------------------------------------
# Test C: DSR row schema after seed (D-10-18 #6)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
def test_dsr_row_schema_passes_after_seed(leaderboard_dsr_seeded):
    """D-10-18 assertion #6.

    After leaderboard_dsr_seeded arranges:
      - leaderboard row with dsr=0.97 at /data/tournament.db
      - MLGATE marker at /run/mlgate_auto_flip.json
      - trading-engine restarted with ENABLE_ML_PREDICTIONS=true

    /api/preflight/live-readiness must return a dsr_evidence check with:
      - status == "PASS"
      - detail containing the numeric "0.97"
      - detail containing today's ISO run_date (YYYY-MM-DD)
    """
    today_iso = date.today().isoformat()

    lr_data = _get_preflight_live_readiness()
    checks = lr_data.get("checks", [])

    dsr_check = next((c for c in checks if c.get("check") == "dsr_evidence"), None)
    assert dsr_check is not None, (
        f"dsr_evidence check not found in /api/preflight/live-readiness. "
        f"Checks present: {[c.get('check') for c in checks]}"
    )

    assert dsr_check.get("status") == "PASS", (
        f"dsr_evidence.status expected 'PASS', got {dsr_check.get('status')!r}. "
        f"detail: {dsr_check.get('detail')!r}"
    )

    detail = dsr_check.get("detail", "")
    assert "0.97" in detail, (
        f"dsr_evidence.detail expected to contain '0.97', got: {detail!r}"
    )
    assert today_iso in detail, (
        f"dsr_evidence.detail expected to contain today's run_date '{today_iso}', "
        f"got: {detail!r}"
    )


# ---------------------------------------------------------------------------
# Test D: 24h window fast-forward to READY (D-10-18 #7)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("bootstrap_stack")
def test_24h_window_reaches_ready_with_fast_forward(
    leaderboard_dsr_seeded, all_preflight_checks_passing
):
    """D-10-18 assertion #7.

    With:
      - PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1 (compose default + CI override)
      - leaderboard_dsr_seeded: ENABLE_ML_PREDICTIONS=true + dsr=0.97 row seeded
      - all_preflight_checks_passing: LIVE-mode env vars flipped on trading-engine
        (PAPER_TRADING_MODE=false, TRADING_MODE=LIVE, LIVE_TRADING_ACK, cap=2%)

    The second carry-ins poll (after >=2s) must return:
      - overall == "READY"
      - window.elapsed_seconds >= 1

    Silent skipping via pytest.mark.skipif is FORBIDDEN — assertion #7 is a
    MUST-cover assertion per D-10-18; if the fixture cannot satisfy the
    preconditions, the test MUST fail loudly to surface the contract gap.
    """
    # First poll: establishes _state.first_all_pass_at
    first = _get_carry_ins()
    first_overall = first.get("overall")
    # With PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1 the window is extremely short;
    # a single poll may already reach READY if all 6 checks are PASS.
    # We normalise: if already READY on first poll, elapsed_seconds check still validates.

    # Wait at least 2s to exceed the 1s required window
    time.sleep(2)

    # Second poll: window should have elapsed
    second = _get_carry_ins()

    overall = second.get("overall")
    window = second.get("window", {})
    elapsed = window.get("elapsed_seconds", 0)

    assert overall == "READY", (
        f"Expected overall=='READY' after 2s with PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1, "
        f"got overall={overall!r}. "
        f"window={window}. "
        f"First poll overall was {first_overall!r}. "
        "Check that all 6 PREFLIGHT checks are PASS under the LIVE-mode override and "
        "that PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1 is set on the api-gateway."
    )

    assert elapsed >= 1, (
        f"Expected window.elapsed_seconds >= 1 after 2s wait, got {elapsed}. "
        f"window={window}"
    )
