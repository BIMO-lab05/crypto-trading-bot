"""Host/CI test wiring for portfolio-manager.

`app.config.Settings` requires `initial_capital` (refuse-to-boot by design —
no capital default may exist in code; shared/account.py is the declaration
of record) and `settings = Settings()` runs at import time. In the container
compose supplies INITIAL_CAPITAL; on the host and in CI nothing does, so
test collection would die with ValidationError before a single test runs.
This resolves the declared value from shared/account.py (repo root is two
levels up from this conftest) so the test environment can never drift from
the declaration of record; compose supplies the same value in-container.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

os.environ.setdefault("INITIAL_CAPITAL", str(ACCOUNT_EQUITY_USD))
