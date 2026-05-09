"""
T0.1 GRU rebuild — one-shot research script.

Trains the rebuild candidate (target=log_returns, feature_set=stationary,
gru_units=[32]) on each production symbol and emits a per-symbol report
covering the four pre-flight gates from the design doc §4 (R²-returns,
dir-acc-corrected, DSR, forward-paper Sharpe — last is operator-driven
and not measured here).

The script does NOT bypass the trainer. It mutates env vars so
``ModelTrainer()`` reads the rebuild settings, then calls
``train_model`` like any other retrain. Outputs land at
``docs/strategy/research-2026-04-29/T0.1-rebuild-results.{json,md}``.

Run inside the ml-retraining container so tensorflow + sklearn + pandas
are all in scope:

    docker compose -f docker-compose.unified.yml exec ml-retraining \\
        python docs/strategy/research-2026-04-29/T0_1_rebuild.py \\
            --data-dir /tmp/rebuild/data \\
            --output-dir docs/strategy/research-2026-04-29

CSV inputs follow the persistence_shootout convention:
``{SYMBOL}_1H_*.csv`` with the standard OHLCV columns
(``timestamp, open, high, low, close, volume``).

Two halves of this file:

- :func:`train_and_evaluate` (TF-required) does the actual training. It
  is a regular import path so the docker exec invocation is trivial.
- :func:`verdict_for_row` and :func:`render_markdown_table` are pure
  pandas/numpy + stdlib so they unit-test cleanly without TF and can
  be reused by chunk 5 (which renders the deploy / no-edge-found
  decision).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


SYMBOLS_DEFAULT = ("SOLUSDT", "BNBUSDT", "ADAUSDT")
DEFAULT_THRESHOLDS = {
    "r2_returns": 0.0,
    "dir_acc_corrected": 0.55,
    "dsr": 0.95,
}
ENV_OVERRIDES = {
    "RETRAIN_TARGET_MODE": "log_returns",
    "RETRAIN_FEATURE_SET": "stationary",
    "RETRAIN_GRU_UNITS": "[32]",
}


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers — no TF dependency, unit-testable
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    name: str
    value: Optional[float]
    threshold: float
    passed: bool  # False also when value is missing or NaN

    @property
    def cell(self) -> str:
        if self.value is None or (
            isinstance(self.value, float) and math.isnan(self.value)
        ):
            return f"_n/a_ {'❌' if self.passed is False else ''}"
        marker = "✅" if self.passed else "❌"
        return f"{self.value:+.4f} {marker}"


def verdict_for_row(
    metrics: Dict[str, Any],
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, GateResult]:
    """
    Apply the three in-script gates to one symbol's metrics dict.

    Args:
        metrics: dict containing ``test_r2_returns`` /
            ``test_dir_acc_corrected`` / ``test_dsr`` (keys can be
            missing — treated as failure).
        thresholds: per-gate threshold dict; defaults to
            :data:`DEFAULT_THRESHOLDS`. Each gate is a "value >= threshold"
            check; missing or NaN value fails.

    Returns:
        ``{"r2_returns": GateResult, "dir_acc_corrected": GateResult,
            "dsr": GateResult}``.
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    def _gate(metric_key: str, gate_key: str) -> GateResult:
        v = metrics.get(metric_key)
        threshold = thresholds[gate_key]
        if v is None or (isinstance(v, float) and math.isnan(v)):
            passed = False
        else:
            passed = v >= threshold
        return GateResult(
            name=gate_key, value=v, threshold=threshold, passed=passed
        )

    return {
        "r2_returns": _gate("test_r2_returns", "r2_returns"),
        "dir_acc_corrected": _gate("test_dir_acc_corrected", "dir_acc_corrected"),
        "dsr": _gate("test_dsr", "dsr"),
    }


def overall_verdict(gates: Dict[str, GateResult]) -> str:
    """Single-line verdict: '✅ pass' iff all three gates pass, else '❌ fail'."""
    return "✅ pass" if all(g.passed for g in gates.values()) else "❌ fail"


