"""BC-02 / D-07 — rotate_secrets auth-ping refactor RED-first unit tests.

Cross-references:
- BC-02 in `.planning/REQUIREMENTS.md`
- D-07 in `.planning/phases/13-bybit-connector-market-data-centralization/13-CONTEXT.md`
  ("infrastructure/scripts/rotate_secrets.py — refactor pybit + URL switching to
  use bybit-connector /api/v1/account/balance for the post-rotation auth ping.")
- 13-RESEARCH.md §"Pattern 3: Auth-Ping Refactor (rotate_secrets.py)" — Option A
  default: restart bybit-connector with new credentials, then ping
  /api/v1/account/balance.
- 13-RESEARCH.md "Pitfall 3" — bybit-connector reads credentials at boot, NOT
  per-request, so the restart MUST happen BEFORE the ping or the validation
  silently passes against the old credentials.
- 13-07-PLAN.md §<task type="tdd" tdd="true"> Task 1.

Contract (Option A — restart-then-ping):
1. `validate_credentials(api_key, api_secret, testnet)` orchestrates:
   - `subprocess.run(["docker", "compose", ..., "restart", "bybit-connector"], ...)`
   - poll `${BYBIT_CONNECTOR_URL}/health` until 200 OK (or fail)
   - GET `${BYBIT_CONNECTOR_URL}/api/v1/account/balance` (the auth ping)
2. Returns True iff the connector restart succeeded AND the balance ping returned
   `{"success": True, "data": {"list": [...non-empty...]}}`.
3. NEVER logs credential bytes — sentinel api_key strings must NOT appear in any
   captured log message (T-BC02-CredentialSpill mitigation).

RED today: the file still imports `pybit.unified_trading.HTTP` and validates
credentials by calling Bybit directly. There is no `validate_credentials`
top-level function; the validation lives inside the
`SecretRotation._validate_bybit_credentials` method. These tests target the
refactored top-level `validate_credentials` (or the renamed method) — the import
will fail OR the function will not behave as contracted until Task 1 GREEN
lands.
"""

from __future__ import annotations

import logging
import subprocess  # noqa: F401 — patched as `infrastructure.scripts.rotate_secrets.subprocess.run`

import httpx
import pytest
import respx


CONNECTOR_URL = "http://bybit-connector:8001"
SENTINEL_KEY = "SENTINEL_KEY_DO_NOT_LEAK"
SENTINEL_SECRET = "SENTINEL_SECRET_DO_NOT_LEAK"


def _wrap_success(payload: dict) -> dict:
    """Bybit-connector wrapper shape: {success, data, error?}."""
    return {"success": True, "data": payload, "error": None}


def _wrap_failure(error_msg: str) -> dict:
    """Bybit-connector wrapper failure shape."""
    return {"success": False, "data": None, "error": error_msg}


@pytest.fixture
def patch_subprocess_success(monkeypatch):
    """Patch subprocess.run in the rotate_secrets module to succeed and record
    the invocation args for assertion."""
    calls: list[list[str]] = []

    class _FakeCompleted:
        returncode = 0

    def _fake_run(*args, **kwargs):
        # subprocess.run can be called positional or as `subprocess.run(cmd, ...)`.
        cmd = args[0] if args else kwargs.get("args")
        calls.append(list(cmd) if cmd is not None else [])
        return _FakeCompleted()

    # Patch at the module path the refactored rotate_secrets imports from.
    from infrastructure.scripts import rotate_secrets

    monkeypatch.setattr(rotate_secrets.subprocess, "run", _fake_run)
    monkeypatch.setenv("BYBIT_CONNECTOR_URL", CONNECTOR_URL)
    # Keep the connector-health poll short so the unreachable / 503 tests
    # don't wait the full 30s default.
    monkeypatch.setenv("BYBIT_CONNECTOR_HEALTH_TIMEOUT", "2")
    return calls


@pytest.fixture
def patch_subprocess_already_invoked(monkeypatch):
    """Same as patch_subprocess_success but signals 'restart called, but
    connector never came back healthy'."""
    calls: list[list[str]] = []

    class _FakeCompleted:
        returncode = 0

    def _fake_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        calls.append(list(cmd) if cmd is not None else [])
        return _FakeCompleted()

    from infrastructure.scripts import rotate_secrets

    monkeypatch.setattr(rotate_secrets.subprocess, "run", _fake_run)
    monkeypatch.setenv("BYBIT_CONNECTOR_URL", CONNECTOR_URL)
    # Keep the connector-health poll short so the unreachable / 503 tests
    # don't wait the full 30s default.
    monkeypatch.setenv("BYBIT_CONNECTOR_HEALTH_TIMEOUT", "2")
    return calls


