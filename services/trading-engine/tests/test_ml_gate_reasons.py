"""Unit tests for app.aggregation.ml_gate_reasons (MLGATE-03, Plan 09-03).

Covers:
- Enum tuple shape (exactly 5 members, exact membership).
- log_ml_disabled emits the load-bearing literal and increments the counter.
- log_ml_disabled rejects unknown reasons.
- Counter increment / snapshot return-a-copy semantics.
- D-09-03-06 cross-plan reason-state cache:
    * default before any auto-flip is "manual_override"
    * set_current_reason propagates to get_current_reason
    * set_current_reason rejects unknown reasons
    * log_ml_disabled's default-fallback reads get_current_reason
- Parametrized 5-reason reachability via the explicit-arg path AND via the
  cross-plan set_current_reason fallback path (closes checker Blocker 1).
"""

from __future__ import annotations

import logging

import pytest

from app.aggregation.ml_gate_reasons import (
    ML_GATE_REASONS,
    get_current_reason,
    log_ml_disabled,
    record_ml_gate_event,
    reset_counter,
    set_current_reason,
    snapshot_reasons,
)


def test_enum_tuple_has_exactly_five_members():
    assert len(ML_GATE_REASONS) == 5


def test_enum_tuple_members_match_spec():
    assert set(ML_GATE_REASONS) == {
        "no_evidence",
        "dsr_below_gate",
        "evidence_stale",
        "regime_shift",
        "manual_override",
    }


def test_log_ml_disabled_emits_literal_with_reason(caplog):
    reset_counter()
    caplog.set_level(logging.INFO, logger="app.aggregation.ml_gate_reasons")
    log_ml_disabled("no_evidence")
    # Load-bearing literal: "ML predictions disabled reason=<value>"
    assert "ML predictions disabled reason=no_evidence" in caplog.text


def test_log_ml_disabled_rejects_unknown_reason():
    with pytest.raises(ValueError) as ei:
        log_ml_disabled("bogus_reason")  # type: ignore[arg-type]
    assert "unknown ML gate reason" in str(ei.value)


def test_record_ml_gate_event_increments_counter():
    reset_counter()
    record_ml_gate_event("dsr_below_gate")
    record_ml_gate_event("dsr_below_gate")
    assert snapshot_reasons()["dsr_below_gate"] == 2


def test_record_ml_gate_event_rejects_unknown_reason():
    with pytest.raises(ValueError):
        record_ml_gate_event("bogus_reason")  # type: ignore[arg-type]


def test_snapshot_returns_copy_not_reference():
    """Mutating the returned dict must not corrupt internal counter state."""
    reset_counter()
    record_ml_gate_event("no_evidence")
    snap1 = snapshot_reasons()
    snap1["no_evidence"] = 999
    snap1["injected_key"] = 42
    snap2 = snapshot_reasons()
    assert snap2["no_evidence"] == 1
    assert "injected_key" not in snap2


def test_get_current_reason_defaults_to_manual_override():
    """D-09-03-06: before any auto-flip fires, the cache defaults to manual_override."""
    reset_counter()
    assert get_current_reason() == "manual_override"


def test_set_current_reason_propagates_to_get():
    reset_counter()
    set_current_reason("dsr_below_gate")
    assert get_current_reason() == "dsr_below_gate"


def test_set_current_reason_rejects_unknown():
    with pytest.raises(ValueError):
        set_current_reason("bogus")  # type: ignore[arg-type]


def test_log_ml_disabled_reads_current_reason_default(caplog):
    """D-09-03-06 cross-plan propagation proof — closes Blocker 1.

    When `log_ml_disabled()` is called with no explicit reason argument, it
    falls back to `get_current_reason()`. After `set_current_reason("evidence_stale")`
    the emission must name `evidence_stale`, not the prior default.
    """
    reset_counter()
    caplog.set_level(logging.INFO, logger="app.aggregation.ml_gate_reasons")
    set_current_reason("evidence_stale")
    log_ml_disabled()  # No explicit reason — must use the cached value.
    assert "ML predictions disabled reason=evidence_stale" in caplog.text
    assert snapshot_reasons()["evidence_stale"] == 1


@pytest.mark.parametrize("reason", list(ML_GATE_REASONS))
def test_all_five_reasons_reachable_via_explicit_arg(reason, caplog):
    """Closes Blocker 1 enum-reachability — explicit-arg path.

    Every one of the 5 enum members must be reachable as an explicit positional
    argument to `log_ml_disabled()` and produce the literal grep gate anchor.
    """
    reset_counter()
    caplog.set_level(logging.INFO, logger="app.aggregation.ml_gate_reasons")
    log_ml_disabled(reason)
    expected_substring = f"reason={reason}"
    assert expected_substring in caplog.text
    assert snapshot_reasons()[reason] == 1


@pytest.mark.parametrize("reason", list(ML_GATE_REASONS))
def test_all_five_reasons_reachable_via_set_current_reason(reason, caplog):
    """Closes Blocker 1 enum-reachability — auto-flip propagation path.

    Every one of the 5 enum members must be reachable via the cross-plan
    default-fallback (Plan 09-02 writes via `set_current_reason`, this plan's
    emission sites read via `log_ml_disabled()` with no explicit reason).
    """
    reset_counter()
    caplog.set_level(logging.INFO, logger="app.aggregation.ml_gate_reasons")
    set_current_reason(reason)
    log_ml_disabled()  # No explicit arg — exercises the default-fallback path.
    assert snapshot_reasons()[reason] == 1
    expected_substring = f"reason={reason}"
    assert expected_substring in caplog.text


def test_reset_counter_clears_both_counter_and_current_reason():
    """reset_counter() must wipe BOTH state slots so tests don't leak state."""
    set_current_reason("dsr_below_gate")
    record_ml_gate_event("no_evidence")
    reset_counter()
    assert snapshot_reasons() == {}
    assert get_current_reason() == "manual_override"
