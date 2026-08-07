"""Host/CI test wiring for portfolio-manager.

`app.config.Settings` requires `initial_capital` (refuse-to-boot by design —
no capital default may exist in code; shared/account.py is the declaration
of record) and `settings = Settings()` runs at import time. In the container
compose supplies INITIAL_CAPITAL; on the host and in CI nothing does, so
test collection would die with ValidationError before a single test runs.
This mirrors compose's value for the test environment only.
"""

import os

os.environ.setdefault("INITIAL_CAPITAL", "100.0")