@pytest.mark.asyncio
@respx.mock
async def test_auth_ping_calls_bybit_connector_balance_endpoint(
    patch_subprocess_success,
) -> None:
    """Task 1 contract: `validate_credentials` MUST
    (a) invoke `subprocess.run(["docker", "compose", ..., "restart", "bybit-connector"], ...)`
        to propagate new creds (Option A / Pitfall 3 mitigation), AND
    (b) call `${BYBIT_CONNECTOR_URL}/api/v1/account/balance` for the post-restart
        auth ping.

    A valid response (`{"success": True, "data": {"list": [{"totalEquity": ...}]}}`)
    yields a True return.
    """
    health_route = respx.get(f"{CONNECTOR_URL}/health").mock(
        return_value=httpx.Response(
            200, json={"status": "healthy", "service": "bybit-connector"}
        )
    )
    balance_route = respx.get(f"{CONNECTOR_URL}/api/v1/account/balance").mock(
        return_value=httpx.Response(
            200,
            json=_wrap_success(
                {"list": [{"accountType": "UNIFIED", "totalEquity": "1234.56"}]}
            ),
        )
    )

    from infrastructure.scripts.rotate_secrets import validate_credentials

    result = await validate_credentials(
        api_key=SENTINEL_KEY,
        api_secret=SENTINEL_SECRET,
        testnet=False,
    )

    assert result is True, (
        "Option A contract: validate_credentials must return True on a successful "
        "restart + balance ping. Returned: %r" % (result,)
    )
    assert balance_route.called, (
        "BC-02/D-07 violation: refactored validate_credentials must call "
        "${BYBIT_CONNECTOR_URL}/api/v1/account/balance for the auth ping (was "
        "previously a direct pybit call)."
    )
    assert health_route.called, (
        "Option A contract: validate_credentials must poll /health before the "
        "auth ping to confirm the restarted connector is back up."
    )

    # Assert the docker-compose restart was invoked with the expected shape.
    assert patch_subprocess_success, (
        "Pitfall 3 (RESEARCH.md): bybit-connector reads creds at boot; the auth "
        "ping must be preceded by `docker compose restart bybit-connector`. No "
        "subprocess.run invocation was recorded."
    )
    flat_calls = [" ".join(map(str, c)) for c in patch_subprocess_success]
    assert any(
        "docker" in c and "compose" in c and "restart" in c and "bybit-connector" in c
        for c in flat_calls
    ), (
        "Restart-then-ping contract: subprocess.run must be invoked with the "
        "docker-compose restart command for the bybit-connector service. "
        "Recorded calls: %r" % (flat_calls,)
    )


@pytest.mark.asyncio
@respx.mock
async def test_auth_ping_returns_false_on_connector_failure(
    patch_subprocess_success,
) -> None:
    """If the bybit-connector returns `{"success": False, ...}` (e.g. invalid
    credentials surface as a wrapper-error), `validate_credentials` MUST return
    False — NOT raise, NOT return True."""
    respx.get(f"{CONNECTOR_URL}/health").mock(
        return_value=httpx.Response(200, json={"status": "healthy"})
    )
    respx.get(f"{CONNECTOR_URL}/api/v1/account/balance").mock(
        return_value=httpx.Response(
            200,
            json=_wrap_failure("auth failed"),
        )
    )

    from infrastructure.scripts.rotate_secrets import validate_credentials

    result = await validate_credentials(
        api_key=SENTINEL_KEY,
        api_secret=SENTINEL_SECRET,
        testnet=False,
    )

    assert result is False, (
        "Contract: wrapper-level `{success: False}` from the connector indicates "
        "the auth ping rejected the credentials. validate_credentials must "
        "return False. Returned: %r" % (result,)
    )


@pytest.mark.asyncio
@respx.mock
async def test_auth_ping_returns_false_when_connector_unreachable(
    patch_subprocess_success,
) -> None:
    """If the bybit-connector is unreachable (503 / network error) after restart,
    `validate_credentials` MUST return False — it MUST NOT silently pass."""
    # /health 503 — connector never returns to healthy after restart.
    respx.get(f"{CONNECTOR_URL}/health").mock(
        return_value=httpx.Response(503, json={"status": "unhealthy"})
    )
    # Even if balance is mocked, the health gate should prevent the ping.
    respx.get(f"{CONNECTOR_URL}/api/v1/account/balance").mock(
        return_value=httpx.Response(503, json={"detail": "Bybit connection failed"})
    )

    from infrastructure.scripts.rotate_secrets import validate_credentials

    result = await validate_credentials(
        api_key=SENTINEL_KEY,
        api_secret=SENTINEL_SECRET,
        testnet=False,
    )

    assert result is False, (
        "Contract: connector-side failure (unhealthy or 503) means validation "
        "FAILED — the new credentials cannot be confirmed safely. Must return "
        "False. Returned: %r" % (result,)
    )


@pytest.mark.asyncio
@respx.mock
async def test_no_credentials_in_log_output(
    patch_subprocess_success, caplog: pytest.LogCaptureFixture
) -> None:
    """T-BC02-CredentialSpill mitigation (Test 4 of plan):
    raw credential bytes MUST NOT appear in any captured log message,
    regardless of which code path runs."""
    respx.get(f"{CONNECTOR_URL}/health").mock(
        return_value=httpx.Response(200, json={"status": "healthy"})
    )
    respx.get(f"{CONNECTOR_URL}/api/v1/account/balance").mock(
        return_value=httpx.Response(
            200,
            json=_wrap_success(
                {"list": [{"accountType": "UNIFIED", "totalEquity": "1234.56"}]}
            ),
        )
    )

    from infrastructure.scripts.rotate_secrets import validate_credentials

    with caplog.at_level(logging.DEBUG, logger="infrastructure.scripts.rotate_secrets"):
        await validate_credentials(
            api_key=SENTINEL_KEY,
            api_secret=SENTINEL_SECRET,
            testnet=False,
        )

    captured = "\n".join(rec.getMessage() for rec in caplog.records)
    assert SENTINEL_KEY not in captured, (
        "Security V7 hygiene violation: api_key bytes leaked into log output. "
        "Found %r in captured logs:\n%s" % (SENTINEL_KEY, captured)
    )
    assert SENTINEL_SECRET not in captured, (
        "Security V7 hygiene violation: api_secret bytes leaked into log output. "
        "Found %r in captured logs:\n%s" % (SENTINEL_SECRET, captured)
    )
