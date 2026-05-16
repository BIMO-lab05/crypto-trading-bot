"""Lifespan integration tests for PREFLIGHT-02 — boot-time cap enforcement.

Five tests:

* ``test_lifespan_source_contains_cap_check`` — source-inspection guard
  catching a future refactor that moves the cap-check OUT of ``lifespan()``
  (the function body's source must contain ``LIVE_PREFLIGHT_REJECTED``,
  ``max_risk_per_trade``, and the literal ``0.02``).
* ``test_lifespan_rejects_live_with_high_cap`` — runtime: LIVE + 0.03 must
  raise ``RuntimeError`` referencing both 0.03 and 0.02.
* ``test_lifespan_accepts_live_with_strict_cap`` — runtime: LIVE + 0.02 must
  pass the cap-check (emits the "cap check passed" INFO line).
* ``test_lifespan_paper_mode_skips_cap_check`` — runtime: PAPER + 0.10 must
  skip the cap-check entirely.
* ``test_lifespan_and_check_cap_agree_at_boundary`` — drift detector for the
  two hard-coded 0.02 thresholds (inline at main.py + ``check_cap()`` at
  app/preflight/checks.py). The boundary 0.0200 must produce PASS in BOTH
  paths; 0.0201 must produce FAIL in BOTH. Per 08-CONTEXT.md locked
  decision, the two thresholds are intentional duplicates — this test is
  the safety net against silent divergence.
"""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app.config import Settings
from app.preflight.checks import check_cap


# ---------------------------------------------------------------------------
# Helpers — async-context-manager stub for the 4 phase managers downstream
# of the cap-check. Mirrors the AsyncContextManagerMock shape used in other
# lifespan tests; kept local to avoid pulling in extra test infra.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _noop_phase():
    """Async no-op context manager. Substitute for the 4 phase managers so
    tests that need to enter the lifespan body don't try to connect to DB /
    Redis / RabbitMQ / TA service.
    """
    yield


def _patch_phase_managers(monkeypatch) -> None:
    """Replace init_data / init_ml / init_strategy / init_risk on
    ``app.main`` with the no-op context manager factory.

    Also replace ``app.auto_trader.get_auto_trader`` so the lifespan's
    auto-start branch (gated on ``auto_trading_enabled`` + EMERGENCY_STOP)
    doesn't try to import the real module.
    """
    monkeypatch.setattr("app.main.init_data", _noop_phase, raising=True)
    monkeypatch.setattr("app.main.init_ml", _noop_phase, raising=True)
    monkeypatch.setattr("app.main.init_strategy", _noop_phase, raising=True)
    monkeypatch.setattr("app.main.init_risk", _noop_phase, raising=True)


def _fake_app_for_lifespan() -> FastAPI:
    """Throwaway FastAPI app so we can drive the ``lifespan(app)`` context
    without touching the global one from ``app.main``."""
    return FastAPI()


# ---------------------------------------------------------------------------
# 1. Source-inspection guard — the cap-check must live INSIDE lifespan()
# ---------------------------------------------------------------------------


def test_lifespan_source_contains_cap_check():
    """The cap-check block must live in ``lifespan()`` (not in a helper
    module). If a future refactor extracts it, ``inspect.getsource`` on the
    lifespan function no longer contains the three load-bearing literals
    and this test fails — that's the regression detector.

    08-CONTEXT.md lines 36-53 lock the inline form per "Per-trade cap
    enforcement point" decision (co-located with existing LIVE_TRADING_ACK
    gate). Do NOT relocate.
    """
    import app.main as main_mod

    src = inspect.getsource(main_mod.lifespan)
    assert "LIVE_PREFLIGHT_REJECTED" in src, (
        "LIVE_PREFLIGHT_REJECTED literal removed from lifespan source"
    )
    assert "max_risk_per_trade" in src, (
        "max_risk_per_trade reference removed from lifespan source"
    )
    assert "0.02" in src, "LIVE-strict 0.02 threshold removed from lifespan source"


