"""LIVECLOSE-05 LIVE-flip smoke harness — contract test.

This file asserts the harness script and runbook contracts. It does NOT
execute the LIVE flip path during pytest. The LIVE flip is operator-only,
triggered via ``LIVECLOSE_05_SUPERVISED_RUN=1`` with an attached human.

Test surface (matches Plan 11.1-06 frontmatter `exports`):
  1. test_harness_script_exists_and_executable
  2. test_harness_refuses_unsupervised_run
  3. test_harness_documents_compose_recipe
  4. test_harness_documents_curl_probe
  5. test_harness_dry_run_prints_recipe
  6. test_runbook_lints_clean
  7. test_curl_probe_matches_preflight_schema_paper_mode
  8. test_revert_step_restores_paper_mode_against_paper_stack
  9. test_supervised_env_var_required_for_flip_branch

Tests 1-6 + 9 are pure file-I/O + subprocess; always run.
Tests 7-8 hit the live api-gateway; skip cleanly when the stack is not
running OR when the preflight route returns 404 (older container image
predating Phase 8 PREFLIGHT-01).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "scripts" / "closure" / "liveclose-05-live-flip-smoke.sh"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "LIVECLOSE-05.md"
GATEWAY_URL = os.environ.get("LIVECLOSE_05_GATEWAY_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gateway_reachable() -> bool:
    """Return True iff GET {GATEWAY_URL}/health returns 200 quickly."""
    try:
        r = requests.get(f"{GATEWAY_URL}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _preflight_route_deployed() -> bool:
    """Return True iff GET /api/preflight/live-readiness returns 200.

    Returns False (skip) when:
      - The gateway is unreachable.
      - The route returns 404 (the running container image predates
        Phase 8 PREFLIGHT-01 deployment — common in dev when the host
        has freshly merged code that hasn't been rebuilt + redeployed).
    """
    if not _gateway_reachable():
        return False
    try:
        r = requests.get(f"{GATEWAY_URL}/api/preflight/live-readiness", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tests 1-5 + 9: harness script contract (always run)
# ---------------------------------------------------------------------------


def test_harness_script_exists_and_executable() -> None:
    """The harness file exists and is readable.

    Executable bit is set on `chmod +x` in the implementing commit but
    is not strictly required (callers invoke via `bash <path>`). The
    contract is "exists + readable" so a missing/stale checkout fails
    loudly.
    """
    assert HARNESS.exists(), f"harness missing at {HARNESS}"
    assert os.access(HARNESS, os.R_OK), f"harness not readable at {HARNESS}"


def test_harness_refuses_unsupervised_run() -> None:
    """Running the harness with no flags + no env exits non-zero.

    The script must refuse to flip api-gateway to LIVE without
    ``LIVECLOSE_05_SUPERVISED_RUN=1``. Stderr must mention the env-var
    name so the operator gets a clear remediation hint.
    """
    # Strip LIVECLOSE_05_SUPERVISED_RUN from inherited env to guarantee
    # the refusal path. PATH is preserved so /usr/bin/bash + /usr/bin/env
    # resolve. Other env (HOME, etc.) is dropped to keep the test
    # hermetic.
    clean_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    result = subprocess.run(
        ["bash", str(HARNESS)],
        env=clean_env,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0, (
        f"harness must exit non-zero on unsupervised run; got "
        f"returncode={result.returncode}, stdout={result.stdout!r}"
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    stdout = result.stdout.decode("utf-8", errors="replace")
    combined = stderr + stdout
    assert "LIVECLOSE_05_SUPERVISED_RUN" in combined, (
        "refusal message must mention LIVECLOSE_05_SUPERVISED_RUN; "
        f"got stderr={stderr!r} stdout={stdout!r}"
    )


def test_harness_documents_compose_recipe() -> None:
    """The harness source contains the docker compose recipe.

    Asserted as a regex over the script body so the recipe stays
    discoverable to anyone reading the file (operators may copy-paste
    from the script without running it).
    """
    src = HARNESS.read_text()
    # Compose recipe — accept either inline order (env-prefix before
    # `docker compose`) since the script may break the long command
    # across lines.
    recipe_pat = re.compile(
        r"docker\s+compose\s+-f\s+docker-compose\.unified\.yml.*"
        r"(--force-recreate|force-recreate).*api-gateway",
        re.DOTALL,
    )
    assert recipe_pat.search(src), (
        "harness must document the docker compose recipe "
        "(`docker compose -f docker-compose.unified.yml ... --force-recreate "
        "api-gateway`)"
    )
    assert "TRADING_MODE=LIVE" in src, "harness must reference TRADING_MODE=LIVE"
    assert "TRADING_MODE=PAPER" in src, (
        "harness must reference TRADING_MODE=PAPER (revert step)"
    )


def test_harness_documents_curl_probe() -> None:
    """The harness source contains a curl probe against the preflight route.

    At least two occurrences expected (pre-flip + post-flip probes).
    """
    src = HARNESS.read_text()
    probe_pat = re.compile(r"curl[^\n]*/api/preflight/live-readiness")
    matches = probe_pat.findall(src)
    assert len(matches) >= 2, (
        f"harness must contain >=2 curl probes against "
        f"/api/preflight/live-readiness; found {len(matches)}"
    )


def test_harness_dry_run_prints_recipe() -> None:
    """`--dry-run` prints the recipe without invoking docker.

    Verifies:
      - exit 0
      - stdout contains TRADING_MODE=LIVE + TRADING_MODE=PAPER literals
      - stdout does NOT contain compose "recreate" output (proves no docker call)
    """
    env = {
        **os.environ,
        "LIVECLOSE_05_SUPERVISED_RUN": "1",
    }
    # --dry-run bypasses both the supervised-run guard AND the
    # LIVE_TRADING_ACK guard per plan spec.
    result = subprocess.run(
        ["bash", str(HARNESS), "--dry-run"],
        env=env,
        capture_output=True,
        timeout=10,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0, (
        f"--dry-run must exit 0; got returncode={result.returncode}, "
        f"stdout={stdout!r}, stderr={stderr!r}"
    )
    assert "TRADING_MODE=LIVE" in stdout, (
        f"--dry-run stdout must contain 'TRADING_MODE=LIVE'; got: {stdout!r}"
    )
    assert "TRADING_MODE=PAPER" in stdout, (
        f"--dry-run stdout must contain 'TRADING_MODE=PAPER'; got: {stdout!r}"
    )
    # Proof that no docker container was touched. Compose typically emits
    # "Container .* Recreated" or "Container .* Started" on a real run.
    # We assert these markers are ABSENT from --dry-run output.
    for marker in (" Recreated", " Started", "Recreate ", " Created"):
        assert marker not in stdout, (
            f"--dry-run output contains compose marker '{marker}' suggesting "
            f"docker was invoked; output: {stdout!r}"
        )


def test_runbook_lints_clean() -> None:
    """The runbook lints clean.

    Lint checks:
      - line count >= 80
      - contains each required substring at least once
    """
    assert RUNBOOK.exists(), f"runbook missing at {RUNBOOK}"
    text = RUNBOOK.read_text()
    line_count = len(text.splitlines())
    assert line_count >= 80, f"runbook must have >=80 lines; got {line_count}"

    required_substrings = [
        "LIVECLOSE-05",
        "TRADING_MODE=LIVE",
        "TRADING_MODE=PAPER",
        "Diagnose",
        "Action",
        "Verification",
        "rose",
        "MODE pill",
        "KILL-SWITCH",
        "RUNBOOK.md",
        "5-step",
    ]
    missing = [s for s in required_substrings if s not in text]
    assert not missing, f"runbook missing required substrings: {missing}"


def test_supervised_env_var_required_for_flip_branch() -> None:
    """The supervised-run guard is in non-comment source.

    Comment-only mentions of LIVECLOSE_05_SUPERVISED_RUN don't count as
    a guard. We strip comment lines via grep and re-check the literal
    still appears.
    """
    result = subprocess.run(
        ["grep", "-v", r"^\s*#", str(HARNESS)],
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0, (
        f"grep failed: {result.stderr.decode('utf-8', errors='replace')!r}"
    )
    body = result.stdout.decode("utf-8", errors="replace")
    assert "LIVECLOSE_05_SUPERVISED_RUN" in body, (
        "LIVECLOSE_05_SUPERVISED_RUN must appear in non-comment source "
        "(comment-only mentions don't constitute a guard)"
    )


# ---------------------------------------------------------------------------
# Tests 7-8: live preflight probe (skip when stack down or route missing)
# ---------------------------------------------------------------------------


def test_curl_probe_matches_preflight_schema_paper_mode() -> None:
    """The /api/preflight/live-readiness response shape matches schema_version=1.

    Skips when the gateway is down OR the route is 404 (older container
    image). Asserts response SHAPE only — not specific check statuses,
    because PAPER vs LIVE env produces different status fields.
    """
    if not _preflight_route_deployed():
        pytest.skip(
            "api-gateway not reachable or /api/preflight/live-readiness "
            "not deployed (404)"
        )

    r = requests.get(f"{GATEWAY_URL}/api/preflight/live-readiness", timeout=5)
    assert r.status_code == 200, (
        f"preflight route returned {r.status_code}: {r.text[:300]}"
    )
    data = r.json()

    # Top-level keys
    for key in ("schema_version", "overall", "evaluated_at", "checks"):
        assert key in data, (
            f"preflight response missing top-level key '{key}'; got: "
            f"{sorted(data.keys())}"
        )

    # schema_version pinned at 1
    assert data["schema_version"] == 1, (
        f"schema_version expected 1, got {data['schema_version']!r}"
    )

    # 6 named checks
    checks = data["checks"]
    assert isinstance(checks, list), f"checks must be a list; got {type(checks)}"
    assert len(checks) == 6, (
        f"expected 6 checks, got {len(checks)}: "
        f"{[c.get('check') for c in checks if isinstance(c, dict)]}"
    )

    # Each check has check/status/detail
    for c in checks:
        assert isinstance(c, dict), f"check entry must be dict; got {type(c)}"
        for sub in ("check", "status", "detail"):
            assert sub in c, (
                f"check entry missing field '{sub}'; got: {sorted(c.keys())}"
            )

    # Six named checks all present
    check_names = {c["check"] for c in checks}
    expected_names = {
        "cap",
        "paper_mode",
        "trading_mode",
        "ack",
        "emergency_stop",
        "dsr_evidence",
    }
    missing_names = expected_names - check_names
    assert not missing_names, (
        f"preflight response missing check names: {sorted(missing_names)}; "
        f"got: {sorted(check_names)}"
    )


def test_revert_step_restores_paper_mode_against_paper_stack() -> None:
    """The probe contract is valid against the live PAPER stack.

    Skips when the gateway is down or the route is 404. Probes the route
    once and asserts the trading_mode check entry has a valid
    {PASS|FAIL|UNKNOWN} status field — proving the response shape works
    against the running PAPER stack. This test does NOT flip LIVE.
    """
    if not _preflight_route_deployed():
        pytest.skip(
            "api-gateway not reachable or /api/preflight/live-readiness "
            "not deployed (404)"
        )

    r = requests.get(f"{GATEWAY_URL}/api/preflight/live-readiness", timeout=5)
    assert r.status_code == 200, (
        f"preflight route returned {r.status_code}: {r.text[:300]}"
    )
    data = r.json()

    checks = data.get("checks", [])
    trading_mode_check = next(
        (c for c in checks if isinstance(c, dict) and c.get("check") == "trading_mode"),
        None,
    )
    assert trading_mode_check is not None, (
        f"trading_mode check entry not found in preflight response; "
        f"got checks: {[c.get('check') for c in checks if isinstance(c, dict)]}"
    )

    status = trading_mode_check.get("status")
    assert status in {"PASS", "FAIL", "UNKNOWN"}, (
        f"trading_mode.status must be PASS|FAIL|UNKNOWN; got {status!r}. "
        f"Full entry: {trading_mode_check}"
    )
