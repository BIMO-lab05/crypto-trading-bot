"""BC-05 default-port RED test — sibling file to test_config.py.

Cross-references:
- BC-05 in `.planning/REQUIREMENTS.md`
- D-09 in `.planning/phases/13-bybit-connector-market-data-centralization/13-CONTEXT.md`
  ("Fix services/market-data-service/app/config.py:58 default bybit_connector_url=
  'http://localhost:8002' → 'http://localhost:8001'.")
- 13-PATTERNS.md §"BC-05 test assertion — WARNING: host file is wholesale-skipped"
  (Critical Warning #1).

WHY THIS FILE EXISTS (PATTERNS.md Critical Warning #1):
`services/market-data-service/tests/test_config.py:15` carries a module-level
`pytestmark = pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")`
which wholesale-skips every test in that file. Adding the BC-05 assertion there
would silently no-op — the most likely false-pass point in this phase. This
sibling file has NO module-level skip mark, so its tests actually run.

STATE ON `main` (RED-by-design):
- Test 1 (`test_bybit_connector_url_default_is_8001`): FAILS because the current
  default at `services/market-data-service/app/config.py:58` is the defect value
  `"http://localhost:8002"` (a copy-paste of the service's own port). The fix in
  Plan 06 Task 3 changes it to `"http://localhost:8001"` (bybit-connector's port);
  test goes GREEN immediately after.
- Test 2 (`test_service_port_default_is_8002`): ALWAYS GREEN. Guards against
  accidental regression of the service's own port during the BC-05 fix.

This test imports `Settings` from `app.config` directly — same pattern as the
existing wholesale-skipped `test_config.py`. The plan note flags that this may
need to run inside `crypto-bot-market-data` if host Pydantic v1/v2 differences
bite; the test imports `app.config` lazily inside each test function so the file
loads (and pytest collects it) even when the import would fail on host.
"""

from __future__ import annotations

import pytest

# NOTE: NO module-level `pytestmark = pytest.mark.skip` here — that wholesale-skip
# is the trap on the sibling `test_config.py:15`. Removing it (or doing the BC-05
# work in that file) would require unskipping ~10 unrelated broken tests; this
# sibling file isolates the BC-05 assertion cleanly.


def test_bybit_connector_url_default_is_8001(monkeypatch: pytest.MonkeyPatch) -> None:
    """BC-05 / D-09: `Settings().bybit_connector_url` default MUST point at the
    bybit-connector service's port (`:8001`), not the market-data-service's own
    port (`:8002`).

    RED on main today — the current default is `http://localhost:8002` (the
    defect; a copy-paste of the service's own service_port). GREEN after the
    one-line fix in Plan 06 Task 3 lands:
        bybit_connector_url: str = Field(default="http://localhost:8001")

    monkeypatch.delenv calls below clear any operator-leaked env that might let
    Pydantic Settings paper over the default — the assertion is on the DEFAULT,
    not on an env-overridden value.
    """
    # Clear any BYBIT_* env that could shadow the default. `raising=False` keeps
    # this idempotent on hosts that never had these set.
    for key in (
        "BYBIT_CONNECTOR_URL",
        "BYBIT_TESTNET",
        "BYBIT_API_KEY",
        "BYBIT_API_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)

    try:
        from app.config import Settings  # type: ignore[import-not-found]
    except ImportError as exc:
        pytest.fail(
            "Could not import `app.config.Settings` from the market-data-service "
            "venv on the host. Per the plan note, this test may need to run via "
            "`docker exec crypto-bot-market-data pytest "
            "services/market-data-service/tests/test_config_defaults.py -v`. "
            f"Underlying ImportError: {exc!r}"
        )

    settings = Settings()
    actual = settings.bybit_connector_url
    assert actual == "http://localhost:8001", (
        "BC-05 / D-09 violation: `Settings().bybit_connector_url` default is "
        f"{actual!r}, expected 'http://localhost:8001'. The current default is "
        "the defect — a copy-paste of the service's own port. Fix is a one-line "
        "edit at services/market-data-service/app/config.py:58. RED-by-design "
        "until Plan 06 Task 3 lands the fix."
    )


def test_service_port_default_is_8002(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard: market-data-service's own port stays at 8002 (matches compose +
    project port table in CLAUDE.md). Always GREEN — flags if the BC-05 fix
    accidentally bumps the wrong setting.
    """
    monkeypatch.delenv("SERVICE_PORT", raising=False)

    try:
        from app.config import Settings  # type: ignore[import-not-found]
    except ImportError as exc:
        pytest.fail(
            "Could not import `app.config.Settings`. See note on Test 1; run "
            "via `docker exec crypto-bot-market-data pytest ...` if host import "
            f"resists. Underlying ImportError: {exc!r}"
        )

    settings = Settings()
    actual = settings.service_port
    assert actual == 8002, (
        f"Regression: market-data-service service_port default is {actual!r}, "
        "expected 8002 per compose / project port table. The BC-05 fix must "
        "ONLY change `bybit_connector_url`, not the service's own port."
    )
