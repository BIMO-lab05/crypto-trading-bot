"""
Tests for chunk 4 of T0.1 — the rebuild script's pure helpers and the
``retrain_gru_units`` setting plumbing.

The script lives at ``docs/strategy/research-2026-04-29/T0_1_rebuild.py``
because it's research output (mirrors ``persistence_shootout.py`` from
the V0 work). These tests cover only the TF-free surface:

- ``retrain_gru_units`` Pydantic field: default, JSON-string parsing,
  validation of positive ints.
- :func:`verdict_for_row` — per-gate pass/fail logic with the design
  doc's thresholds (R²-returns ≥ 0.0, dir-acc ≥ 0.55, DSR ≥ 0.95).
- :func:`render_markdown_table` — table shape, error rows, missing-
  value rendering.
- :func:`render_markdown_report` — full report format covering both
  passing and error rows.

The TF-required halves (``train_and_evaluate``, ``main``) are
integration code; verifying them needs the container.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Settings field
# ---------------------------------------------------------------------------


from app.config.settings import RetrainingSettings  # noqa: E402


class TestRetrainGruUnitsSetting:
    def test_default_is_legacy_two_layer(self):
        with patch.dict(os.environ, {}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_gru_units == [128, 64]

    def test_env_json_string_parsed(self):
        with patch.dict(os.environ, {"RETRAIN_GRU_UNITS": "[32]"}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_gru_units == [32]

    def test_env_multilayer_parsed(self):
        with patch.dict(
            os.environ, {"RETRAIN_GRU_UNITS": "[128, 64, 32]"}, clear=True
        ):
            s = RetrainingSettings()
        assert s.retrain_gru_units == [128, 64, 32]

    def test_invalid_json_rejected(self):
        from pydantic import ValidationError
        with patch.dict(
            os.environ, {"RETRAIN_GRU_UNITS": "32"}, clear=True
        ):
            with pytest.raises(ValidationError):
                RetrainingSettings()

    def test_empty_list_rejected(self):
        from pydantic import ValidationError
        with patch.dict(os.environ, {"RETRAIN_GRU_UNITS": "[]"}, clear=True):
            with pytest.raises(ValidationError):
                RetrainingSettings()

    def test_zero_or_negative_rejected(self):
        from pydantic import ValidationError
        for bad in ("[0]", "[-1]", "[32, 0]", "[32, -16]"):
            with patch.dict(os.environ, {"RETRAIN_GRU_UNITS": bad}, clear=True):
                with pytest.raises(ValidationError):
                    RetrainingSettings()

    def test_non_int_rejected(self):
        from pydantic import ValidationError
        for bad in ("[32.5]", '["32"]', "[true]"):
            with patch.dict(os.environ, {"RETRAIN_GRU_UNITS": bad}, clear=True):
                with pytest.raises(ValidationError):
                    RetrainingSettings()


# ---------------------------------------------------------------------------
# Make the rebuild script importable as a module despite living under
# docs/strategy/research-2026-04-29/. The persistence_shootout.py
# precedent does the same trick.
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPT_PATH = (
    _REPO_ROOT
    / "docs"
    / "strategy"
    / "research-2026-04-29"
    / "T0_1_rebuild.py"
)


def _load_rebuild_module():
    spec = importlib.util.spec_from_file_location("t0_1_rebuild", _SCRIPT_PATH)
    if spec is None or spec.loader is None:
        pytest.skip(f"could not load rebuild script: {_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["t0_1_rebuild"] = module
    spec.loader.exec_module(module)
    return module


# Module-level fixture so every test in this file shares one load.
@pytest.fixture(scope="module")
def rebuild():
    return _load_rebuild_module()


# ---------------------------------------------------------------------------
# verdict_for_row
# ---------------------------------------------------------------------------


class TestVerdictForRow:
    def test_all_three_pass_yields_three_passed_gates(self, rebuild):
        gates = rebuild.verdict_for_row(
            {
                "test_r2_returns": 0.05,
                "test_dir_acc_corrected": 0.62,
                "test_dsr": 0.97,
            }
        )
        assert gates["r2_returns"].passed is True
        assert gates["dir_acc_corrected"].passed is True
        assert gates["dsr"].passed is True

    def test_all_three_fail(self, rebuild):
        gates = rebuild.verdict_for_row(
            {
                "test_r2_returns": -0.5,
                "test_dir_acc_corrected": 0.50,
                "test_dsr": 0.10,
            }
        )
        assert all(g.passed is False for g in gates.values())

    def test_missing_keys_fail(self, rebuild):
        # Empty dict → all three gates fail (treated as missing).
        gates = rebuild.verdict_for_row({})
        assert all(g.passed is False for g in gates.values())

    def test_nan_fails(self, rebuild):
        gates = rebuild.verdict_for_row(
            {
                "test_r2_returns": float("nan"),
                "test_dir_acc_corrected": float("nan"),
                "test_dsr": float("nan"),
            }
        )
        assert all(g.passed is False for g in gates.values())

    def test_threshold_overrides_apply(self, rebuild):
        # Lower DSR threshold → 0.50 now passes.
        gates = rebuild.verdict_for_row(
            {"test_dsr": 0.50, "test_r2_returns": 0.0, "test_dir_acc_corrected": 0.55},
            thresholds={"r2_returns": 0.0, "dir_acc_corrected": 0.55, "dsr": 0.40},
        )
        assert gates["dsr"].passed is True


class TestOverallVerdict:
    def test_all_pass(self, rebuild):
        gates = rebuild.verdict_for_row(
            {
                "test_r2_returns": 0.10,
                "test_dir_acc_corrected": 0.65,
                "test_dsr": 0.99,
            }
        )
        assert "pass" in rebuild.overall_verdict(gates)

    def test_one_fails_overall_fails(self, rebuild):
        gates = rebuild.verdict_for_row(
            {
                "test_r2_returns": 0.10,
                "test_dir_acc_corrected": 0.65,
                "test_dsr": 0.05,
            }
        )
        assert "fail" in rebuild.overall_verdict(gates)


# ---------------------------------------------------------------------------
# render_markdown_table
# ---------------------------------------------------------------------------


class TestRenderMarkdownTable:
    def test_header_present_and_one_row_per_result(self, rebuild):
        results = [
            {
                "symbol": "SOLUSDT",
                "test_r2_returns": 0.05,
                "test_dir_acc_corrected": 0.62,
                "test_dsr": 0.97,
            },
            {
                "symbol": "BNBUSDT",
                "test_r2_returns": -0.2,
                "test_dir_acc_corrected": 0.49,
                "test_dsr": 0.10,
            },
        ]
        out = rebuild.render_markdown_table(results)
        # Markdown header + separator + 2 data rows = 4 lines + trailing nl.
        rows = [l for l in out.splitlines() if l.startswith("|")]
        assert len(rows) == 4
        assert "Symbol" in rows[0]
        assert "SOLUSDT" in rows[2]
        assert "BNBUSDT" in rows[3]

    def test_error_row_renders_as_error_cells(self, rebuild):
        results = [{"symbol": "SOLUSDT", "error": "no CSV found"}]
        out = rebuild.render_markdown_table(results)
        # Error rows should contain the error message and ❌
        assert "no CSV found" in out
        assert "❌" in out
        assert "_error_" in out

    def test_missing_metric_renders_n_a(self, rebuild):
        results = [
            {
                "symbol": "ADAUSDT",
                "test_r2_returns": 0.05,
                # no dir_acc, no dsr
            }
        ]
        out = rebuild.render_markdown_table(results)
        assert "_n/a_" in out

    def test_thresholds_appear_in_header(self, rebuild):
        out = rebuild.render_markdown_table(
            [{"symbol": "X"}],
            thresholds={"r2_returns": 0.1, "dir_acc_corrected": 0.6, "dsr": 0.99},
        )
        assert "0.1" in out
        assert "0.6" in out
        assert "0.99" in out


class TestRenderMarkdownReport:
    def test_report_includes_header_table_and_per_symbol_section(self, rebuild):
        results = [
            {
                "symbol": "SOLUSDT",
                "test_r2": 0.10,
                "test_r2_returns": 0.05,
                "test_dir_acc_corrected": 0.62,
                "test_dsr": 0.97,
                "test_cpcv_n_paths": 45,
            }
        ]
        out = rebuild.render_markdown_report(results)
        assert "T0.1 GRU Rebuild" in out
        assert "Pre-flight gates" in out
        assert "Per-symbol detail" in out
        assert "SOLUSDT" in out
        assert "test_cpcv_n_paths" in out

    def test_error_row_in_report_does_not_crash(self, rebuild):
        results = [
            {"symbol": "SOLUSDT", "error": "boom"},
            {
                "symbol": "BNBUSDT",
                "test_r2_returns": 0.0,
                "test_dir_acc_corrected": 0.55,
                "test_dsr": 0.95,
            },
        ]
        out = rebuild.render_markdown_report(results)
        assert "boom" in out
        assert "BNBUSDT" in out


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
