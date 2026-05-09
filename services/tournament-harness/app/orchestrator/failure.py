"""Container-state → D-15 failure_reason enum classifier.

Three possible outcomes:
  - "success"     — container exit 0 + result.json with status="success"
  - <D-15 enum>   — typed failure
  - "unknown"     — defensive last bucket

D-15 enum: oom_killed, nan_loss, timeout, exit_nonzero, train_diverged,
db_unreachable, unknown. The runner writes typed reasons (nan_loss,
db_unreachable, train_diverged) into result.json itself; the orchestrator
infers (oom_killed, timeout, exit_nonzero) from container state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple


logger = logging.getLogger(__name__)


VALID_FAILURE_REASONS = {
    "oom_killed",
    "nan_loss",
    "timeout",
    "exit_nonzero",
    "train_diverged",
    "db_unreachable",
    "unknown",
}


def classify(
    container_state: Dict[str, Any],
    result_payload: Optional[Dict[str, Any]],
    validation_error: Optional[str],
) -> Tuple[str, str]:
    """Map (container_state, result_payload, validation_error) → (status, failure_reason).

    Args:
        container_state: dict with at minimum keys {ExitCode, OOMKilled, TimedOut}.
            'TimedOut' is set to True by the launcher when container.wait raised
            the timeout exception (Docker doesn't surface it in inspect by default).
        result_payload: parsed JSON dict from /output/result.json, or None if missing.
        validation_error: stringified ValueError from result_schema.validate, or None
            when validation succeeded.

    Returns:
        (status, failure_reason) where:
          - status ∈ {"success", "failed"}
          - failure_reason is None on success, else a member of VALID_FAILURE_REASONS.
    """
    exit_code = int(container_state.get("ExitCode", -1) or 0)
    oom_killed = bool(container_state.get("OOMKilled", False))
    timed_out = bool(container_state.get("TimedOut", False))

    # 1. Timeout (orchestrator-side observable wins — see T-03-27)
    if timed_out:
        return ("failed", "timeout")

    # 2. OOM-killed (exit code 137 = SIGKILL from cgroup OOM, or inspect.State.OOMKilled)
    if oom_killed or exit_code == 137:
        return ("failed", "oom_killed")

    # 3. Result.json present and parses
    if result_payload is not None and validation_error is None:
        status = result_payload.get("status")
        if status == "success":
            return ("success", "")
        if status == "failed":
            reason = (
                result_payload.get("reason")
                or result_payload.get("failure_reason")
                or "unknown"
            )
            if reason in VALID_FAILURE_REASONS:
                return ("failed", reason)
            return ("failed", "unknown")

    # 4. Validation error against an existing result.json — runner emitted bad shape
    if validation_error is not None:
        logger.warning("result.json failed schema validation: %s", validation_error)
        # If container also exited non-zero, blame the exit; else "unknown"
        if exit_code != 0:
            return ("failed", "exit_nonzero")
        return ("failed", "unknown")

    # 5. No result.json at all
    if exit_code != 0:
        return ("failed", "exit_nonzero")

    # 6. exit 0 but no result.json — defensive
    return ("failed", "unknown")