# ---------------------------------------------------------------------------
# 2. LIVE + cap=0.03 — runtime rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_rejects_live_with_high_cap(monkeypatch):
    """LIVE + MAX_RISK_PER_TRADE=0.03 + ACK present must raise RuntimeError.

    The error fires BEFORE the 4 phase context managers, so no phase
    mocking is needed here — the RuntimeError aborts lifespan setup.
    """
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("MAX_RISK_PER_TRADE", "0.03")
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")

    # Drive the lifespan with the LIVE + 0.03 Settings instance directly.
    # We patch the module-level ``settings`` reference rather than relying
    # on ``reload_settings()`` because pydantic-settings may cache fields
    # that pass through env validators with side effects.
    import app.main as main_mod

    bad_settings = Settings(trading_mode="LIVE", max_risk_per_trade=0.03)
    monkeypatch.setattr(main_mod, "settings", bad_settings, raising=False)

    with pytest.raises(RuntimeError, match=r"max_risk_per_trade.*0\.03.*0\.02"):
        async with main_mod.lifespan(_fake_app_for_lifespan()):
            pass


# ---------------------------------------------------------------------------
# 3. LIVE + cap=0.02 — runtime acceptance (cap-check PASSES)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_accepts_live_with_strict_cap(monkeypatch, caplog):
    """LIVE + MAX_RISK_PER_TRADE=0.02 + ACK present must pass the cap-check.

    The downstream phase managers are mocked so the test isolates the
    cap-check branch. After lifespan entry, the INFO log
    ``LIVE preflight cap check passed`` must be present and the FAIL log
    must NOT.
    """
    import logging

    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("MAX_RISK_PER_TRADE", "0.02")
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")

    import app.main as main_mod

    good_settings = Settings(
        trading_mode="LIVE",
        max_risk_per_trade=0.02,
        auto_trading_enabled=False,
    )
    monkeypatch.setattr(main_mod, "settings", good_settings, raising=False)
    _patch_phase_managers(monkeypatch)

    caplog.set_level(logging.INFO)
    async with main_mod.lifespan(_fake_app_for_lifespan()):
        pass

    assert "LIVE preflight cap check passed" in caplog.text, (
        "Expected the cap-check PASS log line; lifespan may have skipped the LIVE branch"
    )
    assert "LIVE_PREFLIGHT_REJECTED" not in caplog.text, (
        "Cap-check incorrectly emitted the FAIL log for max_risk_per_trade=0.02"
    )


# ---------------------------------------------------------------------------
# 4. PAPER + cap=0.10 — runtime: cap-check is SKIPPED (ADR-010)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_paper_mode_skips_cap_check(monkeypatch, caplog):
    """PAPER + MAX_RISK_PER_TRADE=0.10 must skip the cap-check entirely.

    ADR-010 paper-relaxed 10% must continue to boot. Neither the
    ``LIVE_PREFLIGHT_REJECTED`` line nor the ``cap check passed`` line is
    expected — the entire ``if settings.trading_mode == "LIVE":`` branch
    is short-circuited.
    """
    import logging

    monkeypatch.delenv("TRADING_MODE", raising=False)  # default is PAPER
    monkeypatch.setenv("MAX_RISK_PER_TRADE", "0.10")

    import app.main as main_mod

    paper_settings = Settings(
        trading_mode="PAPER",
        max_risk_per_trade=0.10,
        auto_trading_enabled=False,
    )
    monkeypatch.setattr(main_mod, "settings", paper_settings, raising=False)
    _patch_phase_managers(monkeypatch)

    caplog.set_level(logging.INFO)
    async with main_mod.lifespan(_fake_app_for_lifespan()):
        pass

    assert "LIVE_PREFLIGHT_REJECTED" not in caplog.text, (
        "PAPER mode incorrectly tripped the cap-check FAIL path"
    )
    assert "LIVE preflight cap check passed" not in caplog.text, (
        "PAPER mode incorrectly entered the LIVE branch (cap-check should be skipped entirely)"
    )


