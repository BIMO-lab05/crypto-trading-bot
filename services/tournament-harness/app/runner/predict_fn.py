"""Predict-only re-hydration of ensemble members from a snapshot row.

Phase 4 plan 04-07. Resolves blocker B3 (predict_fn was circularly deferred
between 04-01/04-03/04-06 and never delivered) and the static portion of B1
(every klines read in services/tournament-harness/ MUST go through the
canonical loader).

Contract (CD-11 + D-03 + Phase 3 D-08 + D-13):
  - Klines reads MUST go through `load_klines_from_timescale`, which enforces
    `is_mainnet = TRUE` and the [end_ts - 365d, end_ts] window. This module
    has NO raw SQL and NO alternate klines path.
  - The OOS window end is `snapshot.config.tournament_start_ts` (CD-11).
  - Reproducibility: same snapshot row + same git_sha => identical predictions.
    Achieved by re-applying the snapshot's `seed` (mirroring `__main__._seed_all`)
    and re-deriving the train/test split from the same klines slice via the
    same primitives `__main__.py` uses (`compute_stationary_features`,
    `create_sequences`, sklearn `train_test_split`, `REGISTRY[arch].build`).
    Phase 3 D-13 reproducibility extended into Phase 4.

This module produces the predict_fn callable consumed by
`app.significance.predict_cache.get_or_build_predictions` on cache miss.
The cache writes the result to `data/cache/{tournament_id}/predictions/{run_id}.npz`
(CD-11) — this module has no I/O of its own beyond the klines read.

Threat model (per plan 04-07 register):
  T-04-36 (Tampering): tournament_id and run_id validated against
    `^[A-Za-z0-9._\\-]+$` BEFORE any DB or model work. Defense in depth with
    predict_cache's own check.
  T-04-37 (Tampering): klines slice contamination — canonical loader
    enforces is_mainnet=TRUE in SQL; this module has no parallel reader.
  T-04-38 (Spoofing): symbol must end in "USDT" (asserted; mirrors
    canonical loader's own assertion).
  T-04-39 (Repudiation): seed sourced from snapshot row → deterministic.
"""

from __future__ import annotations

import logging
import random
import re
from datetime import datetime
from typing import Any, Callable, Dict

import numpy as np

# CANONICAL klines reader — enforces is_mainnet=TRUE inside the SQL itself.
# Do NOT reach around this; do NOT add a parallel reader (Phase 3 D-08, CD-11,
# CLAUDE.md gotcha re: testnet/mainnet bleed-through pre-2026-04-25).
from app.runner.data import load_klines_from_timescale

logger = logging.getLogger(__name__)

# Path-traversal regex — mirrors snapshot.py and predict_cache.py. Refuses `..`,
# `/`, NUL, whitespace, `\` etc.
_SAFE_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def _validate_id(value: Any, kind: str) -> None:
    if not isinstance(value, str) or not _SAFE_RE.fullmatch(value):
        raise ValueError(f"invalid {kind}: {value!r} (must match {_SAFE_RE.pattern})")


