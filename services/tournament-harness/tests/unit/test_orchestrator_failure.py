"""Unit tests for app.orchestrator.failure.classify — D-15 enum coverage."""


from app.orchestrator.failure import classify, VALID_FAILURE_REASONS


def test_success_path():
    state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    payload = {"status": "success"}
    assert classify(state, payload, None) == ("success", "")


def test_oom_via_oomkilled_flag():
    state = {"ExitCode": 1, "OOMKilled": True, "TimedOut": False}
    assert classify(state, None, None) == ("failed", "oom_killed")


def test_oom_via_exit_137():
    state = {"ExitCode": 137, "OOMKilled": False, "TimedOut": False}
    assert classify(state, None, None) == ("failed", "oom_killed")


def test_timeout_wins_over_exit():
    state = {"ExitCode": 137, "OOMKilled": False, "TimedOut": True}
    assert classify(state, None, None) == ("failed", "timeout")


def test_runner_emitted_nan_loss():
    state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    payload = {"status": "failed", "reason": "nan_loss"}
    assert classify(state, payload, None) == ("failed", "nan_loss")


def test_runner_emitted_db_unreachable():
    state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    payload = {"status": "failed", "reason": "db_unreachable"}
    assert classify(state, payload, None) == ("failed", "db_unreachable")


def test_runner_emitted_train_diverged():
    state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    payload = {"status": "failed", "reason": "train_diverged"}
    assert classify(state, payload, None) == ("failed", "train_diverged")


def test_invalid_runner_reason_falls_back_to_unknown():
    state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    payload = {"status": "failed", "reason": "operator_typed_nonsense"}
    assert classify(state, payload, None) == ("failed", "unknown")


def test_no_result_nonzero_exit_is_exit_nonzero():
    state = {"ExitCode": 2, "OOMKilled": False, "TimedOut": False}
    assert classify(state, None, None) == ("failed", "exit_nonzero")


def test_no_result_zero_exit_is_unknown():
    state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    assert classify(state, None, None) == ("failed", "unknown")


def test_validation_error_with_exit_nonzero():
    state = {"ExitCode": 1, "OOMKilled": False, "TimedOut": False}
    assert classify(state, {"status": "success"}, "metric out of range") == (
        "failed",
        "exit_nonzero",
    )


def test_validation_error_with_exit_zero_is_unknown():
    state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    assert classify(state, {"status": "success"}, "metric out of range") == (
        "failed",
        "unknown",
    )


def test_classifier_returns_only_d15_values():
    """All possible classify() outputs land in {success} ∪ VALID_FAILURE_REASONS."""
    for state in [
        {"ExitCode": 0, "OOMKilled": False, "TimedOut": False},
        {"ExitCode": 137, "OOMKilled": False, "TimedOut": False},
        {"ExitCode": 1, "OOMKilled": True, "TimedOut": False},
        {"ExitCode": 1, "OOMKilled": False, "TimedOut": True},
        {"ExitCode": 0, "OOMKilled": False, "TimedOut": False},
    ]:
        for payload in [
            None,
            {"status": "failed", "reason": "nan_loss"},
            {"status": "success"},
        ]:
            for verr in [None, "schema mismatch"]:
                status, reason = classify(state, payload, verr)
                assert status in {"success", "failed"}
                if status == "success":
                    assert reason == ""
                else:
                    assert reason in VALID_FAILURE_REASONS