def render_markdown_table(
    results: Sequence[Dict[str, Any]],
    thresholds: Optional[Dict[str, float]] = None,
) -> str:
    """
    Build the rebuild-results markdown table.

    Each row is one symbol. Columns: symbol, R²(returns), dir-acc, DSR,
    overall verdict. Failures show ``❌`` next to the value; passes show
    ``✅``. Missing values render as ``_n/a_``.

    Args:
        results: list of per-symbol dicts. Each must contain at least
            ``"symbol"`` and any subset of the gate keys
            (``test_r2_returns`` / ``test_dir_acc_corrected`` / ``test_dsr``).
            Optionally ``"error"`` for symbols whose run failed entirely.
        thresholds: see :func:`verdict_for_row`.

    Returns:
        Markdown-formatted string ending with one trailing newline.
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    headers = (
        "Symbol",
        f"R²(returns) ≥ {thresholds['r2_returns']}",
        f"Dir.Acc ≥ {thresholds['dir_acc_corrected']}",
        f"DSR ≥ {thresholds['dsr']}",
        "Verdict",
    )
    lines: List[str] = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")

    for row in results:
        symbol = row.get("symbol", "?")
        if row.get("error"):
            lines.append(
                f"| {symbol} | _error_ | _error_ | _error_ | "
                f"❌ {row['error']} |"
            )
            continue
        gates = verdict_for_row(row, thresholds=thresholds)
        verdict = overall_verdict(gates)
        lines.append(
            "| "
            + " | ".join(
                [
                    symbol,
                    gates["r2_returns"].cell,
                    gates["dir_acc_corrected"].cell,
                    gates["dsr"].cell,
                    verdict,
                ]
            )
            + " |"
        )

    return "\n".join(lines) + "\n"


def render_markdown_report(
    results: Sequence[Dict[str, Any]],
    thresholds: Optional[Dict[str, float]] = None,
) -> str:
    """Full report: header + table + per-symbol diagnostic detail."""
    body: List[str] = [
        "# T0.1 GRU Rebuild — Results",
        "",
        "Auto-generated by `T0_1_rebuild.py`. Each symbol was trained with",
        "`target_mode=log_returns`, `feature_set=stationary`,",
        "`gru_units=[32]`. The forward-paper Sharpe gate (≥ 0.5 net of",
        "fees, ≥ 7 days) is operator-driven and lives outside this script —",
        "see `T0.1-gru-rebuild-design.md` §4.",
        "",
        "## Pre-flight gates",
        "",
        render_markdown_table(results, thresholds=thresholds),
    ]

    body.append("## Per-symbol detail\n")
    for row in results:
        symbol = row.get("symbol", "?")
        body.append(f"### {symbol}\n")
        if row.get("error"):
            body.append(f"- error: `{row['error']}`\n")
            continue
        for key in (
            "test_r2",
            "test_r2_returns",
            "test_dir_acc_corrected",
            "test_dsr",
            "test_cpcv_sharpe_mean",
            "test_cpcv_sharpe_std",
            "test_cpcv_sharpe_ci_low",
            "test_cpcv_sharpe_ci_high",
            "test_cpcv_n_paths",
            "test_cpcv_n_samples",
            "test_cpcv_oos_sharpe",
        ):
            v = row.get(key)
            if v is None:
                continue
            if isinstance(v, float):
                body.append(f"- `{key}`: {v:+.6f}")
            else:
                body.append(f"- `{key}`: {v}")
        body.append("")

    return "\n".join(body) + "\n"


# ---------------------------------------------------------------------------
# TF-required: actual training
# ---------------------------------------------------------------------------


def train_and_evaluate(
    symbol: str,
    csv_path: Path,
    test_size: float = 0.2,
    validation_split: float = 0.2,
) -> Dict[str, Any]:
    """
    Train one symbol's rebuild candidate and return the test metrics.

    Reads OHLCV from ``csv_path``, instantiates a fresh ``ModelTrainer``
    (which reads the env-set rebuild settings), runs ``train_model``, and
    flattens the relevant test_metrics + identifying info into a single
    dict suitable for :func:`render_markdown_table`.

    Importing ``pandas`` and ``app.core.model_trainer`` here keeps the
    pure-helper section above usable without TF.

    Args:
        symbol: symbol label (e.g. ``"SOLUSDT"``). Used for logging only;
            the trainer derives nothing from it beyond metadata.
        csv_path: OHLCV CSV with the standard columns.
        test_size, validation_split: passed straight through to
            ``ModelTrainer.train_model``.

    Returns:
        Flat dict including ``"symbol"`` plus the test_* metric keys.
        On training failure returns ``{"symbol": ..., "error": "..."}``.
    """
    import pandas as pd  # noqa: F401  — TF-import path
    from app.config import settings as settings_mod
    from app.core.model_trainer import ModelTrainer

    # Force a fresh settings read so env-var overrides take effect.
    settings_mod._settings = None

    df = pd.read_csv(csv_path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    trainer = ModelTrainer()
    logger.info(
        "Training %s with target_mode=%s feature_set=%s gru_units=%s",
        symbol, trainer.target_mode, trainer.feature_set, trainer.gru_units,
    )
    result = trainer.train_model(
        data=df,
        symbol=symbol,
        interval="60",
        test_size=test_size,
        validation_split=validation_split,
    )

    if not result.get("success"):
        return {"symbol": symbol, "error": result.get("error", "unknown")}

    out: Dict[str, Any] = {"symbol": symbol}
    out.update(result.get("test_metrics", {}))
    out["target_mode"] = trainer.target_mode
    out["feature_set"] = trainer.feature_set
    out["gru_units"] = list(trainer.gru_units)
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing {SYMBOL}_1H_*.csv files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/strategy/research-2026-04-29"),
        help="Where to drop T0.1-rebuild-results.{json,md}.",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=list(SYMBOLS_DEFAULT),
        help="Symbol allowlist; defaults to the production three.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Set env so ModelTrainer reads the rebuild settings.
    for k, v in ENV_OVERRIDES.items():
        os.environ[k] = v

    results: List[Dict[str, Any]] = []
    for symbol in args.symbols:
        matches = sorted(args.data_dir.glob(f"{symbol}_1H_*.csv"))
        if not matches:
            results.append({"symbol": symbol, "error": "no CSV found"})
            continue
        csv_path = matches[-1]  # newest by name (timestamp in filename)
        logger.info("=== %s — %s ===", symbol, csv_path.name)
        try:
            results.append(train_and_evaluate(symbol, csv_path))
        except Exception as exc:  # pragma: no cover  — TF runtime path
            logger.exception("train_and_evaluate failed for %s", symbol)
            results.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "T0.1-rebuild-results.json"
    md_path = args.output_dir / "T0.1-rebuild-results.md"
    json_path.write_text(json.dumps(results, indent=2, default=str))
    md_path.write_text(render_markdown_report(results))
    logger.info("wrote %s and %s", json_path, md_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
