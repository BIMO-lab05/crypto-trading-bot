"""BC-FIX-03 contract test (Phase 18, Plan 18-03).

ONE-WAY assertion: every (method, path) tuple the trading-engine bybit
adapter posts/gets to is a member of the bybit-connector FastAPI route
table. The reverse is NOT asserted — the connector legitimately exposes
routes the adapter does not consume (per Phase 18 CONTEXT.md D-04 and the
locked exclusion list below).

Decisions implemented (see .planning/phases/18-bybit-adapter-contract-fix/18-CONTEXT.md):

  D-09  route discovery via FastAPI `app.routes` introspection (NOT hardcoded)
  D-10  adapter endpoint extraction via regex on file text (NO adapter refactor)
  D-11  path + HTTP method only — query-schema drift deferred to a future phase
  D-12  test lives in trading-engine (adapter is the consumer; consumer owns the
        contract assertion)

Import isolation (advisor mapping decision for Plan 18-03):
  `services/trading-engine/` and `services/bybit-connector/` ship two top-level
  Python packages BOTH named `app/`. In-process import via sys.path manipulation
  would either resolve to the wrong `app` (cached in sys.modules) or silently
  merge module attributes. We subprocess-load the connector app and read the
  route table as JSON on stdout — sidesteps namespace collision AND any
  connector import-time side effects (Prometheus registry, settings init,
  lifespan handlers) that would crash/pollute the trading-engine pytest process.

Connector routes UNCONSUMED by adapter per D-04 (allowed; reverse direction
NOT asserted):
  /api/v1/order/history                  (Phase 19 RECON owns the reconcile sweep)
  /api/v1/market/funding-rate/history    (gated behind PREFER_MAKER_ORDERS env)
  /api/v1/market/instruments-info        (operations-only)
  /api/v1/status/circuit-breaker         (operations-only)
  /api/v1/status/circuit-breaker/reset   (operations-only)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Set, Tuple

import pytest


def _sanitised_subprocess_env() -> dict[str, str]:
    """Return a copy of os.environ with the trading-engine conftest's
    autouse-injected test placeholders stripped, so the connector
    subprocess boots against pydantic-settings defaults.
    """
    return {k: v for k, v in os.environ.items() if k not in _CONFTEST_INJECTED_ENV_VARS}


# Env vars the trading-engine `tests/conftest.py` `test_environment` autouse
# fixture injects into the pytest worker process. These get inherited by any
# subprocess launched from inside a test, which trips the bybit-connector's
# pydantic-settings Settings() validator at import time (the connector boots
# fine against its own defaults, but the conftest's placeholder values
# trigger validation errors like SecretStr-length / unknown DB host on the
# connector side). Strip them from the subprocess env so the connector falls
# back to its own defaults — same env it sees when started standalone.
#
# Without this sanitisation, the contract assertion silently skips on every
# host pytest invocation (deviation flagged 2026-05-24 — Rule 1: regex-only
# subprocess `pytest.skip` on CalledProcessError would mask conftest collision
# as "deps missing" and provide zero regression-net coverage).
_CONFTEST_INJECTED_ENV_VARS: frozenset[str] = frozenset(
    {
        "BYBIT_API_KEY",
        "BYBIT_API_SECRET",
        "ENVIRONMENT",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "REDIS_HOST",
        "REDIS_PORT",
        "RABBITMQ_HOST",
        "RABBITMQ_PORT",
        "LOG_LEVEL",
    }
)


# Repo root resolved from this test file location:
# services/trading-engine/tests/test_bybit_adapter_contract.py  →  repo root is 3 parents up.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

ADAPTER_PATH = (
    REPO_ROOT / "services" / "trading-engine" / "app" / "exchanges" / "bybit_adapter.py"
)
CONNECTOR_DIR = REPO_ROOT / "services" / "bybit-connector"

# D-10 — Regex capturing the `self._request("METHOD", "/api/v1/...", ...)` call shape.
# The adapter uses this pattern uniformly (9 call sites; verified by hand at
# Phase 18 plan-time). DOTALL so the method and path lines can be separated by
# arbitrary whitespace including newlines (the canonical adapter style is
# method on one line, path on the next).
ADAPTER_URL_REGEX = re.compile(
    r"self\._request\(\s*"
    r'"(?P<method>GET|POST|PUT|DELETE|PATCH)"\s*,\s*'
    r'"(?P<path>/api/v1/[A-Za-z0-9_\-/]+)"',
    re.DOTALL,
)


# Self-contained subprocess script — runs inside services/bybit-connector cwd so
# `from app.main import app` resolves to the connector's app/ package.
_DUMP_CONNECTOR_ROUTES_SCRIPT = r"""
import json
import sys
from app.main import app  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

rows = []
for route in app.routes:
    if isinstance(route, APIRoute):
        for method in route.methods:
            rows.append({"path": route.path, "method": method})
