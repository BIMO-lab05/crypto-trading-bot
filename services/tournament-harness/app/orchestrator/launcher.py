"""Docker SDK launcher (D-02) — sequential, single-image runner pattern (D-03, D-05).

The launcher is the only place that talks to the Docker socket. Bounded
parallelism (CD-04) is deferred — a `for exp in experiments` loop is the
v1 implementation.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.config.settings import get_settings
from app.config.tournament_loader import (
    ExperimentSpec,
    enumerate_experiments,
    load_tournament,
)
from app.leaderboard.db import LeaderboardDB, run_migrations
from app.orchestrator.ingest import ingest_run


logger = logging.getLogger(__name__)


def _git_sha() -> str:
    """git rev-parse HEAD — captured once at tournament start (D-13)."""
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd="/app").strip()
        return out.decode()
    except Exception as e:
        logger.warning("git_sha unavailable: %s", e)
        return "unknown"


def _git_is_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd="/app"
        ).strip()
        return bool(out)
    except Exception:
        return False


def _coerce_resource_caps(caps: Dict[str, Any]) -> Dict[str, Any]:
    """Translate YAML resource caps → Docker SDK kwargs (D-04)."""
    return {
        "mem_limit": caps.get("mem_limit", "4g"),
        "nano_cpus": int(float(caps.get("cpus", 2.0)) * 1_000_000_000),
    }


def _spec_to_runner_arg(spec: ExperimentSpec) -> str:
    """JSON-serialise the spec for the runner --spec-json arg."""
    return json.dumps(asdict(spec), default=str, separators=(",", ":"))


def launch_one_experiment(
    docker_client,
    spec: ExperimentSpec,
    settings,
    output_root: Path,
    env_extra: Dict[str, str],
) -> Dict[str, Any]:
    """Run ONE experiment to completion. Returns container state dict + stderr tail.

    Result.json read + DB insert is the caller's job (caller has the LeaderboardDB).
    """
    run_output = output_root / spec.tournament_id / spec.run_id
    run_output.mkdir(parents=True, exist_ok=True)

    caps = _coerce_resource_caps(spec.resource_caps)
    env = {
        "TIMESCALE_HOST": settings.timescale_host,
        "TIMESCALE_PORT": str(settings.timescale_port),
        "TIMESCALE_DB": settings.timescale_db,
        "TIMESCALE_USER": settings.timescale_user,
        "TIMESCALE_PASSWORD": settings.timescale_password,
        "PYTHONUNBUFFERED": "1",
        **env_extra,
    }

    container = None
    timed_out = False
    try:
        # T-03-24: read_only=True, cap_drop=ALL, no privileged, only the run's own /output bind.
        container = docker_client.containers.run(
            image=settings.runner_image,
            command=[
                "python",
                "-m",
                "app.runner",
                "--spec-json",
                _spec_to_runner_arg(spec),
            ],
            detach=True,
            mem_limit=caps["mem_limit"],
            nano_cpus=caps["nano_cpus"],
            network=settings.docker_network,
            environment=env,
            volumes={str(run_output): {"bind": "/output", "mode": "rw"}},
            labels={
                "tournament_id": spec.tournament_id,
                "run_id": spec.run_id,
                "architecture": spec.architecture,
                "symbol": spec.symbol,
            },
            read_only=True,
            cap_drop=["ALL"],
            tmpfs={"/tmp": "size=512m"},  # writable tmp inside read-only fs
        )
    except Exception:
        tb = traceback.format_exc()
        return {
            "state": {"ExitCode": -1, "OOMKilled": False, "TimedOut": False},
            "stderr_tail": tb[-4096:],
            "result_path": run_output / "result.json",
        }

    timeout = int(spec.resource_caps.get("wallclock_timeout_seconds", 1800))
    try:
        wait_result = container.wait(timeout=timeout)
        exit_code = int(wait_result.get("StatusCode", -1))
    except Exception as e:
        logger.warning("wait timed out for run %s: %s", spec.run_id, e)
        timed_out = True
        try:
            container.kill(signal="SIGTERM")
            time.sleep(10)
            container.reload()
            if container.status == "running":
                container.kill(signal="SIGKILL")
        except Exception:
            pass
        try:
            container.reload()
            exit_code = int(container.attrs.get("State", {}).get("ExitCode", -1) or -1)
        except Exception:
            exit_code = -1

    # Inspect for OOMKilled
    try:
        container.reload()
        state = container.attrs.get("State", {})
        oom = bool(state.get("OOMKilled", False))
    except Exception:
        oom = False

    # Capture stderr tail (4 KB) before removing the container
    stderr_tail = ""
    try:
        log_bytes = container.logs(stdout=False, stderr=True, tail=200)
        stderr_tail = (log_bytes or b"").decode(errors="replace")[-4096:]
        # Also dump full logs to the run dir for operator (CD-03)
        full_stdout = container.logs(stdout=True, stderr=False)
        full_stderr = container.logs(stdout=False, stderr=True)
        (run_output / "stdout.log").write_bytes(full_stdout or b"")
        (run_output / "stderr.log").write_bytes(full_stderr or b"")
    except Exception:
        pass

    # Tear down
    try:
        container.remove(force=True)
    except Exception:
        pass

    return {
        "state": {
            "ExitCode": exit_code,
            "OOMKilled": oom,
            "TimedOut": timed_out,
        },
        "stderr_tail": stderr_tail,
        "result_path": run_output / "result.json",
    }


def run_tournament(
    yaml_path: str | os.PathLike,
    *,
    allow_dirty: bool = False,
    docker_client=None,
) -> Dict[str, Any]:
    """End-to-end orchestrator: load YAML → launch all experiments → leaderboard ingest.

    Args:
        yaml_path: Path to operator's tournament.yaml.
        allow_dirty: if False (default), refuse to run on a dirty tree (D-13 / Integration Points).
        docker_client: optional pre-built docker.client.DockerClient (for testing).

    Returns:
        Summary dict with tournament_id, n_total, n_success, n_failed, leaderboard_path.
    """
    if not allow_dirty and _git_is_dirty():
        raise RuntimeError(
            "git tree is dirty — refusing to run a tournament with unrecorded changes. "
            "Commit or pass --allow-dirty if this is intentional (development override)."
        )

    spec = load_tournament(yaml_path)
    experiments = enumerate_experiments(spec)
    logger.info(
        "tournament %s: %d experiments enumerated", spec.tournament_id, len(experiments)
    )

    settings = get_settings()
    if settings.timescale_password in ("", "CHANGE_ME_VIA_ENV"):
        raise RuntimeError(
            "TIMESCALE_PASSWORD is unset or still the placeholder; "
            "follow RUNBOOK.md tournament-harness first-time setup before running."
        )

    if docker_client is None:
        import docker as docker_sdk

        docker_client = docker_sdk.from_env()

    db_path = Path(settings.leaderboard_db_path)
    run_migrations(db_path, Path("/app/migrations"))
    db = LeaderboardDB(db_path)
    db.upsert_tournament(spec.tournament_id, spec.config_yaml, _git_sha(), spec.seed)

    # Tournament-wide invariants captured once
    git_sha = _git_sha()
    tournament_start_ts = datetime.now(timezone.utc).isoformat()
    env_extra = {"GIT_SHA": git_sha, "TS_START": tournament_start_ts}

    n_success = 0
    n_failed = 0
    output_root = Path(settings.results_dir)

    for i, exp in enumerate(experiments, start=1):
        logger.info("[%d/%d] launching %s", i, len(experiments), exp.run_id)
        try:
            outcome = launch_one_experiment(
                docker_client=docker_client,
                spec=exp,
                settings=settings,
                output_root=output_root,
                env_extra=env_extra,
            )
            spec_dict = asdict(exp)
            spec_dict["git_sha"] = git_sha
            spec_dict["tournament_start_ts"] = tournament_start_ts
            reason = ingest_run(
                db=db,
                spec=spec_dict,
                container_state=outcome["state"],
                result_path=outcome["result_path"],
                stderr_tail=outcome["stderr_tail"],
            )
            if reason == "":
                n_success += 1
            else:
                n_failed += 1
            logger.info(
                "[%d/%d] %s → %s",
                i,
                len(experiments),
                exp.run_id,
                "success" if reason == "" else f"failed({reason})",
            )
            db.update_tournament_counts(
                spec.tournament_id,
                len(experiments),
                n_success,
                n_failed,
                completed=False,
            )
        except Exception:
            logger.exception("launcher fatal for run %s", exp.run_id)
            n_failed += 1

    db.update_tournament_counts(
        spec.tournament_id,
        len(experiments),
        n_success,
        n_failed,
        completed=True,
    )
    db.close()
    return {
        "tournament_id": spec.tournament_id,
        "n_total": len(experiments),
        "n_success": n_success,
        "n_failed": n_failed,
        "leaderboard_path": str(db_path),
    }


__all__ = ["launch_one_experiment", "run_tournament"]
