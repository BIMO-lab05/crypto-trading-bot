"""Unit tests for send_daily_summary ml_gate_reason_counts kwarg (MLGATE-03, Plan 09-03).

Covers:
- Backward-compatible default: omitting the kwarg renders the original message.
- New ML Gate Reasons section appears when counts dict is non-empty.
- Canonical reason ordering is preserved regardless of dict insertion order.
- AlertCreate.metadata carries the raw counts dict for downstream consumers.

The Telegram dispatch layer is mocked at AlertManager.send_alert so these
tests do NOT exercise the real notification provider.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.alert_manager import AlertManager


@pytest.fixture
def manager(monkeypatch) -> AlertManager:
    """Fresh AlertManager with send_alert patched to capture the AlertCreate."""
    am = AlertManager()
    captured: list = []

    async def _capture_send_alert(alert_create):
        captured.append(alert_create)
        # Return a minimal AlertResponse-shaped object — fixture consumers
        # care about the captured AlertCreate, not the return value.
        from app.models import AlertResponse

        return AlertResponse(
            success=True,
            alert_id="test-alert-id",
            message="captured",
            channels_sent=[],
        )

    monkeypatch.setattr(am, "send_alert", AsyncMock(side_effect=_capture_send_alert))
    # Stash the captured list on the fixture so tests can read it.
    am._captured = captured  # type: ignore[attr-defined]
    return am


@pytest.mark.asyncio
async def test_digest_message_unchanged_when_ml_counts_absent(manager):
    """Backward compatibility: omitting ml_gate_reason_counts → no ML section."""
    await manager.send_daily_summary(
        total_pnl=100.0,
        total_trades=5,
        win_rate=0.6,
        balance=1000.0,
    )
    assert len(manager._captured) == 1
    captured = manager._captured[0]
    assert "ML Gate Reasons" not in captured.message
    # The original performance section is intact.
    assert "Performance Summary" in captured.message
    assert "Total P&L:" in captured.message


@pytest.mark.asyncio
async def test_digest_message_unchanged_when_ml_counts_empty_dict(manager):
    """An empty dict must also produce no ML section (no spurious header)."""
    await manager.send_daily_summary(
        total_pnl=0.0,
        total_trades=0,
        win_rate=0.0,
        balance=1000.0,
        ml_gate_reason_counts={},
    )
    assert "ML Gate Reasons" not in manager._captured[0].message


@pytest.mark.asyncio
async def test_digest_message_includes_ml_counts_section(manager):
    """Non-empty counts → message contains the rendered section."""
    await manager.send_daily_summary(
        total_pnl=0.0,
        total_trades=0,
        win_rate=0.0,
        balance=1000.0,
        ml_gate_reason_counts={"no_evidence": 3, "dsr_below_gate": 1},
    )
    msg = manager._captured[0].message
    assert "ML Gate Reasons (24h):" in msg
    assert "- no_evidence: 3" in msg
    assert "- dsr_below_gate: 1" in msg


@pytest.mark.asyncio
async def test_digest_message_reason_order_is_canonical(manager):
    """Canonical ordering: no_evidence < dsr_below_gate < ... < manual_override.

    Pass the dict in REVERSE insertion order and verify the rendered text
    still puts no_evidence before manual_override.
    """
    await manager.send_daily_summary(
        total_pnl=0.0,
        total_trades=0,
        win_rate=0.0,
        balance=1000.0,
        ml_gate_reason_counts={
            "manual_override": 1,
            "no_evidence": 2,
        },
    )
    msg = manager._captured[0].message
    idx_no_evidence = msg.find("no_evidence:")
    idx_manual_override = msg.find("manual_override:")
    assert idx_no_evidence != -1 and idx_manual_override != -1
    assert idx_no_evidence < idx_manual_override


@pytest.mark.asyncio
async def test_digest_message_all_five_reasons_render(manager):
    """When every member is present with count ≥1, all 5 lines render in order."""
    await manager.send_daily_summary(
        total_pnl=0.0,
        total_trades=0,
        win_rate=0.0,
        balance=1000.0,
        ml_gate_reason_counts={
            "no_evidence": 1,
            "dsr_below_gate": 2,
            "evidence_stale": 3,
            "regime_shift": 4,
            "manual_override": 5,
        },
    )
    msg = manager._captured[0].message
    assert "ML Gate Reasons (24h):" in msg
    for reason, count in [
        ("no_evidence", 1),
        ("dsr_below_gate", 2),
        ("evidence_stale", 3),
        ("regime_shift", 4),
        ("manual_override", 5),
    ]:
        assert f"- {reason}: {count}" in msg
    # Verify canonical order.
    indices = [
        msg.find("no_evidence:"),
        msg.find("dsr_below_gate:"),
        msg.find("evidence_stale:"),
        msg.find("regime_shift:"),
        msg.find("manual_override:"),
    ]
    assert indices == sorted(indices), f"reason order is not canonical: {indices}"


@pytest.mark.asyncio
async def test_digest_metadata_carries_reason_counts(manager):
    """The raw counts dict must appear under metadata for downstream consumers."""
    counts = {"no_evidence": 5}
    await manager.send_daily_summary(
        total_pnl=0.0,
        total_trades=0,
        win_rate=0.0,
        balance=1000.0,
        ml_gate_reason_counts=counts,
    )
    captured = manager._captured[0]
    assert captured.metadata is not None
    assert captured.metadata.get("ml_gate_reason_counts") == counts


@pytest.mark.asyncio
async def test_digest_metadata_omits_counts_key_when_none(manager):
    """When kwarg is None, metadata MUST NOT carry an ml_gate_reason_counts key."""
    await manager.send_daily_summary(
        total_pnl=0.0,
        total_trades=0,
        win_rate=0.0,
        balance=1000.0,
    )
    captured = manager._captured[0]
    assert captured.metadata is not None
    assert "ml_gate_reason_counts" not in captured.metadata
