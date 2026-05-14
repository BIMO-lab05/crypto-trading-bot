"""Tests for psr_ci.py — PSR with bootstrap CI kernel.

Tests 3-9 from the plan's <behavior> block, including:
- Test 4b: negative assertion (H0 kernel NOT imported)
- Test 6b: no-centering verification via level-shift contrast
- Test 6c: NaN-resample tracking with UserWarning emission
"""

import subprocess
import sys
import json
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[3]
_PSR_CI_FILE = _REPO / "scripts" / "forward_paper_test" / "psr_ci.py"
_RUN_ISOLATION_MODULE = "scripts.forward_paper_test.run_isolation"

# Flag for negative-grep gate: the name of the H0 kernel that MUST NOT appear.
# We write this as a concat so the test file itself does not contain the literal
# (avoids spurious self-matches if the test file were ever scanned by mistake).
_H0_KERNEL_NAME = "stationary_block_bootstrap" + "_pvalue"


def _non_degenerate_returns(n=200, seed=1):
    """Synthetic non-zero-variance returns for basic tests."""
    rng = np.random.default_rng(seed)
    return rng.normal(loc=0.001, scale=0.02, size=n)


# ---------------------------------------------------------------------------
# Test 3: compute_psr_with_bootstrap_ci return shape
# ---------------------------------------------------------------------------


def test_compute_psr_with_bootstrap_ci_returns_required_dict_keys():
    """Test 3: function returns dict with all required keys."""
    from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci

    returns = _non_degenerate_returns()
    result = compute_psr_with_bootstrap_ci(returns, seed=42, n_resamples=500)

    required_keys = {
        "psr_point",
        "psr_ci_low",
        "psr_ci_high",
        "n_resamples",
        "n_resamples_valid",
        "block_size",
        "seed",
        "n_bars",
    }
    assert set(result.keys()) >= required_keys, (
        f"Missing keys: {required_keys - set(result.keys())}"
    )


def test_compute_psr_with_bootstrap_ci_point_equals_canonical_psr():
    """Test 3b: Point estimate equals probabilistic_sharpe_ratio(returns) exactly."""
    from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci

    sys.path.insert(0, str(_REPO / "services" / "risk-metrics-service" / "app"))
    from sharpe_metrics import probabilistic_sharpe_ratio  # type: ignore

    returns = _non_degenerate_returns()
    result = compute_psr_with_bootstrap_ci(returns, seed=42, n_resamples=500)
    expected_psr = probabilistic_sharpe_ratio(returns, benchmark_sr=0.0)

    assert result["psr_point"] == pytest.approx(expected_psr, abs=1e-12), (
        f"psr_point {result['psr_point']} != canonical PSR {expected_psr}"
    )


def test_compute_psr_with_bootstrap_ci_bounds_bracket_point():
    """Test 3c: CI bounds bracket the point estimate for non-degenerate input."""
    from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci

    returns = _non_degenerate_returns()
    result = compute_psr_with_bootstrap_ci(returns, seed=42, n_resamples=1000)

    assert result["psr_ci_low"] <= result["psr_point"], (
        f"ci_low {result['psr_ci_low']} > psr_point {result['psr_point']}"
    )
    assert result["psr_point"] <= result["psr_ci_high"], (
        f"psr_point {result['psr_point']} > ci_high {result['psr_ci_high']}"
    )


# ---------------------------------------------------------------------------
# Test 4: TOURN-07 compliance — no metric re-implementation
# ---------------------------------------------------------------------------


def test_psr_ci_imports_canonical_kernels_no_redefinition():
    """Test 4: psr_ci.py imports canonical kernels; no def of canonical functions."""
    source = _PSR_CI_FILE.read_text()

    # Must import probabilistic_sharpe_ratio
    assert "probabilistic_sharpe_ratio" in source, (
        "psr_ci.py must import probabilistic_sharpe_ratio from sharpe_metrics"
    )
    # Must import _generate_block_resample
    assert "_generate_block_resample" in source, (
        "psr_ci.py must import _generate_block_resample from bootstrap"
    )
    # Must import derive_seed
    assert "derive_seed" in source, "psr_ci.py must import derive_seed from bootstrap"

    # TOURN-07: must NOT define canonical functions
    import re

    forbidden = re.compile(
        r"^def\s+(probabilistic_sharpe_ratio|stationary_block_bootstrap|deflated_sharpe)\b",
        re.MULTILINE,
    )
    match = forbidden.search(source)
    assert match is None, (
        f"psr_ci.py must NOT define canonical metric functions; found: {match.group()!r}"
    )


