"""BC-07 RED-first tape-preservation integration test (Phase 13 Plan 03).

Cross-references:
- BC-07 in `.planning/REQUIREMENTS.md`
- D-08 in `.planning/phases/13-bybit-connector-market-data-centralization/13-CONTEXT.md`
  ("Bybit-connector's tape-replay mode MUST work unchanged after refactor.")
- Researcher's "Tape-Mode Coverage Gap" Option A
  (`13-RESEARCH.md` §"Tape-Mode Coverage Gap (BC-07)"): assert empty-but-shape-correct
  payloads do not crash refactored consumers; richer orderbook fixtures deferred.
- PATTERNS.md §"tests/integration/test_bybit_connector_tape_preserved.py (BC-07 — NEW)".

State on `main` (RED-by-design):
- Test 3 (`test_tape_stub_shapes_match_handler_expectations`) — ALWAYS GREEN. It is the
  contract pin against `services/bybit-connector/app/tape_replay_client.py:206-218`
  stub shapes.
- Test 1 (`test_bybit_connector_orderbook_under_tape_returns_empty_shape`) — RED on
  main because `services/ml-prediction-service/app/handlers/orderbook.py:262` still
  calls `https://api.bybit.com/v5/market/orderbook` directly. respx won't match;
  the unmocked outbound call falls through and the assertion fails.
- Test 2 (`test_no_live_bybit_call_during_tape_mode`) — RED on main for the same reason:
  the consumer hits the live URL, which is wired to raise on hit.
- The Wave 1 (Plan 04) refactor flips Tests 1 and 2 to GREEN by pointing the consumer
  at `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook` with the wrapper-shape parser.

Notes on imports:
- `services/bybit-connector` and `services/ml-prediction-service` contain hyphens and
  are NOT importable as `services.bybit-connector.app...`. Use `importlib.util` to
  load by file path. This keeps the test runnable from repo root without requiring
  a service venv on `sys.path`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Optional

import httpx
import pytest
import respx

pytestmark = pytest.mark.asyncio

REPO_ROOT = Path(__file__).resolve().parents[2]
CONNECTOR_URL = "http://bybit-connector:8001"


def _load_module_by_path(module_name: str, file_path: Path) -> Any:
    """Load a module by absolute file path (works around hyphenated service dirs)."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"Could not build spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_tape_replay_client():
    """services/bybit-connector/app/tape_replay_client.py — stub shapes contract."""
    return _load_module_by_path(
        "bc_tape_replay_client",
        REPO_ROOT / "services" / "bybit-connector" / "app" / "tape_replay_client.py",
    )


def _try_load_orderbook_handler() -> Optional[Any]:
    """Best-effort import of the ml-prediction orderbook handler. Returns None if the
    module cannot be loaded (e.g., missing transitive deps on the host). The test
    that depends on it skips with a RED-style xfail in that case so the contract
    remains visible.
    """
    target = (
        REPO_ROOT
        / "services"
        / "ml-prediction-service"
        / "app"
        / "handlers"
        / "orderbook.py"
    )
    if not target.exists():
        return None
    try:
        return _load_module_by_path("ml_pred_orderbook_handler", target)
    except Exception:  # pragma: no cover - executes in unfriendly host envs
        return None


def _resolve_orderbook_fetcher(handler_module: Any):
    """Return whichever name the handler exposes — pre-refactor or post-refactor.
    BC-02 Wave 1 (Plan 04) is expected to rename
    `fetch_orderbook_from_bybit` → `fetch_orderbook_from_connector`. We accept
    either so the test compiles before and after the rename.
    """
    for name in ("fetch_orderbook_from_connector", "fetch_orderbook_from_bybit"):
        if hasattr(handler_module, name):
            return getattr(handler_module, name)
    return None


# =============================================================================
# Test 1: RED-by-design — fetch via refactored consumer returns empty shape
# =============================================================================


