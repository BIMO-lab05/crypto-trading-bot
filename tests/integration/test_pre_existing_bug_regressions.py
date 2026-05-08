"""
Phase 2 INFRA-06 integration regressions for the 3 named pre-existing bugs.

Bug 1 (stale ML model):
    Touch model file mtime inside the running container, hit prediction
    endpoint, assert the MODEL_RELOAD: path= log line appears in
    ml-prediction-service logs (proves _reload_if_stale() fired in gru_predictor.py).
    Container name + model path are resolved from docker-compose.unified.yml at
    test time (Blocker #4) — the test does NOT hardcode against an unverified
    assumption.  Because ml-prediction has `profiles: [ml]` in compose, this
    test brings it up with --profile ml if it isn't already healthy.

Bug 2 (confidence=0 signals):
    Integration coverage is implicit via
    tests/integration/test_fresh_clone_round_trip.py (Plan 02-04).  If
    confidence=0 signals leaked to the aggregator in the round-trip's
    deterministic tape-mode run, the resulting signal distribution would shift.
    Unit-level regression is in
    services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py.

Bug 3 (WSL2 BuildKit hang):
    No integration test is possible — the hang is environmental.  Documented in
    RUNBOOK.md § BuildKit hang; ergonomic shortcut via `make build-no-buildkit`.
"""

import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx
import pytest


# ---------------------------------------------------------------------------
# Compose-resolution helpers (Blocker #4 — resolved at test time, not
# hardcoded; if docker-compose.unified.yml changes the block the test adapts).
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Walk up from this file to the git repo root."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    raise RuntimeError("Cannot find git repo root from test file")


def _resolve_compose_value(service_block: str, pattern: str) -> Optional[str]:
    """
    Read docker-compose.unified.yml; extract a field from the named service block.

    Scans from the ``^  <service>:`` line to the next sibling-level service
    header, then applies *pattern* (with one capture group) within that block.
    Returns the captured group or None if not found.
    """
    repo_root = _repo_root()
    compose_path = repo_root / "docker-compose.unified.yml"
    if not compose_path.exists():
        return None
    compose = compose_path.read_text()
    m = re.search(
        rf"^  {re.escape(service_block)}:\n(.*?)(?=\n  [a-z][a-z0-9-]*:)",
        compose,
        re.DOTALL | re.MULTILINE,
    )
    if not m:
        return None
    block = m.group(1)
    found = re.search(pattern, block)
    return found.group(1).strip() if found else None


def _resolve_ml_container_name() -> str:
    """
    Resolve the container_name for the ml-prediction service from compose.

    Fails the test loudly if the value cannot be found — a missing/renamed
    container_name in compose is itself a configuration error worth surfacing.
    """
    name = _resolve_compose_value("ml-prediction", r"container_name:\s*(\S+)")
    if not name:
        pytest.fail(
            "Could not resolve ml-prediction container_name from "
            "docker-compose.unified.yml.  Verify the service block still "
            "exists and has a container_name: field."
        )
    return name


def _resolve_first_model_file_inside_container() -> str:
    """
    Find the first .keras/.h5/.pkl model file in the host-side models dir and
    return its path as it appears inside the container (/app/models/<filename>).

    The volume mount is ./services/ml-prediction-service/models:/app/models per
    docker-compose.unified.yml.  All files in that dir are accessible inside the
    container at /app/models/.
    """
    repo_root = _repo_root()
    host_dir = repo_root / "services" / "ml-prediction-service" / "models"
    candidates = sorted(
        list(host_dir.glob("*.keras"))
        + list(host_dir.glob("*.h5"))
        + list(host_dir.glob("*.pkl"))
    )
    if not candidates:
        pytest.fail(
            f"No model files found in {host_dir}.  Train a model first "
            "(scripts/train_ml.*) or adjust the glob patterns in the test."
        )
    return f"/app/models/{candidates[0].name}"


# ---------------------------------------------------------------------------
# ml-prediction service lifecycle (profile-gated in compose)
# ---------------------------------------------------------------------------


def _ml_prediction_url() -> str:
    """Return the ml-prediction service base URL (default: http://localhost:8007)."""
    import os

    return os.getenv("ML_PREDICTION_URL", "http://localhost:8007")