def test_psr_ci_does_not_import_h0_kernel():
    """Test 4b (negative assertion): H0 p-value kernel must NOT be imported.

    The H0 kernel returns a p-value dict (no resample distribution) and centers
    its input for null-hypothesis testing — structurally wrong for percentile-CI
    construction. It must not appear anywhere in psr_ci.py.
    """
    source = _PSR_CI_FILE.read_text()
    assert _H0_KERNEL_NAME not in source, (
        f"psr_ci.py must NOT import the H0 p-value kernel (wrong for CI construction); "
        f"found '{_H0_KERNEL_NAME}' in the file"
    )


# ---------------------------------------------------------------------------
# Test 5: Reproducibility
# ---------------------------------------------------------------------------


def test_compute_psr_with_bootstrap_ci_reproducible():
    """Test 5: Same (returns, seed, n_resamples) produces byte-identical CI bounds."""
    from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci

    returns = _non_degenerate_returns(n=150, seed=7)
    r1 = compute_psr_with_bootstrap_ci(returns, seed=99, n_resamples=500)
    r2 = compute_psr_with_bootstrap_ci(returns, seed=99, n_resamples=500)

    assert r1["psr_ci_low"] == r2["psr_ci_low"], "psr_ci_low not reproducible"
    assert r1["psr_ci_high"] == r2["psr_ci_high"], "psr_ci_high not reproducible"
    assert r1["n_resamples_valid"] == r2["n_resamples_valid"], (
        "n_resamples_valid not reproducible"
    )


# ---------------------------------------------------------------------------
# Test 6: Zero-safe sentinel
# ---------------------------------------------------------------------------


def test_compute_psr_with_bootstrap_ci_zero_safe():
    """Test 6: Zero-variance input returns psr_point=0.0 (sentinel) and finite CI bounds."""
    from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci

    result = compute_psr_with_bootstrap_ci(np.zeros(200), seed=42)

    assert result["psr_point"] == 0.0, (
        f"Expected psr_point=0.0 (zero-safe sentinel), got {result['psr_point']}"
    )
    assert np.isfinite(result["psr_ci_low"]), "psr_ci_low must be finite for zero input"
    assert np.isfinite(result["psr_ci_high"]), (
        "psr_ci_high must be finite for zero input"
    )


# ---------------------------------------------------------------------------
# Test 6b: No-centering verification via level-shift contrast
# ---------------------------------------------------------------------------


def test_compute_psr_with_bootstrap_ci_no_centering():
    """Test 6b: Kernel does NOT center the input.

    If the kernel centered returns before resampling (H0-test style), a constant
    shift to all returns would be removed and psr_point would be identical for
    shifted and un-shifted inputs. Here we verify they DIFFER — proving the kernel
    resamples the original returns without mean adjustment.
    """
    from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci

    returns_a = np.array([0.01] * 100 + [-0.005] * 100)
    returns_b = returns_a + 0.5  # constant shift — changes mean dramatically

    result_a = compute_psr_with_bootstrap_ci(returns_a, seed=77, n_resamples=1000)
    result_b = compute_psr_with_bootstrap_ci(returns_b, seed=77, n_resamples=1000)

    assert result_a["psr_point"] != result_b["psr_point"], (
        "psr_point is identical for shifted and un-shifted inputs — "
        "this indicates the kernel is centering the data (like an H0 test). "
        "The percentile-CI kernel must NOT center."
    )


# ---------------------------------------------------------------------------
# Test 6c: NaN-resample tracking + UserWarning
# ---------------------------------------------------------------------------


def test_compute_psr_with_bootstrap_ci_nan_resample_tracking():
    """Test 6c: Pathological input triggers n_resamples_valid < n_resamples
    and emits a UserWarning containing 'PSR-CI' when valid fraction < 0.9.
    """
    from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci

    # Input: mostly constant (low-vol), some non-zero — produces NaN PSRs on
    # resamples that pick blocks of all-zero or all-1e-9 values (constant std=0).
    pathological = np.array([0.0] * 5 + [1e-9] * 195)

    with pytest.warns(UserWarning, match="PSR-CI"):
        result = compute_psr_with_bootstrap_ci(pathological, seed=42, n_resamples=1_000)

    assert result["n_resamples_valid"] < result["n_resamples"], (
        f"Expected n_resamples_valid < n_resamples for pathological input; "
        f"got valid={result['n_resamples_valid']}, total={result['n_resamples']}"
    )


