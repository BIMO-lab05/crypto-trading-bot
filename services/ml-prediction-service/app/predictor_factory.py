"""
Predictor Factory - Creates GRU model instances.
LSTM was phased out late 2025 (GRU replaced it; avg R²=0.92).
"""

import logging
from typing import Dict, List

from app.ml_models.gru_model import GRUPricePredictor

logger = logging.getLogger(__name__)


class PredictorFactory:
    """Factory for creating GRU predictors."""

    @staticmethod
    def create_predictor(
        model_type: str,
        symbol: str,
        interval: str = "60",
    ) -> GRUPricePredictor:
        """Create a GRU predictor. LSTM raises ValueError (removed late 2025)."""
        model_type = model_type.upper()
        if model_type == "LSTM":
            raise ValueError("LSTM model type is no longer supported; use GRU")
        if model_type == "GRU":
            logger.info(f"Creating GRU predictor for {symbol} {interval}m")
            return GRUPricePredictor(symbol, interval)
        raise ValueError(f"Unsupported model type: {model_type}. Use 'GRU'")

    @staticmethod
    def get_supported_models() -> List[str]:
        """Get list of supported model types"""
        return ["GRU"]


class ModelComparator:
    """
    Backward-compatibility stub. LSTM-vs-GRU comparison is gone (LSTM removed
    late 2025). New code should call GRUPricePredictor directly. Existing
    callers see lstm_predictor=None and a working gru_predictor.
    """

    def __init__(self, symbol: str, interval: str = "60"):
        self.symbol = symbol
        self.interval = interval
        self.lstm_predictor = None
        self.gru_predictor = GRUPricePredictor(symbol, interval)

    async def compare_predictions(self, recent_data) -> Dict:
        """Returns GRU prediction in the legacy compare-shape (lstm slot is None)."""
        result = {
            "symbol": self.symbol,
            "interval": f"{self.interval}m",
            "lstm": None,
            "gru": None,
            "comparison": {},
        }
        if self.gru_predictor.model is None:
            return result
        try:
            gru_pred = await self.gru_predictor.predict(recent_data)
            result["gru"] = {
                "predictions": [
                    {
                        "timestamp": p.timestamp.isoformat(),
                        "price": p.predicted_price,
                        "confidence": p.confidence,
                    }
                    for p in gru_pred.predictions
                ],
                "direction": gru_pred.predicted_direction,
                "avg_confidence": gru_pred.average_confidence,
            }
        except Exception as e:
            logger.error(f"GRU prediction failed: {e}")
            result["gru"] = {"error": str(e)}
        return result

    def get_recommendation(self) -> str:
        if self.gru_predictor.model is None:
            return "NONE: GRU model not trained yet"
        return "GRU: only model type supported"
