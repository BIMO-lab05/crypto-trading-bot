"""TCN builder — residual stack of dilated causal Conv1D blocks (CD-01)."""

from typing import Tuple

from tensorflow import keras
from tensorflow.keras import layers


_REQUIRED_HP_KEYS = (
    "units",
    "dropout",
    "lr",
    "horizon",
    "kernel_size",
    "dilation_base",
    "n_blocks",
)
_VALID_KERNEL_SIZES = {2, 3, 4, 5, 7}
_VALID_DILATION_BASES = {2, 3}


def _validate_hp(hp: dict) -> None:
    """Defensive validation — fail early (T-03-04, T-03-05)."""
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
    if hp["kernel_size"] not in _VALID_KERNEL_SIZES:
        raise ValueError(
            f"hp['kernel_size'] must be in {_VALID_KERNEL_SIZES}, got {hp['kernel_size']!r}"
        )
    if hp["dilation_base"] not in _VALID_DILATION_BASES:
        raise ValueError(
            f"hp['dilation_base'] must be in {_VALID_DILATION_BASES}, got {hp['dilation_base']!r}"
        )
    if not (isinstance(hp["n_blocks"], int) and 1 <= hp["n_blocks"] <= 8):
        raise ValueError(
            f"hp['n_blocks'] must be int in [1, 8], got {hp['n_blocks']!r}"
        )


def build(input_shape: Tuple[int, int], hp: dict) -> keras.Model:
    """Build a TCN: residual stack of dilated causal Conv1D + pool + dense."""
    _validate_hp(hp)
    units_list = hp["units"]
    dropout = float(hp["dropout"])
    lr = float(hp["lr"])
    horizon = int(hp["horizon"])
    kernel_size = int(hp["kernel_size"])
    dilation_base = int(hp["dilation_base"])
    n_blocks = int(hp["n_blocks"])

    inputs = keras.Input(shape=input_shape)
    x = inputs
    for i in range(n_blocks):
        dilation = dilation_base**i
        channels = units_list[i % len(units_list)]
        conv = layers.Conv1D(
            filters=channels,
            kernel_size=kernel_size,
            padding="causal",
            dilation_rate=dilation,
            activation="relu",
        )(x)
        conv = layers.Dropout(dropout)(conv)
        if x.shape[-1] != channels:
            x = layers.Conv1D(filters=channels, kernel_size=1, padding="same")(x)
        x = layers.Add()([x, conv])
    x = layers.GlobalAveragePooling1D()(x)
    outputs = layers.Dense(horizon)(x)
    model = keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=lr), loss="mse", metrics=["mae"]
    )
    return model
