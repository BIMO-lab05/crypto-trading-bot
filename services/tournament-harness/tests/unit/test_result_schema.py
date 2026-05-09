"""Unit tests for app.leaderboard.result_schema.validate."""

import json
import pytest
from app.leaderboard.result_schema import (
    validate,
    MAX_RESULT_BYTES,
    VALID_FAILURE_REASONS,
)


def _success_payload(**overrides):
    base = {
        "status": "success",
        "run_id": "r1",
        "tournament_id": "t1",
        "architecture": "gru",
        "symbol": "SOLUSDT",
        "horizon": 5,
        "target_mode": "log_returns",
        "hp_hash": "deadbeef",
        "git_sha": "abc123",
        "tournament_start_ts": "2026-05-08T00:00:00",
        "metrics": {
            "r2_returns": 0.05,
            "dir_acc_corrected": 0.55,
            "oos_sharpe": 0.8,
            "psr": 0.7,
            "dsr": 0.55,
            "cpcv_dsr": 0.5,
            "train_seconds": 120.0,
        },
    }
    base.update(overrides)
    return base


def test_validate_happy_success():
    p = _success_payload()
    raw = json.dumps(p).encode()
    status, norm = validate(p, raw)
    assert status == "success"
    assert norm["failure_reason"] is None


def test_validate_size_cap():
    p = _success_payload()
    raw = b"x" * (MAX_RESULT_BYTES + 1)
    with pytest.raises(ValueError, match="exceeds 256KB"):
        validate(p, raw)


def test_validate_missing_required_field():
    p = _success_payload()
    del p["git_sha"]
    raw = json.dumps(p).encode()
    with pytest.raises(ValueError, match="missing required"):
        validate(p, raw)


def test_validate_bad_architecture():
    p = _success_payload(architecture="random_forest")
    raw = json.dumps(p).encode()
    with pytest.raises(ValueError, match="invalid architecture"):
        validate(p, raw)


def test_validate_bad_target_mode():
    p = _success_payload(target_mode="absolute_returns")
    raw = json.dumps(p).encode()
    with pytest.raises(ValueError, match="invalid target_mode"):
        validate(p, raw)


def test_validate_horizon_out_of_range():
    p = _success_payload(horizon=0)
    raw = json.dumps(p).encode()
    with pytest.raises(ValueError, match="horizon"):
        validate(p, raw)


def test_validate_metric_out_of_range():
    p = _success_payload()
    p["metrics"]["psr"] = 1.5
    raw = json.dumps(p).encode()
    with pytest.raises(ValueError, match="psr.*sanity range"):
        validate(p, raw)


def test_validate_metric_nan_rejected():
    p = _success_payload()
    p["metrics"]["dsr"] = float("nan")
    raw = json.dumps(p).encode()
    with pytest.raises(ValueError, match="finite number"):
        validate(p, raw)


def test_validate_failed_with_valid_reason():
    p = _success_payload(status="failed")
    p["reason"] = "nan_loss"
    raw = json.dumps(p).encode()
    status, norm = validate(p, raw)
    assert status == "failed"
    assert norm["failure_reason"] == "nan_loss"


def test_validate_failed_with_invalid_reason():
    p = _success_payload(status="failed")
    p["reason"] = "operator_pressed_ctrl_c"
    raw = json.dumps(p).encode()
    with pytest.raises(ValueError, match="failure_reason"):
        validate(p, raw)


def test_validate_failed_missing_reason():
    p = _success_payload(status="failed")
    raw = json.dumps(p).encode()
    with pytest.raises(ValueError, match="failure_reason"):
        validate(p, raw)


def test_validate_all_d15_enum_values_accepted():
    for r in VALID_FAILURE_REASONS:
        p = _success_payload(status="failed")
        p["reason"] = r
        raw = json.dumps(p).encode()
        status, norm = validate(p, raw)
        assert norm["failure_reason"] == r