def _is_ml_prediction_healthy(timeout: float = 3.0) -> bool:
    """Return True if ml-prediction /health returns 200."""
    try:
        r = httpx.get(f"{_ml_prediction_url()}/health", timeout=timeout)
        return r.status_code == 200
    except httpx.RequestError:
        return False


def _ensure_ml_prediction_running(compose_file: str) -> None:
    """
    Bring ml-prediction up with --profile ml if it is not already healthy.

    ml-prediction has `profiles: [ml]` in docker-compose.unified.yml so it is
    NOT started by the default `docker compose up -d` (no profile flag).  This
    function starts it on-demand so the regression test can run without requiring
    the full bootstrap to be re-executed with a profile flag.
    """
    if _is_ml_prediction_healthy():
        return  # already up

    repo_root = _repo_root()
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            compose_file,
            "--profile",
            "ml",
            "up",
            "-d",
            "ml-prediction",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    # Wait up to 90 s for the service to become healthy (model loading takes ~30 s).
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        if _is_ml_prediction_healthy():
            return
        time.sleep(2.0)

    pytest.fail(
        "ml-prediction service did not become healthy within 90 s after "
        "`docker compose --profile ml up -d ml-prediction`.  Check "
        "`docker compose logs ml-prediction` for startup errors."
    )


# ---------------------------------------------------------------------------
# Bug 1 integration regression
# ---------------------------------------------------------------------------


def test_stale_ml_model_reload():
    """
    Bug 1 regression (INFRA-06): touching the model file mtime inside the
    running ml-prediction container causes gru_predictor._reload_if_stale()
    to reload the model and emit a MODEL_RELOAD: path= log line.

    Container name + model path are resolved from docker-compose.unified.yml at
    run time (Blocker #4) — no hardcoded container name.

    Flow:
      1. Ensure ml-prediction is running (start with --profile ml if needed).
      2. Resolve container_name and an in-container model file path from compose.
      3. Touch the model file inside the container (bumps mtime without changing
         content — simulates what ml-retraining-service does after a successful
         retrain).
      4. Hit the prediction endpoint twice (the first call after the mtime change
         triggers _reload_if_stale()).
      5. Assert the MODEL_RELOAD: path= line appears in the container logs.
    """
    repo_root = _repo_root()
    compose_file = str(repo_root / "docker-compose.unified.yml")

    # Step 1: ensure the service is running.
    _ensure_ml_prediction_running(compose_file)

    # Step 2: resolve compose values at runtime (Blocker #4).
    container = _resolve_ml_container_name()
    model_path_inside_container = _resolve_first_model_file_inside_container()

    # Step 3: touch the model file inside the container to bump mtime.
    touch_result = subprocess.run(
        ["docker", "exec", container, "touch", model_path_inside_container],
        capture_output=True,
        text=True,
    )
    if touch_result.returncode != 0:
        pytest.fail(
            f"Could not touch {model_path_inside_container} inside "
            f"container {container!r}: stderr={touch_result.stderr!r}.  "
            "Verify the container is running and the model path is correct."
        )

    # Step 4: hit the prediction endpoint to trigger _reload_if_stale().
    # Use any symbol — SOLUSDT is reliable (model exists in models/).
    url = f"{_ml_prediction_url()}/api/v1/predictions/SOLUSDT"
    try:
        r1 = httpx.get(url, timeout=30.0)
        assert r1.status_code == 200, (
            f"Prediction endpoint returned {r1.status_code}: {r1.text}"
        )
        # A second call ensures the reload path is exercised even if the first
        # call pre-empted the mtime check.
        r2 = httpx.get(url, timeout=30.0)
        assert r2.status_code == 200
    except httpx.RequestError as exc:
        pytest.fail(
            f"Could not reach ml-prediction at {url}: {exc}.  Is the service running?"
        )

    # Step 5: check container logs for the MODEL_RELOAD log line.
    logs_result = subprocess.run(
        ["docker", "logs", "--tail", "200", container],
        capture_output=True,
        text=True,
    )
    combined_logs = logs_result.stdout + logs_result.stderr
    assert "MODEL_RELOAD: path=" in combined_logs, (
        f"Expected MODEL_RELOAD: path= log line in {container!r} logs after "
        "touching the model file.  Last 200 lines follow:\n" + combined_logs
    )