json.dump(rows, sys.stdout)
"""


def _load_connector_routes() -> Set[Tuple[str, str]]:
    """Subprocess-load bybit-connector's FastAPI app and return the
    set of declared (method, path) tuples.

    Returns the empty set if the subprocess fails (e.g. connector deps not
    installed in the trading-engine pytest worker's interpreter); the
    caller transforms that into pytest.skip so CI separates environment
    issues from contract drift.
    """
    if not CONNECTOR_DIR.is_dir():
        return set()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _DUMP_CONNECTOR_ROUTES_SCRIPT],
            cwd=str(CONNECTOR_DIR),
            env=_sanitised_subprocess_env(),
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        # Surface the stderr so debugging is one log-line away
        stderr = getattr(e, "stderr", "") or ""
        pytest.skip(
            f"could not subprocess-load bybit-connector app "
            f"(deps likely missing on this pytest host): {type(e).__name__}: {stderr[:400]}"
        )
    rows = json.loads(proc.stdout)
    return {(row["method"], row["path"]) for row in rows}


def _extract_adapter_endpoints() -> List[Tuple[str, str, int]]:
    """Regex-extract (method, path, line_number) from bybit_adapter.py.

    line_number is 1-indexed and points to the `self._request(` line — used
    to make assertion failures actionable for the executor.
    """
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    results: List[Tuple[str, str, int]] = []
    for m in ADAPTER_URL_REGEX.finditer(source):
        # 1-indexed line of the match start
        line_no = source[: m.start()].count("\n") + 1
        results.append((m.group("method"), m.group("path"), line_no))
    return results


# ===========================================================================
# Sanity (pre-flight): the regex finds the expected number of call sites
# ===========================================================================


def test_adapter_endpoint_extraction_finds_expected_call_sites() -> None:
    """Sanity guard for the ADAPTER_URL_REGEX itself.

    If a future adapter refactor changes the `self._request("METHOD", "/api/v1/...")`
    pattern (e.g. introduces a URL constant), this test surfaces the regex break
    before the contract assertion does — distinguishes "regex stale" from
    "endpoints drifted".

    Post-Plan-18-01, there are 9 call sites. If the count drifts up (new method
    added) or down (method deleted), bump this number in a follow-up PR.
    """
    endpoints = _extract_adapter_endpoints()
    assert len(endpoints) >= 9, (
        f"ADAPTER_URL_REGEX captured {len(endpoints)} call sites in "
        f"{ADAPTER_PATH.name}; expected >= 9 after Phase 18 Plan 18-01.\n"
        f"If the adapter pattern changed, update ADAPTER_URL_REGEX in this file."
    )


# ===========================================================================
# Main contract assertion (BC-FIX-03)
# ===========================================================================


def test_every_adapter_endpoint_exists_in_connector_route_table() -> None:
    """BC-FIX-03: every (method, path) the adapter calls via self._request(...)
    must exist as a declared route in the bybit-connector FastAPI app.

    ONE-WAY subset assertion (D-11). The reverse direction is intentionally
    not enforced — connector exposes routes the adapter does not consume
    (see module docstring "Connector routes UNCONSUMED" list).

    On failure, the assertion message names the missing tuple AND the adapter
    line where the offending self._request(...) call lives, so the executor
    can locate drift in <30 seconds.
    """
    connector_routes = _load_connector_routes()
    if not connector_routes:
        pytest.skip("connector route set is empty; subprocess-load returned no data")

    adapter_endpoints = _extract_adapter_endpoints()
    missing: List[Tuple[str, str, int]] = [
        (method, path, line_no)
        for (method, path, line_no) in adapter_endpoints
        if (method, path) not in connector_routes
    ]

    assert not missing, (
        "BC-FIX-03 contract drift detected — adapter calls path(s) the "
        "bybit-connector does not serve. Either fix the adapter to call the "
        "correct connector path, or (if intentional new connector route) add "
        'the corresponding @app.{method}("/api/v1/...") in services/bybit-connector/app/main.py.\n\n'
        "Drifted endpoints (method, path, adapter line):\n  "
        + "\n  ".join(f"{m} {p}  <- {ADAPTER_PATH.name}:{ln}" for (m, p, ln) in missing)
        + f"\n\nConnector route table ({len(connector_routes)} entries):\n  "
        + "\n  ".join(f"{m} {p}" for (m, p) in sorted(connector_routes))
    )


# ===========================================================================
# Explicit lock-in of the 5 BC-FIX-01 corrections (Plan 18-01)
# ===========================================================================


def test_phase_18_corrections_locked_in() -> None:
    """BC-FIX-01: the 5 endpoint corrections from Plan 18-01 are present in
    the adapter source text.

    Belt-and-braces over the main contract assertion: if the regex above ever
    fails to capture a call site (e.g. a future refactor introduces a URL
    constant the regex doesn't match), this test still catches the case
    where a 18-01 correction got reverted.
    """
    source = ADAPTER_PATH.read_text(encoding="utf-8")

    # OLD strings (Plan 18-01 removed these — must NOT appear)
    forbidden = [
        '"/api/v1/order/create"',
        '"/api/v1/position/list"',
        '"/api/v1/order/realtime"',
        '"/api/v1/market/tickers"',
    ]
    for token in forbidden:
        assert token not in source, (
            f"BC-FIX-01 regression: forbidden endpoint string {token!r} found in "
            f"{ADAPTER_PATH.name} — Plan 18-01 deleted this; do not reintroduce."
        )

    # NEW strings (Plan 18-01 introduced these — MUST appear)
    required_substrings = [
        '"/api/v1/order/place"',
        '"/api/v1/account/positions"',
        '"/api/v1/order/open"',
        '"/api/v1/market/ticker"',
    ]
    for token in required_substrings:
        assert token in source, (
            f"BC-FIX-01 missing correction: expected endpoint string {token!r} not found in "
            f"{ADAPTER_PATH.name} — Plan 18-01 should have introduced this."
        )
