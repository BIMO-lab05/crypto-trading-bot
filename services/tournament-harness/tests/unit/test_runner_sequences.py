"""Unit tests for app.runner.sequences."""

import numpy as np
import pandas as pd
import pytest

from app.runner.sequences import create_sequences


def test_create_sequences_shape():
    df = pd.DataFrame(
        {
            "f1": np.arange(100.0),
            "f2": np.arange(100.0) * 2,
            "close": np.arange(100.0) + 5,
        }
    )
    X, y = create_sequences(
        df, "close", ["f1", "f2"], sequence_length=10, prediction_horizon=3
    )
    # n = 100 - 10 - 3 + 1 = 88
    assert X.shape == (88, 10, 2)
    assert y.shape == (88, 3)


def test_create_sequences_chronological_no_shuffle():
    df = pd.DataFrame(
        {
            "f1": np.arange(20.0),
            "close": np.arange(20.0),
        }
    )
    X, y = create_sequences(
        df, "close", ["f1"], sequence_length=5, prediction_horizon=2
    )
    # Window 0: features rows 0..4 = [0,1,2,3,4]; target rows 5..6 = [5,6]
    np.testing.assert_array_equal(X[0, :, 0], np.arange(5.0))
    np.testing.assert_array_equal(y[0], np.array([5.0, 6.0]))


def test_create_sequences_rejects_missing_target():
    df = pd.DataFrame({"f1": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="target_col"):
        create_sequences(df, "close", ["f1"], sequence_length=2, prediction_horizon=1)


def test_create_sequences_rejects_missing_feature():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="feature_cols missing"):
        create_sequences(df, "close", ["f1"], sequence_length=2, prediction_horizon=1)


def test_create_sequences_rejects_too_few_rows():
    df = pd.DataFrame({"f1": [1.0] * 5, "close": [1.0] * 5})
    with pytest.raises(ValueError, match="not enough rows"):
        create_sequences(df, "close", ["f1"], sequence_length=10, prediction_horizon=5)
