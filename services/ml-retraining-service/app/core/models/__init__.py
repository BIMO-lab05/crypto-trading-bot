"""Model architecture registry (CD-01).

Each module under app.core.models exposes a `build(input_shape, hp) -> keras.Model`
callable. Tournament harness (Phase 3) imports REGISTRY to launch experiments
across architectures; ml-retraining-service uses REGISTRY["gru"] by default.
"""

from app.core.models import gru

REGISTRY = {
    "gru": gru,
}

__all__ = ["REGISTRY"]
