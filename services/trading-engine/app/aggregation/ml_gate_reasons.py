"""
ML-Gate Reason Enum + In-Process Counter + Cross-Plan Reason-State Cache (MLGATE-03).

Single source of truth for the 5-member structured-reason enum emitted at every
`ENABLE_ML_PREDICTIONS=false` branch in the trading-engine signal-aggregation path
(see Phase 9 Plan 09-03 — `services/trading-engine/app/aggregation/enhanced_aggregator.py`
and `services/trading-engine/app/signal_aggregator.py`).

Reasons (D-09-03-02):
    no_evidence        -- ML never produced DSR>0.95 evidence yet (or evidence row missing)
    dsr_below_gate     -- DSR row present but score < 0.95 acceptance gate
    evidence_stale     -- DSR evidence row older than freshness window (auto-flip cause)
    regime_shift       -- Live regime no longer matches the regime the DSR row was scored on
    manual_override    -- Operator-set disable (default before any auto-flip fires)

Log-literal contract (D-09-03-03):
    Every emission MUST contain the contiguous substring
    "ML predictions disabled reason=<value>" — load-bearing for the CI grep gate at
    `tests/integration/test_mlgate_reason_grep_gate.py`. f-string composition where the
    f-string STARTS with that literal is fine; concatenation that splits the literal
    is forbidden.

Cross-plan reason-state contract (D-09-03-06):
    Plan 09-02's `auto_flip_ml_predictions()` IMPORTS `set_current_reason` from this
    module and calls it exactly once per auto-flip outcome. The signal-aggregator
    emission sites in this plan use `get_current_reason()` as the default-reason
    fallback for `log_ml_disabled()` — so per-cycle emissions reflect the truthful
    auto-flip outcome instead of a hardcoded `"manual_override"`. This closes
    checker Blocker 1 (the per-cycle log message now names the real cause).

Threading note:
    The module-level `_current_reason: str` is a plain attribute write. Python's GIL
    makes the single-attribute write atomic. No `threading.Lock` is required for the
    read-mostly access pattern (write once per auto-flip; read once per
    signal-aggregation cycle). If a future operator surfaces a race during hot
    reload, the lock is a one-line follow-up.

Stdlib-only by design — same constraint as `app.preflight` so this module can be
imported by both `app/lifespan/ml.py` (Plan 09-02) and the aggregator modules
without circular-import risk.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enum — five members exactly. NEVER add a sixth here; Plan 09-02's auto-flip
# event vocabulary is a SEPARATE local 6-member tuple that includes
# `"dsr_above_gate"` for the enabled direction (interfaces block in the plan
# documents the split). This module is for DISABLED-event emissions only.
# ---------------------------------------------------------------------------
MLGateReason = Literal[
    "no_evidence",
    "dsr_below_gate",
    "evidence_stale",
    "regime_shift",
    "manual_override",
]

ML_GATE_REASONS: tuple[str, ...] = (
    "no_evidence",
    "dsr_below_gate",
    "evidence_stale",
    "regime_shift",
    "manual_override",
)

# ---------------------------------------------------------------------------
# Module-level state
#   _counter        -- 24h running tally of disabled-event reasons, surfaced via
#                      `snapshot_reasons()` and consumed by the unauthenticated
#                      read-only handler `app/handlers/ml_gate_reasons.py`.
#   _current_reason -- Live truthful reason cache (D-09-03-06). Default before
#                      any auto-flip has fired is `"manual_override"` — matches
#                      operator semantics (ML is off because the operator chose
#                      to keep it off, until auto-flip determines otherwise).
# ---------------------------------------------------------------------------
_counter: Counter[str] = Counter()
_current_reason: str = "manual_override"


def set_current_reason(reason: MLGateReason) -> None:
    """Cache the live truthful reason for downstream emissions (D-09-03-06).

    Called by Plan 09-02's `auto_flip_ml_predictions()` after the auto-flip
    outcome is determined. The cached value is read by `log_ml_disabled()` as
    the default reason argument so per-cycle emissions reflect the auto-flip
    outcome rather than a hardcoded fallback.

    Raises:
        ValueError: if `reason` is not one of the five members of
            `ML_GATE_REASONS`.
    """
    if reason not in ML_GATE_REASONS:
        raise ValueError(f"unknown ML gate reason: {reason!r}")
    global _current_reason
    _current_reason = reason


def get_current_reason() -> MLGateReason:
    """Return the cached live reason; defaults to 'manual_override' before first auto-flip."""
    return _current_reason  # type: ignore[return-value]


def log_ml_disabled(
    reason: MLGateReason | None = None,
    *,
    detail: str = "",
) -> None:
    """Emit structured ML-disabled log + increment counter (MLGATE-03).

    When `reason` is None, uses `get_current_reason()` — i.e. the truthful
    reason cached by Plan 09-02's auto-flip outcome (D-09-03-06). Callers
    with a more specific local cause (e.g. test-only manual disables) may
    pass an explicit reason to override.

    The literal substring "ML predictions disabled reason=" appears at the
    start of the f-string and is load-bearing for the CI grep gate.

    Raises:
        ValueError: if the resolved reason is not one of the five members
            of `ML_GATE_REASONS`.
    """
    if reason is None:
        reason = get_current_reason()
    if reason not in ML_GATE_REASONS:
        raise ValueError(f"unknown ML gate reason: {reason!r}")
    # Literal substring "ML predictions disabled reason=" is load-bearing.
    logger.info(f"ML predictions disabled reason={reason} detail={detail}")
    _counter[reason] += 1


def record_ml_gate_event(reason: MLGateReason) -> None:
    """Lower-level counter increment for direct callers (Plan 09-02 lifespan, tests).

    Does NOT emit a log line — that's `log_ml_disabled()`'s job. Use this when
    you need to record an event in the counter without producing a per-cycle
    log emission (e.g. seeding test state).

    Raises:
        ValueError: if `reason` is not one of the five members of
            `ML_GATE_REASONS`.
    """
    if reason not in ML_GATE_REASONS:
        raise ValueError(f"unknown ML gate reason: {reason!r}")
    _counter[reason] += 1


def snapshot_reasons() -> dict[str, int]:
    """Return a COPY of the current reason counter.

    Safe to mutate the returned dict — internal state is not affected.
    Consumed by the unauthenticated read-only endpoint
    `GET /api/preflight/ml-gate-reason-counts` and by integration tests that
    assert counter contents without race-prone reads on the shared Counter.
    """
    return dict(_counter)


def reset_counter() -> None:
    """Testing helper: clear counter AND reset _current_reason to default.

    Resetting the cross-plan reason-state cache between tests is required so
    that one test's `set_current_reason("dsr_below_gate")` does not leak into
    a sibling test's default-fallback assertion.
    """
    global _current_reason
    _counter.clear()
    _current_reason = "manual_override"


__all__ = [
    "MLGateReason",
    "ML_GATE_REASONS",
    "log_ml_disabled",
    "record_ml_gate_event",
    "snapshot_reasons",
    "reset_counter",
    "set_current_reason",
    "get_current_reason",
]
