"""
Lifespan phase context managers for trading-engine.

Splits the formerly-200-line main.py:lifespan() into 4 composed
@asynccontextmanager phases:

  init_data      — db, portfolio, positions, paper-engine balance sync
  init_ml        — TA aggregator, multi-timeframe, sqzmom, attribution
  init_strategy  — correlation manager, Kelly position sizer
  init_risk      — risk budget manager, smart router, execution scheduler

main.py composes them as:

  async with init_data(), init_ml(), init_strategy(), init_risk():
      yield

Auto-trader start/stop stays in main.py outside these phases — it's
gated on settings.auto_trading_enabled and the EMERGENCY_STOP file.

Mirrors the existing pattern in app/database/connection.py:156
(DatabaseManager.get_async_session).
"""

from .data import init_data
from .ml import auto_flip_ml_predictions, init_ml
from .risk import init_risk
from .strategy import init_strategy

__all__ = [
    "init_data",
    "init_ml",
    "init_risk",
    "init_strategy",
    "auto_flip_ml_predictions",
]