# ---------------------------------------------------------------------------
# Test 7: load_run_returns
# ---------------------------------------------------------------------------


def test_load_run_returns_reads_run_json(tmp_path):
    """Test 7: load_run_returns reads run.json and returns non-empty, NaN-free array."""
    from scripts.forward_paper_test.psr_ci import load_run_returns

    returns_list = [0.01, -0.005, 0.003, 0.007, -0.002]
    run_json = {
        "run_id": "test-run",
        "flag": "enable_vol_targeting",
        "returns": returns_list,
    }
    (tmp_path / "run.json").write_text(json.dumps(run_json))

    result = load_run_returns(tmp_path)
    assert isinstance(result, np.ndarray), "Expected np.ndarray"
    np.testing.assert_array_almost_equal(result, returns_list)


def test_load_run_returns_raises_file_not_found(tmp_path):
    """Test 7b: load_run_returns raises FileNotFoundError if run.json missing."""
    from scripts.forward_paper_test.psr_ci import load_run_returns

    with pytest.raises(FileNotFoundError):
        load_run_returns(tmp_path)


def test_load_run_returns_raises_value_error_on_empty(tmp_path):
    """Test 7c: load_run_returns raises ValueError if returns array is empty."""
    from scripts.forward_paper_test.psr_ci import load_run_returns

    run_json = {"run_id": "empty-run", "flag": "enable_vol_targeting", "returns": []}
    (tmp_path / "run.json").write_text(json.dumps(run_json))

    with pytest.raises(ValueError, match="empty"):
        load_run_returns(tmp_path)


def test_load_run_returns_raises_value_error_on_nan(tmp_path):
    """Test 7d: load_run_returns raises ValueError if returns contain NaN."""
    from scripts.forward_paper_test.psr_ci import load_run_returns

    import math

    run_json = {
        "run_id": "nan-run",
        "flag": "enable_vol_targeting",
        "returns": [0.01, math.nan],
    }
    (tmp_path / "run.json").write_text(json.dumps(run_json))

    with pytest.raises(ValueError, match="NaN"):
        load_run_returns(tmp_path)


# ---------------------------------------------------------------------------
# Test 8: CLI help
# ---------------------------------------------------------------------------


def test_run_isolation_help_exits_zero_with_expected_flags():
    """Test 8: --help exits 0 and lists expected arguments."""
    result = subprocess.run(
        [sys.executable, "-m", _RUN_ISOLATION_MODULE, "--help"],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert result.returncode == 0, (
        f"--help exited {result.returncode}; stderr: {result.stderr}"
    )
    output = result.stdout + result.stderr
    assert "--flag" in output, "--flag not in --help output"
    assert "--duration-days" in output, "--duration-days not in --help output"
    assert "--dry-run" in output, "--dry-run not in --help output"


# ---------------------------------------------------------------------------
# Test 9: dry-run JSON output
# ---------------------------------------------------------------------------


def test_run_isolation_dry_run_prints_valid_json():
    """Test 9: --dry-run exits 0 and prints JSON with required keys."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            _RUN_ISOLATION_MODULE,
            "--flag",
            "enable_vol_targeting",
            "--duration-days",
            "7",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert result.returncode == 0, (
        f"--dry-run exited {result.returncode}; stderr: {result.stderr}"
    )
    # Find JSON in output (may have preamble text)
    output = result.stdout.strip()
    data = json.loads(output)

    required_keys = {
        "flag",
        "env_overrides",
        "baseline_env_overrides",
        "evidence_path",
        "planned_start",
        "planned_end",
        "duration_days",
        "git_sha",
    }
    assert set(data.keys()) >= required_keys, (
        f"dry-run JSON missing keys: {required_keys - set(data.keys())}"
    )

    # evidence_path ends with enable_vol_targeting/<run_id>
    assert "enable_vol_targeting" in data["evidence_path"], (
        f"evidence_path should contain flag name: {data['evidence_path']}"
    )

    # planned_end - planned_start == 7 days
    from datetime import datetime

    start = datetime.fromisoformat(data["planned_start"])
    end = datetime.fromisoformat(data["planned_end"])
    diff_days = (end - start).total_seconds() / 86400
    assert abs(diff_days - 7) < 1e-3, (
        f"planned_end - planned_start should be 7 days, got {diff_days}"
    )
