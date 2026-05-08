"""Transformer builder — registry entry (CD-01).

Functional Keras model with stacked MultiHeadAttention + FFN blocks.
"""

from typing import Tuple

from tensorflow import keras
from tensorflow.keras import layers


_REQUIRED_HP_KEYS = ("units", "dropout", "lr", "horizon", "n_heads", "n_blocks")
_VALID_N_HEADS = {1, 2, 4, 8, 16}


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
    if hp["n_heads"] not in _VALID_N_HEADS:
        raise ValueError(
            f"hp['n_heads'] must be in {_VALID_N_HEADS}, got {hp['n_heads']!r}"
        )
    if not (isinstance(hp["n_blocks"], int) and 1 <= hp["n_blocks"] <= 8):
        raise ValueError(
            f"hp['n_blocks'] must be int in [1, 8], got {hp['n_blocks']!r}"
        )


def build(input_shape: Tuple[int, int], hp: dict) -> keras.Model:
    """Build a Transformer encoder model: project + n_blocks(MHA+FFN) + pool + dense."""
    _validate_hp(hp)
    units_list = hp["units"]
    dropout = float(hp["dropout"])
    lr = float(hp["lr"])
    horizon = int(hp["horizon"])
    n_heads = int(hp["n_heads"])
    n_blocks = int(hp["n_blocks"])
    width = units_list[0]

    inputs = keras.Input(shape=input_shape)
    x = layers.Dense(width)(inputs)
    for _ in range(n_blocks):
        attn_out = layers.MultiHeadAttention(
            num_heads=n_heads, key_dim=max(1, width // n_heads)
        )(x, x)
        attn_out = layers.Dropout(dropout)(attn_out)
        x = layers.LayerNormalization(epsilon=1e-6)(x + attn_out)
        ffn_out = keras.Sequential(
            [
                layers.Dense(width * 2, activation="relu"),
                layers.Dense(width),
            ]
        )(x)
        ffn_out = layers.Dropout(dropout)(ffn_out)
        x = layers.LayerNormalization(epsilon=1e-6)(x + ffn_out)
    x = layers.GlobalAveragePooling1D()(x)
    outputs = layers.Dense(horizon)(x)
    model = keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=lr),
        loss="mse",
        metrics=["mae"],
    )
    return model