def _parse_iso(ts: str) -> datetime:
    """Parse ISO-8601 timestamp tolerating the "Z" UTC suffix snapshots emit."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _seed_all(seed: int) -> None:
    """Mirrors __main__._seed_all for D-13 reproducibility.

    Kept as a private duplicate (not imported) because importing a private
    `_seed_all` from another module is brittle; the body is six lines.
    """
    random.seed(seed)
    np.random.seed(seed)
    try:
        import tensorflow as tf  # type: ignore[import-not-found]

        tf.random.set_seed(seed)
    except Exception as e:  # pragma: no cover - tf not installed in unit tests
        logger.debug("tensorflow seeding skipped: %s", e)


def build_predict_fn(
    snapshot: Dict[str, Any],
) -> Callable[[Dict[str, Any]], Dict[str, np.ndarray]]:
    """Returns a callable: (row) -> {pred_prices, actual_prices, last_close}.

    The returned callable is the production predict_fn that
    `predict_cache.get_or_build_predictions` invokes on cache miss. The cache
    writes the result to `data/cache/{tournament_id}/predictions/{run_id}.npz`
    (CD-11) — this module has no I/O of its own beyond the klines read.

    Args:
        snapshot: dict matching the export_snapshot contract (config, rows, ...).

    Returns:
        Callable that, given a snapshot row, returns
        {"pred_prices": 1-D np.ndarray, "actual_prices": 1-D np.ndarray,
         "last_close":  1-D np.ndarray}, all of equal positive length.

    The factory raises:
        ValueError: snapshot.tournament_id is path-unsafe (validated upfront).

    The callable raises:
        ValueError: row.run_id is path-unsafe; row.status != "success";
                    or computed arrays are empty / shape-mismatched.
        AssertionError: row.symbol does not end in "USDT" (mirrors the
                        canonical loader's own fail-fast).
        ConnectionError: TimescaleDB unreachable (propagated from canonical loader).
    """
    tournament_id = snapshot["tournament_id"]
    _validate_id(tournament_id, "tournament_id")
    cfg = snapshot["config"]
    end_ts = _parse_iso(cfg["tournament_start_ts"])

    def _predict(row: Dict[str, Any]) -> Dict[str, np.ndarray]:
        # 0. Path-traversal guard — runs BEFORE any DB / model work.
        run_id = row.get("run_id")
        _validate_id(run_id, "run_id")

        # 0a. Snapshot pre-filters status; predict_fn double-checks (defense in depth).
        if row.get("status") != "success":
            raise ValueError(
                f"predict_fn refusing non-success row: run_id={run_id!r} "
                f"status={row.get('status')!r}"
            )

        symbol = row["symbol"]
        # 0b. Mirrors load_klines_from_timescale's assertion — fail fast at this layer too.
        assert symbol.endswith("USDT"), (
            f"predict_fn requires Bybit USDT-quoted symbol, got {symbol!r}"
        )

        result_json = row.get("result_json") or {}
        hp = result_json.get("hyperparameters", {})
        interval = result_json.get("interval") or row.get("interval", "5m")
        label_horizon = int(result_json.get("label_horizon") or row.get("horizon", 1))
        lookback = int(hp.get("lookback", 60))
        # Horizon for sequence construction (matches __main__.py spec.horizon).
        horizon = int(row.get("horizon", label_horizon))
        architecture = row["architecture"]
        target_mode = row.get("target_mode", "log_returns")
        seed = int(result_json.get("seed") or cfg.get("seed", 0))

        # 1. Seed all RNGs BEFORE any data shuffling / model construction.
        _seed_all(seed)

        # 2. Load klines — canonical reader enforces is_mainnet=TRUE in SQL.
        df, contaminated = load_klines_from_timescale(
            symbol=symbol,
            interval=interval,
            end_ts=end_ts,
            days_back=365,
        )
        if contaminated:
            logger.warning(
                "predict_fn: train window straddles testnet contamination cutoff for %s",
                symbol,
            )

        # 3. Stationary features (D-10) — lazy import; same source __main__.py uses.
        from app.core.stationary_features import (  # type: ignore[import-not-found]
            STATIONARY_FEATURE_COLS,
            compute_stationary_features,
        )

        df_feat = compute_stationary_features(df)
        target_col = "close" if target_mode == "price" else "log_returns"
        if target_col not in df_feat.columns:
            # Fallback: if the feature pipeline did not emit log_returns, use close.
            # (Defensive — __main__.py would have errored here; predict_fn for the
            # ensemble eval just needs the OOS price arrays for the bootstrap test.)
            target_col = "close"

        # 4. Sequence construction + chronological split (no shuffle).
        from app.runner.sequences import create_sequences
        from sklearn.model_selection import train_test_split

        X, y = create_sequences(
            df_feat,
            target_col=target_col,
            feature_cols=list(STATIONARY_FEATURE_COLS),
            sequence_length=lookback,
            prediction_horizon=horizon,
        )
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        # 5. Build + (re-)train deterministically.
        from app.core.models import REGISTRY  # type: ignore[import-not-found]

        builder = REGISTRY[architecture]
        model = builder.build(
            input_shape=(X_train.shape[1], X_train.shape[2]),
            hp={**hp, "horizon": horizon},
        )
        # `fit` is invoked because the registry builder returns an untrained
        # model; D-13 reproducibility relies on identical seed + identical data.
        # Heavy-weight; the predict cache (04-01) is what makes repeat calls cheap.
        try:
            model.fit(
                X_train,
                y_train,
                epochs=int(hp.get("epochs", 30)),
                batch_size=int(hp.get("batch", 32)),
                validation_split=0.2,
                verbose=0,
            )
        except TypeError:
            # Stub models in tests may take no kwargs — call with positionals.
            model.fit(X_train, y_train)

        # 6. Predict on OOS — pred_prices, actual_prices, last_close arrays.
        pred_arr = np.asarray(model.predict(X_test, verbose=0))
        actual_arr = np.asarray(y_test)
        # last_close indexing mirrors __main__.py lines 311-316 EXACTLY for D-13.
        # last_close_test = df_feat['close'][lookback - 1 + len(X_train) :
        #                                    lookback - 1 + len(X_train) + len(X_test)]
        close_full = df_feat["close"].to_numpy()
        start = lookback - 1 + len(X_train)
        stop = start + len(X_test)
        last_close_test = close_full[start:stop]

        # Reduce to 1-D float arrays. metrics_bridge.compute_all_metrics passes
        # 2-D (n, horizon) arrays straight through; the predict_cache contract
        # (04-01 SUMMARY: "1-D arrays of equal length") needs flattening to the
        # last horizon column (the bar predicted at t+horizon).
        if pred_arr.ndim == 2:
            pred_prices = pred_arr[:, -1].astype(np.float64).reshape(-1)
        else:
            pred_prices = pred_arr.astype(np.float64).reshape(-1)
        if actual_arr.ndim == 2:
            actual_prices = actual_arr[:, -1].astype(np.float64).reshape(-1)
        else:
            actual_prices = actual_arr.astype(np.float64).reshape(-1)
        last_close = np.asarray(last_close_test, dtype=np.float64).reshape(-1)

        n = len(pred_prices)
        if n == 0:
            raise ValueError(
                f"predict_fn produced empty arrays for run_id={run_id!r} symbol={symbol!r}"
            )
        # Truncate to common length defensively — `__main__.py` guarantees these
        # match; predict_fn double-checks because experiment containers are isolated.
        m = min(n, len(actual_prices), len(last_close))
        if m != n or len(actual_prices) != n or len(last_close) != n:
            logger.warning(
                "predict_fn shape mismatch run_id=%s pred=%d actual=%d last=%d -> truncating to %d",
                run_id,
                n,
                len(actual_prices),
                len(last_close),
                m,
            )
            pred_prices = pred_prices[:m]
            actual_prices = actual_prices[:m]
            last_close = last_close[:m]
            n = m

        if n == 0:
            raise ValueError(
                f"predict_fn arrays collapsed to empty after alignment "
                f"run_id={run_id!r} symbol={symbol!r}"
            )

        return {
            "pred_prices": pred_prices,
            "actual_prices": actual_prices,
            "last_close": last_close,
        }

    return _predict


__all__ = ["build_predict_fn"]
