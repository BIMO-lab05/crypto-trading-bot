"""
DEFER-21-01 REGRESSION NET: a non-unique index must fail LOUDLY, never vanish.

Run:
    cd services/technical-analysis && \
        python3 -m pytest tests/test_sqzmom_duplicate_index.py --no-cov -q

TA tests are cwd-sensitive: run them from `services/technical-analysis`, always
with `--no-cov` (`pytest.ini` injects `--cov --strict-config` otherwise).

WHAT THIS PINS
--------------
`EnhancedSqueezeMomentum.calculate` used to return `None` when the input frame
carried a duplicate index label. A label lookup on a non-unique index returns a
Series rather than a scalar -- `prev_momentum.loc[row.name]` inside the
`sqz_color` apply, and `result_df.loc[:row.name, 'squeeze_on']` inside the
confidence closure -- so the surrounding arithmetic raised
`ValueError: truth value of a Series is ambiguous`, and the broad
`except Exception` at the end of `calculate` swallowed it into a `None`.

That `None` was invisible downstream. `app/handlers/analysis.py:146` guards
`if sqz_df is not None and not sqz_df.empty`, so the SQZMOM leg simply VANISHED
from the aggregate vote: the endpoint returned a well-formed 200 computed from
one fewer voter, and `"sqzmom": null` in the response was the only trace. A
silent `None` from a voting indicator is the harder failure mode to notice.

This is not theoretical. TimescaleDB kline history in this repo has a documented
record of holes and repairs, so a duplicate timestamp reaching the indicator is
a live possibility.

WHY THIS TEST COULD NOT LAND IN 21-01
-------------------------------------
It would have been red. `.claude/rules/testing.md` forbids landing a red test,
or marking one xfail/skip without a tracking requirement ID, so plan 21-01
recorded DEFER-21-01 as a deferred item instead of shipping the test. Here the
test ships together with the fix, so it lands green.

WHY THE GUARD SITS BEFORE THE `try`
-----------------------------------
Placement is load-bearing, and the one-ERROR-record assertion in
`test_duplicate_index_logs_before_raising` is what proves it. Inside the `try`,
the module's own `except Exception` would swallow the guard's `ValueError`
straight back into the `None` this item exists to remove.

WHY THE DUPLICATE MUST LAND PAST WARM-UP (measured, not assumed)
----------------------------------------------------------------
`_determine_histogram_color` opens with
`if pd.isna(momentum) or pd.isna(prev_momentum)`. Python's `or` SHORT-CIRCUITS,
so on a warm-up bar -- where `sqz_momentum` is still NaN -- the first operand is
already True and the ambiguous `pd.isna(<2-element Series>)` is never evaluated.
The duplicate therefore passes through silently and `calculate` returns a normal
frame.

Measured on this fixture: `sqz_momentum` is NaN for positions 0-29, first valid
at position 30. Duplicating at position 10 (the example DEFER-21-01 and the plan
both suggest) returns a full DataFrame and logs NOTHING. Duplicating at 101, 201
or 251 returns `None` and logs
`Error calculating Enhanced Squeeze Momentum: The truth value of a Series is
ambiguous`.

So DUP_DST sits at 201, well past warm-up, and
`test_duplicate_index_raises_instead_of_dropping_the_leg` asserts the chosen bar
really is past warm-up. Without that assertion this whole suite would pass
against a warm-up duplicate while the real defect went untested.

SCOPE
-----
The fix rejects the input at the top of `calculate`. The full positional-indexing
rewrite of every `.loc[row.name]` site is explicitly deferred (22.1-CONTEXT
"Deferred Ideas") and is unnecessary once the input is rejected up front.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from app.config import get_settings
from app.indicators.sqzmom_enhanced import EnhancedSqueezeMomentum

SETTINGS = get_settings()

# 400 bars, matching tests/test_leakage_regression.py. The minimum-periods check
# in `calculate` is max(bb_length, kc_length, momentum_length) + 5; sitting well
# clear of it keeps this suite testing the index guard rather than accidentally
# exercising the insufficient-data path, which still returns None by design.
BARS = 400

# The row whose label gets copied over its neighbour. This MUST sit past the
# momentum warm-up (NaN for positions 0-29 on this fixture) or the short-circuit
# in `_determine_histogram_color` hides the defect entirely -- see the module
# docstring. 201 matches the leakage suite's post-warm-up probe convention.
DUP_SRC = 200
DUP_DST = 201

LOGGER_NAME = "app.indicators.sqzmom_enhanced"


def _synthetic_ohlcv(seed: int = 42, n: int = BARS) -> pd.DataFrame:
    """Deterministic, non-degenerate OHLCV on an hourly DatetimeIndex.

    Same builder shape as tests/test_leakage_regression.py. Seeded with numpy's
    default_rng so the frame is byte-identical on every run and machine -- a
    flaky fixture would make a real regression look like noise.
    """
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    high = close * (1 + rng.uniform(0.000, 0.006, n))
    low = close * (1 - rng.uniform(0.000, 0.006, n))
    return pd.DataFrame(
        {
            "open": np.r_[close[0], close[:-1]],
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(800, 1500, n),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="1h"),
    )


def _with_duplicate_label(df: pd.DataFrame) -> pd.DataFrame:
    """Copy one index label over the next one, producing exactly one duplicate.

    Rebuilds the axis rather than mutating `df.index.values` in place: that
    buffer can be read-only, and the write then either raises or silently
    no-ops depending on the pandas version. A silent no-op would leave a
    unique-index frame behind and make the rejection tests vacuous.
    """
    labels = df.index.to_numpy().copy()
    labels[DUP_DST] = labels[DUP_SRC]
    return df.set_axis(pd.DatetimeIndex(labels))


def _calculator() -> EnhancedSqueezeMomentum:
    """Resolve every knob from TA Settings, as app/handlers/analysis.py:80-86 does.

    Constructing with literals would test a parameterisation the service never
    runs.
    """
    return EnhancedSqueezeMomentum(
        bb_length=SETTINGS.default_sqzmom_bb_period,
        bb_mult=SETTINGS.default_sqzmom_bb_mult,
        kc_length=SETTINGS.default_sqzmom_kc_period,
        kc_mult=SETTINGS.default_sqzmom_kc_mult,
        momentum_length=SETTINGS.default_sqzmom_mom_period,
    )


def _duplicated_labels(df: pd.DataFrame) -> list:
    return [str(label) for label in df.index[df.index.duplicated()].unique()]


def test_duplicate_index_raises_instead_of_dropping_the_leg():
    """A duplicate label must raise, not return None.

    The pre-fix behaviour was `calculate(...) is None`, which the caller guard
    at handlers/analysis.py:146 converts into a silently one-voter-short vote.
    """
    df = _with_duplicate_label(_synthetic_ohlcv())

    # Guard the fixture itself. If a future pandas made the duplication a no-op,
    # every assertion below would pass against a unique-index frame and this
    # suite would go quiet on the defect it exists to catch.
    assert df.index.is_unique is False, (
        "fixture stopped reproducing the duplicate-index condition; the "
        "rejection tests below would be vacuous"
    )
    assert len(df) == BARS, "duplication must not change the row count"

    # The duplicate must land past the momentum warm-up. On a warm-up bar,
    # `_determine_histogram_color`'s `pd.isna(momentum) or ...` short-circuits
    # before touching the ambiguous Series, the frame computes cleanly, and this
    # whole suite would go green against code that never got the guard. This is
    # not hypothetical: duplicating at position 10 does exactly that.
    warm_up_reference = _calculator().calculate(_synthetic_ohlcv())
    assert warm_up_reference is not None
    assert not pd.isna(warm_up_reference["sqz_momentum"].iloc[DUP_DST]), (
        f"position {DUP_DST} is still in the momentum warm-up (sqz_momentum is "
        f"NaN there), so the duplicate would be short-circuited past and this "
        f"test would prove nothing -- move DUP_DST later"
    )

    duplicated = _duplicated_labels(df)
    assert len(duplicated) == 1, (
        f"expected exactly one duplicated label, got {duplicated}"
    )

    with pytest.raises(ValueError) as excinfo:
        _calculator().calculate(df)

    message = str(excinfo.value)
    assert duplicated[0] in message, (
        f"the raised error must name the duplicated label so an operator can "
        f"find the offending candles; got: {message!r}"
    )


def test_duplicate_index_logs_before_raising(caplog):
    """Exactly one ERROR record, and it must be the guard's.

    Asserting merely that "an ERROR record exists" would be satisfied by the
    PRE-FIX code too: the broad `except Exception` at the end of `calculate`
    already logged `Error calculating Enhanced Squeeze Momentum: ...` on its way
    to returning None. Discriminating on count and content is what makes this
    test able to tell the loud rejection apart from the silent swallow.

    caplog is pointed at this module's logger explicitly rather than relying on
    propagation config, which the service configures at app startup.
    """
    df = _with_duplicate_label(_synthetic_ohlcv())
    assert df.index.is_unique is False
    duplicated = _duplicated_labels(df)

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        with pytest.raises(ValueError):
            _calculator().calculate(df)

    errors = [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.levelno == logging.ERROR
    ]
    assert len(errors) == 1, (
        f"expected exactly one ERROR record (the guard's). More than one means "
        f"the raise travelled through the broad except handler, i.e. the guard "
        f"was placed inside the try. Got: {[r.getMessage() for r in errors]}"
    )

    message = errors[0].getMessage()
    assert duplicated[0] in message, (
        f"the logged error must name the duplicated label; got: {message!r}"
    )
    assert "unique" in message.lower(), (
        f"the logged error must say why the frame was rejected; got: {message!r}"
    )


def test_unique_index_still_computes():
    """Control: the guard must reject duplicates, not everything.

    Without this, the rejection test would still pass if the check degenerated
    into an unconditional raise -- which would take the aggregate-signal
    endpoint down on good data.
    """
    df = _synthetic_ohlcv()
    assert df.index.is_unique is True

    result = _calculator().calculate(df)

    assert result is not None, "a unique-index frame must still compute"
    assert not result.empty
    # The two columns app/handlers/analysis.py:146-151 reads off the last row.
    for column in ("sqz_signal", "sqz_confidence"):
        assert column in result.columns, (
            f"aggregator reads {column!r}; it must be present"
        )
