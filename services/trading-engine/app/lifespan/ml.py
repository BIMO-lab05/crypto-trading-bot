"""ML/TA-layer lifespan phase: aggregator health, multi-timeframe, sqzmom, attribution.

Phase 9 MLGATE-02 adds ``auto_flip_ml_predictions()`` — the boot-time gate
that turns ``ENABLE_ML_PREDICTIONS`` on iff DSR evidence in the
``leaderboard`` table justifies it (per the extended ``check_dsr_evidence``
from Phase 8 + Phase 9 Plan 09-02 Task 1). The auto-flip runs at the start
of ``init_ml`` BEFORE the aggregator is constructed so the new env value
is read at aggregator-init time (per D-09-02-03).

Cross-plan wiring (D-09-02-06): after the marker JSON write, the auto-flip
calls ``set_current_reason()`` on Plan 09-03's ``app.aggregation.ml_gate_reasons``
module so every signal-aggregator emission site reads the truthful reason at
zero file-IO cost — closes checker Blocker 1.
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.aggregation.ml_gate_reasons import set_current_reason
from app.analytics import get_attribution_analyzer
from app.config import get_settings
from app.multi_timeframe import close_multi_timeframe_analyzer
from app.preflight import check_dsr_evidence
from app.preflight.checks import _MLGATE_MARKER_PATH
from app.signal_aggregator import close_aggregator, get_aggregator
from app.strategies import sqzmom_config, sqzmom_strategy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auto-flip reason vocabulary — INTENTIONALLY a 6-member superset of Plan
# 09-03's 5-member ``ML_GATE_REASONS``: adds ``"dsr_above_gate"`` for the
# ``direction=enabled`` outcome. The disabled-event vocab (the first 5
# members) is the one we forward to ``set_current_reason()``; the enabled
# direction does not propagate to that cache because Plan 09-03's
# ``log_ml_disabled()`` is by definition the disabled-event emission path.
# ---------------------------------------------------------------------------
_MLGATE_REASONS: tuple[str, ...] = (
    "no_evidence",
    "dsr_below_gate",
    "evidence_stale",
    "regime_shift",
    "manual_override",
    "dsr_above_gate",
)

# Reasons that propagate to Plan 09-03's `set_current_reason()` cache (the
# 5 disabled-event members — `dsr_above_gate` is the enabled direction and
# is intentionally NOT cached as a disabled-event reason).
_DISABLED_EVENT_REASONS: frozenset[str] = frozenset(
    {
        "no_evidence",
        "dsr_below_gate",
        "evidence_stale",
        "regime_shift",
        "manual_override",
    }
)

# Regex helpers for marker-JSON extraction from ``CheckResult.detail`` strings.
# The detail-string format is owned by ``check_dsr_evidence`` in
# ``app/preflight/checks.py``; if that format changes, update both regexes.
_DSR_VALUE_RE = re.compile(r"dsr=([0-9]+(?:\.[0-9]+)?)")
_RUN_DATE_RE = re.compile(r"run_date=([0-9T:+\-Z\.]+)")


def _extract_dsr_from_detail(detail: str) -> float | None:
    """Parse the ``dsr=<float>`` token from a CheckResult detail string.

    Returns None when the detail does not carry a dsr value (e.g. ML-disabled
    short-circuit, marker-absent UNKNOWN, sqlite-error UNKNOWN). The marker
    JSON schema declares this field as ``float | null`` so None is conformant.
    """
    if not detail:
        return None
    m = _DSR_VALUE_RE.search(detail)
    if m is None:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _extract_run_date_from_detail(detail: str) -> str | None:
    """Parse the ``run_date=<iso8601>`` token from a CheckResult detail string.

    Returns None when the detail does not carry a run_date (same conditions
    as ``_extract_dsr_from_detail``). The marker JSON schema declares this
    field as ``str | null`` so None is conformant.
    """
    if not detail:
        return None
    m = _RUN_DATE_RE.search(detail)
    if m is None:
        return None
    return m.group(1)


def auto_flip_ml_predictions(
    now: datetime | None = None,
    marker_path: str | None = None,
) -> dict:
    """Boot-time gate: flip ENABLE_ML_PREDICTIONS based on DSR evidence (MLGATE-02).

    Reads ``check_dsr_evidence(now=now)`` (Path A — single source of truth
    per D-09-02-01), maps the verdict to a 6-member reason enum, emits a
    structured log at ``logger.critical(...)`` BEFORE mutating env (per
    D-09-02-04 load-bearing ordering — the grep gate anchors on a stable
    log literal; mutating env first would open a window where the gate
    could pass against a no-op code path), then mutates
    ``os.environ["ENABLE_ML_PREDICTIONS"]`` + reloads settings + writes
    the marker JSON + calls ``set_current_reason()`` on Plan 09-03's
    cache (cross-plan wiring per D-09-02-06).

    All three "side-effect" steps after the log emission (env mutation,
    marker write, set_current_reason) are best-effort: a failure in any
    one MUST NOT crash trading-engine boot. The log line is the only
    load-bearing artifact.

    Args:
        now: injectable wall-clock for deterministic tests; defaults to
            ``datetime.now(timezone.utc)``.
        marker_path: override for the marker JSON path; defaults to
            ``_MLGATE_MARKER_PATH`` from app.preflight.checks.

    Returns:
        A dict ``{"direction": str, "reason": str}`` echoing the auto-flip
        outcome — useful for unit-test assertions; the production caller
        does not consume the return value.
    """
    result = check_dsr_evidence(now=now)

    # Map verdict -> (direction, reason). Order matters: the PASS-with-
    # "ML disabled" branch is the short-circuit at the very top of
    # check_dsr_evidence (ENABLE_ML_PREDICTIONS!=true) and means the
    # operator has the env var off; treat as manual_override so the cache
    # reflects the operator's choice, not a falsy "no_evidence" inference.
    if result.status == "PASS" and "ML disabled" in result.detail:
        direction, reason = "disabled", "manual_override"
    elif result.status == "PASS":
        direction, reason = "enabled", "dsr_above_gate"
    elif result.status == "FAIL" and "stale" in result.detail.lower():
        direction, reason = "disabled", "evidence_stale"
    elif result.status == "FAIL":
        direction, reason = "disabled", "dsr_below_gate"
    else:  # UNKNOWN (marker-absent / sqlite-error / empty leaderboard)
        direction, reason = "disabled", "no_evidence"

    # Internal contract — typo guard. Raises only on a programming error,
    # never on operator input or DB state, so it is allowed to propagate.
    assert reason in _MLGATE_REASONS, (
        f"internal contract violation: reason={reason!r} not in _MLGATE_REASONS"
    )

    # LOG FIRST (D-09-02-04). The literal substring
    # `"MLGATE_AUTO_FLIP direction="` must appear as one contiguous string
    # in this f-string so the CI grep gate at
    # `tests/integration/test_mlgate_grep_gates.py` can anchor on it.
    logger.critical(f"MLGATE_AUTO_FLIP direction={direction} reason={reason}")

    # THEN mutate env + reload settings so aggregator construction
    # downstream sees the new value (signal_aggregator.py:1125 and
    # aggregation/enhanced_aggregator.py:59 read settings.enable_ml_predictions
    # at INIT TIME).
    os.environ["ENABLE_ML_PREDICTIONS"] = "true" if direction == "enabled" else "false"
    try:
        from app.config import reload_settings

        reload_settings()
    except Exception as e:  # noqa: BLE001 — never crash boot on settings reload
        logger.warning(f"MLGATE settings reload failed: {type(e).__name__}")

    # Best-effort marker write — the marker is cross-process state for
    # Phase 10's DASHLIVE-01 tile; a read-only mount must NOT crash boot
    # (T-09-02-05).
    try:
        marker = Path(marker_path or _MLGATE_MARKER_PATH)
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "direction": direction,
            "reason": reason,
            "evaluated_at": (now or datetime.now(timezone.utc)).isoformat(),
            "dsr_value": _extract_dsr_from_detail(result.detail),
            "run_date": _extract_run_date_from_detail(result.detail),
        }
        marker.write_text(json.dumps(payload))
    except OSError as e:
        logger.warning(f"MLGATE marker write failed: {type(e).__name__}")

    # D-09-02-06 cross-plan reason-state propagation (closes checker Blocker 1):
    # cache the truthful reason in Plan 09-03's module so every signal-aggregator
    # emission site reads the live reason at zero file-IO cost. Best-effort —
    # if the cache update fails, trading-engine boot continues (the marker
    # JSON above is the durable source of truth).
    #
    # `set_current_reason` only accepts Plan 09-03's 5-member disabled-event
    # vocab. For the enabled direction (reason="dsr_above_gate"), we do NOT
    # propagate via this cache — Plan 09-03's `log_ml_disabled()` is by
    # definition the disabled-event emission path; when ML is enabled, no
    # disabled-event fires.
    if reason in _DISABLED_EVENT_REASONS:
        try:
            set_current_reason(reason)
        except Exception as e:  # noqa: BLE001 — best-effort cross-plan cache
            logger.warning(f"MLGATE set_current_reason failed: {type(e).__name__}")

    return {"direction": direction, "reason": reason}


@asynccontextmanager
async def init_ml():
    """TA aggregator health probe + attribution analyzer init.

    Phase 9 MLGATE-02: ``auto_flip_ml_predictions()`` runs at the very start
    BEFORE aggregator construction so the new env value is read at
    aggregator-init time (per D-09-02-03).

    On exit: close aggregator, multi-timeframe analyzer, sqzmom strategy.
    """
    logger.info("init_ml: enter")
    # Phase 9 MLGATE-02: auto-flip ENABLE_ML_PREDICTIONS based on DSR evidence
    # BEFORE constructing the aggregator (which reads settings.enable_ml_predictions
    # at __init__ time). The function is sync — call directly, no await.
    auto_flip_ml_predictions()
    # Refresh settings ref so paper_initial_balance below reads any value
    # the auto-flip's reload_settings() may have re-loaded from env.
    settings = get_settings()
    from app.main import ta_service_health  # deferred: avoid circular import

    try:
        aggregator = await get_aggregator()
        is_healthy = await aggregator.health_check()
        if is_healthy:
            logger.info("Technical Analysis Service connection verified")
            ta_service_health.set(1)
        else:
            logger.warning("Technical Analysis Service not available")
            ta_service_health.set(0)

        try:
            get_attribution_analyzer(initial_capital=settings.paper_initial_balance)
            logger.info("[OK] Attribution Analyzer initialized (Phase 5.1)")
            logger.info(f"     Initial capital: ${settings.paper_initial_balance:,.2f}")
        except Exception as e:
            logger.warning(f"[WARN] Failed to initialize Attribution Analyzer: {e}")

        logger.info("=" * 60)
        logger.info("SQZMOM Strategy Configuration:")
        logger.info(f"  Enabled symbols: {sqzmom_config.enabled_symbols}")
        logger.info(f"  Paper trading: {sqzmom_config.paper_trading}")
        logger.info(f"  Auto trading: {sqzmom_config.auto_trading}")
        logger.info(f"  Max positions: {sqzmom_config.max_positions}")
        logger.info("=" * 60)

        yield
    finally:
        try:
            await close_aggregator()
        except Exception as e:
            logger.error(f"Error closing aggregator: {e}")
        try:
            await close_multi_timeframe_analyzer()
        except Exception as e:
            logger.error(f"Error closing multi-timeframe analyzer: {e}")
        try:
            await sqzmom_strategy.close()
        except Exception as e:
            logger.error(f"Error closing sqzmom strategy: {e}")
        logger.info("init_ml: exit")
