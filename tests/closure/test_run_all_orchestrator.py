"""Tests for scripts/closure/run-all.sh — Phase 11.1 Plan 07 Wave-3 orchestrator.

The orchestrator is a discovery + status entrypoint for the five LIVECLOSE
carry-in closure harnesses. It is read-mostly: `--list` (default) and
`--status` print harness metadata; `--exec <ID>` invokes ONE named
harness with a whitelist of LIVECLOSE-01..04 (LIVECLOSE-05 is refused —
operator-supervised only).

All tests are subprocess-driven against `scripts/closure/run-all.sh` —
no docker, no network. The `--exec LIVECLOSE-01` test exercises the
LIVECLOSE-01 harness's dry-run env var (LIVECLOSE_01_DRY_RUN=1), so no
docker / git clone fires.

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-07-PLAN.md
Harness: scripts/closure/run-all.sh
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution — repo root is two parents above this file.
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]
_ORCHESTRATOR = _REPO / "scripts" / "closure" / "run-all.sh"

# Five carry-in IDs the orchestrator MUST list.
_IDS = [f"LIVECLOSE-0{n}" for n in range(1, 6)]

# Tests are bash-driven; skip on Windows native shells.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="run-all.sh is a bash script; Windows native shells skip.",
)


def _run(
    *args: str,
    env_overrides: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Invoke the orchestrator with a minimal, deterministic env."""
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        # Default to a clean env — tests that need TRADING_MODE / LIVECLOSE_*
        # set it explicitly via env_overrides.
    }
    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        ["bash", str(_ORCHESTRATOR), *args],
        cwd=str(cwd or _REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# ---------------------------------------------------------------------------
# Pre-flight: orchestrator file exists and is syntactically valid bash.
# ---------------------------------------------------------------------------


def test_run_all_script_exists() -> None:
    """The orchestrator script must exist and be executable bash."""
    assert _ORCHESTRATOR.exists(), f"orchestrator not found at {_ORCHESTRATOR}"
    # bash -n parses without executing; catches syntax errors early.
    result = subprocess.run(
        ["bash", "-n", str(_ORCHESTRATOR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"bash syntax check failed for {_ORCHESTRATOR}:\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Orchestrator contract tests
# ---------------------------------------------------------------------------


def test_run_all_help_prints_usage() -> None:
    """`--help` exits 0 and prints all four flag names."""
    result = _run("--help")
    assert result.returncode == 0, (
        f"--help should exit 0, got {result.returncode}; stderr={result.stderr!r}"
    )
    for flag in ("--list", "--status", "--help", "--exec"):
        assert flag in result.stdout, (
            f"--help output missing flag '{flag}' in usage; stdout={result.stdout!r}"
        )


def test_run_all_lists_five_harnesses() -> None:
    """Default invocation (no flags) discovers all five carry-ins.

    Must contain all five LIVECLOSE-0X identifiers, all five harness
    command literals, and a pointer at LIVECLOSE-INDEX.md.
    """
    result = _run()
    assert result.returncode == 0, (
        f"default invocation should exit 0, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )

    # All five IDs.
    for liveclose_id in _IDS:
        assert liveclose_id in result.stdout, (
            f"stdout missing carry-in ID '{liveclose_id}': {result.stdout!r}"
        )

    # All five harness command tokens (use the most-stable token for each).
    for token in (
        "liveclose-01-fresh-clone.sh",
        "liveclose-02-record-ci.sh",
        "scripts.closure.liveclose_03_psr_evidence",
        "scripts.closure.liveclose_04_sweep_verdict",
        "liveclose-05-live-flip-smoke.sh",
    ):
        assert token in result.stdout, (
            f"stdout missing harness token '{token}': {result.stdout!r}"
        )

    # Footer references the INDEX.
    assert "LIVECLOSE-INDEX.md" in result.stdout, (
        f"stdout missing LIVECLOSE-INDEX.md footer reference: {result.stdout!r}"
    )


def test_run_all_refuses_liveclose_05_without_supervised_env() -> None:
    """`--exec LIVECLOSE-05` MUST refuse without LIVECLOSE_05_SUPERVISED_RUN.

    The orchestrator must NEVER auto-flip TRADING_MODE=LIVE. Per the
    threat model (T-11.1-07-01), the refusal is a security boundary.
    """
    result = _run("--exec", "LIVECLOSE-05")
    assert result.returncode != 0, (
        f"--exec LIVECLOSE-05 should exit non-zero without supervised env, "
        f"got {result.returncode}; stdout={result.stdout!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "operator-supervised" in combined or "LIVECLOSE_05_SUPERVISED_RUN" in combined
    ), (
        f"refusal message missing 'operator-supervised' or "
        f"'LIVECLOSE_05_SUPERVISED_RUN' marker: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


def test_run_all_accepts_known_liveclose_id() -> None:
    """`--exec LIVECLOSE-01` with LIVECLOSE_01_DRY_RUN=1 exits 0.

    Plan 02's LIVECLOSE-01 harness supports LIVECLOSE_01_DRY_RUN=1 — the
    orchestrator must pass the env var through and the child harness must
    print the dry-run stdout contract.
    """
    result = _run(
        "--exec",
        "LIVECLOSE-01",
        env_overrides={"LIVECLOSE_01_DRY_RUN": "1"},
    )
    assert result.returncode == 0, (
        f"--exec LIVECLOSE-01 with LIVECLOSE_01_DRY_RUN=1 should exit 0, "
        f"got {result.returncode}; stderr={result.stderr!r}; stdout={result.stdout!r}"
    )
    # First line of the LIVECLOSE-01 dry-run stdout contract:
    assert "LIVECLOSE-01 fresh-clone harness starting" in result.stdout, (
        f"orchestrator did not pipe through LIVECLOSE-01 dry-run stdout; "
        f"stdout={result.stdout!r}"
    )


def test_run_all_rejects_unknown_id() -> None:
    """`--exec LIVECLOSE-99` MUST exit non-zero with a clear error."""
    result = _run("--exec", "LIVECLOSE-99")
    assert result.returncode != 0, (
        f"--exec LIVECLOSE-99 should exit non-zero, got {result.returncode}"
    )
    combined = result.stdout + result.stderr
    assert (
        "unknown" in combined.lower()
        or "invalid" in combined.lower()
        or "LIVECLOSE-99" in combined
    ), (
        f"rejection message missing 'unknown'/'invalid'/'LIVECLOSE-99' marker: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_run_all_state_lookup_handles_missing_carry_ins_json(tmp_path: Path) -> None:
    """When `.planning/state/carry_ins.json` is absent, state is 'unknown'.

    Operator may run the orchestrator before Phase 10 DASHLIVE-02 lands
    the state file, or after a fresh clone before the operator commits it.
    Either way, the orchestrator must print `unknown` rather than crashing.
    """
    # Stage a minimal repo skeleton: the orchestrator + its parent
    # directories, plus an empty .planning/ tree WITHOUT carry_ins.json.
    skel_scripts_closure = tmp_path / "scripts" / "closure"
    skel_scripts_closure.mkdir(parents=True)
    skel_planning_evidence = tmp_path / ".planning" / "evidence"
    skel_planning_evidence.mkdir(parents=True)
    # Symlink the orchestrator into the skeleton so we exercise the
    # actual script under the missing-state-file condition.
    skel_orchestrator = skel_scripts_closure / "run-all.sh"
    skel_orchestrator.symlink_to(_ORCHESTRATOR)

    result = _run(cwd=tmp_path)
    assert result.returncode == 0, (
        f"orchestrator should exit 0 even with missing carry_ins.json, "
        f"got {result.returncode}; stderr={result.stderr!r}"
    )
    assert "unknown" in result.stdout.lower(), (
        f"orchestrator stdout should report 'unknown' state when "
        f"carry_ins.json is absent; stdout={result.stdout!r}"
    )
