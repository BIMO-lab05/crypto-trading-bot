"""
Preflight LIVE Readiness package (PREFLIGHT-01).

Re-exports the public surface so callers can write:

    from app.preflight import run_all, CheckResult, PreflightReport

Mirrors the ``app.lifespan`` re-export shape (see
``services/trading-engine/app/lifespan/__init__.py``).

The bare-package import ``from app.preflight import`` is asserted by
Phase 8 grep gate #2 against ``services/trading-engine/app/main.py`` —
do NOT remove the re-exports without coordinating with that gate.
"""

from app.preflight.types import CheckResult, PreflightReport

# Check function re-exports are uncommented in Task 2 once checks.py lands.
# Keeping them commented here makes the Task 1 commit importable even though
# checks.py does not yet exist; coverage / static-analysis passes that import
# the package would otherwise hit ImportError on this commit.
# from app.preflight.checks import (  # noqa: F401 (re-export)
#     run_all,
#     check_cap,
#     check_paper_mode,
#     check_trading_mode,
#     check_ack,
#     check_emergency_stop,
#     check_dsr_evidence,
# )

__all__ = [
    # Re-exported in Task 2:
    # "run_all",
    # "check_cap",
    # "check_paper_mode",
    # "check_trading_mode",
    # "check_ack",
    # "check_emergency_stop",
    # "check_dsr_evidence",
    "CheckResult",
    "PreflightReport",
]
