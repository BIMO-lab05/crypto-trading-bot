"""
Confidence value guard.

Audit 2026-04-27 found the aggregator pipeline never validated confidence
inputs: NaN/inf/None/out-of-range values from ML/sentiment APIs could
silently bypass the trade-execution gate (NaN comparisons are always False,
None raised TypeError on `>=`). This module centralises the check.

Use `validate_confidence()` at every boundary where confidence enters the
pipeline from outside the voter (ML predictions, sentiment scores, cached
values from external services). Internal voter code should also call it
before publishing a value downstream.
"""
import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def validate_confidence(value, source: str = "unknown", default: float = 0.0) -> float:
    """
    Coerce a confidence value into a safe float in [0.0, 1.0].

    - None / non-numeric / NaN / inf  -> log WARNING, return `default`.
    - Numeric outside [0, 1]          -> log WARNING, clamp into range.
    - Numeric inside [0, 1]           -> return as-is.

    `source` is included in the warning so log audits can find the upstream.
    """
    if value is None:
        logger.warning("Confidence guard [%s]: got None; using default=%.3f", source, default)
        return default

    try:
        f = float(value)
    except (TypeError, ValueError):
        logger.warning(
            "Confidence guard [%s]: non-numeric %r (%s); using default=%.3f",
            source, value, type(value).__name__, default,
        )
        return default

    if math.isnan(f) or math.isinf(f):
        logger.warning("Confidence guard [%s]: NaN/inf; using default=%.3f", source, default)
        return default

    if f < 0.0:
        logger.warning("Confidence guard [%s]: %.3f < 0; clamping to 0.0", source, f)
        return 0.0
    if f > 1.0:
        logger.warning("Confidence guard [%s]: %.3f > 1; clamping to 1.0", source, f)
        return 1.0

    return f