async def test_bybit_connector_orderbook_under_tape_returns_empty_shape(monkeypatch):
    """Refactored ml-prediction orderbook handler MUST hit bybit-connector and
    handle the tape stub `{"a":[],"b":[],"ts":0,"u":0}` without crashing.

    RED-by-design on main: current handler calls `https://api.bybit.com/v5/market/orderbook`
    directly. respx records ZERO calls to the bybit-connector mock; `route.called`
    fails. After BC-02 Wave 1 lands the URL swap + wrapper parser, this test goes GREEN.

    Setup mirrors MARKET_DATA_SOURCE=tape end-to-end:
    - bybit-connector internally returns the TapeReplayClient stub shape
    - the wrapper `{"success": True, "data": {...stub...}}` is what the consumer sees
    """
    monkeypatch.setenv("MARKET_DATA_SOURCE", "tape")
    monkeypatch.setenv("BYBIT_CONNECTOR_URL", CONNECTOR_URL)

    handler_module = _try_load_orderbook_handler()
    if handler_module is None:
        pytest.fail(
            "Could not load services/ml-prediction-service/app/handlers/orderbook.py "
            "(missing transitive deps in this host env). BC-07 Test 1 cannot run; "
            "this counts as RED. Rerun inside the ml-prediction-service container "
            "or install its requirements."
        )

    fetcher = _resolve_orderbook_fetcher(handler_module)
    assert fetcher is not None, (
        "Neither `fetch_orderbook_from_connector` (post-refactor) nor "
        "`fetch_orderbook_from_bybit` (pre-refactor) is exposed by the handler. "
        "BC-02 Wave 1 refactor renamed the function or removed it."
    )

    tape_stub_payload = {
        "success": True,
        "data": {"a": [], "b": [], "ts": 0, "u": 0},
    }

    with respx.mock(assert_all_called=False) as mock_router:
        connector_route = mock_router.get(
            f"{CONNECTOR_URL}/api/v1/market/orderbook"
        ).mock(return_value=httpx.Response(200, json=tape_stub_payload))

        # Live URLs must NOT be hit under tape mode.
        live_route = mock_router.get("https://api.bybit.com/v5/market/orderbook").mock(
            return_value=httpx.Response(500, json={"retCode": -1, "retMsg": "leak"})
        )
        testnet_route = mock_router.get(
            "https://api-testnet.bybit.com/v5/market/orderbook"
        ).mock(return_value=httpx.Response(500, json={"retCode": -1, "retMsg": "leak"}))

        try:
            result = await fetcher("BTCUSDT", limit=25)
        except Exception as exc:
            pytest.fail(
                "Refactored consumer raised under tape mode. Tape stubs must be "
                f"handled without exception. Exception was: {exc!r}. "
                "RED until BC-02 Wave 1 (Plan 04) lands the bybit-connector REST URL "
                "swap + wrapper-shape parser."
            )

    # Contract: consumer points at bybit-connector, not at the live URLs.
    assert connector_route.called, (
        "BC-02 Wave 1 not yet applied: refactored consumer did NOT hit "
        f"{CONNECTOR_URL}/api/v1/market/orderbook. This test is RED-by-design "
        "until Plan 04 swaps the orderbook handler to bybit-connector REST."
    )
    assert not live_route.called, (
        "Tape mode violation: consumer still calls api.bybit.com directly. "
        "BC-07 demands a refactored consumer that routes through bybit-connector."
    )
    assert not testnet_route.called, (
        "Tape mode violation: consumer still calls api-testnet.bybit.com directly."
    )

    # Empty-but-shape-correct response (Option A): handler must return empty
    # bids/asks lists rather than crashing on missing fields.
    assert result.get("bids") == [], f"expected empty bids, got {result.get('bids')!r}"
    assert result.get("asks") == [], f"expected empty asks, got {result.get('asks')!r}"
    assert result.get("timestamp") == 0, (
        f"expected timestamp=0 from tape stub, got {result.get('timestamp')!r}"
    )


# =============================================================================
# Test 2: RED-by-design — no live Bybit URL is touched under tape mode
# =============================================================================