# ---------------------------------------------------------------------------
# 5. Boundary-agreement (drift detector) — addresses checker W2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cap, expect_lifespan_raises, expect_check_cap_status",
    [
        # Case A — exactly at limit: 0.0200 > 0.02 is False → both PASS.
        (0.0200, False, "PASS"),
        # Case B — just above limit: 0.0201 > 0.02 is True → both FAIL.
        (0.0201, True, "FAIL"),
    ],
    ids=["boundary_exact_0.0200", "boundary_plus_epsilon_0.0201"],
)
async def test_lifespan_and_check_cap_agree_at_boundary(
    cap,
    expect_lifespan_raises,
    expect_check_cap_status,
    monkeypatch,
    caplog,
):
    """Drift detector: the inline lifespan cap-check at ``main.py`` and the
    ``check_cap()`` function in ``app/preflight/checks.py`` MUST agree at
    the 2% boundary for the same ``Settings(...)`` input.

    08-CONTEXT.md lines 36-53 lock both thresholds as intentional duplicates
    (the inline form lives next to the existing LIVE_TRADING_ACK gate; the
    function form lives in the shared preflight module used by the CLI and
    HTTP route). Without this test, a future commit could relax one
    threshold to 0.025 while leaving the other strict and silent drift
    would land on a labelled LIVE PR.

    Case 0.0200: ``0.0200 > 0.02`` is False, so the lifespan does NOT
    raise; ``check_cap`` returns PASS. Both agree → PASS.

    Case 0.0201: ``0.0201 > 0.02`` is True, so the lifespan raises
    RuntimeError; ``check_cap`` returns FAIL with detail containing
    "0.0201" and "0.02". Both agree → FAIL.
    """
    import logging

    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("MAX_RISK_PER_TRADE", str(cap))
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")

    settings = Settings(
        trading_mode="LIVE",
        max_risk_per_trade=cap,
        auto_trading_enabled=False,
    )

    import app.main as main_mod

    monkeypatch.setattr(main_mod, "settings", settings, raising=False)
    _patch_phase_managers(monkeypatch)

    # --- Path 1: inline lifespan cap-check at main.py ---
    caplog.set_level(logging.INFO)
    if expect_lifespan_raises:
        with pytest.raises(RuntimeError, match=rf"max_risk_per_trade.*{cap}.*0\.02"):
            async with main_mod.lifespan(_fake_app_for_lifespan()):
                pass
    else:
        # 0.0200 — lifespan must NOT raise for the cap check. Phase managers
        # are mocked so the body executes cleanly.
        async with main_mod.lifespan(_fake_app_for_lifespan()):
            pass
        assert "LIVE preflight cap check passed" in caplog.text, (
            "Lifespan failed to emit the PASS log at boundary cap=0.0200"
        )

    # --- Path 2: check_cap() from app.preflight.checks ---
    result = check_cap(settings)
    assert result.status == expect_check_cap_status, (
        f"check_cap disagrees with the lifespan inline check at cap={cap}: "
        f"lifespan_raises={expect_lifespan_raises}, "
        f"check_cap.status={result.status} (expected {expect_check_cap_status})"
    )

    # --- Cross-agreement: both paths produce the same verdict ---
    lifespan_verdict = "FAIL" if expect_lifespan_raises else "PASS"
    assert result.status == lifespan_verdict, (
        f"DRIFT DETECTED at cap={cap}: lifespan inline check verdict="
        f"{lifespan_verdict} but check_cap.status={result.status}. The two "
        f"hard-coded 0.02 thresholds (services/trading-engine/app/main.py "
        f"inline + services/trading-engine/app/preflight/checks.py "
        f"check_cap) have diverged. Fix BOTH to match — they are intentional "
        f"duplicates per 08-CONTEXT.md locked decision (per-trade cap "
        f"enforcement point co-located with the LIVE_TRADING_ACK gate)."
    )

    # For the FAIL case, the detail string must contain both the offending
    # cap value AND the 0.02 limit — matches check_cap's contract.
    if expect_check_cap_status == "FAIL":
        assert str(cap) in result.detail, (
            f"check_cap FAIL detail missing offending cap value {cap}: {result.detail!r}"
        )
        assert "0.02" in result.detail, (
            f"check_cap FAIL detail missing 0.02 limit literal: {result.detail!r}"
        )
