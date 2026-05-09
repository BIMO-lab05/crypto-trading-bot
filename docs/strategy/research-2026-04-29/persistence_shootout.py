"""
Persistence-baseline shootout for production GRU models.

Compares each GRU's predictions against a trivial persistence baseline
(`next_price = last_price`) on the same chronological 80/20 OOS window
that the model was trained on. Reports three metrics:

  1. R² on inverse-transformed close price level (the existing metric).
     If GRU R² ≈ persistence R², the metric is autocorrelation noise.
  2. R² on log-returns (predicted-change vs actual-change).
     If GRU R² <= 0 here, the model has zero predictive skill on returns.
  3. Corrected directional accuracy — reference is last bar of input
     sequence (not the buggy y_test[:, -1] reference).

Run inside the ml-prediction container so all deps + scaler classes are
in scope. CSV data and model files are docker-cp'd into /tmp/shootout/.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
from tensorflow import keras
import joblib

DATA_DIR = Path("/tmp/shootout/data")
MODELS_DIR = Path("/tmp/shootout/models")
SYMBOLS = ["SOLUSDT", "BNBUSDT", "ADAUSDT"]
SEQUENCE_LENGTH = 60
PREDICTION_HORIZON = 5
TRAIN_TEST_SPLIT = 0.8

# Mirror the feature engineering in services/ml-prediction-service/app/ml_models/gru_model.py
# Must match exactly or the model won't accept the input shape.
def create_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["return_1"] = df["close"].pct_change(1)
    df["return_5"] = df["close"].pct_change(5)
    df["return_10"] = df["close"].pct_change(10)
    df["price_momentum_5"] = df["close"] - df["close"].shift(5)
    df["price_momentum_10"] = df["close"] - df["close"].shift(10)
    df["sma_7"] = df["close"].rolling(7).mean()
    df["sma_14"] = df["close"].rolling(14).mean()
    df["sma_30"] = df["close"].rolling(30).mean()
    df["ema_7"] = df["close"].ewm(span=7, adjust=False).mean()
    df["ema_14"] = df["close"].ewm(span=14, adjust=False).mean()
    df["price_vs_sma7"] = (df["close"] - df["sma_7"]) / df["sma_7"]
    df["price_vs_sma14"] = (df["close"] - df["sma_14"]) / df["sma_14"]
    df["high_low_range"] = (df["high"] - df["low"]) / df["close"]
    df["volatility_10"] = df["return_1"].rolling(10).std()
    df["volatility_20"] = df["return_1"].rolling(20).std()
    df["volume_sma_7"] = df["volume"].rolling(7).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma_7"]
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))
    return df.dropna()


def prepare_sequences(df: pd.DataFrame, feature_columns: list, scaler):
    feature_cols = [c for c in feature_columns if c in df.columns]
    if feature_cols != feature_columns:
        missing = set(feature_columns) - set(feature_cols)
        raise RuntimeError(f"Missing features: {missing}")
    data = df[feature_columns].values
    scaled = scaler.transform(data)
    close_idx = feature_columns.index("close")
    X, y = [], []
    for i in range(len(scaled) - SEQUENCE_LENGTH - PREDICTION_HORIZON):
        X.append(scaled[i : i + SEQUENCE_LENGTH])
        y.append(
            scaled[
                i + SEQUENCE_LENGTH : i + SEQUENCE_LENGTH + PREDICTION_HORIZON,
                close_idx,
            ]
        )
    return np.array(X), np.array(y), close_idx


def evaluate_symbol(symbol: str) -> dict:
    csv = next(DATA_DIR.glob(f"{symbol}_1H_*.csv"))
    model = keras.models.load_model(MODELS_DIR / f"{symbol}_60m_gru.keras")
    scalers = joblib.load(MODELS_DIR / f"{symbol}_60m_gru_scalers.pkl")
    metadata = json.loads((MODELS_DIR / f"{symbol}_60m_gru_metadata.json").read_text())

    feature_scaler = scalers.get("feature_scaler") if isinstance(scalers, dict) else scalers
    feature_columns = metadata["feature_columns"]

    df = pd.read_csv(csv)
    df = create_features(df)
    X, y, close_idx = prepare_sequences(df, feature_columns, feature_scaler)

    split = int(len(X) * TRAIN_TEST_SPLIT)
    X_test, y_test = X[split:], y[split:]

    if len(X_test) < 100:
        return {"symbol": symbol, "error": f"insufficient OOS samples: {len(X_test)}"}

    # GRU predictions
    y_pred_gru = model.predict(X_test, verbose=0)

    # Persistence: next-bar close = last input close (in scaled space, all horizons)
    last_input_close = X_test[:, -1, close_idx]  # shape (N,)
    y_pred_persistence = np.tile(last_input_close[:, None], (1, PREDICTION_HORIZON))

    # === Metric 1: R² on inverse-transformed close price level ===
    # Inverse transform requires reconstructing the full feature vector. We only
    # care about the close column. Trick: build a zero matrix of feature width,
    # put the y values in close_idx column, inverse-transform, take close column.
    def inv_close(y_scaled):
        # y_scaled shape (N, horizon). Inverse for each horizon step, take col close_idx.
        N, H = y_scaled.shape
        out = np.empty_like(y_scaled, dtype=float)
        for h in range(H):
            tmp = np.zeros((N, len(feature_columns)))
            tmp[:, close_idx] = y_scaled[:, h]
            inv = feature_scaler.inverse_transform(tmp)
            out[:, h] = inv[:, close_idx]
        return out

    y_test_price = inv_close(y_test)
    y_pred_gru_price = inv_close(y_pred_gru)
    y_pred_pers_price = inv_close(y_pred_persistence)

    r2_price_gru = r2_score(y_test_price[:, 0], y_pred_gru_price[:, 0])
    r2_price_pers = r2_score(y_test_price[:, 0], y_pred_pers_price[:, 0])

    # === Metric 2: R² on log-returns ===
    last_input_close_price = inv_close(last_input_close[:, None])[:, 0]
    actual_log_ret = np.log(y_test_price[:, 0] / last_input_close_price)
    gru_pred_log_ret = np.log(y_pred_gru_price[:, 0] / last_input_close_price)
    pers_pred_log_ret = np.log(y_pred_pers_price[:, 0] / last_input_close_price)

    r2_ret_gru = r2_score(actual_log_ret, gru_pred_log_ret)
    r2_ret_pers = r2_score(actual_log_ret, pers_pred_log_ret)

    # === Metric 3: Corrected directional accuracy ===
    actual_dir = np.sign(y_test[:, 0] - last_input_close)
    gru_dir = np.sign(y_pred_gru[:, 0] - last_input_close)
    pers_dir = np.sign(y_pred_persistence[:, 0] - last_input_close)
    da_gru = float(np.mean(actual_dir == gru_dir))
    da_pers = float(np.mean(actual_dir == pers_dir))

    # Bonus: also recompute the BUGGY directional accuracy for reference
    buggy_actual = np.sign(y_test[:, 0] - y_test[:, -1])
    buggy_gru = np.sign(y_pred_gru[:, 0] - y_test[:, -1])
    da_gru_buggy = float(np.mean(buggy_actual == buggy_gru))

    return {
        "symbol": symbol,
        "n_oos": int(len(X_test)),
        "r2_price_gru": float(r2_price_gru),
        "r2_price_persistence": float(r2_price_pers),
        "r2_returns_gru": float(r2_ret_gru),
        "r2_returns_persistence": float(r2_ret_pers),
        "dir_acc_gru_corrected": da_gru,
        "dir_acc_persistence_corrected": da_pers,
        "dir_acc_gru_BUGGY_for_reference": da_gru_buggy,
        "metadata_recorded_r2": metadata["training_stats"]["r2_score"],
        "metadata_recorded_dir_acc": metadata["training_stats"]["directional_accuracy"],
    }


def main():
    results = []
    for sym in SYMBOLS:
        try:
            r = evaluate_symbol(sym)
            results.append(r)
            print(f"--- {sym} ---")
            for k, v in r.items():
                if isinstance(v, float):
                    print(f"  {k}: {v:.6f}")
                else:
                    print(f"  {k}: {v}")
        except Exception as e:
            print(f"--- {sym}: ERROR {type(e).__name__}: {e} ---", file=sys.stderr)
            import traceback
            traceback.print_exc()

    out = Path("/tmp/shootout/results.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
