"""Tournament experiment runner — invoked once per Docker container.

Entry point: python -m app.runner --spec-json '<json>'

Flow:
  1. parse spec-json -> ExperimentSpec
  2. seed all RNGs (np, tf, random) from spec.experiment_seed
  3. load klines from TimescaleDB (D-09) -- D-08 contamination flag captured
  4. compute_stationary_features (D-10 -- locked stationary pile)
  5. create_sequences (chronological, no-shuffle split)
  6. build model from REGISTRY (CD-01 -- 03-02)
  7. train with EarlyStopping + ReduceLROnPlateau
  8. compute_all_metrics via metrics_bridge (TOURN-07 -- imports only)
  9. write /output/result.json atomically (T-03-22)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import numpy as np

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


OUTPUT_DIR = Path("/output")
RESULT_PATH = OUTPUT_DIR / "result.json"


def _seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import tensorflow as tf

        tf.random.set_seed(seed)
    except Exception as e:
        logger.warning("could not seed tensorflow: %s", e)


def _atomic_write_result(payload: Dict[str, Any]) -> None:
    """Write result.json atomically -- orchestrator never sees a half-written file (T-03-22)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="result.", suffix=".json.tmp", dir=str(OUTPUT_DIR)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(RESULT_PATH))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _build_failure_result(
    spec: Dict[str, Any], reason: str, err_msg: str = ""
) -> Dict[str, Any]:
    return {
        "status": "failed",
        "reason": reason,  # parsed by orchestrator + result_schema
        "tournament_id": spec.get("tournament_id"),
        "run_id": spec.get("run_id"),
        "architecture": spec.get("architecture"),
        "symbol": spec.get("symbol"),
        "horizon": spec.get("horizon"),
        "target_mode": spec.get("target_mode"),
        "hp_hash": spec.get("hp_hash"),
        "metrics": {
            "r2_returns": None,
            "dir_acc_corrected": None,
            "oos_sharpe": None,
            "psr": None,
            "dsr": None,
            "cpcv_dsr": None,
            "train_seconds": None,
        },
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
        "tournament_start_ts": os.environ.get("TS_START", ""),
        "train_window_includes_contaminated": False,
        "failure_stderr_tail": err_msg[-4000:],
    }


