"""Phase 01-03 gap test: bootstrap.sh static structure verification.

Codifies the plan 01-03 verification gates as a pytest test suite.
No Docker required — pure text-grep on the script file.

Requirements covered:
  INFRA-02: provisions .env from template, no git clean -fdx
  D-11: EMERGENCY_STOP touched
  D-12: health probe loop with declare -A SERVICES
  D-13: fail-loud, leave stack up, NO auto-teardown
  CLAUDE.md gotcha: DOCKER_BUILDKIT=0 on WSL2
  CLAUDE.md gotcha: canonical docker-compose.unified.yml, not docker-compose.yml
  Security: no echo of BYBIT_API credentials
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = REPO_ROOT / "bootstrap.sh"


@pytest.fixture(scope="module")
def script_text():
    """Load bootstrap.sh content once for all tests."""
    assert BOOTSTRAP.exists(), f"bootstrap.sh not found at {BOOTSTRAP}"
    return BOOTSTRAP.read_text()


# ---------------------------------------------------------------------------
# INFRA-02: .env provisioning — cp -n (no-clobber), no git clean -fdx
# ---------------------------------------------------------------------------


def test_provisions_env_with_no_clobber_cp(script_text):
    """INFRA-02: .env must be provisioned via 'cp -n' (no-clobber) from .env.example."""
    assert "cp -n" in script_text, (
        "bootstrap.sh must use 'cp -n' (no-clobber) to provision .env from template"
    )


def test_references_env_example(script_text):
    """INFRA-02: template source must be .env.example."""
    assert ".env.example" in script_text, (
        "bootstrap.sh must reference .env.example as template source"
    )


def test_no_git_clean_fdx(script_text):
    """INFRA-02: 'git clean -fdx' destroys .env and must never appear in bootstrap.sh."""
    assert "git clean -fdx" not in script_text, (
        "bootstrap.sh must NOT contain 'git clean -fdx' — would destroy .env"
    )


# ---------------------------------------------------------------------------
# WSL2 gotcha: DOCKER_BUILDKIT=0
# ---------------------------------------------------------------------------


def test_sets_docker_buildkit_zero(script_text):
    """CLAUDE.md gotcha: BuildKit hangs on WSL2 — bootstrap must set DOCKER_BUILDKIT=0."""
    assert "DOCKER_BUILDKIT=0" in script_text, (
        "bootstrap.sh must export DOCKER_BUILDKIT=0 to prevent WSL2 build hangs"
    )


# ---------------------------------------------------------------------------
# Canonical compose file reference
# ---------------------------------------------------------------------------


def test_uses_canonical_compose_file(script_text):
    """CLAUDE.md: docker-compose.unified.yml is canonical; docker-compose.yml incomplete."""
    assert "docker-compose.unified.yml" in script_text, (
        "bootstrap.sh must reference docker-compose.unified.yml (canonical), not docker-compose.yml"
    )


def test_does_not_use_bare_compose_file(script_text):
    """bootstrap.sh must not invoke the incomplete docker-compose.yml directly."""
    import re

    # Look for `-f docker-compose.yml` pattern (but not docker-compose.unified.yml)
    bad_pattern = re.search(r"-f\s+docker-compose\.yml\b", script_text)
    assert bad_pattern is None, (
        "bootstrap.sh must not reference docker-compose.yml directly "
        "(incomplete — missing DBs). Use docker-compose.unified.yml"
    )


# ---------------------------------------------------------------------------
# D-11: EMERGENCY_STOP touched at bootstrap
# ---------------------------------------------------------------------------


def test_touches_emergency_stop(script_text):
    """D-11: bootstrap must touch EMERGENCY_STOP so auto-trader loop holds at STEP-0."""
    assert "touch" in script_text and "EMERGENCY_STOP" in script_text, (
        "bootstrap.sh must touch EMERGENCY_STOP (D-11)"
    )
    # More precise: touch command applied to EMERGENCY_STOP
    import re

    assert re.search(r"touch\s+.*EMERGENCY_STOP", script_text), (
        "bootstrap.sh must have 'touch ... EMERGENCY_STOP' command"
    )


# ---------------------------------------------------------------------------
# D-12: health probe with declare -A SERVICES dict
# ---------------------------------------------------------------------------


def test_has_declare_services_dict(script_text):
    """D-12: health probe must iterate a 'declare -A SERVICES' associative array."""
    assert "declare -A SERVICES" in script_text, (
        "bootstrap.sh must use 'declare -A SERVICES' for health probe service map"
    )


def test_health_probe_uses_curl(script_text):
    """D-12: health probe must use curl to hit /health endpoints."""
    assert "curl" in script_text and "/health" in script_text, (
        "bootstrap.sh must probe services via curl ... /health"
    )


# ---------------------------------------------------------------------------
# D-13: fail-loud, leave stack up on failure (no auto-teardown, no auto-retry)
# ---------------------------------------------------------------------------


def test_exits_nonzero_on_failure(script_text):
    """D-13: bootstrap must exit 1 when services are unhealthy."""
    assert "exit 1" in script_text, "bootstrap.sh must exit 1 when health probe fails"


def test_no_auto_teardown_on_failure(script_text):
    """D-13: NO auto-teardown — 'docker compose down' must not appear in failure path."""
    import re

    # Detect `docker compose down` NOT guarded by `if: always()` or similar
    # Simple check: if `down` appears outside a comment with teardown intent
    lines = script_text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Pattern: docker compose ... down (not in a comment, not prefixed with || true as cleanup)
        if re.search(r"docker\s+compose\s+.*\bdown\b", stripped):
            pytest.fail(
                f"bootstrap.sh must NOT call 'docker compose down' (D-13: leave stack up for triage). "
                f"Found: {stripped!r}"
            )


# ---------------------------------------------------------------------------
# Security: no echo of BYBIT_API credentials
# ---------------------------------------------------------------------------


def test_no_echo_of_bybit_api_key(script_text):
    """Security: bootstrap.sh must not echo BYBIT_API_KEY or BYBIT_API_SECRET."""
    import re

    bad = re.search(r"echo\s+.*BYBIT_API", script_text)
    assert bad is None, (
        "bootstrap.sh must not echo BYBIT_API_KEY or BYBIT_API_SECRET "
        "(GitHub auto-redacts, but still a bad practice; use printf)"
    )


# ---------------------------------------------------------------------------
# Script is executable
# ---------------------------------------------------------------------------


def test_bootstrap_script_is_executable():
    """INFRA-02: bootstrap.sh must be executable (chmod +x)."""
    import os

    assert os.access(BOOTSTRAP, os.X_OK), f"bootstrap.sh is not executable: {BOOTSTRAP}"
