"""Phase 01-04 gap test: live-smoke.yml YAML structural verification.

Asserts the GitHub Actions workflow satisfies all plan 01-04 requirements:
  D-16: advisory only — no push/PR triggers; never blocks deterministic CI
  INFRA-03: nightly + manual dispatch triggers present
  Safety: BYBIT_TESTNET hardcoded 'true', PAPER_TRADING_MODE 'true', AUTO_TRADING_ENABLED 'false'
  Security: uses secrets refs, no echo of BYBIT_API_ credentials
  Operational: continue-on-error on probe, references docker-compose.unified.yml, down -v cleanup

No Docker, no network — pure YAML parsing.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_FILE = REPO_ROOT / ".github" / "workflows" / "live-smoke.yml"


@pytest.fixture(scope="module")
def workflow():
    """Load and parse live-smoke.yml once for all tests."""
    assert WORKFLOW_FILE.exists(), f"Workflow not found: {WORKFLOW_FILE}"
    import yaml

    text = WORKFLOW_FILE.read_text()
    parsed = yaml.safe_load(text)
    return parsed


@pytest.fixture(scope="module")
def workflow_text():
    """Raw text for grep-style checks."""
    assert WORKFLOW_FILE.exists(), f"Workflow not found: {WORKFLOW_FILE}"
    return WORKFLOW_FILE.read_text()


# ---------------------------------------------------------------------------
# D-16: MUST NOT have push or pull_request triggers
# ---------------------------------------------------------------------------


def test_no_push_trigger(workflow):
    """D-16: live-smoke must never fire on push — must not block deterministic CI."""
    # YAML 'on' key parses as Python True (boolean) in safe_load
    triggers = workflow.get("on", workflow.get(True, {})) or {}
    assert "push" not in triggers, (
        "live-smoke.yml must NOT have a 'push' trigger — "
        "it would block the deterministic CI lane (D-16)"
    )


def test_no_pull_request_trigger(workflow):
    """D-16: live-smoke must never fire on pull_request."""
    triggers = workflow.get("on", workflow.get(True, {})) or {}
    assert "pull_request" not in triggers, (
        "live-smoke.yml must NOT have a 'pull_request' trigger (D-16)"
    )


# ---------------------------------------------------------------------------
# INFRA-03: schedule (nightly) + workflow_dispatch triggers present
# ---------------------------------------------------------------------------


def test_has_schedule_trigger(workflow):
    """INFRA-03: nightly cron must be present."""
    triggers = workflow.get("on", workflow.get(True, {})) or {}
    assert "schedule" in triggers, (
        "live-smoke.yml must have a 'schedule' (cron) trigger for nightly run"
    )


def test_has_workflow_dispatch_trigger(workflow):
    """INFRA-03: manual dispatch must be present for on-demand runs."""
    triggers = workflow.get("on", workflow.get(True, {})) or {}
    assert "workflow_dispatch" in triggers, (
        "live-smoke.yml must have 'workflow_dispatch' for manual on-demand runs"
    )


# ---------------------------------------------------------------------------
# Advisory probe: continue-on-error on the probe step
# ---------------------------------------------------------------------------


def test_probe_step_has_continue_on_error(workflow):
    """D-16: probe failures must be advisory — probe step must have continue-on-error: true."""
    jobs = workflow.get("jobs", {})
    assert jobs, "live-smoke.yml has no jobs"

    found = False
    for job_name, job in jobs.items():
        for step in job.get("steps", []):
            if step.get("continue-on-error") is True:
                found = True
                break

    assert found, (
        "live-smoke.yml must have at least one step with 'continue-on-error: true' "
        "so probe failures are advisory (D-16, INFRA-03)"
    )


# ---------------------------------------------------------------------------
# Safety: hardcoded triple-belt trading guards
# ---------------------------------------------------------------------------


def test_bybit_testnet_hardcoded_true(workflow_text):
    """Safety: BYBIT_TESTNET must be hardcoded 'true' — not a variable."""
    assert "BYBIT_TESTNET: 'true'" in workflow_text, (
        "live-smoke.yml must hardcode BYBIT_TESTNET: 'true' "
        "(triple-belt safety: testnet URL + paper mode + auto-trade off)"
    )


def test_paper_trading_mode_hardcoded_true(workflow_text):
    """Safety: PAPER_TRADING_MODE must be hardcoded 'true'."""
    assert (
        "PAPER_TRADING_MODE: 'true'" in workflow_text
        or "PAPER_TRADING_MODE=true" in workflow_text
    ), "live-smoke.yml must hardcode PAPER_TRADING_MODE: 'true'"


def test_auto_trading_enabled_hardcoded_false(workflow_text):
    """Safety: AUTO_TRADING_ENABLED must be hardcoded 'false'."""
    assert (
        "AUTO_TRADING_ENABLED: 'false'" in workflow_text
        or "AUTO_TRADING_ENABLED=false" in workflow_text
        or "AUTO_TRADING_ENABLED: false" in workflow_text
    ), "live-smoke.yml must hardcode AUTO_TRADING_ENABLED: 'false'"


# ---------------------------------------------------------------------------
# Security: uses secrets refs, not plaintext credentials
# ---------------------------------------------------------------------------


def test_uses_secrets_bybit_api_key(workflow_text):
    """Security: BYBIT_API_KEY must reference ${{ secrets.BYBIT_API_KEY }}."""
    assert "secrets.BYBIT_API_KEY" in workflow_text, (
        "live-smoke.yml must use ${{ secrets.BYBIT_API_KEY }}, not a hardcoded value"
    )


def test_uses_secrets_bybit_api_secret(workflow_text):
    """Security: BYBIT_API_SECRET must reference ${{ secrets.BYBIT_API_SECRET }}."""
    assert "secrets.BYBIT_API_SECRET" in workflow_text, (
        "live-smoke.yml must use ${{ secrets.BYBIT_API_SECRET }}, not a hardcoded value"
    )


def test_no_echo_of_bybit_api_credentials(workflow_text):
    """Security: credentials must not be echoed in workflow (use printf instead)."""
    import re

    bad = re.search(r"echo\s+.*BYBIT_API", workflow_text)
    assert bad is None, (
        "live-smoke.yml must not echo BYBIT_API_KEY or BYBIT_API_SECRET directly; "
        "use printf to write to .env (plan 01-04 security gate)"
    )


# ---------------------------------------------------------------------------
# Operational: canonical compose file + down -v cleanup
# ---------------------------------------------------------------------------


def test_references_canonical_compose_file(workflow_text):
    """CLAUDE.md: docker-compose.unified.yml is canonical."""
    assert "docker-compose.unified.yml" in workflow_text, (
        "live-smoke.yml must reference docker-compose.unified.yml (canonical compose)"
    )


def test_cleanup_step_calls_down_v(workflow_text):
    """Operational: cleanup step must call 'down -v' to remove volumes between runs."""
    assert "down -v" in workflow_text, (
        "live-smoke.yml must call 'docker compose ... down -v' in cleanup step "
        "to remove volumes between nightly runs"
    )


# ---------------------------------------------------------------------------
# MARKET_DATA_SOURCE=live in the boot step
# ---------------------------------------------------------------------------


def test_boots_in_live_market_data_mode(workflow_text):
    """INFRA-03: live-smoke boots with MARKET_DATA_SOURCE=live (hits real Bybit)."""
    assert "MARKET_DATA_SOURCE" in workflow_text and "live" in workflow_text, (
        "live-smoke.yml must set MARKET_DATA_SOURCE=live in the boot step"
    )