def _build_success_result(
    spec: Dict[str, Any],
    metrics: Dict[str, float],
    contaminated: bool,
    train_seconds: float,
) -> Dict[str, Any]:
    return {
        "status": "success",
        "reason": None,
        "tournament_id": spec["tournament_id"],
        "run_id": spec["run_id"],
        "architecture": spec["architecture"],
        "symbol": spec["symbol"],
        "horizon": spec["horizon"],
        "target_mode": spec["target_mode"],
        "hp_hash": spec["hp_hash"],
        "metrics": {
            "r2_returns": metrics["r2_returns"],
            "dir_acc_corrected": metrics["dir_acc_corrected"],
            "oos_sharpe": metrics["oos_sharpe"],
            "psr": metrics["psr"],
            "dsr": metrics["dsr"],
            "cpcv_dsr": metrics["cpcv_dsr"],
            "train_seconds": train_seconds,
        },
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
        "tournament_start_ts": os.environ.get("TS_START", ""),
        "train_window_includes_contaminated": bool(contaminated),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.runner")
    parser.add_argument(
        "--spec-json",
        required=True,
        help="JSON-serialised ExperimentSpec from orchestrator",
    )
    args = parser.parse_args()

    # Fail-fast on canonical-metrics PYTHONPATH break (TOURN-07, v1.0 audit INT-02).
    # If the chain is unavailable here, no point parsing spec or loading data --
    # compute_all_metrics would raise at the end anyway, costing a full train.
    from app.runner.metrics_bridge import assert_canonical_metrics_available

    try:
        assert_canonical_metrics_available()
    except RuntimeError as e:
        logger.error("canonical-metrics chain unavailable at runner boot: %s", e)
        _atomic_write_result(_build_failure_result({}, "exit_nonzero", str(e)))
        return 1

    try:
        spec: Dict[str, Any] = json.loads(args.spec_json)
    except json.JSONDecodeError as e:
        logger.exception("spec-json parse failure")
        # No spec_id available -- write a minimal failure file so orchestrator sees something
        _atomic_write_result(_build_failure_result({}, "exit_nonzero", str(e)))
        return 1

    # T-03-19: defensive -- every required key must be present
    required = (
        "tournament_id",
        "run_id",
        "architecture",
        "symbol",
        "interval",
        "horizon",
        "target_mode",
        "hp",
        "hp_hash",
        "experiment_seed",
        "resource_caps",
    )
    missing = [k for k in required if k not in spec]
    if missing:
        msg = f"spec missing required keys: {missing}"
        logger.error(msg)
        _atomic_write_result(_build_failure_result(spec, "exit_nonzero", msg))
        return 1

    _seed_all(int(spec["experiment_seed"]))

    # 1. Load klines (D-06, D-07, D-08, D-09)
    try:
        from app.runner.data import load_klines_from_timescale

        end_ts_str = os.environ.get("TS_START", "")
        end_ts = datetime.fromisoformat(end_ts_str) if end_ts_str else datetime.utcnow()
        df, contaminated = load_klines_from_timescale(
            symbol=spec["symbol"],
            interval=spec["interval"],
            end_ts=end_ts,
        )
    except ConnectionError as e:
        logger.exception("db unreachable")
        _atomic_write_result(_build_failure_result(spec, "db_unreachable", str(e)))
        return 0  # exit 0 so orchestrator parses result.json (D-15)
    except ValueError as e:
        logger.exception("insufficient klines")
        _atomic_write_result(_build_failure_result(spec, "train_diverged", str(e)))
        return 0
    except Exception:
        tb = traceback.format_exc()
        _atomic_write_result(_build_failure_result(spec, "exit_nonzero", tb))
        return 1

    # 2. Stationary features (D-10)
    try:
        from app.core.stationary_features import (
            STATIONARY_FEATURE_COLS,
            compute_stationary_features,
        )

        df_feat = compute_stationary_features(df)
    except Exception:
        tb = traceback.format_exc()
        _atomic_write_result(_build_failure_result(spec, "exit_nonzero", tb))
        return 1

    # 3. Target column flips on target_mode (D-14)
    target_col = "close" if spec["target_mode"] == "price" else "log_returns"
    if target_col not in df_feat.columns:
        msg = f"target_col {target_col!r} not present after compute_stationary_features"
        _atomic_write_result(_build_failure_result(spec, "exit_nonzero", msg))
        return 1

    # 4. Create sequences
    try:
        from app.runner.sequences import create_sequences
        from sklearn.model_selection import train_test_split

        X, y = create_sequences(
            df_feat,
            target_col=target_col,
            feature_cols=list(STATIONARY_FEATURE_COLS),
            sequence_length=int(spec["hp"]["lookback"]),
            prediction_horizon=int(spec["horizon"]),
        )
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )
    except ValueError as e:
        _atomic_write_result(_build_failure_result(spec, "train_diverged", str(e)))
        return 0
    except Exception:
        tb = traceback.format_exc()
        _atomic_write_result(_build_failure_result(spec, "exit_nonzero", tb))
        return 1

    # 5. Build + train (CD-01 registry)
    try:
        from app.core.models import REGISTRY
        from tensorflow.keras import callbacks

        builder = REGISTRY[spec["architecture"]]
        # The registry builders only consume the keys they declared (gru/lstm
        # use units/dropout/lr/horizon; transformer/tcn add their nested keys).
        model = builder.build(
            input_shape=(X_train.shape[1], X_train.shape[2]),
            hp={**spec["hp"], "horizon": int(spec["horizon"])},
        )
        # NOTE: monitor='val_loss' is the deferred-equivalent of TOURN-04 Clause 1's
        # "monitor on r2_returns / dir_acc_corrected". For target_mode=log_returns + loss=MSE,
        # val_loss is monotonic with r2_returns (R^2 is a constant-shift transform of negative
        # MSE on a fixed validation set), so EarlyStopping(monitor='val_loss', mode='min') is
        # mathematically equivalent to EarlyStopping(monitor='val_r2_returns', mode='max').
        # See CONTEXT.md <deferred> for the equivalence proof and the v2 path if early-stopping
        # precision becomes a bottleneck (e.g., requires a custom Keras metric that recovers
        # prev_close from validation batches per epoch).
        early = callbacks.EarlyStopping(
            monitor="val_loss", patience=10, restore_best_weights=True, verbose=1
        )
        reduce_lr = callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=5, min_lr=1e-5, verbose=1
        )
        t0 = time.time()
        history = model.fit(
            X_train,
            y_train,
            epochs=int(spec["hp"].get("epochs", 30)),
            batch_size=int(spec["hp"]["batch"]),
            validation_split=0.2,
            callbacks=[early, reduce_lr],
            verbose=1,
        )
        train_seconds = time.time() - t0

        # NaN loss check (D-15)
        if np.isnan(history.history["loss"]).any():
            _atomic_write_result(
                _build_failure_result(
                    spec, "nan_loss", "loss history contains NaN -- early termination"
                )
            )
            return 0

        # train_diverged: best val_loss never improved from initial
        val_history = history.history.get("val_loss", [])
        if val_history and val_history[-1] >= val_history[0]:
            # No improvement at all by the last epoch -- flag for operator review
            _atomic_write_result(
                _build_failure_result(
                    spec,
                    "train_diverged",
                    f"val_loss did not improve: start={val_history[0]:.4f} end={val_history[-1]:.4f}",
                )
            )
            return 0

    except Exception:
        tb = traceback.format_exc()
        _atomic_write_result(_build_failure_result(spec, "exit_nonzero", tb))
        return 1

    # 6. Metrics -- IMPORTED only (TOURN-07)
    try:
        from app.runner.metrics_bridge import compute_all_metrics

        last_close_test = df_feat["close"].to_numpy()[
            int(spec["hp"]["lookback"]) - 1 + len(X_train) : int(spec["hp"]["lookback"])
            - 1
            + len(X_train)
            + len(X_test)
        ]
        label_horizon = int(spec["hp"]["lookback"]) + int(spec["horizon"]) - 1
        metrics = compute_all_metrics(
            model, X_test, y_test, last_close_test, label_horizon
        )
        result = _build_success_result(spec, metrics, contaminated, train_seconds)
        _atomic_write_result(result)
        logger.info("run %s SUCCESS in %.1fs", spec["run_id"], train_seconds)
        return 0

    except Exception:
        tb = traceback.format_exc()
        _atomic_write_result(_build_failure_result(spec, "exit_nonzero", tb))
        return 1


if __name__ == "__main__":
    sys.exit(main())
