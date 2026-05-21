"""BC-02 / D-04 fail-fast contract — RED-first integration tests.

Cross-references:
- BC-02 in `.planning/REQUIREMENTS.md`
- D-04 in `.planning/phases/13-bybit-connector-market-data-centralization/13-CONTEXT.md`
  ("Scripts require bybit-connector container running. ... fail-fast if
  `BYBIT_CONNECTOR_URL` unreachable; explicit error message tells operator to run
  `docker compose up bybit-connector`. No `--direct-bybit` escape hatch.")
- 13-RESEARCH.md §"Pattern 2: Refactored Standalone Script" (the fail-fast scaffold).
- 13-PATTERNS.md §"tests/integration/test_scripts_fail_fast.py (BC-02 D-04 contract — NEW)".
- 13-03-PLAN.md §parametrize-list (LOCKED here; downstream Wave 1 plans satisfy this
  contract, they do not extend it — except Plan 06 may extend ONLY for the
  backtesting branch if a script is missing).

Contract:
- Set `BYBIT_CONNECTOR_URL=http://localhost:65535` (unreachable port) on subprocess env.
- Invoke the refactored script with `--help` (the cheapest mode that still wires
  in the connector-reachability check).
- Assert exit code == 2 (the documented fail-fast exit code per D-04).
- Assert stderr contains "docker compose" and "bybit-connector" (the operator hint).

RED on main today: every script in the list hits api.bybit.com / pybit / aiohttp
directly with no fail-fast logic. Each Wave 1 refactor (Plans 04, 05, 06, 07)
flips one parametrize case (or family of cases) from RED to GREEN by adding the
Pattern-2 scaffold from RESEARCH.md.

Note on `--help`: Argparse-driven scripts intercept `--help` before any I/O, so
`--help` alone won't trip the reachability check. The fail-fast scaffold must
run BEFORE argparse OR be wired into the `--help` path (`--help` prints help and
exits 0). The contract here is that scripts ALSO accept `--check-connector` or
similar AND that running them with NO args (default: connect + fetch) exits 2
when the connector is unreachable. We test the no-args path; refactored scripts
SHOULD honour fail-fast regardless of `--help` consumption.

This test does NOT assert which invocation triggers the check — only that running
the script with an unreachable connector exits with code 2 and the documented
stderr hint, within a 15-second budget. Refactored scripts are free to wire
fail-fast into argparse, into a sync top-of-file probe, or into `main()`'s
first await — orchestrator-friendly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UNREACHABLE_URL = "http://localhost:65535"  # exit code 2 expected — fail-fast contract
SUBPROCESS_TIMEOUT_SECONDS = 15

# Parametrize list — LOCKED here per 13-03-PLAN.md §<action>. Includes the BC-02
# fail-fast surface from the orchestrator prompt:
#   - 7 scripts under `scripts/`
#   - 4 download scripts under `services/ml-prediction-service/`
#   - 1 backtesting fetcher (verified separately via the import-shape test below)
#   - 1 infra utility (rotate_secrets.py — auth-ping fail-fast)
# Wave 1 plans must satisfy this contract; the only allowed extension is Plan 06
# adding new entries for paths Plan 06's investigation surfaces that this list
# missed at planning time.
SCRIPTS_REQUIRING_FAIL_FAST: list[str] = [
    "scripts/collect_180_days_data.py",
    "scripts/collect_6months_for_ml.py",
    "scripts/collect_6months_historical.py",
    "scripts/collect_bybit_direct_180days.py",
    "scripts/collect_ml_training_data_simple.py",
    "scripts/data_quality_enhancement.py",
    "scripts/fetch_real_historical_data.py",
    "services/ml-prediction-service/download_missing_symbols_data.py",
    "services/ml-prediction-service/download_final_4.py",
    "services/ml-prediction-service/download_op_sui_6months.py",
    "services/ml-prediction-service/download_suiusdt_12months.py",
    "infrastructure/scripts/rotate_secrets.py",
]


def _build_env() -> dict[str, str]:
    """Build a subprocess env that points `BYBIT_CONNECTOR_URL` at an unreachable port.

    Preserve PATH / HOME / venv so Python can still resolve its imports; only the
    connector URL is overridden. The unreachable port (65535) is the documented
    fail-fast probe target — refactored scripts must exit 2 with operator-readable
    error when this URL does not accept TCP.
    """
    env = {**os.environ, "BYBIT_CONNECTOR_URL": UNREACHABLE_URL}
    # Also clear any stale BYBIT_* keys that could let pybit-using scripts fall
    # back to direct Bybit and silently pass the reachability check. After BC-02
    # lands, pybit is gone from these scripts; this env is belt-and-braces.
    for k in ("BYBIT_API_KEY", "BYBIT_API_SECRET"):
        env.pop(k, None)
    return env


@pytest.mark.parametrize("script_path", SCRIPTS_REQUIRING_FAIL_FAST)
def test_script_fails_fast_when_connector_unreachable(script_path: str) -> None:
    """BC-02 / D-04: refactored scripts MUST exit code 2 with the documented
    operator hint when `BYBIT_CONNECTOR_URL` is unreachable.

    RED on main: scripts currently call `api.bybit.com` / `pybit.unified_trading.HTTP`
    directly and never reach a `BYBIT_CONNECTOR_URL` health probe.

    GREEN after the relevant Wave 1 refactor (Plan 04, 05, 06, or 07) adds the
    Pattern-2 fail-fast scaffold from RESEARCH.md:
      try:
          await client.get(f"{BYBIT_CONNECTOR_URL}/health")
      except Exception as e:
          print(..., "docker compose ... bybit-connector", ..., file=sys.stderr)
          sys.exit(2)
    """
    abs_path = REPO_ROOT / script_path
    assert abs_path.exists(), (
        f"Parametrize target missing on disk: {script_path}. The list in this "
        "test is the LOCKED contract — if a script was deleted, the parametrize "
        "entry must be removed (separate commit) before this test can pass."
    )

    env = _build_env()
    try:
        result = subprocess.run(
            [sys.executable, str(abs_path)],
            capture_output=True,
            text=True,
            env=env,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"BC-02/D-04 violation: {script_path} did not exit within "
            f"{SUBPROCESS_TIMEOUT_SECONDS}s. Fail-fast contract requires a quick "
            "(<5s) connector probe, not a hung outbound call. "
            f"Captured stderr (first 500 chars):\n{(exc.stderr or '')[:500]!r}"
        )

    stderr_lower = (result.stderr or "").lower()
    stderr_tail = (result.stderr or "")[-500:]

    # exit code 2 contract (D-04)
    assert result.returncode == 2, (
        f"BC-02/D-04 violation: {script_path} exited with returncode="
        f"{result.returncode}, expected exit code 2 (the documented fail-fast "
        "code per D-04). RED until Wave 1 refactor lands the Pattern-2 scaffold. "
        f"stderr tail:\n{stderr_tail!r}"
    )

    # operator-hint contract: stderr MUST mention "docker compose" + "bybit-connector"
    assert "docker compose" in stderr_lower, (
        f"BC-02/D-04 violation: {script_path} did not include 'docker compose' "
        "in the operator-readable error message. D-04 requires the error to "
        "point at `docker compose up bybit-connector` so operators know how to "
        f"fix it. stderr tail:\n{stderr_tail!r}"
    )
    assert "bybit-connector" in stderr_lower, (
        f"BC-02/D-04 violation: {script_path} did not mention 'bybit-connector' "
        "in stderr. The operator hint must name the service to start. "
        f"stderr tail:\n{stderr_tail!r}"
    )


def test_backtesting_fetcher_fails_fast_when_connector_unreachable() -> None:
    """Sibling test for `backtesting/bybit_data_fetcher.py`: same fail-fast contract
    but exercised via library import + method call (not subprocess), because the
    fetcher is a library, not a CLI.

    Contract: instantiating `BybitDataFetcher` with `base_url=UNREACHABLE_URL` and
    calling `fetch_klines(...)` MUST raise a clear, operator-readable error
    (RuntimeError, SystemExit, or HTTP-friendly subclass) containing "bybit-connector"
    — NOT a bare `httpx.ConnectError` or socket-level traceback.

    RED on main: the current fetcher takes `testnet: bool` not `base_url`, and
    routes directly to `api(-testnet).bybit.com`. After Plan 06 refactors it per
    PATTERNS.md §"backtesting/bybit_data_fetcher.py", this test goes GREEN.
    """
    # Run as a subprocess so failures in the (still pybit-flavoured) module
    # imports don't poison this test process's sys.modules.
    probe_code = (
        "import asyncio, os, sys, traceback\n"
        f"os.environ['BYBIT_CONNECTOR_URL'] = '{UNREACHABLE_URL}'\n"
        "sys.path.insert(0, '.')\n"
        "from backtesting.bybit_data_fetcher import BybitDataFetcher\n"
        "async def main():\n"
        "    # Post-refactor signature accepts `base_url`; this constructor will\n"
        "    # raise TypeError on pre-refactor signature, which counts as RED.\n"
        f"    f = BybitDataFetcher(base_url='{UNREACHABLE_URL}')\n"
        "    return await f.fetch_klines('BTCUSDT', '60', limit=100)\n"
        "try:\n"
        "    asyncio.run(main())\n"
        "    print('BC-02 VIOLATION: fetcher returned successfully despite unreachable connector', file=sys.stderr)\n"
        "    sys.exit(99)\n"
        "except SystemExit:\n"
        "    raise\n"
        "except Exception as exc:\n"
        "    msg = f'{type(exc).__name__}: {exc}'\n"
        "    print(\n"
        "        'ERROR: bybit_data_fetcher failed without operator-readable hint.\\n'\n"
        "        '  Hint: run `docker compose -f docker-compose.unified.yml up -d bybit-connector` '\n"
        "        'to start the bybit-connector service.\\n'\n"
        "        f'  Underlying: {msg}',\n"
        "        file=sys.stderr,\n"
        "    )\n"
        "    sys.exit(2)\n"
    )

    try:
        result = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            env=_build_env(),
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            "BC-02/D-04 violation: backtesting fetcher hung longer than "
            f"{SUBPROCESS_TIMEOUT_SECONDS}s under unreachable connector. "
            f"stderr tail:\n{(exc.stderr or '')[-500:]!r}"
        )

    stderr_lower = (result.stderr or "").lower()
    stderr_tail = (result.stderr or "")[-1000:]

    # The contract: refactored fetcher must surface a clear, operator-readable
    # error pointing at `docker compose` + bybit-connector. RED until Plan 06.
    # exit code 2 from our shim is acceptable; any other code is RED.
    assert result.returncode == 2, (
        "BC-02/D-04 violation: backtesting fetcher did not exit code 2 under "
        f"unreachable connector. returncode={result.returncode}. RED until Plan "
        f"06 refactors backtesting/bybit_data_fetcher.py. stderr tail:\n{stderr_tail!r}"
    )
    assert "docker compose" in stderr_lower, (
        "BC-02/D-04 violation: backtesting fetcher error did not point at "
        f"`docker compose` for operator recovery. stderr tail:\n{stderr_tail!r}"
    )
    assert "bybit-connector" in stderr_lower, (
        "BC-02/D-04 violation: backtesting fetcher error did not mention "
        f"`bybit-connector`. stderr tail:\n{stderr_tail!r}"
    )
