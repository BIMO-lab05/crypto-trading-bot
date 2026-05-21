"""C2 wrap experiment — flat-zone signal over regression GRU.

Pre-commit rules: see C2-wrap-decision-rules.md
- Train regression GRU on log_returns (T0.1 plumbing).
- After train: epsilon = std of train predictions (1-sigma deadband).
- Test signal: pred > +eps -> +1, pred < -eps -> -1, else 0.
- Strategy returns: signal * actual_log_return at horizon step.
- Run existing CPCV on strategy returns -> DSR.
- Verdict: balanced_acc >= 0.45 AND DSR >= 0.95.

Run inside ml-retraining container:
    docker run --rm \\
      -v /tmp/t01_4h_clean:/tmp/rebuild/data:ro \\
      -v <repo>/docs/strategy/research-2026-05-21/wrap_c2.py:/work/wrap_c2.py:ro \\
      -v <repo>/docs/strategy/research-2026-05-21/C2-wrap:/work/output \\
      -e RETRAIN_TARGET_MODE=log_returns \\
      -e RETRAIN_FEATURE_SET=stationary \\
      -e RETRAIN_GRU_UNITS='[32]' \\
      -e DATABASE_URL='postgresql://placeholder@nowhere/db' \\
      -e TF_CPP_MIN_LOG_LEVEL=2 \\
      -w /app crypto-bot-ml-retraining:t01 \\
      python /work/wrap_c2.py /tmp/rebuild/data /work/output
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from tensorflow.keras import callbacks

# settings refresh so env vars take
from app.config import settings as settings_mod

settings_mod._settings = None

from app.core.model_trainer import ModelTrainer  # noqa: E402
from app.core.stationary_features import STATIONARY_FEATURE_COLS  # noqa: E402
from app.cpcv import (  # noqa: E402
    CombinatorialPurgedCV,
    cpcv_sharpe_distribution,
    cpcv_to_dsr,
)

logger = logging.getLogger(__name__)

SYMBOLS = ("SOLUSDT", "BNBUSDT", "ADAUSDT")
PASS_BAL_ACC = 0.45
PASS_DSR = 0.95


def _balanced_accuracy(actual_class: np.ndarray, signal: np.ndarray) -> Dict:
    classes = (-1, 0, 1)
    recalls = []
    counts = {}
    for c in classes:
        mask = actual_class == c
        counts[c] = int(mask.sum())
        if mask.sum() == 0:
            recalls.append(float("nan"))
        else:
            recalls.append(float((signal[mask] == c).sum()) / mask.sum())
    bal = float(np.nanmean(recalls))
    return {
        "balanced_accuracy": bal,
        "recall_short": recalls[0],
        "recall_flat": recalls[1],
        "recall_long": recalls[2],
        "actual_class_counts": counts,
    }


def _cpcv_on_returns(strat: np.ndarray, horizon: int) -> Dict:
    nan = {
        "dsr": float("nan"),
        "cpcv_sharpe_mean": float("nan"),
        "cpcv_sharpe_std": float("nan"),
        "cpcv_sharpe_median": float("nan"),
        "cpcv_sharpe_ci_low": float("nan"),
        "cpcv_sharpe_ci_high": float("nan"),
        "cpcv_n_paths": 0,
    }
    if len(strat) < 2:
        return nan

    try:
        cv = CombinatorialPurgedCV(n_groups=10, k_test_groups=2, embargo_pct=0.01)
        splits = list(cv.split(len(strat), horizon))
    except ValueError:
        return nan

    if not splits:
        return nan

    rpp: List[np.ndarray] = [strat[s.test_idx] for s in splits]
    sd = cpcv_sharpe_distribution(rpp)
    dsr = cpcv_to_dsr(rpp, strat)
    return {
        "dsr": dsr,
        "cpcv_sharpe_mean": sd["mean"],
        "cpcv_sharpe_std": sd["std"],
        "cpcv_sharpe_median": sd["median"],
        "cpcv_sharpe_ci_low": sd["ci_low"],
        "cpcv_sharpe_ci_high": sd["ci_high"],
        "cpcv_n_paths": sd["n_paths"],
    }


def train_and_wrap(symbol: str, csv_path: Path) -> Dict:
    logger.info("=== %s — %s ===", symbol, csv_path.name)
    df = pd.read_csv(csv_path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    trainer = ModelTrainer()

    # Replicate trainer.train_model up to model.fit, BUT keep handles to splits.
    data_with_features = trainer.prepare_features(df)
    feature_cols_used = (
        list(STATIONARY_FEATURE_COLS) if trainer.feature_set == "stationary" else None
    )
    X, y = trainer.create_sequences(
        data_with_features,
        target_col=trainer.target_col,
        feature_cols=feature_cols_used,
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, shuffle=False
    )

    # Build via same registry path the trainer uses.
    from app.core.models import REGISTRY

    builder = REGISTRY[trainer.architecture]
    model = builder.build(
        input_shape=(X_train.shape[1], X_train.shape[2]),
        hp={
            "units": list(trainer.gru_units),
            "dropout": float(trainer.dropout_rate),
            "lr": 0.001,
            "horizon": int(trainer.prediction_horizon),
        },
    )

    early = callbacks.EarlyStopping(
        monitor="val_loss", patience=10, restore_best_weights=True, verbose=0
    )
    rlr = callbacks.ReduceLROnPlateau(
        monitor="val_loss", factor=0.5, patience=5, min_lr=0.00001, verbose=0
    )
    model.fit(
        X_train,
        y_train,
        epochs=trainer.settings.retrain_max_epochs,
        batch_size=trainer.settings.retrain_batch_size,
        validation_split=0.2,
        callbacks=[early, rlr],
        verbose=0,
    )

    # Predictions, inverse-scaled, last horizon step.
    train_pred_scaled = model.predict(X_train, verbose=0)
    test_pred_scaled = model.predict(X_test, verbose=0)
    train_pred_real = trainer.scaler_y.inverse_transform(train_pred_scaled)
    test_pred_real = trainer.scaler_y.inverse_transform(test_pred_scaled)
    y_test_real = trainer.scaler_y.inverse_transform(y_test)

    train_pred_h = train_pred_real[:, -1]
    test_pred_h = test_pred_real[:, -1]
    actual_h = y_test_real[:, -1]

    # Pre-committed epsilon: 1.0 * sigma(train preds, last horizon step).
    mu_train = float(np.mean(train_pred_h))
    sigma_train = float(np.std(train_pred_h, ddof=1))
    epsilon = sigma_train

    signal = np.where(
        test_pred_h > mu_train + epsilon,
        1,
        np.where(test_pred_h < mu_train - epsilon, -1, 0),
    ).astype(int)

    # Actual class using the SAME epsilon (FLAT bucket where |actual| <= eps).
    actual_class = np.where(
        actual_h > epsilon, 1, np.where(actual_h < -epsilon, -1, 0)
    ).astype(int)

    bal = _balanced_accuracy(actual_class, signal)

    strat = (signal * actual_h).astype(float)
    # Per-bar Sharpe of the whole strategy return series (OOS).
    if len(strat) > 1 and np.std(strat, ddof=1) > 1e-15:
        oos_sharpe = float(np.mean(strat) / np.std(strat, ddof=1))
    else:
        oos_sharpe = float("nan")

    cpcv = _cpcv_on_returns(strat, horizon=trainer.prediction_horizon)

    pass_balacc = bal["balanced_accuracy"] >= PASS_BAL_ACC
    pass_dsr = (not math.isnan(cpcv["dsr"])) and cpcv["dsr"] >= PASS_DSR
    verdict = "PASS" if (pass_balacc and pass_dsr) else "FAIL"

    return {
        "symbol": symbol,
        "csv_file": csv_path.name,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "epsilon": epsilon,
        "mu_train": mu_train,
        "sigma_train": sigma_train,
        "signal_distribution": {
            "buy": int((signal == 1).sum()),
            "flat": int((signal == 0).sum()),
            "sell": int((signal == -1).sum()),
        },
        "balanced_accuracy": bal["balanced_accuracy"],
        "recall_short": bal["recall_short"],
        "recall_flat": bal["recall_flat"],
        "recall_long": bal["recall_long"],
        "actual_class_counts": bal["actual_class_counts"],
        "strat_mean_return": float(np.mean(strat)) if len(strat) else float("nan"),
        "strat_total_return": float(np.sum(strat)) if len(strat) else float("nan"),
        "strat_oos_sharpe": oos_sharpe,
        "strat_dsr": cpcv["dsr"],
        "strat_cpcv_sharpe_mean": cpcv["cpcv_sharpe_mean"],
        "strat_cpcv_sharpe_std": cpcv["cpcv_sharpe_std"],
        "strat_cpcv_sharpe_median": cpcv["cpcv_sharpe_median"],
        "strat_cpcv_sharpe_ci_low": cpcv["cpcv_sharpe_ci_low"],
        "strat_cpcv_sharpe_ci_high": cpcv["cpcv_sharpe_ci_high"],
        "strat_cpcv_n_paths": cpcv["cpcv_n_paths"],
        "pass_balanced_acc": bool(pass_balacc),
        "pass_dsr": bool(pass_dsr),
        "verdict": verdict,
    }


def main(argv: Sequence[str] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("data_dir", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--symbols", nargs="*", default=list(SYMBOLS))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    results: List[Dict] = []
    for symbol in args.symbols:
        matches = sorted(args.data_dir.glob(f"{symbol}_1H_*.csv"))
        if not matches:
            results.append({"symbol": symbol, "error": "no CSV found"})
            continue
        csv = matches[-1]
        try:
            results.append(train_and_wrap(symbol, csv))
        except Exception as exc:
            logger.exception("wrap failed for %s", symbol)
            results.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "results.json").write_text(
        json.dumps(results, indent=2, default=str)
    )

    # Concise verdict line
    n_pass = sum(1 for r in results if r.get("verdict") == "PASS")
    overall = "EDGE_FOUND" if n_pass >= 2 else "NO_EDGE"
    summary = {
        "overall_verdict": overall,
        "n_pass": n_pass,
        "n_symbols": len(results),
        "thresholds": {"balanced_accuracy_min": PASS_BAL_ACC, "dsr_min": PASS_DSR},
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    logger.info("OVERALL: %s (%d/%d symbols PASS)", overall, n_pass, len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
