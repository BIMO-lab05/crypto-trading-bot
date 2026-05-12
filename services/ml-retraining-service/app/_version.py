"""Package metadata for ml-retraining-service.

Lives in a sub-module rather than `app/__init__.py` so the `app/` directory
remains a PEP 420 namespace package — that's required so the tournament-harness
image can merge `/app/app/` (tournament-harness) and `/opt/ml_retraining/app/`
(ml-retraining) under a single `app.*` namespace and resolve
`app.core.returns_metrics`, `app.sharpe_metrics`, `app.cpcv`, etc.

See: .planning/phases/04-tournament-significance-auto-pr/04-08-PLAN.md
and 04-UAT.md Test 6 for context. Re-introducing `app/__init__.py` here
would silently break the canonical-metric import chain inside the
tournament-harness container — the
`test_canonical_metrics_importable.py` regression test in
services/tournament-harness/tests/integration/ guards against that.
"""

from __future__ import annotations

__version__ = "1.0.0"
__service_name__ = "ml-retraining-service"
