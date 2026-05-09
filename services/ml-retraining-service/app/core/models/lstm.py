"""LSTM builder — registry entry mirroring gru.py with layers.LSTM (CD-01)."""

from typing import Tuple

from tensorflow import keras
from tensorflow.keras import layers


_REQUIRED_HP_KEYS = ("units", "dropout", "lr", "horizon")


def _validate_hp(hp: dict) -> None:
    """Defensive validation — fail early on bad operator input (T-03-04)."""
    missing = [k for k in _REQUIRED_HP_KEYS if k not in hp]
    if missing:
        raise ValueError(f"hp missing required keys: {missing}")
    if not isinstance(hp["units"], list) or not hp["units"]:
        raise ValueError(f"hp['units'] must be non-empty list, got {hp['units']!r}")
    if not all(isinstance(u, int) and 1 <= u <= 4096 for u in hp["units"]):
        raise ValueError(
            f"hp['units'] entries must be int in [1, 4096], got {hp['units']!r}"
        )
    if not (0.0 <= float(hp["dropout"]) < 1.0):
        raise ValueError(f"hp['dropout'] must be in [0.0, 1.0), got {hp['dropout']!r}")
    if not (1e-6 <= float(hp["lr"]) <= 1.0):
        raise ValueError(f"hp['lr'] must be in [1e-6, 1.0], got {hp['lr']!r}")
    if not (isinstance(hp["horizon"], int) and 1 <= hp["horizon"] <= 256):
        raise ValueError(
            f"hp['horizon'] must be int in [1, 256], got {hp['horizon']!r}"
        )


def build(input_shape: Tuple[int, int], hp: dict) -> keras.Model:
    """Build a stacked LSTM model with the same shape as gru.build."""
    _validate_hp(hp)
    units_list = hp["units"]
    dropout = float(hp["dropout"])
    lr = float(hp["lr"])
    horizon = int(hp["horizon"])

    n_layers = len(units_list)
    model = keras.Sequential()
    for i, units in enumerate(units_list):
        return_sequences = i < n_layers - 1
        if i == 0:
            model.add(
                layers.LSTM(
                    units,
                    return_sequences=return_sequences,
                    input_shape=input_shape,
                )
            )
        else:
            model.add(layers.LSTM(units, return_sequences=return_sequences))
        model.add(layers.Dropout(dropout))

    model.add(layers.Dense(horizon))
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=lr),
        loss="mse",
        metrics=["mae"],
    )
    return model