async def test_no_live_bybit_call_during_tape_mode(monkeypatch):
    """Under MARKET_DATA_SOURCE=tape, refactored consumers MUST NOT make outbound
    httpx calls to `api.bybit.com` or `api-testnet.bybit.com`.

    The check is enforced by registering catch-all respx routes for those hosts
    and asserting `route.called == False` after the consumer runs.

    RED on main because the orderbook handler still hits `api.bybit.com` directly,
    which trips the catch-all route. GREEN after BC-02 Wave 1 swaps the URL.
    """
    monkeypatch.setenv("MARKET_DATA_SOURCE", "tape")
    monkeypatch.setenv("BYBIT_CONNECTOR_URL", CONNECTOR_URL)

    handler_module = _try_load_orderbook_handler()
    if handler_module is None:
        pytest.fail(
            "Could not load orderbook handler module — BC-07 Test 2 cannot enforce "
            "the no-live-call contract."
        )

    fetcher = _resolve_orderbook_fetcher(handler_module)
    assert fetcher is not None

    with respx.mock(assert_all_called=False) as mock_router:
        # Connector mock so the refactored path has a target.
        mock_router.get(f"{CONNECTOR_URL}/api/v1/market/orderbook").mock(
            return_value=httpx.Response(
                200, json={"success": True, "data": {"a": [], "b": [], "ts": 0, "u": 0}}
            )
        )
        # Catch-all routes for the live URLs we forbid under tape.
        mainnet_route = mock_router.get(
            url__regex=r"^https?://api\.bybit\.com/.*$"
        ).mock(return_value=httpx.Response(500, json={"retCode": -1, "retMsg": "leak"}))
        testnet_route = mock_router.get(
            url__regex=r"^https?://api-testnet\.bybit\.com/.*$"
        ).mock(return_value=httpx.Response(500, json={"retCode": -1, "retMsg": "leak"}))

        # Allow the consumer call to raise; the assertion below still applies.
        try:
            await fetcher("BTCUSDT", limit=25)
        except Exception:
            pass

        assert not mainnet_route.called, (
            "BC-07 violation: refactored consumer called `api.bybit.com` directly "
            "under MARKET_DATA_SOURCE=tape. Tape mode must route all market-data "
            "calls through bybit-connector. RED until BC-02 Wave 1 refactor lands."
        )
        assert not testnet_route.called, (
            "BC-07 violation: refactored consumer called `api-testnet.bybit.com` "
            "directly. Same contract as the mainnet check above."
        )


# =============================================================================
# Test 3: ALWAYS-GREEN contract pin against TapeReplayClient stub shapes
# =============================================================================


async def test_tape_stub_shapes_match_handler_expectations():
    """Contract pin: the four out-of-scope feeds in TapeReplayClient must return the
    exact stub shapes documented in PATTERNS.md and consumed by the BC-02 refactor.

    This test is GREEN today and guards against drift in
    `services/bybit-connector/app/tape_replay_client.py:206-218`. If a future change
    alters the stub shape, downstream refactored consumers break — fail here first.
    """
    tape_module = _load_tape_replay_client()
    TapeReplayClient = tape_module.TapeReplayClient

    # The four stubs ignore `fixtures_path` but the constructor's `_load_fixtures()`
    # demands real `klines/` + `ticker/` subdirs (WSL bind-mount race guard). Point
    # at the in-repo fixtures committed for tape mode.
    fixtures_path = REPO_ROOT / "tests" / "fixtures" / "tape"
    if not (fixtures_path / "klines").is_dir():
        pytest.fail(
            f"Required tape fixtures missing at {fixtures_path}/klines — repo state "
            "broken; cannot exercise TapeReplayClient contract pin."
        )
    client = TapeReplayClient(fixtures_path=fixtures_path)

    orderbook = await client.get_orderbook()
    assert orderbook == {"a": [], "b": [], "ts": 0, "u": 0}, (
        f"TapeReplayClient.get_orderbook drift: got {orderbook!r}"
    )

    recent_trades = await client.get_recent_trades()
    assert recent_trades == {"list": []}, (
        f"TapeReplayClient.get_recent_trades drift: got {recent_trades!r}"
    )

    funding_rate_history = await client.get_funding_rate_history()
    assert funding_rate_history == {"list": []}, (
        f"TapeReplayClient.get_funding_rate_history drift: got {funding_rate_history!r}"
    )

    instruments_info = await client.get_instruments_info()
    assert instruments_info == {"list": []}, (
        f"TapeReplayClient.get_instruments_info drift: got {instruments_info!r}"
    )
